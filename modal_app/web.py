"""Modal-hosted FastAPI web API — replaces local backend.

Endpoints: /chat (streaming SSE), /brief, /alerts, /status, /metrics, /sources, /neighborhood
           /news, /politics, /inspections, /permits, /licenses, /summary
Modal features: @modal.asgi_app, streaming SSE
"""
import asyncio
import base64
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import modal
from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from modal_app.volume import app, volume, web_image, sandbox_image, VOLUME_MOUNT, RAW_DATA_PATH, PROCESSED_DATA_PATH
from modal_app.common import CHICAGO_NEIGHBORHOODS, COMMUNITY_AREA_MAP, NON_SENSOR_PIPELINE_SOURCES, detect_neighborhood, neighborhood_to_ca
from modal_app.pipelines.reddit import (
    FALLBACK_BUDGET_MS,
    merge_rank_reddit_docs,
    rank_reddit_docs,
    reddit_docs_are_weak,
    search_reddit_fallback_runtime,
)

web_app = FastAPI(title="Alethia API", version="2.0")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Profile refresh coordination for background TikTok fetches.
tiktok_refresh_recent_dict = modal.Dict.from_name("alethia-tiktok-refresh-recent", create_if_missing=True)
TIKTOK_TARGET_COUNT = 5
TIKTOK_LOCAL_RESERVE = 2
TIKTOK_TRIGGER_DEBOUNCE_SECONDS = 20
_tiktok_refresh_locks: dict[str, asyncio.Lock] = {}
_tiktok_refresh_locks_guard = asyncio.Lock()


def _load_docs(source: str, limit: int = 200) -> list[dict]:
    """Load documents from a source directory on the volume."""
    docs = []
    source_dir = Path(RAW_DATA_PATH) / source
    if not source_dir.exists():
        return docs
    for json_file in sorted(source_dir.rglob("*.json"), reverse=True)[:limit]:
        try:
            parsed = json.loads(json_file.read_text())
            if isinstance(parsed, dict):
                docs.append(parsed)
        except Exception as e:
            print(f"_load_docs [{source}]: corrupted JSON {json_file.name}: {e}")
            continue
    return docs


async def _spawn_reddit_fallback_persist(docs: list[dict]) -> None:
    """Fire-and-forget persistence for query-time fallback Reddit hits."""
    if not docs:
        return
    try:
        persist_fn = modal.Function.from_name("alethia", "persist_reddit_fallback_batch")
        await persist_fn.spawn.aio(docs=docs)
    except Exception as exc:
        print(f"Reddit fallback persist spawn failed: {exc}")


_COUNT_ONLY_RE = re.compile(r"^\s*\d[\d,.\s]*[KMBkmb]?\s*$")
_TIKTOK_CREATOR_RE = re.compile(r"tiktok\.com/@([^/?#]+)/video/", re.IGNORECASE)


def _is_count_only_text(value: str) -> bool:
    text = (value or "").strip()
    return bool(text) and bool(_COUNT_ONLY_RE.match(text))


def _extract_tiktok_creator_from_url(video_url: str) -> str:
    """Extract creator handle from TikTok video URL when scraper omits it."""
    match = _TIKTOK_CREATOR_RE.search(video_url or "")
    if not match:
        return ""
    return match.group(1).strip().lstrip("@")


def _extract_transcript_headline(content: str, max_len: int = 120) -> str:
    """Create a concise title from transcript-bearing content."""
    text = (content or "").strip()
    if not text:
        return ""
    if "[Transcript]" in text:
        text = text.split("[Transcript]", 1)[1].strip()
    text = re.sub(r"^\d[\d,.\s]*[KMBkmb]?\s*[:\-]?\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    for sep in (". ", "! ", "? "):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0]
    return text.strip(" -:;,.")


def _normalize_tiktok_content(content: str) -> str:
    """Remove count-only prefixes like '13.7K' from legacy TikTok content."""
    text = (content or "").strip()
    if not text:
        return ""
    if "\n[Transcript]" in text:
        first_line, remainder = text.split("\n", 1)
        if _is_count_only_text(first_line):
            text = remainder.strip()
    if _is_count_only_text(text):
        return ""
    return text


def _normalize_tiktok_doc(doc: dict) -> dict:
    """Normalize legacy TikTok records for stable API/front-end rendering."""
    normalized = dict(doc)
    metadata = dict(normalized.get("metadata") or {})
    normalized["metadata"] = metadata

    content = _normalize_tiktok_content(normalized.get("content", ""))
    normalized["content"] = content

    creator = str(metadata.get("creator", "") or "").strip().lstrip("@")
    if not creator:
        creator = _extract_tiktok_creator_from_url(normalized.get("url", ""))
    if creator:
        metadata["creator"] = creator

    search_query = str(metadata.get("search_query", "") or "").strip()
    if not search_query:
        query_match = re.search(r"TikTok video related to:\s*(.+)$", content, re.IGNORECASE)
        if query_match:
            search_query = query_match.group(1).strip()
    if search_query:
        metadata["search_query"] = search_query

    views_normalized = _parse_view_count(str(metadata.get("views_normalized", "") or ""))
    if views_normalized <= 0:
        views_normalized = _parse_view_count(str(metadata.get("views", "") or ""))
    metadata["views_normalized"] = views_normalized

    query_scope = str(metadata.get("query_scope", "") or "").strip().lower()
    if query_scope in ("city", "local"):
        metadata["query_scope"] = query_scope

    title = str(normalized.get("title", "") or "").strip()
    if not title or _is_count_only_text(title) or title.lower() == "tiktok video":
        transcript_title = _extract_transcript_headline(content)
        if transcript_title:
            title = transcript_title
        elif creator:
            title = f"@{creator}"
        elif search_query:
            title = f"TikTok: {search_query}"
        else:
            title = "TikTok video"
    normalized["title"] = title

    return normalized


def _sanitize_business_type(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[/_]+", " ", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_view_count(value: str) -> int:
    text = (value or "").strip().replace(",", "").upper()
    if not text:
        return 0
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMB])?$", text)
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


