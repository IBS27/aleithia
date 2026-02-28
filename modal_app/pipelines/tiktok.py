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
import subprocess
import tempfile
from datetime import datetime, timezone

import modal

from modal_app.common import Document, SourceType, detect_neighborhood
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


# ---------------------------------------------------------------------------
# Scraper function (runs on cloud browser via Kernel.sh)
# ---------------------------------------------------------------------------

async def _scrape_async(search_query: str, max_videos: int) -> list[dict]:
    """Scrape TikTok search results using Kernel cloud browser + Playwright."""
    from kernel import Kernel
    from playwright.async_api import async_playwright

    kernel_api_key = os.environ.get("KERNEL_API_KEY", "")
    if not kernel_api_key:
        logger.error("KERNEL_API_KEY not set — skipping TikTok scrape")
        return []

    k = Kernel(api_key=kernel_api_key)
    try:
        kernel_browser = k.browsers.create()
    except Exception as exc:
        logger.error("Failed to create Kernel browser session: %s", exc)
        return []

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(kernel_browser.cdp_ws_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            encoded_query = search_query.replace(" ", "+")
            url = f"https://www.tiktok.com/search?q={encoded_query}"
            logger.info("Navigating to %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3000)

            # Dismiss cookie banner
            for selector in [
                "button:has-text('Accept all')",
                "button:has-text('Accept')",
                "[data-testid='cookie-banner-accept']",
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except Exception:
                    continue

            # Dismiss login prompt
            for selector in [
                "[data-e2e='modal-close-inner-button']",
                "button[aria-label='Close']",
                ".close-button",
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except Exception:
                    continue

            # Wait for video cards
            card_selectors = [
                "[data-e2e='search_top-item']",
                "[data-e2e='search-card-desc']",
                "[data-e2e='search_video-item']",
                "[class*='DivItemContainerV2']",
                "[class*='VideoListContainer'] a",
            ]
            found_selector = None
            for sel in card_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5_000)
                    found_selector = sel
                    break
                except Exception:
                    continue

            if not found_selector:
                logger.error("No video cards found for query '%s'", search_query)
                return []

            # Scroll to load more
            for _ in range(3):
                await page.mouse.wheel(0, 1500)
                await page.wait_for_timeout(1500)

            # Extract video data
            videos_raw = await page.evaluate(
                """() => {
                const results = [];
                const links = document.querySelectorAll('a[href*="/video/"]');
                const seen = new Set();
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
                    const description = getText(card, [
                        '[data-e2e="search-card-desc"]',
                        '[class*="SpanText"]',
                        '[class*="desc"]',
                    ]) || link.textContent?.trim() || '';
                    const creator = getText(card, [
                        '[data-e2e="search-card-user-unique-id"]',
                        '[class*="SpanUniqueId"]',
                        '[class*="author"]',
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
            await browser.close()
            try:
                k.browsers.delete_by_id(kernel_browser.session_id)
            except Exception:
                pass


@app.function(
    image=tiktok_image,
    timeout=120,
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
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


@app.function(
    image=tiktok_image,
    timeout=600,
    volumes={VOLUME_MOUNT: volume},
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
def ingest_tiktok(
    queries: list[str] | None = None,
    max_videos: int = MAX_VIDEOS_PER_QUERY,
    transcribe: bool = True,
) -> dict:
    """Full TikTok ingestion pipeline.

    1. Scrape search results in parallel via .map()
    2. Optionally transcribe videos in parallel via .map()
    3. Convert to Documents and save to Volume

    Returns summary dict with counts.
    """
    if queries is None:
        queries = CHICAGO_SEARCH_QUERIES

    # --- Step 1: Parallel scrape ---
    scrape_args = [(q, max_videos) for q in queries]
    all_videos: list[dict] = []
    seen_urls: set[str] = set()

    for result in scrape_tiktok.starmap(scrape_args):
        for v in (result or []):
            url = v.get("video_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_videos.append(v)

    logger.info("Scraped %d unique videos from %d queries", len(all_videos), len(queries))

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

        if seen.contains(doc_id):
            skipped += 1
            continue

        content_parts = []
        if v.get("description"):
            content_parts.append(v["description"])
        if v.get("transcription"):
            content_parts.append(f"[Transcript] {v['transcription']}")
        if v.get("hashtags"):
            content_parts.append(f"[Hashtags] {' '.join(v['hashtags'])}")

        content = "\n".join(content_parts) if content_parts else v.get("description", "")
        neighborhood = detect_neighborhood(content)

        doc_data = {
            "id": doc_id,
            "source": SourceType.TIKTOK.value,
            "title": v.get("description", "TikTok video")[:200],
            "content": content,
            "url": v.get("video_url", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "creator": v.get("creator", ""),
                "views": v.get("views", ""),
                "hashtags": v.get("hashtags", []),
                "language": v.get("language", ""),
                "duration": v.get("duration", 0),
                "search_query": v.get("search_query", ""),
            },
            "geo": {"neighborhood": neighborhood} if neighborhood else {},
            "status": "raw",
        }

        doc = Document(**{k: v for k, v in doc_data.items() if k not in ("timestamp", "status")})
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

    return {
        "scraped": len(all_videos),
        "transcribed": transcribed_count,
        "saved": len(new_docs),
        "deduped": skipped,
    }


# ---------------------------------------------------------------------------
# Cron: run the full pipeline daily
# ---------------------------------------------------------------------------

@app.function(
    image=tiktok_image,
    timeout=900,
    volumes={VOLUME_MOUNT: volume},
    secrets=[modal.Secret.from_name("tiktok-scraper-secrets")],
)
def tiktok_on_demand(queries: list[str] | None = None):
    """On-demand TikTok ingestion — pass user-specific queries or use defaults."""
    result = ingest_tiktok.remote(queries=queries)
    logger.info("TikTok on-demand complete: %s", result)
    return result


# ---------------------------------------------------------------------------
# Local entrypoint for testing: modal run modal_app/pipelines/tiktok.py
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main():
    result = ingest_tiktok.remote(
        queries=["chicago small business", "chicago restaurant opening"],
        max_videos=3,
        transcribe=True,
    )
    print(json.dumps(result, indent=2))
