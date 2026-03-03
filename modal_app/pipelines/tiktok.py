"""TikTok trend scraping pipeline.

Scrapes TikTok search results via Kernel.sh cloud browser, transcribes video
audio with Whisper on GPU, and stores results as Documents in the common schema.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re as _re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import modal

from modal_app.common import SourceType, build_document, detect_neighborhood
from modal_app.costs import track_cost
from modal_app.dedup import SeenSet
from modal_app.volume import (
    VOLUME_MOUNT,
    RAW_DATA_PATH,
    app,
    tiktok_image,
    transcribe_image,
    volume,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chicago-relevant TikTok search queries
# ---------------------------------------------------------------------------

CHICAGO_SEARCH_QUERIES = [
    "chicago small business",
    "chicago restaurant opening",
    "chicago food trends",
    "chicago neighborhood guide",
    "chicago business tips",
    "logan square chicago",
    "wicker park chicago",
    "pilsen chicago",
    "chicago coffee shop",
    "chicago nightlife trends",
]

MAX_VIDEOS_PER_QUERY = int(os.environ.get("MAX_VIDEOS_PER_QUERY", "5"))
PROFILE_CITY_QUERY_LIMIT = 5
PROFILE_LOCAL_QUERY_LIMIT = 2
KERNEL_CREATE_MAX_ATTEMPTS = int(os.environ.get("TIKTOK_KERNEL_CREATE_MAX_ATTEMPTS", "3"))
CDP_CONNECT_MAX_ATTEMPTS = int(os.environ.get("TIKTOK_CDP_CONNECT_MAX_ATTEMPTS", "3"))
KERNEL_DELETE_MAX_ATTEMPTS = int(os.environ.get("TIKTOK_KERNEL_DELETE_MAX_ATTEMPTS", "3"))
TIKTOK_QUERY_CONCURRENCY = max(1, int(os.environ.get("TIKTOK_QUERY_CONCURRENCY", "1")))


def sanitize_query_term(value: str) -> str:
    """Normalize user-facing labels into stable TikTok query terms."""
    cleaned = _clean_text(value).lower()
    cleaned = _re.sub(r"[/_]+", " ", cleaned)
    cleaned = _re.sub(r"[^a-z0-9\s-]", " ", cleaned)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_profile_tiktok_queries(business_type: str, neighborhood: str) -> list[dict]:
    """Build 2-query profile plan with fixed per-query limits."""
    biz = sanitize_query_term(business_type) or "small business"
    nb = sanitize_query_term(neighborhood)
    city_query = f"{biz} chicago"
    local_query = f"{biz} {nb} chicago".strip() if nb else city_query

    return [
        {
            "query": city_query,
            "limit": PROFILE_CITY_QUERY_LIMIT,
            "scope": "city",
            "business_type": biz,
            "neighborhood": "",
        },
        {
            "query": local_query,
            "limit": PROFILE_LOCAL_QUERY_LIMIT,
            "scope": "local",
            "business_type": biz,
            "neighborhood": neighborhood,
        },
    ]


# ---------------------------------------------------------------------------
# Scraper function (runs on cloud browser via Kernel.sh)
# ---------------------------------------------------------------------------

async def _dismiss_tiktok_ui_blockers(page) -> None:
    """Best-effort dismissal of cookie/login overlays that block interaction."""
    selectors = [
        # Cookie banners
        "button:has-text('Accept all')",
        "button:has-text('Accept')",
        "[data-testid='cookie-banner-accept']",
        # Login and generic modal close buttons
        "[data-e2e='modal-close-inner-button']",
        "button[aria-label='Close']",
        "button[aria-label='close']",
        "div[role='button'][aria-label='Close']",
        "div[role='button'][aria-label='close']",
        ".close-button",
        "button:has-text('Not now')",
    ]
    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=1_000):
                await btn.click(timeout=1_500)
                await page.wait_for_timeout(250)
        except Exception:
            continue
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass


async def _apply_tiktok_cookie_header(context) -> bool:
    """Optionally load authenticated TikTok cookies from env for gated searches."""
    cookie_header = os.environ.get("TIKTOK_COOKIE_HEADER", "").strip()
    if not cookie_header:
        return False

    cookie_attr_names = {
        "path",
        "domain",
        "expires",
        "max-age",
        "secure",
        "httponly",
        "samesite",
        "priority",
    }

    cookies = []
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name.lower() in cookie_attr_names:
            continue
        if not name or not value:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": ".tiktok.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
            }
        )

    if not cookies:
        return False

    try:
        await context.add_cookies(cookies)
        logger.info("Loaded %d TikTok cookies from TIKTOK_COOKIE_HEADER", len(cookies))
        return True
    except Exception as exc:
        logger.warning("Failed to apply TIKTOK_COOKIE_HEADER: %s", exc)
        return False


async def _has_tiktok_login_gate(page) -> bool:
    """Detect common login-gate copy shown over anonymous search pages."""
    try:
        body_text = (await page.locator("body").inner_text(timeout=2_000)).lower()
    except Exception:
        return False
    markers = [
        "log in to search for popular content",
        "continue with google",
        "continue with apple",
        "use qr code",
    ]
    return any(marker in body_text for marker in markers)


async def _wait_for_video_links(page, timeout_ms: int = 12_000) -> bool:
    """Wait until actual TikTok video links exist on the page."""
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        try:
            if await page.locator("a[href*='/video/']").count() > 0:
                return True
        except Exception:
            pass
        try:
            await page.mouse.wheel(0, 1500)
        except Exception:
            pass
        await page.wait_for_timeout(900)
    return False


def _is_retryable_kernel_create_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "org_limit_exceeded",
        "rate_limit_exceeded",
        "timeout",
        "temporar",
        "429",
    )
    return any(m in text for m in markers)


def _is_retryable_cdp_connect_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "econnrefused",
        "etimedout",
        "timed out",
        "websocket error",
        "code=1006",
        "connection reset",
    )
    return any(m in text for m in markers)


def _is_retryable_kernel_delete_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "timeout",
        "temporar",
        "429",
        "connection reset",
        "econnrefused",
        "etimedout",
    )
    return any(m in text for m in markers)


def _kernel_session_id(kernel_browser: Any) -> str:
    """Extract the Kernel browser session identifier across SDK shapes."""
    for attr in ("session_id", "id"):
        value = getattr(kernel_browser, attr, "")
        if value:
            return str(value)
    return ""


async def _delete_kernel_session_with_retries(k: Any, session_id: str, search_query: str) -> None:
    """Best-effort Kernel session deletion with bounded retries."""
    for attempt in range(1, KERNEL_DELETE_MAX_ATTEMPTS + 1):
        try:
            k.browsers.delete_by_id(session_id)
            if attempt > 1:
                logger.info(
                    "Kernel session cleanup recovered for query '%s' (attempt %d/%d): %s",
                    search_query,
                    attempt,
                    KERNEL_DELETE_MAX_ATTEMPTS,
                    session_id,
                )
            return
        except Exception as exc:
            if attempt >= KERNEL_DELETE_MAX_ATTEMPTS or not _is_retryable_kernel_delete_error(exc):
                logger.warning(
                    "Failed to delete Kernel session for query '%s' after %d attempts (%s): %s",
                    search_query,
                    attempt,
                    session_id,
                    exc,
                )
                return
            delay_s = min(1.0 * attempt, 4.0)
            logger.warning(
                "Kernel session delete failed for query '%s' (attempt %d/%d, %s): %s; retrying in %.1fs",
                search_query,
                attempt,
                KERNEL_DELETE_MAX_ATTEMPTS,
                session_id,
                exc,
                delay_s,
            )
            await asyncio.sleep(delay_s)


async def _scrape_async(search_query: str, max_videos: int) -> list[dict]:
    """Scrape TikTok search results using Kernel cloud browser + Playwright."""
    from kernel import Kernel
    from playwright.async_api import async_playwright

    kernel_api_key = os.environ.get("KERNEL_API_KEY", "")
    if not kernel_api_key:
        logger.error("KERNEL_API_KEY not set — skipping TikTok scrape")
        return []

    k = Kernel(api_key=kernel_api_key)
    kernel_browser = None
    kernel_session_id = ""
    browser = None
    try:
        for attempt in range(1, KERNEL_CREATE_MAX_ATTEMPTS + 1):
            try:
                kernel_browser = k.browsers.create()
                kernel_session_id = _kernel_session_id(kernel_browser)
                break
            except Exception as exc:
                if attempt >= KERNEL_CREATE_MAX_ATTEMPTS or not _is_retryable_kernel_create_error(exc):
                    logger.error("Failed to create Kernel browser session: %s", exc)
                    return []
                delay_s = min(2.0 * attempt, 6.0)
                logger.warning(
                    "Kernel browser session create failed (attempt %d/%d): %s; retrying in %.1fs",
                    attempt,
                    KERNEL_CREATE_MAX_ATTEMPTS,
                    exc,
                    delay_s,
                )
                await asyncio.sleep(delay_s)

        if not kernel_browser:
            logger.error("Failed to create Kernel browser session: unknown error")
            return []

        async with async_playwright() as pw:
            for attempt in range(1, CDP_CONNECT_MAX_ATTEMPTS + 1):
                if kernel_browser is None:
                    try:
                        kernel_browser = k.browsers.create()
                        kernel_session_id = _kernel_session_id(kernel_browser)
                    except Exception as recreate_exc:
                        if attempt >= CDP_CONNECT_MAX_ATTEMPTS:
                            raise
                        delay_s = min(1.5 * attempt, 5.0)
                        logger.warning(
                            "Kernel session recreate failed for query '%s' (attempt %d/%d): %s; retrying in %.1fs",
                            search_query,
                            attempt,
                            CDP_CONNECT_MAX_ATTEMPTS,
                            recreate_exc,
                            delay_s,
                        )
                        await asyncio.sleep(delay_s)
                        continue
                try:
                    browser = await pw.chromium.connect_over_cdp(kernel_browser.cdp_ws_url)
                    break
                except Exception as exc:
                    if attempt >= CDP_CONNECT_MAX_ATTEMPTS or not _is_retryable_cdp_connect_error(exc):
                        raise
                    delay_s = min(1.5 * attempt, 5.0)
                    logger.warning(
                        "CDP connect failed for query '%s' (attempt %d/%d): %s; retrying in %.1fs",
                        search_query,
                        attempt,
                        CDP_CONNECT_MAX_ATTEMPTS,
                        exc,
                        delay_s,
                    )
                    if kernel_session_id:
                        await _delete_kernel_session_with_retries(k, kernel_session_id, search_query)
                        kernel_session_id = ""
                    kernel_browser = None
                    try:
                        kernel_browser = k.browsers.create()
                        kernel_session_id = _kernel_session_id(kernel_browser)
                    except Exception as recreate_exc:
                        logger.warning(
                            "Kernel session recreate failed for query '%s' during CDP retry: %s",
                            search_query,
                            recreate_exc,
                        )
                    await asyncio.sleep(delay_s)

            if browser is None:
                logger.error("Scrape failed for query '%s': browser unavailable after retries", search_query)
                return []

            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            cookies_loaded = await _apply_tiktok_cookie_header(context)
            page = context.pages[0] if context.pages else await context.new_page()

            encoded_query = quote_plus(search_query)
            candidate_urls = [
                f"https://www.tiktok.com/search/video?q={encoded_query}",
                f"https://www.tiktok.com/search?q={encoded_query}",
            ]

            links_ready = False
            login_gate_detected = False
            for url in candidate_urls:
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2_500)

                await _dismiss_tiktok_ui_blockers(page)
                await page.wait_for_timeout(500)
                await _dismiss_tiktok_ui_blockers(page)

                if await _has_tiktok_login_gate(page):
                    login_gate_detected = True
                    logger.warning("TikTok login gate detected for query '%s'", search_query)

                if await _wait_for_video_links(page, timeout_ms=9_000):
                    links_ready = True
                    break

            if not links_ready:
                if not cookies_loaded:
                    logger.warning(
                        "TikTok scrape for query '%s' running without TIKTOK_COOKIE_HEADER; "
                        "anonymous sessions are often login-gated.",
                        search_query,
                    )
                if login_gate_detected:
                    logger.error(
                        "Blocked by TikTok login gate for query '%s'; "
                        "use authenticated session cookies/profile.",
                        search_query,
                    )
                else:
                    logger.error("No video links found for query '%s'", search_query)
                return []

            # Extract video data
            videos_raw = await page.evaluate(
                """() => {
                const results = [];
                const links = document.querySelectorAll('a[href*="/video/"]');
                const seen = new Set();
                const isCountString = (s) => /^\\d[\\d.,]*\\s*[KkMmBb]?$/.test(s.trim());
                for (const link of links) {
                    const href = link.href;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    let card = link.closest('[data-e2e]') || link.parentElement?.parentElement;
                    const getText = (el, selectors) => {
                        if (!el) return '';
                        for (const sel of selectors) {
                            const found = el.querySelector(sel);
                            if (found) return found.textContent.trim();
                        }
                        return '';
                    };
                    let description = getText(card, [
                        '[data-e2e="search-card-desc"]',
                        '[class*="SpanText"]',
                        '[class*="desc"]',
                        '[class*="card-desc"]',
                        '[class*="VideoDesc"]',
                    ]);
                    if (isCountString(description)) description = '';
                    if (!description) {
                        const fallback = (link.textContent || '').trim();
                        if (fallback.length > 10 && !isCountString(fallback)) {
                            description = fallback;
                        }
                    }
                    const creator = getText(card, [
                        '[data-e2e="search-card-user-unique-id"]',
                        '[class*="SpanUniqueId"]',
                        '[class*="author"]',
                        '[class*="AuthorTitle"]',
                    ]);
                    const views = getText(card, [
                        '[class*="video-count"]',
                        '[class*="StrongVideoCount"]',
                        'strong',
                    ]);
                    const hashtags = [];
                    if (card) {
                        const hashEls = card.querySelectorAll('a[href*="/tag/"]');
                        for (const h of hashEls) hashtags.push(h.textContent.trim());
                    }
                    results.push({ description, video_url: href, creator, views, likes: '', hashtags });
                }
                return results;
            }"""
            )

            # Dedup and cap
            seen_urls: set[str] = set()
            videos: list[dict] = []
            for v in videos_raw:
                if not v.get("video_url") or v["video_url"] in seen_urls:
                    continue
                seen_urls.add(v["video_url"])
                videos.append(v)
                if len(videos) >= max_videos:
                    break

            return videos

    except Exception as exc:
        logger.error("Scrape failed for query '%s': %s", search_query, exc)
        return []
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if kernel_browser is not None:
            if not kernel_session_id:
                kernel_session_id = _kernel_session_id(kernel_browser)
            if kernel_session_id:
                await _delete_kernel_session_with_retries(k, kernel_session_id, search_query)
            else:
                logger.warning(
                    "Kernel browser session id missing during cleanup for query '%s'",
                    search_query,
                )


@app.function(
    image=tiktok_image,
    timeout=120,
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
@track_cost("scrape_tiktok", "CPU")
def scrape_tiktok(search_query: str, max_videos: int = MAX_VIDEOS_PER_QUERY) -> list[dict]:
    """Scrape TikTok search results for a given query via Kernel cloud browser."""
    return asyncio.run(_scrape_async(search_query, max_videos))


# ---------------------------------------------------------------------------
# Transcription function (GPU — Whisper on A10G)
# ---------------------------------------------------------------------------

@app.function(
    image=transcribe_image,
    gpu="A10G",
    timeout=300,
)
@track_cost("transcribe_video", "A10G")
def transcribe_video(video_url: str) -> dict:
    """Download video audio with yt-dlp and transcribe with Whisper."""
    import glob as globmod
    import whisper

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.wav")

        cmd = [
            "yt-dlp",
            "--no-check-certificates",
            "-x",
            "--audio-format", "wav",
            "-o", os.path.join(tmpdir, "audio.%(ext)s"),
            "--no-playlist",
            "--socket-timeout", "30",
            video_url,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {
                "transcription": "",
                "language": "",
                "duration": 0,
                "error": f"yt-dlp failed: {result.stderr[:500]}",
            }

        wav_files = globmod.glob(os.path.join(tmpdir, "*.wav"))
        if not wav_files:
            return {
                "transcription": "",
                "language": "",
                "duration": 0,
                "error": "No audio file produced by yt-dlp",
            }
        audio_path = wav_files[0]

        model = whisper.load_model("base")
        transcription = model.transcribe(audio_path)

        segments = transcription.get("segments", [{}])
        total_duration = segments[-1].get("end", 0) if segments else 0

        return {
            "transcription": transcription.get("text", "").strip(),
            "language": transcription.get("language", ""),
            "duration": round(total_duration, 1),
            "error": "",
        }


# ---------------------------------------------------------------------------
# Orchestrated pipeline: scrape → transcribe → store as Documents
# ---------------------------------------------------------------------------

def _make_doc_id(video_url: str) -> str:
    """Deterministic ID from video URL."""
    return f"tiktok-{hashlib.sha256(video_url.encode()).hexdigest()[:16]}"


_VIEW_COUNT_RE = _re.compile(r"^\s*\d[\d,.\s]*[KkMmBb]?\s*$")
_CREATOR_FROM_URL_RE = _re.compile(r"tiktok\.com/@([^/?#]+)/video/", _re.IGNORECASE)


def _is_count_only_text(value: str) -> bool:
    text = (value or "").strip()
    return bool(text) and bool(_VIEW_COUNT_RE.match(text))


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_view_count(value: str) -> int:
    """Parse TikTok view strings like '13.7K' into integers."""
    text = _clean_text(value).replace(",", "").upper()
    if not text:
        return 0
    match = _re.match(r"^(\d+(?:\.\d+)?)\s*([KMB])?$", text)
    if not match:
        return 0
    num = float(match.group(1))
    suffix = match.group(2) or ""
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    elif suffix == "B":
        num *= 1_000_000_000
    return int(round(num))


def _normalize_query_specs(
    query_specs: list[dict[str, Any]] | None,
    queries: list[str] | None,
    max_videos: int,
) -> list[dict[str, Any]]:
    """Normalize caller-provided query inputs to structured specs."""
    if query_specs:
        normalized: list[dict[str, Any]] = []
        for spec in query_specs:
            query = _clean_text(str(spec.get("query", "")))
            if not query:
                continue
            raw_limit = spec.get("limit", max_videos)
            try:
                limit = max(1, int(raw_limit))
            except (TypeError, ValueError):
                limit = max_videos
            normalized.append(
                {
                    "query": query,
                    "limit": limit,
                    "scope": _clean_text(str(spec.get("scope", ""))).lower() or "city",
                    "business_type": sanitize_query_term(str(spec.get("business_type", ""))),
                    "neighborhood": _clean_text(str(spec.get("neighborhood", ""))),
                }
            )
        if normalized:
            return normalized

    if not queries:
        queries = CHICAGO_SEARCH_QUERIES

    return [
        {
            "query": _clean_text(q),
            "limit": max_videos,
            "scope": "city",
            "business_type": "",
            "neighborhood": "",
        }
        for q in (queries or [])
        if _clean_text(q)
    ]


def _derive_business_fallback_terms(business_type: str) -> list[str]:
    """Return narrower fallback business terms for broad combined labels."""
    biz = sanitize_query_term(business_type)
    terms: list[str] = []
    if "salon" in biz and ("barber" in biz or "barbershop" in biz):
        terms.extend(["salon", "barbershop"])

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        norm = sanitize_query_term(term)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(norm)
    return deduped


def _build_fallback_query_specs(spec: dict[str, Any]) -> list[dict[str, str]]:
    """Build progressive fallback query variants when the primary query is empty."""
    primary_query = _clean_text(str(spec.get("query", "")))
    scope = _clean_text(str(spec.get("scope", "city"))).lower() or "city"
    biz = sanitize_query_term(str(spec.get("business_type", "")))
    neighborhood_raw = _clean_text(str(spec.get("neighborhood", "")))
    neighborhood_norm = sanitize_query_term(neighborhood_raw)

    fallbacks: list[dict[str, str]] = []
    seen_queries: set[str] = {primary_query.lower()}

    def add(query: str, query_scope: str, query_neighborhood: str) -> None:
        q = _clean_text(query)
        key = q.lower()
        if not q or key in seen_queries:
            return
        seen_queries.add(key)
        fallbacks.append(
            {
                "query": q,
                "scope": query_scope,
                "query_neighborhood": query_neighborhood,
            }
        )

    # First fallback for local queries: drop neighborhood and retry city-wide.
    if scope == "local" and biz:
        add(f"{biz} chicago", "city", "")

    # Domain-specific split fallback for broad combined business labels.
    for term in _derive_business_fallback_terms(biz):
        if scope == "local" and neighborhood_norm:
            add(f"{term} {neighborhood_norm} chicago", "local", neighborhood_raw)
        add(f"{term} chicago", "city", "")

    return fallbacks


def _extract_creator_from_url(video_url: str) -> str:
    """Extract TikTok creator handle from canonical video URL."""
    match = _CREATOR_FROM_URL_RE.search(video_url or "")
    if not match:
        return ""
    return _clean_text(match.group(1)).lstrip("@")


def _extract_transcript_title(transcription: str, max_len: int = 120) -> str:
    """Derive a short human-readable title from transcript text."""
    text = _clean_text(transcription)
    if not text:
        return ""
    text = _re.sub(r"\s+", " ", text)
    text = _re.sub(r"^\d[\d,.\s]*[KkMmBb]?\s*[:\-]?\s*", "", text)

    for sep in (". ", "! ", "? "):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break

    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0]
    return text.strip(" -:;,.")


def _build_tiktok_title(v: dict) -> str:
    """Build a meaningful title for a TikTok video document."""
    desc = _clean_text(v.get("description", ""))
    if _is_count_only_text(desc):
        desc = ""
    if desc:
        return desc[:200]

    transcript_title = _extract_transcript_title(v.get("transcription", ""))
    if transcript_title:
        return transcript_title[:200]

    parts = []
    creator = v.get("creator", "")
    if creator:
        parts.append(f"@{creator}")
    hashtags = v.get("hashtags", [])
    if hashtags:
        parts.append(" ".join(f"#{str(h).lstrip('#')}" for h in hashtags[:3]))
    if parts:
        return " ".join(parts)[:200]
    search_query = v.get("search_query", "")
    if search_query:
        return f"TikTok: {search_query}"
    return "TikTok video"


@app.function(
    image=tiktok_image,
    timeout=600,
    volumes={VOLUME_MOUNT: volume},
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
@track_cost("ingest_tiktok", "CPU")
def ingest_tiktok(
    queries: list[str] | None = None,
    query_specs: list[dict[str, Any]] | None = None,
    max_videos: int = MAX_VIDEOS_PER_QUERY,
    transcribe: bool = True,
) -> dict:
    """Full TikTok ingestion pipeline.

    1. Scrape search results in parallel via .map()
    2. Optionally transcribe videos in parallel via .map()
    3. Convert to Documents and save to Volume

    Returns summary dict with counts.
    """
    specs = _normalize_query_specs(query_specs=query_specs, queries=queries, max_videos=max_videos)
    if not specs:
        return {"scraped": 0, "transcribed": 0, "saved": 0, "deduped": 0, "videos": []}
    ingested_at = datetime.now(timezone.utc).isoformat()

    # --- Step 1: Parallel scrape ---
    scrape_args = [(spec["query"], spec["limit"]) for spec in specs]
    all_videos: list[dict] = []
    seen_urls: set[str] = set()

    for start in range(0, len(scrape_args), TIKTOK_QUERY_CONCURRENCY):
        end = start + TIKTOK_QUERY_CONCURRENCY
        batch_specs = specs[start:end]
        batch_args = scrape_args[start:end]
        for spec, result in zip(batch_specs, scrape_tiktok.starmap(batch_args)):
            used_query = spec["query"]
            used_scope = spec.get("scope", "city")
            used_neighborhood = spec.get("neighborhood", "")
            resolved = list(result or [])

            if not resolved:
                for fallback in _build_fallback_query_specs(spec):
                    fallback_query = fallback["query"]
                    fallback_scope = fallback["scope"]
                    fallback_neighborhood = fallback["query_neighborhood"]
                    try:
                        fallback_result = scrape_tiktok.remote(fallback_query, spec["limit"]) or []
                    except Exception as exc:
                        logger.warning(
                            "TikTok fallback query errored for '%s' using '%s': %s",
                            spec["query"],
                            fallback_query,
                            exc,
                        )
                        continue
                    if fallback_result:
                        resolved = list(fallback_result)
                        used_query = fallback_query
                        used_scope = fallback_scope
                        used_neighborhood = fallback_neighborhood
                        logger.info(
                            "TikTok fallback query succeeded for '%s' using '%s'",
                            spec["query"],
                            fallback_query,
                        )
                        break
                    logger.info(
                        "TikTok fallback query returned no videos for '%s' using '%s'",
                        spec["query"],
                        fallback_query,
                    )

            for v in resolved:
                url = v.get("video_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    v["search_query"] = used_query
                    v["query_scope"] = used_scope
                    v["query_business_type"] = spec.get("business_type", "")
                    v["query_neighborhood"] = used_neighborhood
                    all_videos.append(v)

    logger.info("Scraped %d unique videos from %d queries", len(all_videos), len(specs))

    if not all_videos:
        return {"scraped": 0, "transcribed": 0, "saved": 0}

    # --- Step 2: Parallel transcription ---
    transcribed_count = 0
    if transcribe:
        video_urls = [v["video_url"] for v in all_videos]
        for v, t_result in zip(all_videos, transcribe_video.map(video_urls)):
            t = t_result or {}
            v["transcription"] = t.get("transcription", "")
            v["language"] = t.get("language", "")
            v["duration"] = t.get("duration", 0)
            v["transcription_error"] = t.get("error", "")
            if v["transcription"]:
                transcribed_count += 1

    # --- Step 3: Dedup, convert to Documents, save, push to queue ---
    seen = SeenSet("tiktok")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_dir = f"{RAW_DATA_PATH}/tiktok/{today}"
    os.makedirs(save_dir, exist_ok=True)

    new_docs: list[dict] = []
    skipped = 0
    for v in all_videos:
        doc_id = _make_doc_id(v["video_url"])

        # TikTok metadata is volatile; refresh entries periodically to improve quality.
        if seen.contains(doc_id, max_age_hours=72):
            skipped += 1
            continue

        # Normalize known scraper artifacts: count-only strings captured as description.
        raw_desc = _clean_text(v.get("description", ""))
        raw_views = _clean_text(v.get("views", ""))
        if _is_count_only_text(raw_desc):
            if not raw_views:
                raw_views = raw_desc
            raw_desc = ""
        if _is_count_only_text(raw_views):
            # Canonicalize display string (e.g. "6,745" -> "6745")
            raw_views = raw_views.replace(",", "")

        creator = _clean_text(v.get("creator", ""))
        if not creator:
            creator = _extract_creator_from_url(v.get("video_url", ""))

        query_hint = _clean_text(v.get("search_query", ""))
        if not query_hint and specs:
            query_hint = specs[0]["query"]
        query_scope = _clean_text(v.get("query_scope", "")).lower() or "city"
        query_business_type = sanitize_query_term(v.get("query_business_type", ""))
        query_neighborhood = _clean_text(v.get("query_neighborhood", ""))

        v["description"] = raw_desc
        v["views"] = raw_views
        v["creator"] = creator
        v["search_query"] = query_hint
        v["query_scope"] = query_scope
        v["query_business_type"] = query_business_type
        v["query_neighborhood"] = query_neighborhood

        transcript_text = _clean_text(v.get("transcription", ""))
        transcript_text = _re.sub(r"^\d[\d,.\s]*[KkMmBb]?\s*[:\-]?\s*", "", transcript_text)
        v["transcription"] = transcript_text

        content_parts = []
        if raw_desc:
            content_parts.append(raw_desc)
        if transcript_text:
            content_parts.append(f"[Transcript] {transcript_text}")
        if v.get("hashtags"):
            content_parts.append(f"[Hashtags] {' '.join(v['hashtags'])}")

        content = "\n".join(content_parts).strip()
        if not content and query_hint:
            content = f"TikTok video related to: {query_hint}"
        neighborhood = detect_neighborhood(content)

        doc_data = {
            "id": doc_id,
            "source": SourceType.TIKTOK.value,
            "title": _build_tiktok_title(v),
            "content": content,
            "url": v.get("video_url", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "creator": v.get("creator", ""),
                "views": raw_views,
                "hashtags": v.get("hashtags", []),
                "language": v.get("language", ""),
                "duration": v.get("duration", 0),
                "search_query": query_hint,
                "query_scope": query_scope,
                "query_business_type": query_business_type,
                "query_neighborhood": query_neighborhood,
                "views_normalized": _parse_view_count(raw_views),
                "ingested_at": ingested_at,
            },
            "geo": {"neighborhood": neighborhood} if neighborhood else {},
            "status": "raw",
        }

        # Guardrail: skip empty/meaningless records.
        if _is_count_only_text(doc_data["title"]) and _is_count_only_text(doc_data["content"]):
            skipped += 1
            continue

        doc = build_document(doc_data)
        filepath = f"{save_dir}/{doc_id}.json"
        with open(filepath, "w") as f:
            f.write(doc.model_dump_json(indent=2))

        seen.add(doc_id)
        new_docs.append(doc_data)

    logger.info(
        "TikTok: %d scraped, %d new, %d deduped",
        len(all_videos), len(new_docs), skipped,
    )

    # Push new docs to classification queue
    from modal_app.classify import doc_queue
    for doc_data in new_docs:
        try:
            doc_queue.put(doc_data)
        except Exception:
            pass

    seen.save()
    volume.commit()
    logger.info("Saved %d TikTok documents to volume", len(new_docs))

    # Build content summaries for downstream consumers (agents, LLM synthesis)
    video_summaries = []
    for doc_data in new_docs[:10]:
        summary = {
            "title": doc_data.get("title", "")[:150],
            "creator": doc_data.get("metadata", {}).get("creator", ""),
            "hashtags": doc_data.get("metadata", {}).get("hashtags", []),
            "views": doc_data.get("metadata", {}).get("views", ""),
            "neighborhood": doc_data.get("geo", {}).get("neighborhood", ""),
        }
        content = doc_data.get("content", "")
        if content:
            summary["content_preview"] = content[:200]
        video_summaries.append(summary)

    return {
        "scraped": len(all_videos),
        "transcribed": transcribed_count,
        "saved": len(new_docs),
        "deduped": skipped,
        "videos": video_summaries,
    }


# ---------------------------------------------------------------------------
# Cron: run the full pipeline daily
# ---------------------------------------------------------------------------

@app.function(
    image=tiktok_image,
    timeout=600,
    volumes={VOLUME_MOUNT: volume},
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
@track_cost("ingest_tiktok_for_profile", "CPU")
def ingest_tiktok_for_profile(
    business_type: str,
    neighborhood: str,
    transcribe: bool = False,
) -> dict:
    """Profile-aware wrapper with fixed 2-query strategy."""
    query_specs = build_profile_tiktok_queries(business_type, neighborhood)
    result = ingest_tiktok.remote(query_specs=query_specs, transcribe=transcribe)
    logger.info(
        "TikTok profile ingest complete (%s / %s): %s",
        business_type,
        neighborhood,
        result,
    )
    return result


@app.function(
    image=tiktok_image,
    timeout=900,
    volumes={VOLUME_MOUNT: volume},
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
@track_cost("tiktok_on_demand", "CPU")
def tiktok_on_demand(
    queries: list[str] | None = None,
    business_type: str = "",
    neighborhood: str = "",
):
    """On-demand TikTok ingestion (custom queries or profile-aware defaults)."""
    if business_type or neighborhood:
        result = ingest_tiktok_for_profile.remote(
            business_type=business_type or "small business",
            neighborhood=neighborhood,
            transcribe=False,
        )
        logger.info("TikTok on-demand profile complete: %s", result)
        return result

    result = ingest_tiktok.remote(queries=queries)
    logger.info("TikTok on-demand complete: %s", result)
    return result


# ---------------------------------------------------------------------------
# Local entrypoint for testing: modal run modal_app/pipelines/tiktok.py
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main(query: str = "", max_videos: int = 5, no_transcribe: bool = False):
    """Run TikTok ingestion. Pass --query to search a specific term, or omit for defaults.

    Examples:
        modal run -m modal_app -- --query "chicago small business"
        modal run -m modal_app -- --query "wicker park restaurants" --max-videos 3
        modal run -m modal_app                # uses all default Chicago queries
    """
    queries = [query] if query else None
    result = ingest_tiktok.remote(
        queries=queries,
        max_videos=max_videos,
        transcribe=not no_transcribe,
    )
    print(json.dumps(result, indent=2))