def _parse_timestamp_epoch(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return 0.0
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _is_local_tiktok_candidate(doc: dict, neighborhood: str) -> bool:
    nb_lower = (neighborhood or "").strip().lower()
    if not nb_lower:
        return False

    metadata = doc.get("metadata", {}) or {}
    query_scope = str(metadata.get("query_scope", "") or "").strip().lower()
    query_nb = str(metadata.get("query_neighborhood", "") or "").strip().lower()
    if query_scope == "local" and query_nb == nb_lower:
        return True

    geo_nb = str((doc.get("geo", {}) or {}).get("neighborhood", "") or "").strip().lower()
    if geo_nb == nb_lower:
        return True

    combined = f"{doc.get('title', '')} {doc.get('content', '')[:600]}".lower()
    return nb_lower in combined


def _score_tiktok_business_relevance(doc: dict, business_type: str) -> int:
    biz = _sanitize_business_type(business_type)
    if not biz:
        return 0

    keyword_sets = [biz]
    for key, values in BUSINESS_TYPE_KEYWORDS.items():
        if _sanitize_business_type(key) == biz:
            keyword_sets = values
            break
    combined = f"{doc.get('title', '')} {doc.get('content', '')[:700]}".lower()

    score = 0
    for kw in keyword_sets:
        kw_clean = _sanitize_business_type(kw)
        if kw_clean and kw_clean in combined:
            score += 3
    for generic in ("business", "startup", "opening", "owner", "restaurant", "shop", "store"):
        if generic in combined:
            score += 1
    return score


def _rank_tiktok_docs(docs: list[dict], business_type: str, neighborhood: str) -> list[dict]:
    """Rank TikTok docs with 2-local reserve + global highest-views fill."""
    if not docs:
        return []

    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for doc in docs:
        doc_id = str(doc.get("id", "") or "")
        if doc_id and doc_id in seen_ids:
            continue
        if doc_id:
            seen_ids.add(doc_id)
        deduped.append(doc)

    def sort_key(doc: dict) -> tuple[int, int, float]:
        meta = doc.get("metadata", {}) or {}
        views = int(meta.get("views_normalized", 0) or 0)
        if views <= 0:
            views = _parse_view_count(str(meta.get("views", "") or ""))
            meta["views_normalized"] = views
        relevance = _score_tiktok_business_relevance(doc, business_type)
        ts = _parse_timestamp_epoch(str(doc.get("timestamp", "") or ""))
        return (views, relevance, ts)

    local_docs: list[dict] = []
    non_local_docs: list[dict] = []
    for doc in deduped:
        if _is_local_tiktok_candidate(doc, neighborhood):
            local_docs.append(doc)
        else:
            non_local_docs.append(doc)

    local_docs.sort(key=sort_key, reverse=True)
    non_local_docs.sort(key=sort_key, reverse=True)

    selected: list[dict] = []
    selected_ids: set[str] = set()
    for doc in local_docs[:TIKTOK_LOCAL_RESERVE]:
        selected.append(doc)
        doc_id = str(doc.get("id", "") or "")
        if doc_id:
            selected_ids.add(doc_id)

    remainder = [d for d in (local_docs[TIKTOK_LOCAL_RESERVE:] + non_local_docs) if str(d.get("id", "") or "") not in selected_ids]
    remainder.sort(key=sort_key, reverse=True)

    for doc in remainder:
        if len(selected) >= TIKTOK_TARGET_COUNT:
            break
        selected.append(doc)

    return selected[:TIKTOK_TARGET_COUNT]


def _profile_tiktok_freshness(docs: list[dict], business_type: str, neighborhood: str) -> tuple[int, int, float]:
    """Return profile_count, local_count, freshest_epoch for profile-aware docs."""
    biz = _sanitize_business_type(business_type) or "small business"
    nb_lower = (neighborhood or "").strip().lower()
    profile_docs = []
    local_docs = []

    for doc in docs:
        metadata = doc.get("metadata", {}) or {}
        scope = str(metadata.get("query_scope", "") or "").strip().lower()
        q_biz = _sanitize_business_type(str(metadata.get("query_business_type", "") or ""))
        q_nb = str(metadata.get("query_neighborhood", "") or "").strip().lower()

        if scope not in ("city", "local"):
            continue
        if q_biz and q_biz != biz:
            continue

        if scope == "local" and q_nb == nb_lower:
            local_docs.append(doc)
            profile_docs.append(doc)
            continue
        if scope == "city":
            profile_docs.append(doc)

    freshest = 0.0
    if profile_docs:
        freshest = max(_parse_timestamp_epoch(str(d.get("timestamp", "") or "")) for d in profile_docs)
    return (len(profile_docs), len(local_docs), freshest)


def _filter_tiktok_pool_for_profile(docs: list[dict], business_type: str) -> list[dict]:
    """Keep docs aligned with the active business type, plus legacy docs with no profile metadata."""
    biz = _sanitize_business_type(business_type) or "small business"
    filtered: list[dict] = []
    for doc in docs:
        metadata = doc.get("metadata", {}) or {}
        q_biz = _sanitize_business_type(str(metadata.get("query_business_type", "") or ""))
        if not q_biz or q_biz == biz:
            filtered.append(doc)
    return filtered


def _refresh_key(business_type: str, neighborhood: str) -> str:
    biz = _sanitize_business_type(business_type) or "small business"
    nb = (neighborhood or "").strip().lower()
    return f"{biz}|{nb}"


async def _get_tiktok_refresh_lock(key: str) -> asyncio.Lock:
    """Return a per-profile in-process lock to avoid duplicate refresh spawns."""
    async with _tiktok_refresh_locks_guard:
        lock = _tiktok_refresh_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _tiktok_refresh_locks[key] = lock
        return lock


async def _dict_get_float_aio(d: modal.Dict, key: str, default: float = 0.0) -> float:
    """Async-safe float lookup for modal.Dict values."""
    try:
        getter_aio = getattr(d.__getitem__, "aio", None)
        if callable(getter_aio):
            value = await getter_aio(key)
        else:
            value = d[key]
    except KeyError:
        return default
    except Exception:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _dict_put_value_aio(d: modal.Dict, key: str, value: float) -> None:
    """Set modal.Dict key using async API when available, sync fallback otherwise."""
    put_aio = getattr(getattr(d, "put", None), "aio", None)
    if callable(put_aio):
        await put_aio(key, value)
    else:
        d[key] = value


def _is_low_quality_tiktok_doc(doc: dict) -> bool:
    title = (doc.get("title", "") or "").strip()
    content = (doc.get("content", "") or "").strip()
    meta = doc.get("metadata", {}) or {}
    creator = str(meta.get("creator", "") or "").strip()
    hashtags = meta.get("hashtags", []) or []
    transcript_present = "[Transcript]" in content
    meaningful_content = bool(content) and not _is_count_only_text(content)

    # Reject records that only contain numeric counters and no creator/tags/transcript.
    if _is_count_only_text(title) and not meaningful_content and not creator and not hashtags and not transcript_present:
        return True
    return False


def _filter_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents by neighborhood with multi-strategy matching."""
    if not neighborhood:
        return docs
    nb_lower = neighborhood.lower()

    nb_community_area = neighborhood_to_ca(neighborhood)

    matched = []
    for d in docs:
        geo = d.get("geo", {})
        # Match by geo.neighborhood field
        if geo.get("neighborhood", "").lower() == nb_lower:
            matched.append(d)
            continue
        # Match by community_area number
        if nb_community_area and geo.get("community_area") == nb_community_area:
            matched.append(d)
            continue
        # Match by content text (check title first, then content)
        title = d.get("title", "").lower()
        if nb_lower in title:
            matched.append(d)
            continue
        # Content match — only for multi-word neighborhoods to avoid false positives
        if len(nb_lower) > 4 and nb_lower in d.get("content", "").lower()[:500]:
            matched.append(d)
            continue
    return matched


# Business type → review category keywords (for filtering reviews/licenses by relevance)
BUSINESS_TYPE_KEYWORDS: dict[str, list[str]] = {
    "restaurant": ["restaurant", "food", "dining", "cuisine", "eatery", "diner"],
    "coffee shop": ["coffee", "cafe", "tea", "espresso", "bakery"],
    "bar / nightlife": ["bar", "nightlife", "tavern", "pub", "lounge", "cocktail", "brewery"],
    "retail store": ["retail", "shopping", "store", "boutique", "merchandise"],
    "grocery / convenience": ["grocery", "convenience", "market", "deli", "bodega"],
    "salon / barbershop": ["salon", "barbershop", "beauty", "hair", "spa", "nail"],
    "fitness studio": ["fitness", "gym", "yoga", "pilates", "crossfit", "health club"],
    "professional services": ["professional", "consulting", "legal", "accounting", "office"],
    "food truck": ["food truck", "food", "catering", "street food", "mobile"],
    "bakery": ["bakery", "pastry", "bread", "cake", "dessert", "sweets"],
}


def _filter_by_business_type(docs: list[dict], business_type: str) -> list[dict]:
    """Filter review/market documents by business type relevance."""
    if not business_type:
        return docs
    keywords = BUSINESS_TYPE_KEYWORDS.get(business_type.lower(), [business_type.lower()])
    matched = []
    for d in docs:
        cats = d.get("metadata", {}).get("categories", [])
        cat_text = " ".join(c.lower() if isinstance(c, str) else "" for c in cats)
        title = d.get("title", "").lower()
        content = d.get("content", "").lower()[:300]
        combined = f"{cat_text} {title} {content}"
        if any(kw in combined for kw in keywords):
            matched.append(d)
    return matched


# Patterns indicating ceremonial/low-value legislation
_CEREMONIAL_PATTERNS = [
    "congratulat", "honorar", "commemorate", "memorial", "tribute",
    "recognize", "recognition of", "appreciation", "in memory of",
    "retirement of", "sympathy", "condolence",
]

# Patterns indicating bulk administrative items (low business relevance)
_ADMINISTRATIVE_PATTERNS = [
    "handicapped parking",
    "disabled parking",
    "parking permit no",
    "vehicle sticker",
    "pet license",
    "animal license",
    "residential parking",
    "driveway permit",
]


def _filter_politics_relevance(docs: list[dict], business_type: str = "") -> list[dict]:
    """Filter politics docs: remove ceremonial + bulk administrative items,
    optionally boost business-relevant ones."""
    filtered = []
    for d in docs:
        title_lower = d.get("title", "").lower()
        if any(pat in title_lower for pat in _CEREMONIAL_PATTERNS):
            continue
        if any(pat in title_lower for pat in _ADMINISTRATIVE_PATTERNS):
            continue
        filtered.append(d)

    if not business_type or not filtered:
        return filtered

    keywords = BUSINESS_TYPE_KEYWORDS.get(business_type.lower(), [business_type.lower()])
    # Specific permit/license types instead of bare "permit" (which boosts parking permits)
    keywords += [
        "zoning", "ordinance", "inspection", "health", "safety",
        "business permit", "liquor permit", "food permit", "building permit",
        "liquor license", "food license", "special use",
    ]

    def relevance(d: dict) -> int:
        text = f"{d.get('title', '')} {d.get('content', '')[:500]}".lower()
        return sum(1 for kw in keywords if kw in text)

    filtered.sort(key=relevance, reverse=True)
    return filtered


# --- News relevance filtering ---

_NON_LOCAL_NEWS_PATTERNS = re.compile(
    r"(nba|nfl|mlb|nhl|sox\s+(spring|training)|cubs\s+spring|"
    r"bears\s+(draft|trade)|bulls\s+(trade|score)|blackhawks|"
    r"world\s+series|super\s+bowl|march\s+madness|"
    r"iran|ukraine|gaza|autoridades|"
    r"election\s+results|white\s+house)",
    re.IGNORECASE,
)


def _is_likely_english(text: str) -> bool:
    """Quick heuristic: check if text is predominantly ASCII/English."""
    if not text:
        return True
    ascii_count = sum(1 for c in text[:200] if ord(c) < 128)
    return (ascii_count / min(len(text), 200)) > 0.85


def _filter_news_relevance(
    docs: list[dict], business_type: str = "", neighborhood: str = "",
) -> list[dict]:
    """Score and filter news by Chicago/business relevance.

    Removes clearly irrelevant content (sports scores, foreign affairs,
    non-English articles) and ranks remainder by business-type relevance.
    """
    nb_names_lower = [n.lower() for n in CHICAGO_NEIGHBORHOODS]
    biz_keywords = (
        BUSINESS_TYPE_KEYWORDS.get(business_type.lower(), [business_type.lower()])
        if business_type else []
    )

    scored: list[tuple[dict, int]] = []
    for d in docs:
        title = d.get("title", "")
        content = d.get("content", "")[:500]
        combined = f"{title} {content}".lower()

        # Hard filters
        if not _is_likely_english(title):
            continue
        if _NON_LOCAL_NEWS_PATTERNS.search(combined):
            continue

        score = 0
        if "chicago" in combined:
            score += 3
        for nb in nb_names_lower:
            if len(nb) > 4 and nb in combined:
                score += 2
                break
        if neighborhood and neighborhood.lower() in combined:
            score += 3
        for kw in biz_keywords:
            if kw in combined:
                score += 2
                break
        for biz_word in ["business", "restaurant", "shop", "store", "zoning",
                         "license", "regulation", "opening", "closing"]:
            if biz_word in combined:
                score += 1
                break
        # Local feed bonus
        feed = d.get("metadata", {}).get("feed_name", "").lower()
        if "block club" in feed:
            score += 2
        elif "tribune" in feed or "sun-times" in feed:
            score += 1

        scored.append((d, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    result = [d for d, s in scored if s > 0]
    if not result and scored:
        result = [d for d, _ in scored[:5]]
    return result


def _load_demographics_summary() -> dict:
    """Load pre-aggregated demographics summary (one file instead of 1300+ individual reads)."""
    candidate_paths = [
        Path(PROCESSED_DATA_PATH) / "demographics_summary.json",
        Path(PROCESSED_DATA_PATH) / "summaries" / "demographics_summary.json",
    ]
    for summary_path in candidate_paths:
        if summary_path.exists():
            try:
                return json.loads(summary_path.read_text())
            except Exception as e:
                print(f"Failed to load demographics summary ({summary_path}): {e}")
    return {}


def _aggregate_demographics(neighborhood: str) -> dict:
    """Look up pre-aggregated census demographics for a neighborhood."""
    summary = _load_demographics_summary()
    if not summary:
        return {}

    nb_community_area = neighborhood_to_ca(neighborhood)
    if nb_community_area and nb_community_area in summary.get("by_community_area", {}):
        return summary["by_community_area"][nb_community_area]

    return {}


def _logistic(x: float, x0: float, k: float) -> float:
    """Logistic (sigmoid) normalization: f(x) = 1 / (1 + e^(-k(x - x₀)))."""
    import math
    return 1 / (1 + math.exp(-k * (x - x0)))


def _compute_risk_wlc(inspections: list, permits: list, licenses: list, news: list, politics: list, reviews: list | None = None) -> float:
    """Weighted Linear Combination risk score — same model as frontend Dashboard.tsx.

    Methodology (ISO 31000-aligned):
      Logistic normalization of each input to [0, 1] risk scale,
      then WLC aggregation: risk = Σ(wᵢ · rᵢ) / Σ(wᵢ) over available dimensions.

    Returns 0-10 risk score (higher = more risk).
    """
    W = {
        "regulatory": 0.25,
        "market": 0.20,
        "economic": 0.20,
        "accessibility": 0.15,
        "political": 0.10,
        "community": 0.10,
    }

    scored: list[tuple[str, float, float]] = []  # (dimension, risk, weight)

    # ── Regulatory Compliance (25%) — inspection fail rate
    total_inspections = len(inspections)
    if total_inspections > 0:
        failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))
        fail_rate = failed / total_inspections
        scored.append(("regulatory", _logistic(fail_rate, 0.22, 8), W["regulatory"]))

    # ── Market Competition (20%) — license density + review quality
    license_count = len(licenses)
    if license_count > 0:
        scored.append(("market", _logistic(license_count, 12, 0.25), W["market"] * 0.5))

    ratings = [r.get("metadata", {}).get("rating", 0) for r in (reviews or []) if r.get("metadata", {}).get("rating")]
    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        scored.append(("market", 1 - _logistic(avg_rating, 3.5, 3), W["market"] * 0.5))

    # ── Economic Vitality (20%) — permit activity (inverted: more permits = lower risk)
    permit_count = len(permits)
    if permit_count > 0:
        scored.append(("economic", 1 - _logistic(permit_count, 8, 0.3), W["economic"]))

    # ── Political Stability (10%) — legislative activity volume
    if politics:
        scored.append(("political", _logistic(len(politics), 5, 0.4), W["political"]))

    # ── Community Presence (10%) — news visibility (inverted: low visibility = higher risk)
    if news:
        scored.append(("community", 1 - _logistic(len(news), 8, 0.3), W["community"]))

    if not scored:
        return 5.0  # no data — neutral default

    weighted_risk = sum(r * w for _, r, w in scored)
    total_weight = sum(w for _, _, w in scored)
    normalized = weighted_risk / total_weight
    return round(normalized * 10, 1)


def _compute_metrics(name: str, inspections: list, permits: list, licenses: list, news: list, politics: list, reviews: list | None = None) -> dict:
    """Compute neighborhood metrics from actual data.

    Risk score uses the same WLC logistic model as frontend Dashboard.tsx.
    Returns zeros for missing data instead of seeded fakes.
    """
    total_inspections = len(inspections)
    failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))

    # Regulatory density: normalized inspection volume (0-100 scale)
    regulatory_density = min(100, total_inspections * 5) if total_inspections > 0 else 0

    # Business activity: normalized license count (0-100 scale)
    business_activity = min(100, len(licenses) * 8) if licenses else 0

    # Risk score: WLC logistic model (same formula as frontend)
    risk_score = _compute_risk_wlc(inspections, permits, licenses, news, politics, reviews)

    # Sentiment: placeholder based on news volume (more news = more activity = higher)
    sentiment = min(100, len(news) * 10) if news else 0

    # Review rating from actual review docs
    ratings = [r.get("metadata", {}).get("rating", 0) for r in (reviews or []) if r.get("metadata", {}).get("rating")]
    avg_review_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    return {
        "neighborhood": name,
        "regulatory_density": round(regulatory_density, 1),
        "business_activity": round(business_activity, 1),
        "sentiment": round(sentiment, 1),
        "risk_score": risk_score,
        "active_permits": len(permits),
        "crime_incidents_30d": 0,
        "avg_review_rating": avg_review_rating,
        "review_count": len(ratings),
    }


@web_app.post("/chat")
async def chat(request: Request):
    """Streaming chat endpoint — orchestrates agent swarm + streams LLM tokens via SSE."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    body = await request.json()
    question = body.get("message", "")

    if not question or not question.strip():
        return JSONResponse({"error": "message is required"}, status_code=400)
    if len(question) > 5000:
        return JSONResponse({"error": "message exceeds 5000 character limit"}, status_code=400)

    user_id = body.get("user_id", str(uuid.uuid4()))
    business_type = body.get("business_type", "Restaurant")
    neighborhood = body.get("neighborhood", "Loop")

    async def event_stream():
        # Send agent deployment status
        yield f"data: {json.dumps({'type': 'status', 'content': 'Deploying intelligence agents...'})}\n\n"

        span_ctx = tracer.start_as_current_span("chat-request") if tracer else None
        span = span_ctx.__enter__() if span_ctx else None

        # Initialize Supermemory client early for profile + memory retrieval
        api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
        sm = None
        profile_data = {}
        past_memories = []
        if api_key:
            try:
                from modal_app.supermemory import SupermemoryClient
                sm = SupermemoryClient(api_key)
                # Parallel fetch: profile (v4 API) + user memories (retrieval API)
                profile_task = sm.get_profile(user_id)
                memory_task = sm.search(question, container_tags=[f"user_{user_id}"], limit=5)
                profile_data, past_memories = await asyncio.gather(
                    profile_task, memory_task, return_exceptions=True
                )
                if isinstance(profile_data, Exception):
                    profile_data = {}
                if isinstance(past_memories, Exception):
                    past_memories = []
            except Exception:
                profile_data = {}
                past_memories = []

        # Emit memory SSE event
        static_facts = profile_data.get("static", []) if isinstance(profile_data, dict) else []
        dynamic_facts = profile_data.get("dynamic", []) if isinstance(profile_data, dict) else []
        has_profile = bool(static_facts or dynamic_facts)
        yield f"data: {json.dumps({'type': 'memory', 'has_profile': has_profile, 'profile_facts': (static_facts[:3] + dynamic_facts[:2]) if has_profile else [], 'past_interactions': len(past_memories)})}\n\n"

        try:
            if span:
                span.set_attribute("openinference.span.kind", "CHAIN")
                span.set_attribute("input.value", question)
                span.set_attribute("chat.business_type", business_type)
                span.set_attribute("chat.neighborhood", neighborhood)
                span.set_attribute("chat.has_profile", has_profile)
            # Phase 1: Agent gathering (returns synthesis_messages, NOT response text)
            from modal_app.instrumentation import inject_context

            orchestrate_query = modal.Function.from_name("alethia", "orchestrate_query")
            result = await orchestrate_query.remote.aio(
                user_id=user_id,
                question=question,
                business_type=business_type,
                target_neighborhood=neighborhood,
                trace_context=inject_context(),
            )

            # Build per-agent summaries for frontend
            agent_summaries = []
            agent_results = result.get("context", {}).get("agent_results", {})
            for key, agent_result in agent_results.items():
                if isinstance(agent_result, dict) and "error" not in agent_result:
                    summary = {
                        "name": key,
                        "data_points": agent_result.get("data_points", 0),
                    }
                    if "findings" in agent_result:
                        summary["sources"] = list(agent_result["findings"].keys())
                    if "regulations" in agent_result:
                        summary["regulation_count"] = len(agent_result["regulations"])
                    agent_summaries.append(summary)
                else:
                    agent_summaries.append({"name": key, "data_points": 0, "error": True})

            # Send agent stats with per-agent breakdown
            yield f"data: {json.dumps({'type': 'agents', 'agents_deployed': result.get('agents_deployed', 0), 'neighborhoods': result.get('neighborhoods_analyzed', []), 'data_points': result.get('total_data_points', 0), 'agent_summaries': agent_summaries})}\n\n"

            # Status bridge between agents and LLM streaming
            yield f"data: {json.dumps({'type': 'status', 'content': 'Synthesizing intelligence report...'})}\n\n"

            # Phase 2: Inject user memory context into synthesis messages
            messages = result["synthesis_messages"]
            if has_profile or past_memories:
                memory_context_parts = []
                if static_facts:
                    memory_context_parts.append(f"Known facts: {'; '.join(str(f) for f in static_facts[:5])}")
                if dynamic_facts:
                    memory_context_parts.append(f"Recent context: {'; '.join(str(f) for f in dynamic_facts[:3])}")
                if past_memories:
                    snippets = []
                    for mem in past_memories[:3]:
                        content = mem.get("content", "") if isinstance(mem, dict) else str(mem)
                        snippets.append(content[:200])
                    memory_context_parts.append(f"Past interactions: {'; '.join(snippets)}")
                memory_block = "\n\nUSER CONTEXT FROM MEMORY:\n" + "\n".join(memory_context_parts) + "\nUse this context to personalize your response."
                # Append to the last user message in synthesis
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i] = {**messages[i], "content": messages[i]["content"] + memory_block}
                        break

            # Real LLM streaming
            llm_cls = modal.Cls.from_name("alethia", "AlethiaLLM")
            llm = llm_cls()

            full_response = ""
            async for token in llm.generate_stream.remote_gen.aio(
                messages, max_tokens=2048, temperature=0.7
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            if span:
                span.set_attribute("output.value", full_response[:2000])
                span.set_attribute("chat.agents_deployed", result.get("agents_deployed", 0))
                span.set_attribute("chat.data_points", result.get("total_data_points", 0))

            # Generate follow-up suggestions via GPT-4o (non-blocking, skip on failure)
            try:
                from modal_app.openai_utils import openai_available, get_openai_client
                if openai_available():
                    oai_client = get_openai_client()
                    suggestion_resp = await oai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Generate 2-3 concise follow-up questions a small business owner would ask next. Return JSON: {\"questions\": [\"...\", \"...\"]}. Questions should be specific to the business type and neighborhood context provided. Keep each under 60 characters."},
                            {"role": "user", "content": f"User asked: {question}\nResponse summary: {full_response[:2000]}\nBusiness: {business_type}, Neighborhood: {neighborhood}"},
                        ],
                        max_tokens=200,
                        temperature=0.7,
                        response_format={"type": "json_object"},
                    )
                    suggestions = json.loads(suggestion_resp.choices[0].message.content or "{}").get("questions", [])[:3]
                    if suggestions:
                        yield f"data: {json.dumps({'type': 'suggestions', 'questions': suggestions})}\n\n"
            except Exception:
                pass  # Silently skip suggestions on failure

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Store conversation + seed profile in Supermemory (fire-and-forget)
            if sm:
                try:
                    await asyncio.gather(
                        sm.store_conversation(user_id, [
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": full_response},
                        ]),
                        sm.sync_user_profile(user_id, business_type, neighborhood),
                        return_exceptions=True,
                    )
                except Exception:
                    pass

        except Exception as e:
            if span:
                span.set_attribute("error", str(e))
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@web_app.get("/user/memories")
async def user_memories(user_id: str = ""):
    """Get user profile and memory state from Supermemory."""
    if not user_id:
        return JSONResponse({"error": "user_id is required"}, status_code=400)

    api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not api_key:
        return {"profile": {}, "memories": [], "memory_count": 0}

    try:
        from modal_app.supermemory import SupermemoryClient
        sm = SupermemoryClient(api_key)
        profile_data, memories = await asyncio.gather(
            sm.get_profile(user_id),
            sm.search("", container_tags=[f"user_{user_id}"], limit=20),
            return_exceptions=True,
        )
        if isinstance(profile_data, Exception):
            profile_data = {}
        if isinstance(memories, Exception):
            memories = []

        memory_items = [
            {"content": m.get("content", "")[:300], "type": m.get("metadata", {}).get("type", "unknown")}
            for m in memories
            if isinstance(m, dict)
        ]
        return {
            "profile": profile_data if isinstance(profile_data, dict) else {},
            "memories": memory_items,
            "memory_count": len(memory_items),
        }
    except Exception as e:
        return {"profile": {}, "memories": [], "memory_count": 0, "error": str(e)}


@web_app.get("/brief/{neighborhood}")
async def brief(neighborhood: str, business_type: str = "Restaurant"):
    """Get intelligence brief for a neighborhood."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    span_ctx = tracer.start_as_current_span("brief-request") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", f"{business_type} in {neighborhood}")
            span.set_attribute("brief.neighborhood", neighborhood)
            span.set_attribute("brief.business_type", business_type)

        from modal_app.instrumentation import inject_context
        neighborhood_intel_agent = modal.Function.from_name("alethia", "neighborhood_intel_agent")
        result = await neighborhood_intel_agent.remote.aio(
            neighborhood=neighborhood,
            business_type=business_type,
            trace_context=inject_context(),
        )

        if span:
            span.set_attribute("output.value", json.dumps({"data_points": result.get("data_points", 0)}))
        return result
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        return {"error": str(e), "neighborhood": neighborhood}
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


@web_app.get("/alerts")
async def alerts(business_type: str = "Restaurant"):
    """Get active alerts relevant to business type."""
    alert_list = []

    # Check enriched docs for high-severity items
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    if enriched_dir.exists():
        for json_file in sorted(enriched_dir.rglob("*.json"), reverse=True)[:50]:
            try:
                doc = json.loads(json_file.read_text())
                sentiment = doc.get("sentiment", {})
                if sentiment.get("label") == "negative" and sentiment.get("score", 0) > 0.8:
                    alert_list.append({
                        "type": "negative_sentiment",
                        "title": doc.get("title", ""),
                        "source": doc.get("source", ""),
                        "neighborhood": doc.get("geo", {}).get("neighborhood", ""),
                        "severity": "high",
                    })
            except Exception:
                continue

    return {"alerts": alert_list[:20], "count": len(alert_list)}


@web_app.get("/status")
async def status():
    """Pipeline monitor — shows function states, doc counts, GPU status."""
    pipeline_status = {}

    # Traffic/CCTV temporarily excluded — pipelines not yet fully implemented
    for source in NON_SENSOR_PIPELINE_SOURCES:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            json_files = list(source_dir.rglob("*.json"))
            # Find most recent file
            latest = None
            if json_files:
                latest = max(json_files, key=lambda f: f.stat().st_mtime)
            pipeline_status[source] = {
                "doc_count": len(json_files),
                "last_update": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat() if latest else None,
                "state": "idle",
            }
        else:
            pipeline_status[source] = {"doc_count": 0, "last_update": None, "state": "no_data"}

    # Check enriched data
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    enriched_count = len(list(enriched_dir.rglob("*.json"))) if enriched_dir.exists() else 0

    # Cost tracking
    costs = {}
    try:
        cost_dict = modal.Dict.from_name("alethia-costs", create_if_missing=True)
        async for key in cost_dict.keys.aio():
            costs[key] = await cost_dict.get.aio(key)
    except Exception:
        pass

    from modal_app.vectordb import check_vectordb_health
    vectordb_health = check_vectordb_health()

    return {
        "pipelines": pipeline_status,
        "enriched_docs": enriched_count,
        "gpu_status": {
            "h100_llm": "available",
            "t4_classifier": "available",
            "t4_sentiment": "available",
            "t4_cctv": "available",
        },
        "costs": costs,
        "total_docs": sum(p.get("doc_count", 0) for p in pipeline_status.values()),
        "vectordb": vectordb_health,
    }


@web_app.get("/metrics")
async def metrics():
    """Scale numbers for demo display."""
    total_docs = 0
    sources_active = 0
    neighborhoods_covered = set()

    # Traffic/CCTV temporarily excluded — pipelines not yet fully implemented
    for source in NON_SENSOR_PIPELINE_SOURCES:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            json_files = list(source_dir.rglob("*.json"))
            total_docs += len(json_files)
            if json_files:
                sources_active += 1
            for jf in json_files[:100]:
                try:
                    doc = json.loads(jf.read_text())
                    if not isinstance(doc, dict):
                        continue
                    nb = doc.get("geo", {}).get("neighborhood", "")
                    if nb:
                        neighborhoods_covered.add(nb)
                except Exception:
                    continue

    return {
        "total_documents": total_docs,
        "active_pipelines": sources_active,
        "neighborhoods_covered": len(neighborhoods_covered),
        "data_sources": len(NON_SENSOR_PIPELINE_SOURCES),
        "neighborhoods_total": 77,
    }


@web_app.get("/sources")
async def sources():
    """Available data sources with counts."""
    result = {}
    # Traffic/CCTV temporarily excluded — pipelines not yet fully implemented
    for source in NON_SENSOR_PIPELINE_SOURCES:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            count = len(list(source_dir.rglob("*.json")))
            result[source] = {"count": count, "active": count > 0}
        else:
            result[source] = {"count": 0, "active": False}
    return result


def _load_fake_cctv() -> dict:
    """Load pre-generated fake CCTV analytics from JSON file."""
    fake_path = Path(PROCESSED_DATA_PATH) / "cctv" / "fake_analytics.json"
    if fake_path.exists():
        try:
            return json.loads(fake_path.read_text())
        except Exception:
            pass
    return {}


async def _load_cctv_for_neighborhood(name: str) -> dict:
    """Load latest CCTV analysis for cameras near a neighborhood."""
    from modal_app.common import NEIGHBORHOOD_CENTROIDS
    import math

    await volume.reload.aio()

    analysis_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "analysis"
    if not analysis_dir.exists():
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    centroid = NEIGHBORHOOD_CENTROIDS.get(name)
    if not centroid:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    clat, clng = centroid
    cameras = []

    # Group by camera_id, keep latest per camera
    latest_by_cam: dict[str, dict] = {}
    for jf in sorted(analysis_dir.glob("*.json"), reverse=True)[:200]:
        try:
            data = json.loads(jf.read_text())
            cam_id = data.get("camera_id", "")
            if cam_id in latest_by_cam:
                continue
            latest_by_cam[cam_id] = data
        except Exception:
            continue

    # Filter by distance (< 10km from neighborhood centroid)
    for cam_id, data in latest_by_cam.items():
        # Get lat/lng from raw metadata
        meta_dir = Path(RAW_DATA_PATH) / "cctv"
        lat, lng = 0.0, 0.0
        for date_dir in sorted(meta_dir.iterdir(), reverse=True) if meta_dir.exists() else []:
            if not date_dir.is_dir() or date_dir.name == "frames":
                continue
            for mf in date_dir.glob(f"{cam_id}_*.json"):
                try:
                    meta = json.loads(mf.read_text())
                    lat = meta.get("lat", 0)
                    lng = meta.get("lng", 0)
                    break
                except Exception:
                    continue
            if lat:
                break

        if not lat:
            continue

        # Haversine approximation
        R = 6371
        dlat = math.radians(lat - clat)
        dlon = math.radians(lng - clng)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(clat)) * math.cos(math.radians(lat))
             * math.sin(dlon / 2) ** 2)
        dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        if dist < 10:
            cameras.append({
                "camera_id": cam_id,
                "lat": lat,
                "lng": lng,
                "distance_km": round(dist, 2),
                "pedestrians": data.get("pedestrians", 0),
                "vehicles": data.get("vehicles", 0),
                "bicycles": data.get("bicycles", 0),
                "density_level": data.get("density_level", "unknown"),
                "timestamp": data.get("timestamp", ""),
            })

    if not cameras:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    # Overlay fake detection counts onto real cameras (keeps real IDs/positions/frames)
    fake = _load_fake_cctv()
    fake_entry = fake.get(name, {}).get("cameras", {})
    if fake_entry:
        fake_cams = fake_entry.get("cameras", [])
        n_real = len(cameras)
        for i, cam in enumerate(cameras):
            # Round-robin assign fake counts from pre-generated cameras
            fc = fake_cams[i % len(fake_cams)] if fake_cams else {}
            cam["pedestrians"] = fc.get("pedestrians", cam["pedestrians"])
            cam["vehicles"] = fc.get("vehicles", cam["vehicles"])
            cam["bicycles"] = fc.get("bicycles", cam["bicycles"])
            cam["density_level"] = fc.get("density_level", cam["density_level"])

        avg_p = fake_entry.get("avg_pedestrians", 0)
        avg_v = fake_entry.get("avg_vehicles", 0)
        density = fake_entry.get("density", "unknown")
    else:
        avg_p = sum(c["pedestrians"] for c in cameras) / len(cameras)
        avg_v = sum(c["vehicles"] for c in cameras) / len(cameras)
        density = "high" if avg_p > 20 else "medium" if avg_p > 5 else "low"

    return {
        "cameras": cameras[:10],
        "avg_pedestrians": round(avg_p, 1),
        "avg_vehicles": round(avg_v, 1),
        "density": density,
    }


async def _maybe_spawn_tiktok_profile_refresh(
    neighborhood: str,
    business_type: str,
    profile_count: int,
    local_count: int,
    freshest_epoch: float,
) -> dict:
    """Trigger non-blocking profile TikTok refresh, debounced for duplicate UI bursts."""

    status = {
        "requested": False,
        "reason": "pending",
        "cooldown_seconds_remaining": 0,
        "profile_docs": profile_count,
        "local_docs": local_count,
    }

    key = _refresh_key(business_type, neighborhood)
    key_lock = await _get_tiktok_refresh_lock(key)
    async with key_lock:
        now_epoch = time.time()
        last_trigger_epoch = await _dict_get_float_aio(tiktok_refresh_recent_dict, key, default=0.0)
        elapsed = now_epoch - last_trigger_epoch
        if elapsed < TIKTOK_TRIGGER_DEBOUNCE_SECONDS:
            status["reason"] = "debounced"
            status["cooldown_seconds_remaining"] = int(TIKTOK_TRIGGER_DEBOUNCE_SECONDS - elapsed)
            return status

        await _dict_put_value_aio(tiktok_refresh_recent_dict, key, now_epoch)
        try:
            from modal_app.pipelines.tiktok import ingest_tiktok_for_profile

            spawn_aio = getattr(ingest_tiktok_for_profile.spawn, "aio", None)
            if callable(spawn_aio):
                await spawn_aio(
                    business_type=business_type or "small business",
                    neighborhood=neighborhood,
                    transcribe=False,
                )
            else:
                ingest_tiktok_for_profile.spawn(
                    business_type=business_type or "small business",
                    neighborhood=neighborhood,
                    transcribe=False,
                )
            status["requested"] = True
            status["reason"] = "requested"
        except Exception as exc:
            # Allow immediate retry if spawn submission failed.
            await _dict_put_value_aio(tiktok_refresh_recent_dict, key, 0.0)
            status["reason"] = f"spawn_error:{exc}"

    return status


# CTA station locations (dataset 8pix-ypme) — lat/lng per station name
_CTA_STATIONS_CACHE: list[dict] | None = None


def _load_cta_stations() -> list[dict]:
    """Load CTA L station locations from cache or Socrata."""
    global _CTA_STATIONS_CACHE
    if _CTA_STATIONS_CACHE is not None:
        return _CTA_STATIONS_CACHE

    cache_path = Path(PROCESSED_DATA_PATH) / "cache" / "cta_stations.json"
    if cache_path.exists():
        try:
            _CTA_STATIONS_CACHE = json.loads(cache_path.read_text())
            return _CTA_STATIONS_CACHE
        except Exception:
            pass

    # Fetch from Socrata
    try:
        import urllib.request
        url = "https://data.cityofchicago.org/resource/8pix-ypme.json?$limit=500"
        with urllib.request.urlopen(url, timeout=10) as resp:
            stations = json.loads(resp.read().decode())
        parsed = []
        for s in stations:
            try:
                parsed.append({
                    "station_name": s.get("station_name", ""),
                    "lat": float(s.get("location", {}).get("latitude", 0) or s.get("latitude", 0)),
                    "lng": float(s.get("location", {}).get("longitude", 0) or s.get("longitude", 0)),
                })
            except (ValueError, TypeError):
                continue
        # Deduplicate by station name
        seen = set()
        deduped = []
        for p in parsed:
            if p["station_name"] not in seen and p["lat"] != 0:
                seen.add(p["station_name"])
                deduped.append(p)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(deduped, indent=2))
        volume.commit()
        _CTA_STATIONS_CACHE = deduped
        return deduped
    except Exception as e:
        print(f"_load_cta_stations: fetch failed: {e}")
        return []


def _compute_transit_score(neighborhood_name: str) -> dict:
    """Compute transit proximity score from CTA L-station ridership data."""
    import math
    from modal_app.common import NEIGHBORHOOD_CENTROIDS

    centroid = NEIGHBORHOOD_CENTROIDS.get(neighborhood_name)
    if not centroid:
        return {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []}

    clat, clng = centroid
    stations = _load_cta_stations()

    # Find stations within 3km of neighborhood centroid
    nearby: list[dict] = []
    for s in stations:
        dlat = math.radians(s["lat"] - clat)
        dlng = math.radians(s["lng"] - clng)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(clat)) * math.cos(math.radians(s["lat"])) * math.sin(dlng / 2) ** 2
        dist_km = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        if dist_km <= 3.0:
            nearby.append({**s, "distance_km": dist_km})

    if not nearby:
        return {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []}

    nearby_names = {s["station_name"] for s in nearby}

    # Load CTA ridership docs to get avg weekday rides
    ridership_docs = _load_docs("public_data", limit=500)
    total_rides = 0
    matched_stations = 0
    for doc in ridership_docs:
        meta = doc.get("metadata", {})
        if meta.get("dataset") != "cta_ridership_L":
            continue
        raw = meta.get("raw_record", {})
        station = raw.get("stationame", raw.get("station_name", ""))
        if station in nearby_names:
            try:
                rides = float(raw.get("avg_weekday_rides", 0))
                total_rides += rides
                matched_stations += 1
            except (ValueError, TypeError):
                continue

    # Normalize to 0-100 score (10K+ daily riders = 100)
    transit_score = min(100, round((total_rides / 10000) * 100)) if total_rides > 0 else 0
    # Fallback: if we have nearby stations but no ridership data yet, score from station count
    if transit_score == 0 and len(nearby) > 0:
        transit_score = min(100, len(nearby) * 20)

    return {
        "stations_nearby": len(nearby),
        "total_daily_riders": round(total_rides),
        "transit_score": transit_score,
        "station_names": sorted(nearby_names),
    }


@web_app.get("/neighborhood/{name}")
async def neighborhood(name: str, business_type: str = ""):
    """Full neighborhood data profile."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    span_ctx = tracer.start_as_current_span("neighborhood-profile") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", name)
            span.set_attribute("neighborhood.name", name)

        # Also check COMMUNITY_AREA_MAP values for broader coverage
        valid_names = set(n.lower() for n in CHICAGO_NEIGHBORHOODS) | set(n.lower() for n in COMMUNITY_AREA_MAP.values())
        if name.lower() not in valid_names:
            if span:
                span.set_attribute("error", f"Unknown neighborhood: {name}")
            return JSONResponse({"error": f"Unknown neighborhood: {name}"}, status_code=404)

        inspections = []
        permits = []
        licenses = []
        news_docs = []
        politics_docs = []

        # Load and filter public data
        public_docs = _load_docs("public_data", limit=500)
        nb_docs = _filter_by_neighborhood(public_docs, name)

        for doc in nb_docs:
            dataset = doc.get("metadata", {}).get("dataset", "")
            if dataset == "food_inspections":
                inspections.append(doc)
            elif dataset == "building_permits":
                permits.append(doc)
            elif dataset == "business_licenses":
                licenses.append(doc)

        # Load news and politics with improved matching
        all_news = _load_docs("news")
        all_politics = _load_docs("politics")

        news_docs = _filter_by_neighborhood(all_news, name)
        if news_docs:
            news_docs = _filter_news_relevance(news_docs, business_type, name)
        politics_docs = _filter_politics_relevance(
            _filter_by_neighborhood(all_politics, name),
            business_type,
        )

        # Load additional data sources
        all_reddit = _load_docs("reddit")
        all_reviews = _load_docs("reviews")
        all_realestate = _load_docs("realestate")
        all_tiktok = [_normalize_tiktok_doc(d) for d in _load_docs("tiktok")]
        all_tiktok = [d for d in all_tiktok if not _is_low_quality_tiktok_doc(d)]
        all_tiktok_profile = _filter_tiktok_pool_for_profile(all_tiktok, business_type)
        all_federal = _load_docs("federal_register")

        reddit_docs = rank_reddit_docs(
            _filter_by_neighborhood(all_reddit, name),
            business_type=business_type or "small business",
            neighborhood=name,
            min_score=0,
        )
        reviews_docs = _filter_by_neighborhood(all_reviews, name)
        realestate_docs = _filter_by_neighborhood(all_realestate, name)
        tiktok_docs = _rank_tiktok_docs(all_tiktok_profile, business_type, name)
        federal_docs = _filter_politics_relevance(_filter_by_neighborhood(all_federal, name), business_type)
        profile_count, local_count, freshest_epoch = _profile_tiktok_freshness(all_tiktok_profile, business_type, name)
        try:
            tiktok_refresh = await _maybe_spawn_tiktok_profile_refresh(
                neighborhood=name,
                business_type=business_type or "small business",
                profile_count=profile_count,
                local_count=local_count,
                freshest_epoch=freshest_epoch,
            )
        except Exception as exc:
            # Neighborhood response should still succeed even if background refresh scheduling fails.
            print(f"tiktok_refresh_error: {exc}")
            tiktok_refresh = {
                "requested": False,
                "reason": f"refresh_error:{exc}",
                "cooldown_seconds_remaining": 0,
                "profile_docs": profile_count,
                "local_docs": local_count,
            }
        # Traffic/CCTV temporarily disabled — pipelines not yet fully implemented
        traffic_docs: list[dict] = []

        # Further filter reviews by business type
        if business_type and reviews_docs:
            typed_reviews = _filter_by_business_type(reviews_docs, business_type)
            if typed_reviews:
                reviews_docs = typed_reviews

        # Query-time fallback: if neighborhood-local reddit signals are weak, run bounded search.
        if reddit_docs_are_weak(
            reddit_docs,
            business_type=business_type or "small business",
            neighborhood=name,
            min_count=3,
            median_threshold=2.0,
        ):
            start_ms = int(time.time() * 1000)
            fallback_docs = await search_reddit_fallback_runtime(
                business_type=business_type or "small business",
                neighborhood=name,
                budget_ms=FALLBACK_BUDGET_MS,
            )
            latency_ms = int(time.time() * 1000) - start_ms
            print(
                "reddit_fallback_triggered",
                {
                    "neighborhood": name,
                    "business_type": business_type or "small business",
                    "fallback_latency_ms": latency_ms,
                    "fallback_docs_found": len(fallback_docs),
                    "adapter_used": (fallback_docs[0].get("metadata", {}) or {}).get("retrieval_method", "") if fallback_docs else "",
                },
            )
            if fallback_docs:
                await _spawn_reddit_fallback_persist(fallback_docs)
                reddit_docs = merge_rank_reddit_docs(
                    reddit_docs,
                    fallback_docs,
                    business_type=business_type or "small business",
                    neighborhood=name,
                    min_score=0,
                )

        # Final fallback: use relevance-ranked global local-cache docs if still empty.
        if not reddit_docs and all_reddit:
            reddit_docs = rank_reddit_docs(
                all_reddit,
                business_type=business_type or "small business",
                neighborhood=name,
                min_score=0,
            )[:10]

        if not reviews_docs and all_reviews:
            if business_type:
                typed = _filter_by_business_type(all_reviews, business_type)
                reviews_docs = typed[:10] if typed else all_reviews[:5]
            else:
                reviews_docs = all_reviews[:5]

        if not realestate_docs and all_realestate:
            realestate_docs = all_realestate[:5]

        if not federal_docs and all_federal:
            federal_docs = _filter_politics_relevance(all_federal, business_type)[:10]

        # News/politics fallbacks with relevance filtering
        if not news_docs and all_news:
            news_docs = _filter_news_relevance(all_news, business_type, name)[:10]
        if not politics_docs and all_politics:
            politics_docs = _filter_politics_relevance(all_politics, business_type)[:10]

        # Compute inspection stats
        failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))
        passed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") == "Pass")

        # Compute metrics from actual data
        computed_metrics = _compute_metrics(name, inspections, permits, licenses, news_docs, politics_docs, reviews_docs)

        # Load demographics
        demographics = _aggregate_demographics(name)

        # Load CCTV analysis + peak hour from timeseries
        cctv_analysis = await _load_cctv_for_neighborhood(name)
        if cctv_analysis.get("cameras"):
            cam_ids = [c["camera_id"] for c in cctv_analysis["cameras"]]
            ts = await _aggregate_timeseries_for_neighborhood(name, camera_ids=cam_ids)
            if ts.get("hours"):
                cctv_analysis["peak_hour"] = ts["peak_hour"]
                cctv_analysis["peak_pedestrians"] = ts["peak_pedestrians"]

        # CTA transit proximity score
        transit_data = _compute_transit_score(name)

        # Parking analysis
        parking_data = _load_parking_for_neighborhood(name)

        if span:
            span.set_attribute("output.value", json.dumps({
                "inspections": len(inspections), "permits": len(permits),
                "licenses": len(licenses), "news": len(news_docs),
            }))
            span.set_attribute("neighborhood.inspections", len(inspections))
            span.set_attribute("neighborhood.permits", len(permits))
            span.set_attribute("neighborhood.licenses", len(licenses))

        return {
            "neighborhood": name,
            "metrics": computed_metrics,
            "demographics": demographics,
            "inspections": inspections[:50],
            "permits": permits[:50],
            "licenses": licenses[:50],
            "news": news_docs[:20],
            "politics": politics_docs[:20],
            "federal_register": federal_docs[:20],
            "reddit": reddit_docs[:20],
            "reviews": reviews_docs[:20],
            "realestate": realestate_docs[:10],
            "tiktok": tiktok_docs[:TIKTOK_TARGET_COUNT],
            "tiktok_refresh": tiktok_refresh,
            "traffic": traffic_docs[:10],
            "cctv": cctv_analysis,
            "transit": transit_data,
            "parking": parking_data,
            "inspection_stats": {
                "total": len(inspections),
                "failed": failed,
                "passed": passed,
            },
            "permit_count": len(permits),
            "license_count": len(licenses),
        }
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


# ── User settings ─────────────────────────────────────────────────────────────

SETTINGS_PATH = Path(PROCESSED_DATA_PATH) / "user_settings.json"


class _UserSettingsPayload(BaseModel):
    location_type: str = Field(..., min_length=1)
    neighborhood: str = Field(..., min_length=1)


def _read_settings_store() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def _write_settings_store(store: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(store, indent=2))
    volume.commit()


@web_app.get("/trends/{neighborhood}")
async def get_trends(neighborhood: str):
    """24-hour trend analysis: compare last 6h vs prior 6h."""
    import hashlib

    volume.reload()

    # Try to load baseline data
    baseline_path = Path(PROCESSED_DATA_PATH) / "trends" / "baselines" / f"{neighborhood}.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
    else:
        # Generate synthetic baseline from neighborhood name hash
        seed = int(hashlib.md5(neighborhood.encode()).hexdigest()[:8], 16)
        rng_base = (seed % 10) + 5
        baseline = {
            "hours": [
                {
                    "hour": h,
                    "pedestrians": round(rng_base * (0.3 + 0.7 * abs(12 - abs(h - 14)) / 12), 1),
                    "vehicles": round(rng_base * 1.8 * (0.2 + 0.8 * abs(12 - abs(h - 13)) / 12), 1),
                    "congestion": round(0.1 + 0.5 * abs(12 - abs(h - 14)) / 12, 2),
                }
                for h in range(24)
            ]
        }

    hours = baseline["hours"]

    # Compute trend: compare last 6h (18-23) vs prior 6h (12-17)
    recent = hours[18:24]
    prior = hours[12:18]

    def avg_field(entries, field):
        vals = [e[field] for e in entries]
        return sum(vals) / len(vals) if vals else 0

    recent_peds = avg_field(recent, "pedestrians")
    prior_peds = avg_field(prior, "pedestrians")
    ped_change = round(((recent_peds - prior_peds) / max(prior_peds, 0.1)) * 100)

    recent_cong = avg_field(recent, "congestion")
    prior_cong = avg_field(prior, "congestion")
    cong_change = round(((recent_cong - prior_cong) / max(prior_cong, 0.01)) * 100)

    # News activity: count recent news docs for this neighborhood
    news_dir = Path(RAW_DATA_PATH) / "news"
    news_count = 0
    if news_dir.exists():
        for f in list(news_dir.rglob("*.json"))[:200]:
            try:
                doc = json.loads(f.read_text())
                geo = doc.get("geo", {})
                if geo.get("neighborhood", "").lower() == neighborhood.lower():
                    news_count += 1
            except Exception:
                continue
    news_trend = "up" if news_count > 5 else ("stable" if news_count > 2 else "down")

    # Load traffic anomalies from existing data
    anomalies = []
    traffic_dir = Path(RAW_DATA_PATH) / "traffic"
    if traffic_dir.exists():
        for date_dir in sorted(traffic_dir.iterdir(), reverse=True)[:1]:
            if not date_dir.is_dir():
                continue
            for f in date_dir.glob("*.json"):
                try:
                    doc = json.loads(f.read_text())
                    meta = doc.get("metadata", {})
                    if meta.get("is_anomaly") and doc.get("geo", {}).get("neighborhood", "").lower() == neighborhood.lower():
                        anomalies.append({
                            "type": meta.get("severity", "info"),
                            "description": meta.get("congestion_level", "anomaly detected"),
                            "road": doc.get("title", "Unknown road"),
                        })
                except Exception:
                    continue

    def trend_dir(change_pct):
        if change_pct > 5:
            return "up"
        elif change_pct < -5:
            return "down"
        return "stable"

    return {
        "foot_traffic": {
            "trend": trend_dir(ped_change),
            "change_pct": ped_change,
            "current_avg": round(recent_peds, 1),
            "prior_avg": round(prior_peds, 1),
        },
        "congestion": {
            "trend": trend_dir(cong_change),
            "change_pct": cong_change,
            "anomalies": anomalies[:5],
        },
        "news_activity": {
            "trend": news_trend,
            "change_pct": (news_count - 3) * 10,
        },
        "hours": hours,
    }


@web_app.get("/user/settings")
async def get_user_settings(x_user_id: str = Header(default="")):
    if not x_user_id:
        return JSONResponse({"error": "Missing x-user-id header"}, status_code=401)
    store = _read_settings_store()
    entry = store.get(x_user_id)
    if not entry:
        return JSONResponse({"error": "No settings found"}, status_code=404)
    return {"user_id": x_user_id, "location_type": entry.get("location_type", ""), "neighborhood": entry.get("neighborhood", "")}


@web_app.put("/user/settings")
async def put_user_settings(payload: _UserSettingsPayload, x_user_id: str = Header(default="")):
    if not x_user_id:
        return JSONResponse({"error": "Missing x-user-id header"}, status_code=401)
    store = _read_settings_store()
    store[x_user_id] = {"location_type": payload.location_type, "neighborhood": payload.neighborhood}
    _write_settings_store(store)
    return {"user_id": x_user_id, "location_type": payload.location_type, "neighborhood": payload.neighborhood}


# ── Standalone data endpoints (used by api.ts) ──────────────────────────────

@web_app.get("/news")
async def news_list():
    """All recent news articles."""
    docs = _load_docs("news", limit=50)
    return docs


@web_app.get("/politics")
async def politics_list():
    """All recent politics/council items."""
    docs = _load_docs("politics", limit=50)
    return docs


@web_app.get("/inspections")
async def inspections_list(neighborhood: str = "", result: str = ""):
    """Food inspection records, optionally filtered."""
    public_docs = _load_docs("public_data", limit=500)
    inspections = [d for d in public_docs if d.get("metadata", {}).get("dataset") == "food_inspections"]
    if neighborhood:
        inspections = _filter_by_neighborhood(inspections, neighborhood)
    if result:
        inspections = [i for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results", "").lower() == result.lower()]
    return inspections[:100]


@web_app.get("/permits")
async def permits_list(neighborhood: str = ""):
    """Building permit records, optionally filtered."""
    public_docs = _load_docs("public_data", limit=500)
    permits = [d for d in public_docs if d.get("metadata", {}).get("dataset") == "building_permits"]
    if neighborhood:
        permits = _filter_by_neighborhood(permits, neighborhood)
    return permits[:100]


@web_app.get("/licenses")
async def licenses_list(neighborhood: str = ""):
    """Business license records, optionally filtered."""
    public_docs = _load_docs("public_data", limit=500)
    licenses = [d for d in public_docs if d.get("metadata", {}).get("dataset") == "business_licenses"]
    if neighborhood:
        licenses = _filter_by_neighborhood(licenses, neighborhood)
    return licenses[:100]


@web_app.get("/reddit")
async def reddit_list(neighborhood: str = ""):
    """Reddit posts, optionally filtered by neighborhood."""
    docs = _load_docs("reddit", limit=100)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


@web_app.get("/reviews")
async def reviews_list(neighborhood: str = ""):
    """Business reviews (Yelp + Google Places), optionally filtered."""
    docs = _load_docs("reviews", limit=100)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


@web_app.get("/realestate")
async def realestate_list(neighborhood: str = ""):
    """Commercial real estate listings, optionally filtered."""
    docs = _load_docs("realestate", limit=50)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:50]


@web_app.get("/tiktok")
async def tiktok_list(neighborhood: str = ""):
    """TikTok videos with transcriptions, optionally filtered."""
    docs = [_normalize_tiktok_doc(d) for d in _load_docs("tiktok", limit=50)]
    docs = [d for d in docs if not _is_low_quality_tiktok_doc(d)]
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:50]


@web_app.get("/traffic")
async def traffic_list(neighborhood: str = ""):
    """Traffic flow data — temporarily disabled, CCTV pipeline not yet fully implemented."""
    return []


def _aggregate_city_demographics() -> dict:
    """Look up pre-aggregated city-wide demographics."""
    summary = _load_demographics_summary()
    return summary.get("city_wide", {})


@web_app.get("/summary")
async def summary():
    """City-wide summary stats."""
    total_docs = 0
    source_counts = {}
    # Traffic/CCTV temporarily excluded — pipelines not yet fully implemented
    for source in NON_SENSOR_PIPELINE_SOURCES:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            count = len(list(source_dir.rglob("*.json")))
            source_counts[source] = count
            total_docs += count

    demographics = _aggregate_city_demographics()

    return {
        "total_documents": total_docs,
        "source_counts": source_counts,
        "demographics": demographics,
    }


@web_app.get("/cctv/latest")
async def cctv_latest():
    """Latest CCTV analysis per camera: counts, density, location."""
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "analysis"
    if not analysis_dir.exists():
        return {"cameras": [], "count": 0}

    latest_by_cam: dict[str, dict] = {}
    for jf in sorted(analysis_dir.glob("*.json"), reverse=True)[:500]:
        try:
            data = json.loads(jf.read_text())
            cam_id = data.get("camera_id", "")
            if cam_id not in latest_by_cam:
                latest_by_cam[cam_id] = data
        except Exception:
            continue

    cameras = list(latest_by_cam.values())
    return {"cameras": cameras, "count": len(cameras)}


@web_app.get("/cctv/frame/{camera_id}")
async def cctv_frame(camera_id: str):
    """Serve latest annotated JPEG for a camera."""
    from fastapi.responses import Response

    volume.reload()
    ann_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "annotated"
    if not ann_dir.exists():
        return JSONResponse({"error": "no annotated frames"}, status_code=404)

    # Find latest annotated frame for this camera
    frames = sorted(ann_dir.glob(f"{camera_id}_*.jpg"), reverse=True)
    if not frames:
        return JSONResponse({"error": f"no frames for camera {camera_id}"}, status_code=404)

    frame_bytes = frames[0].read_bytes()
    return Response(content=frame_bytes, media_type="image/jpeg")


async def _aggregate_timeseries_for_neighborhood(name: str, camera_ids: list[str] | None = None) -> dict:
    """Aggregate per-camera timeseries into hourly buckets for a neighborhood."""
    from zoneinfo import ZoneInfo

    # Prefer fake analytics if available
    fake = _load_fake_cctv()
    if name in fake and fake[name].get("timeseries"):
        return fake[name]["timeseries"]

    if camera_ids is None:
        volume.reload()
        cctv_data = await _load_cctv_for_neighborhood(name)
        camera_ids = [c["camera_id"] for c in cctv_data.get("cameras", [])]
    if not camera_ids:
        return {"hours": [], "peak_hour": 0, "peak_pedestrians": 0, "camera_count": 0}

    ts_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "timeseries"
    if not ts_dir.exists():
        return {"hours": [], "peak_hour": 0, "peak_pedestrians": 0, "camera_count": len(camera_ids)}

    chicago_tz = ZoneInfo("America/Chicago")
    # Collect all entries per hour
    hourly: dict[int, list[dict]] = {h: [] for h in range(24)}

    for cam_id in camera_ids:
        ts_path = ts_dir / f"{cam_id}.json"
        if not ts_path.exists():
            continue
        try:
            entries = json.loads(ts_path.read_text())
        except Exception:
            continue
        for entry in entries:
            ts_str = entry.get("timestamp", "")
            if not ts_str:
                continue
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                local_hour = dt.astimezone(chicago_tz).hour
                hourly[local_hour].append(entry)
            except Exception:
                continue

    hours = []
    for h in range(24):
        entries = hourly[h]
        if entries:
            avg_p = sum(e.get("pedestrians", 0) for e in entries) / len(entries)
            avg_v = sum(e.get("vehicles", 0) for e in entries) / len(entries)
            density = "high" if avg_p > 20 else "medium" if avg_p > 5 else "low"
            hours.append({
                "hour": h,
                "avg_pedestrians": round(avg_p, 1),
                "avg_vehicles": round(avg_v, 1),
                "density": density,
                "sample_count": len(entries),
            })
        else:
            hours.append({
                "hour": h,
                "avg_pedestrians": 0,
                "avg_vehicles": 0,
                "density": "low",
                "sample_count": 0,
            })

    peak = max(hours, key=lambda b: b["avg_pedestrians"])
    return {
        "hours": hours,
        "peak_hour": peak["hour"],
        "peak_pedestrians": peak["avg_pedestrians"],
        "camera_count": len(camera_ids),
    }


@web_app.get("/cctv/timeseries/{neighborhood}")
async def cctv_timeseries(neighborhood: str):
    """24h rolling timeseries aggregated by hour for a neighborhood's cameras."""
    cctv = await _load_cctv_for_neighborhood(neighborhood)
    cam_ids = [c["camera_id"] for c in cctv.get("cameras", [])]
    return await _aggregate_timeseries_for_neighborhood(neighborhood, camera_ids=cam_ids)


@web_app.get("/vision/streetscape/{neighborhood}")
async def vision_streetscape(neighborhood: str):
    """Streetscape intelligence from vision pipeline analysis results."""
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "vision" / "analysis"
    if not analysis_dir.exists():
        return {"counts": None, "indicators": None, "analysis_count": 0}

    # Scan analysis results filtered by neighborhood
    totals = {
        "person": 0, "vehicle": 0, "storefront_open": 0, "storefront_closed": 0,
        "for_lease_sign": 0, "construction": 0, "restaurant_signage": 0, "outdoor_dining": 0,
    }
    analysis_count = 0
    slug = neighborhood.lower().replace(" ", "_")

    for jf in analysis_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
            counts = data.get("counts")
            if not counts:
                continue
            # Match by filename prefix or JSON neighborhood field
            file_match = jf.name.startswith(f"{slug}_")
            field_match = data.get("neighborhood", "").lower().replace(" ", "_") == slug
            if not file_match and not field_match:
                continue
            for key in totals:
                totals[key] += counts.get(key, 0)
            analysis_count += 1
        except Exception:
            continue

    if analysis_count == 0:
        return {"counts": None, "indicators": None, "analysis_count": 0}

    # Compute interpretation thresholds
    total_storefronts = totals["storefront_open"] + totals["storefront_closed"] + totals["for_lease_sign"]
    if total_storefronts > 0:
        vacancy_pct = (totals["for_lease_sign"] + totals["storefront_closed"]) / total_storefronts
        vacancy_signal = "high" if vacancy_pct > 0.4 else "moderate" if vacancy_pct > 0.15 else "low"
    else:
        vacancy_signal = "low"

    dining_total = totals["restaurant_signage"] + totals["outdoor_dining"]
    dining_saturation = "high" if dining_total > 10 else "moderate" if dining_total > 3 else "low"

    growth_signal = "active" if totals["construction"] > 0 else "stable"

    return {
        "counts": totals,
        "indicators": {
            "vacancy_signal": vacancy_signal,
            "dining_saturation": dining_saturation,
            "growth_signal": growth_signal,
        },
        "analysis_count": analysis_count,
    }


@web_app.get("/parking/latest")
async def parking_latest():
    """Latest parking analysis for all neighborhoods."""
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "parking" / "analysis"
    if not analysis_dir.exists():
        return {"neighborhoods": [], "count": 0}

    latest_by_nb: dict[str, dict] = {}
    for jf in sorted(analysis_dir.glob("*.json"), reverse=True)[:500]:
        try:
            data = json.loads(jf.read_text())
            nb = data.get("neighborhood", "")
            if nb and nb not in latest_by_nb:
                latest_by_nb[nb] = data
        except Exception:
            continue

    neighborhoods = list(latest_by_nb.values())
    return {"neighborhoods": neighborhoods, "count": len(neighborhoods)}


@web_app.get("/parking/{neighborhood}")
async def parking_neighborhood(neighborhood: str):
    """Latest parking analysis for a single neighborhood."""
    data = _load_parking_for_neighborhood(neighborhood)
    if not data:
        return JSONResponse({"error": f"No parking data for {neighborhood}"}, status_code=404)
    return data


@web_app.get("/parking/annotated/{neighborhood}")
async def parking_annotated(neighborhood: str):
    """Serve annotated satellite JPEG with parking lot overlays."""
    from fastapi.responses import Response

    volume.reload()
    slug = neighborhood.lower().replace(" ", "_")
    ann_dir = Path(PROCESSED_DATA_PATH) / "parking" / "annotated"
    ann_path = ann_dir / f"{slug}.jpg"

    if not ann_path.exists():
        return JSONResponse({"error": f"No annotated image for {neighborhood}"}, status_code=404)

    return Response(content=ann_path.read_bytes(), media_type="image/jpeg")


def _load_parking_for_neighborhood(name: str) -> dict | None:
    """Load latest parking analysis JSON for a neighborhood."""
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "parking" / "analysis"
    if not analysis_dir.exists():
        return None

    slug = name.lower().replace(" ", "_")
    # Find latest analysis file for this neighborhood
    candidates = sorted(analysis_dir.glob(f"{slug}_*.json"), reverse=True)
    if not candidates:
        return None

    try:
        return json.loads(candidates[0].read_text())
    except Exception:
        return None


@web_app.get("/vision/assess/{neighborhood}")
async def vision_assess(neighborhood: str):
    """AI-powered street assessment using GPT-4o vision on collected frames."""
    from modal_app.openai_utils import openai_available, get_openai_client

    if not openai_available():
        return JSONResponse(
            {"error": "Vision assessment requires OpenAI API key", "fallback": "Use /vision/streetscape for YOLO-based analysis"},
            status_code=503,
        )

    volume.reload()
    slug = neighborhood.lower().replace(" ", "_")

    # Collect frames from CCTV and vision pipeline
    frame_paths: list[Path] = []

    cctv_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "annotated"
    if cctv_dir.exists():
        for fp in sorted(cctv_dir.glob("*.jpg"), reverse=True)[:5]:
            frame_paths.append(fp)

    vision_dir = Path(RAW_DATA_PATH) / "vision" / "frames"
    if vision_dir.exists():
        for fp in sorted(vision_dir.glob(f"{slug}*.jpg"), reverse=True)[:5]:
            frame_paths.append(fp)
        if len(frame_paths) < 3:
            for fp in sorted(vision_dir.glob("*.jpg"), reverse=True)[:5]:
                if fp not in frame_paths:
                    frame_paths.append(fp)

    frame_paths = frame_paths[:3]

    if not frame_paths:
        return JSONResponse(
            {"error": f"No frames available for {neighborhood}", "frame_count": 0},
            status_code=404,
        )

    # Build vision messages with frames
    client = get_openai_client()
    image_content = []
    for fp in frame_paths:
        try:
            img_bytes = fp.read_bytes()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            image_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
            })
        except Exception:
            continue

    if not image_content:
        return JSONResponse({"error": "Failed to read frame images"}, status_code=500)

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an urban commercial real estate analyst. Analyze street-level images and provide a structured assessment. "
                        "Return JSON with this schema: {\"storefront_viability\": {\"score\": 1-10, \"available_spaces\": str, \"condition\": str}, "
                        "\"competitor_presence\": {\"restaurants\": str, \"retail\": str, \"notable_businesses\": [str]}, "
                        "\"pedestrian_activity\": {\"level\": \"high\"|\"medium\"|\"low\", \"demographics\": str, \"peak_indicators\": str}, "
                        "\"infrastructure\": {\"transit_access\": str, \"parking\": str, \"road_condition\": str}, "
                        "\"overall_recommendation\": str (2-3 sentences)}"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Assess this area in {neighborhood}, Chicago for small business viability. Analyze the street scenes:"},
                        *image_content,
                    ],
                },
            ],
            max_tokens=600,
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        assessment = json.loads(resp.choices[0].message.content or "{}")
        return {
            "assessment": assessment,
            "frame_count": len(image_content),
            "neighborhood": neighborhood,
            "model": "gpt-4o",
        }
    except Exception as e:
        return JSONResponse({"error": f"Vision assessment failed: {e}"}, status_code=500)


@web_app.get("/geo")
async def geo():
    """GeoJSON FeatureCollection for map."""
    geo_path = Path(PROCESSED_DATA_PATH) / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        return json.loads(geo_path.read_text())
    return {"type": "FeatureCollection", "features": []}


def _transform_doc_for_graph(doc: dict) -> dict:
    """Transform Supermemory API doc to DocumentWithMemories format. Preserves all fields for graph viz."""
    memories = doc.get("memories", doc.get("memoryEntries", []))
    memory_entries = []
    for m in memories:
        # Normalize memoryRelations: API may return object {targetId: "updates"} or array [{targetMemoryId, relationType}]
        rels = m.get("memoryRelations")
        if isinstance(rels, dict):
            rels = [{"targetMemoryId": k, "relationType": v} for k, v in rels.items() if v in ("updates", "extends", "derives")]
        entry = {
            "id": m.get("id", ""),
            "documentId": doc.get("id", ""),
            "content": m.get("memory", m.get("content")),
            "summary": m.get("summary"),
            "title": m.get("title"),
            "createdAt": m.get("createdAt", m.get("created_at")),
            "updatedAt": m.get("updatedAt", m.get("updated_at")),
            "isLatest": m.get("isLatest", True),
            "isForgotten": m.get("isForgotten"),
            "forgetAfter": m.get("forgetAfter"),
            "relation": m.get("relation") or m.get("changeType"),
            "memoryRelations": rels if isinstance(rels, list) else m.get("memoryRelations"),
            "updatesMemoryId": m.get("updatesMemoryId"),
            "nextVersionId": m.get("nextVersionId"),
            "parentMemoryId": m.get("parentMemoryId"),
            "rootMemoryId": m.get("rootMemoryId"),
            "metadata": m.get("metadata"),
            "spaceId": m.get("spaceId"),
            "spaceContainerTag": m.get("spaceContainerTag"),
        }
        memory_entries.append(entry)
    out = {
        "id": doc.get("id", ""),
        "customId": doc.get("customId"),
        "title": doc.get("title"),
        "content": doc.get("content"),
        "summary": doc.get("summary"),
        "url": doc.get("url"),
        "source": doc.get("source"),
        "type": doc.get("type", doc.get("documentType")),
        "status": doc.get("status", "done"),
        "metadata": doc.get("metadata"),
        "createdAt": doc.get("createdAt", doc.get("created_at")),
        "updatedAt": doc.get("updatedAt", doc.get("updated_at")),
        "memoryEntries": memory_entries,
    }
    # Preserve x,y for layout; summaryEmbedding for doc-doc similarity edges
    if doc.get("x") is not None:
        out["x"] = doc["x"]
    if doc.get("y") is not None:
        out["y"] = doc["y"]
    if doc.get("summaryEmbedding") is not None:
        out["summaryEmbedding"] = doc["summaryEmbedding"]
    return out


def _build_city_graph_fallback() -> dict:
    """Build minimal city graph from neighborhoods + public data when no precomputed graph exists."""
    from modal_app.common import NEIGHBORHOOD_CENTROIDS, CHICAGO_NEIGHBORHOODS

    nodes = []
    for nb in CHICAGO_NEIGHBORHOODS:
        centroid = NEIGHBORHOOD_CENTROIDS.get(nb)
        if centroid:
            lat, lng = centroid
            nodes.append({
                "id": f"nb:{nb}",
                "type": "neighborhood",
                "label": nb,
                "lat": lat,
                "lng": lng,
                "size": 40,
            })
        else:
            nodes.append({"id": f"nb:{nb}", "type": "neighborhood", "label": nb, "size": 40})

    # Edges: connect neighborhoods that share permits/inspections (from public_data)
    edges = []
    public_docs = _load_docs("public_data", limit=500)
    nb_pairs: set[tuple[str, str]] = set()
    for doc in public_docs:
        meta = doc.get("metadata", {})
        geo = meta.get("geo", {})
        nb = (geo.get("neighborhood") or "").strip()
        if not nb or nb not in CHICAGO_NEIGHBORHOODS:
            nb = detect_neighborhood(doc.get("content", "") or doc.get("title", ""))
        if nb:
            dataset = meta.get("dataset", "")
            # Create edges from same-dataset docs in same/different neighborhoods
            for other in public_docs[:100]:
                o_meta = other.get("metadata", {})
                o_geo = o_meta.get("geo", {})
                o_nb = (o_geo.get("neighborhood") or "").strip()
                if not o_nb:
                    o_nb = detect_neighborhood(other.get("content", "") or other.get("title", ""))
                if o_nb and o_nb != nb and o_meta.get("dataset") == dataset:
                    pair = tuple(sorted([nb, o_nb]))
                    nb_pairs.add(pair)

    for a, b in list(nb_pairs)[:400]:  # Cap edges
        edges.append({"source": f"nb:{a}", "target": f"nb:{b}", "weight": 1})

    return {"nodes": nodes, "edges": edges}


@web_app.get("/graph/full")
async def graph_full():
    """City graph (nodes + edges) from volume or fallback build."""
    await volume.reload.aio()
    for path in [
        Path(PROCESSED_DATA_PATH) / "city_graph.json",
        Path(PROCESSED_DATA_PATH) / "graph" / "city_graph.json",
        Path(PROCESSED_DATA_PATH) / "graph.json",
    ]:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if data.get("nodes") is not None:
                    return data
            except Exception as e:
                print(f"graph/full: failed to read {path}: {e}")
                continue
    return _build_city_graph_fallback()


@web_app.get("/graph")
async def graph(page: int = 1, limit: int = 500):
    """Proxy to Supermemory for Memory Graph. Tries graph/viewport (with bounds) first, then documents/list."""
    empty: dict = {"documents": [], "edges": [], "pagination": {"currentPage": 1, "totalPages": 0}}
    api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not api_key:
        return JSONResponse(empty, status_code=200)
    import httpx
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # Get graph bounds to know the full viewport
            viewport = {"minX": 0, "maxX": 1000000, "minY": 0, "maxY": 1000000}
            try:
                bounds_resp = await client.get(
                    "https://api.supermemory.ai/v3/graph/bounds",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if bounds_resp.is_success:
                    bounds_data = bounds_resp.json()
                    if bounds_data.get("bounds"):
                        viewport = bounds_data["bounds"]
            except Exception:
                pass

            resp = await client.post(
                "https://api.supermemory.ai/v3/graph/viewport",
                headers=headers,
                json={
                    "viewport": viewport,
                    "limit": min(limit, 500),
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_docs = data.get("documents", [])
                docs = [_transform_doc_for_graph(d) for d in raw_docs]
                total = data.get("totalCount", len(docs))
                out = {
                    "documents": docs,
                    "edges": data.get("edges", []),
                    "pagination": {
                        "currentPage": page,
                        "totalPages": max(1, (total + limit - 1) // limit),
                        "totalItems": total,
                    },
                }
                return JSONResponse(out, status_code=200)
        except Exception as e:
            print(f"Supermemory graph/viewport: {e}")
        # Fallback to documents/list endpoints
        for url in ["https://api.supermemory.ai/v3/documents/list", "https://api.supermemory.ai/v3/documents/documents"]:
            try:
                resp = await client.post(url, headers=headers, json={"page": page, "limit": min(limit, 500), "sort": "createdAt", "order": "desc"})
                if resp.status_code in (401, 403):
                    continue
                resp.raise_for_status()
                data = resp.json()
                raw_docs = data.get("documents") or data.get("memories") or []
                docs = [_transform_doc_for_graph(d) for d in raw_docs]
                return JSONResponse({"documents": docs, "pagination": data.get("pagination", {})}, status_code=200)
            except Exception as e:
                print(f"Supermemory {url}: {e}")
                continue
    return JSONResponse(empty, status_code=200)


def _load_city_graph() -> dict:
    """Load the pre-built city graph from volume."""
    volume.reload()
    graph_path = Path(PROCESSED_DATA_PATH) / "graph" / "city_graph.json"
    if not graph_path.exists():
        return {"nodes": [], "edges": [], "stats": {}}
    return json.loads(graph_path.read_text())


@web_app.get("/graph/full")
async def get_full_graph():
    """Full city graph as node/edge JSON for D3."""
    return _load_city_graph()


@web_app.get("/graph/neighborhood/{name}")
async def get_neighborhood_graph(name: str):
    """1-hop subgraph around a neighborhood node."""
    data = _load_city_graph()
    nb_id = f"nb:{name}"

    connected = {nb_id}
    for edge in data["edges"]:
        if edge["source"] == nb_id or edge["target"] == nb_id:
            connected.add(edge["source"])
            connected.add(edge["target"])

    nodes = [n for n in data["nodes"] if n["id"] in connected]
    edges = [e for e in data["edges"] if e["source"] in connected and e["target"] in connected]

    return {"nodes": nodes, "edges": edges, "center": nb_id}


@web_app.get("/graph/stats")
async def get_graph_stats():
    """Graph statistics."""
    data = _load_city_graph()
    return data.get("stats", {})


@web_app.get("/gpu-metrics")
async def gpu_metrics():
    """Live GPU utilization from active containers."""
    import asyncio

    results = {
        "h100_llm": {"status": "cold"},
        "t4_classifier": {"status": "cold"},
        "t4_sentiment": {"status": "cold"},
        "t4_cctv": {"status": "cold"},
    }

    # Query non-batched GPU classes directly (batched classes can't have extra methods)
    gpu_classes = [
        ("AlethiaLLM", "h100_llm"),
        ("TrafficAnalyzer", "t4_cctv"),
    ]

    async def _fetch(cls_name: str, key: str):
        try:
            cls = modal.Cls.from_name("alethia", cls_name)
            instance = cls()
            metrics = await asyncio.wait_for(
                instance.gpu_metrics.remote.aio(), timeout=8,
            )
            results[key] = metrics
        except Exception:
            pass

    await asyncio.gather(
        *[_fetch(name, key) for name, key in gpu_classes],
        return_exceptions=True,
    )

    # Infer classifier status from enriched docs — @modal.batched classes
    # can't expose a gpu_metrics method, so we check the queue drainer
    # (process_queue_batch, 2min cron) activity via enriched file timestamps.
    # scaledown_window=120s means containers stay warm ~2min after last call.
    try:
        enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
        if enriched_dir.exists():
            enriched_files = list(enriched_dir.rglob("*.json"))
            enriched_count = len(enriched_files)
            if enriched_files:
                latest = max(enriched_files, key=lambda f: f.stat().st_mtime)
                last_enriched = latest.stat().st_mtime
                age_seconds = time.time() - last_enriched
                # scaledown_window=120 + cron every 2min → warm if enriched within ~4min
                if age_seconds < 240:
                    warm_status = {"status": "active", "gpu_name": "NVIDIA T4", "inferred": True, "enriched_count": enriched_count}
                    results["t4_classifier"] = warm_status
                    results["t4_sentiment"] = warm_status
                else:
                    idle_status = {"status": "cold", "reason": "idle", "enriched_count": enriched_count, "last_run_ago_s": round(age_seconds)}
                    results["t4_classifier"] = idle_status
                    results["t4_sentiment"] = idle_status
            else:
                no_data = {"status": "cold", "reason": "no_data", "enriched_count": 0}
                results["t4_classifier"] = no_data
                results["t4_sentiment"] = no_data
        else:
            no_data = {"status": "cold", "reason": "no_data", "enriched_count": 0}
            results["t4_classifier"] = no_data
            results["t4_sentiment"] = no_data
    except Exception:
        pass

    return results


@web_app.get("/health")
async def health():
    from modal_app.vectordb import check_vectordb_health
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat(), "vectordb": check_vectordb_health()}


@web_app.post("/demo/scale")
async def demo_scale(request: Request):
    """Trigger scaling demo — fans out parallel agents + classification to generate traces."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    num_agents = body.get("num_agents", 15)
    num_queries = body.get("num_queries", 5)
    run_classify = body.get("run_classify", True)

    demo_fn = modal.Function.from_name("alethia", "scaling_demo")
    result = await demo_fn.remote.aio(
        num_agents=num_agents,
        num_queries=num_queries,
        run_classify=run_classify,
    )
    return result


# ── Deep Dive: AI-generated data analysis via Modal Sandbox ──────────────────

CODEGEN_SYSTEM_PROMPT = """You are a data analyst. Write a self-contained Python script that answers the user's question using real data files.

Rules:
- Read data from /data/raw/{source}/ and /data/processed/enriched/ (JSON files)
- Write results to /output/result.json (required) and optionally /output/chart.png
- result.json must have: {"title": str, "summary": str, "stats": {key: value}}
- Only use: json, os, pathlib, glob, collections, datetime, pandas, numpy, matplotlib, seaborn
- matplotlib.use("Agg") must be called before any plotting
- Max 80 lines. No network calls, no subprocess, no sys.exit.
- Create /output/ directory at the start: os.makedirs("/output", exist_ok=True)
- Always wrap file reads in try/except to handle missing or malformed files gracefully
- Output only the Python code in a ```python``` fence. No explanation."""

CODEGEN_SYSTEM_PROMPT_GPT4O = """You are a senior data analyst. Write a self-contained Python script that answers the user's question using real data files.

Rules:
- Read data from /data/raw/{source}/ and /data/processed/enriched/ (JSON files)
- Write results to /output/result.json (required) and optionally /output/chart.png
- result.json must have: {"title": str, "summary": str, "stats": {key: value}}
- Only use: json, os, pathlib, glob, collections, datetime, pandas, numpy, matplotlib, seaborn
- matplotlib.use("Agg") must be called before any plotting
- Max 100 lines. No network calls, no subprocess, no sys.exit.
- Create /output/ directory at the start: os.makedirs("/output", exist_ok=True)
- Wrap ALL file reads in try/except — skip corrupted/missing files gracefully
- Compute percentile rankings where applicable (e.g. "top 25% of neighborhoods")
- Detect simple trends: compare recent vs older data when timestamps are available
- For charts: use dark theme (plt.style.use('dark_background')), proper axis labels, tight_layout
- Use seaborn color palettes for multi-series plots
- Validate result.json schema before writing: title must be str, stats must be dict
- Output only the Python code in a ```python``` fence. No explanation."""


def _discover_data_files(neighborhood: str | None = None) -> dict:
    """Scan volume for available data files so the LLM knows what exists."""
    sources = {}
    raw = Path(RAW_DATA_PATH)
    if not raw.exists():
        return sources

    for source_dir in sorted(raw.iterdir()):
        if not source_dir.is_dir():
            continue
        json_files = list(source_dir.rglob("*.json"))[:20]
        if not json_files:
            continue
        # Sample first file for schema keys
        schema_keys = []
        try:
            sample = json.loads(json_files[0].read_text())
            if isinstance(sample, dict):
                schema_keys = list(sample.keys())[:10]
        except Exception:
            pass
        sources[source_dir.name] = {
            "count": len(list(source_dir.rglob("*.json"))),
            "sample_path": str(json_files[0]),
            "schema_keys": schema_keys,
        }

    # Check enriched
    enriched = Path(PROCESSED_DATA_PATH) / "enriched"
    if enriched.exists():
        json_files = list(enriched.rglob("*.json"))[:20]
        if json_files:
            schema_keys = []
            try:
                sample = json.loads(json_files[0].read_text())
                if isinstance(sample, dict):
                    schema_keys = list(sample.keys())[:10]
            except Exception:
                pass
            sources["enriched"] = {
                "count": len(list(enriched.rglob("*.json"))),
                "sample_path": str(json_files[0]),
                "schema_keys": schema_keys,
            }

    return sources


def _build_codegen_prompt(
    question: str,
    brief: str,
    neighborhood: str,
    business_type: str,
    available_sources: dict,
) -> str:
    source_listing = "\n".join(
        f"- /data/raw/{src}/: {info['count']} files, keys: {info['schema_keys']}"
        if src != "enriched"
        else f"- /data/processed/enriched/: {info['count']} files, keys: {info['schema_keys']}"
        for src, info in available_sources.items()
    )
    brief_truncated = brief[:3000] if brief else "(no brief provided)"
    return f"""Neighborhood: {neighborhood}
Business type: {business_type}

User question: {question}

Intelligence brief context:
{brief_truncated}

Available data on the volume:
{source_listing}

Write a Python script to analyze this data and answer the question. Include a chart if appropriate."""


def _extract_python_code(response: str) -> str | None:
    """Extract Python code from LLM response."""
    # Try fenced code block first
    match = re.search(r"```python\s*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: unfenced code starting with import/from
    match = re.search(r"^((?:import |from ).*)", response, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


class _AnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    brief: str = Field(default="")
    neighborhood: str = Field(default="Loop")
    business_type: str = Field(default="Restaurant")


@web_app.post("/analyze")
async def analyze(payload: _AnalyzeRequest):
    """Deep Dive: generate a Python analysis script via LLM, run it in a Modal Sandbox."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    span_ctx = tracer.start_as_current_span("deep-dive-analyze") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", payload.question)
            span.set_attribute("deep_dive.neighborhood", payload.neighborhood)

        # 1. Discover available data
        available = _discover_data_files(payload.neighborhood)
        if not available:
            return JSONResponse(
                {"error": "No data files found on volume"},
                status_code=404,
            )

        # 2. Generate analysis code via LLM (GPT-4o when available, Qwen3 fallback)
        from modal_app.openai_utils import openai_available, get_openai_client

        prompt = _build_codegen_prompt(
            payload.question,
            payload.brief,
            payload.neighborhood,
            payload.business_type,
            available,
        )

        async def _codegen_via_qwen(p: str) -> str:
            llm_cls = modal.Cls.from_name("alethia", "AlethiaLLM")
            llm = llm_cls()
            msgs = [{"role": "system", "content": CODEGEN_SYSTEM_PROMPT}, {"role": "user", "content": p}]
            return await llm.generate.remote.aio(msgs, max_tokens=2048, temperature=0.3)

        model_used = "qwen3-8b"
        if openai_available():
            try:
                client = get_openai_client()
                oai_resp = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": CODEGEN_SYSTEM_PROMPT_GPT4O},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=2048,
                    temperature=0.3,
                )
                response = oai_resp.choices[0].message.content or ""
                model_used = "gpt-4o"
            except Exception as e:
                print(f"GPT-4o codegen failed, falling back to Qwen3: {e}")
                response = await _codegen_via_qwen(prompt)
        else:
            response = await _codegen_via_qwen(prompt)

        code = _extract_python_code(response)
        if not code:
            return JSONResponse(
                {"error": "Failed to generate valid analysis code", "raw_response": response[:500]},
                status_code=500,
            )

        # 3. Run in Modal Sandbox
        sb = modal.Sandbox.create(
            "python", "-c", code,
            image=sandbox_image,
            volumes={"/data": volume},
            timeout=30,
            app=app,
        )
        sb.wait()

        stderr_text = sb.stderr.read()
        stdout_text = sb.stdout.read()

        # 4. Read results
        result_data = None
        chart_b64 = None

        try:
            result_file = sb.open("/output/result.json", "r")
            result_data = json.loads(result_file.read())
            result_file.close()
        except Exception:
            # Script may have written to stdout instead
            if stdout_text.strip():
                result_data = {"title": "Analysis Result", "summary": stdout_text.strip()[:2000], "stats": {}}

        try:
            chart_file = sb.open("/output/chart.png", "rb")
            chart_bytes = chart_file.read()
            chart_b64 = base64.b64encode(chart_bytes).decode("utf-8")
            chart_file.close()
        except Exception:
            pass

        if span:
            span.set_attribute("deep_dive.has_chart", chart_b64 is not None)
            span.set_attribute("deep_dive.code_lines", len(code.splitlines()))
            span.set_attribute("deep_dive.model", model_used)

        return {
            "code": code,
            "result": result_data or {"title": "Analysis", "summary": "Script completed but produced no result.json", "stats": {}, "raw_output": stdout_text[:2000]},
            "chart": chart_b64,
            "stderr": stderr_text[:500] if stderr_text else None,
            "model_used": model_used,
        }

    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Impact Briefs — Recursive Agent Architecture endpoints
# ---------------------------------------------------------------------------

@web_app.get("/impact-briefs")
async def list_impact_briefs(limit: int = 20, min_score: float = 0.0):
    """List recent impact briefs generated by the Lead Analyst."""
    volume.reload()
    briefs_dir = Path(PROCESSED_DATA_PATH) / "impact_briefs"
    if not briefs_dir.exists():
        return {"briefs": [], "count": 0}

    briefs = []
    for json_file in sorted(briefs_dir.rglob("*.json"), reverse=True)[:limit]:
        try:
            brief = json.loads(json_file.read_text())
            if brief.get("impact_score", 0) >= min_score:
                briefs.append(brief)
        except Exception:
            continue

    return {"briefs": briefs, "count": len(briefs)}


@web_app.get("/impact-briefs/{brief_id}")
async def get_impact_brief(brief_id: str):
    """Get a single impact brief by ID."""
    volume.reload()
    briefs_dir = Path(PROCESSED_DATA_PATH) / "impact_briefs"
    if not briefs_dir.exists():
        return JSONResponse({"error": "No impact briefs found"}, status_code=404)

    for json_file in briefs_dir.rglob("*.json"):
        try:
            brief = json.loads(json_file.read_text())
            if brief.get("id") == brief_id:
                return brief
        except Exception:
            continue

    return JSONResponse({"error": f"Brief {brief_id} not found"}, status_code=404)


class AnalyzeRequest(BaseModel):
    doc_id: str = Field(..., description="ID of the enriched document to analyze")


@web_app.post("/impact-briefs/analyze")
async def trigger_impact_analysis(req: AnalyzeRequest):
    """Manually trigger impact analysis for a specific document."""
    try:
        from modal_app.lead_analyst import analyze_impact
        result = await analyze_impact.remote.aio(req.doc_id)
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.function(
    image=web_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    min_containers=1,
)
@modal.asgi_app()
def serve():
    """Modal-hosted FastAPI application."""
    from modal_app.instrumentation import init_tracing
    init_tracing()
    return web_app
