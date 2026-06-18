"""News ingester — pulls local Chicago news from RSS feeds and NewsAPI.

Cadence: Every 30 minutes
Sources: RSS (Block Club Chicago, Chicago Tribune, Crain's), NewsAPI
Pattern: async + FallbackChain + gather_with_limit + detect_neighborhood
"""
import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx
import modal

from backend.shared_data import (
    get_dedup_data_dir,
    get_raw_data_dir,
    load_json_file,
    shared_data_lock,
    write_json_file,
    write_source_status,
)
from modal_app.common import SourceType, build_document, detect_neighborhood, gather_with_limit, safe_queue_push, safe_volume_commit
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image

# RSS feeds for Chicago local news
RSS_FEEDS = [
    ("Block Club Chicago", "https://blockclubchicago.org/feed/"),
    ("Chicago Tribune", "https://www.chicagotribune.com/feed/"),
    ("Chicago Sun-Times", "https://chicago.suntimes.com/rss/index.xml"),
]

# Google News RSS fallback
GOOGLE_NEWS_RSS = [
    ("Google News Chicago Business", "https://news.google.com/rss/search?q=Chicago+business+regulation&hl=en-US&gl=US&ceid=US:en"),
    ("Google News Chicago Zoning", "https://news.google.com/rss/search?q=Chicago+zoning+permit&hl=en-US&gl=US&ceid=US:en"),
]

NEWSAPI_KEYWORDS = [
    "Chicago business regulation",
    "Chicago zoning",
    "Chicago small business",
    "Chicago permit",
    "Chicago city council",
    "Chicago restaurant",
]

DEFAULT_CLASSIFICATION_QUEUE_TIMEOUT_SECONDS = 30.0
DEFAULT_RAW_WRITE_CONCURRENCY = 8
DEFAULT_NEWS_DEDUP_LOCK_TIMEOUT_SECONDS = 45.0
DEFAULT_NEWS_DEDUP_LOCK_STALE_SECONDS = 30.0
DEFAULT_NEWS_CLAIM_TTL_SECONDS = 15 * 60


def _classification_queue_timeout_seconds() -> float:
    raw = os.environ.get("NEWS_CLASSIFICATION_QUEUE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_CLASSIFICATION_QUEUE_TIMEOUT_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_CLASSIFICATION_QUEUE_TIMEOUT_SECONDS


def _raw_write_concurrency() -> int:
    raw = os.environ.get("NEWS_RAW_WRITE_CONCURRENCY", "").strip()
    if not raw:
        return DEFAULT_RAW_WRITE_CONCURRENCY
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_RAW_WRITE_CONCURRENCY


def _news_dedup_lock_settings() -> tuple[float, float, float]:
    timeout_raw = os.environ.get("NEWS_DEDUP_LOCK_TIMEOUT_SECONDS", "").strip()
    stale_raw = os.environ.get("NEWS_DEDUP_LOCK_STALE_SECONDS", "").strip()
    poll_raw = os.environ.get("NEWS_DEDUP_LOCK_POLL_SECONDS", "").strip()

    try:
        stale_seconds = max(5.0, float(stale_raw)) if stale_raw else DEFAULT_NEWS_DEDUP_LOCK_STALE_SECONDS
    except ValueError:
        stale_seconds = DEFAULT_NEWS_DEDUP_LOCK_STALE_SECONDS

    try:
        timeout_seconds = max(10.0, float(timeout_raw)) if timeout_raw else DEFAULT_NEWS_DEDUP_LOCK_TIMEOUT_SECONDS
    except ValueError:
        timeout_seconds = DEFAULT_NEWS_DEDUP_LOCK_TIMEOUT_SECONDS
    if timeout_seconds <= stale_seconds:
        timeout_seconds = stale_seconds + 5.0

    try:
        poll_seconds = max(0.1, float(poll_raw)) if poll_raw else 1.0
    except ValueError:
        poll_seconds = 1.0

    return timeout_seconds, poll_seconds, stale_seconds


def _news_claim_ttl_seconds() -> float:
    raw = os.environ.get("NEWS_CLAIM_TTL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_NEWS_CLAIM_TTL_SECONDS
    try:
        return max(60.0, float(raw))
    except ValueError:
        return DEFAULT_NEWS_CLAIM_TTL_SECONDS


def _parse_claim_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _news_dedup_paths():
    directory = get_dedup_data_dir()
    return directory / "news.json", directory / "news.lock"


def _load_news_dedup_state(path) -> tuple[list[str], dict[str, str], dict[str, dict]]:
    parsed = load_json_file(path, default=None)
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item)], {}, {}

    if not isinstance(parsed, dict):
        return [], {}, {}

    ids_raw = parsed.get("ids", [])
    ids = [str(item) for item in ids_raw if str(item)] if isinstance(ids_raw, list) else []

    seen_at_raw = parsed.get("seen_at", {})
    seen_at = {}
    if isinstance(seen_at_raw, dict):
        seen_at = {
            str(key): str(value)
            for key, value in seen_at_raw.items()
            if str(key)
        }

    claims_raw = parsed.get("claims", {})
    claims = {}
    if isinstance(claims_raw, dict):
        claims = {
            str(key): dict(value)
            for key, value in claims_raw.items()
            if str(key) and isinstance(value, dict)
        }
    return ids, seen_at, claims


def _write_news_dedup_state(path, ids: list[str], seen_at: dict[str, str], claims: dict[str, dict]) -> None:
    write_json_file(path, {"ids": ids, "seen_at": seen_at, "claims": claims}, indent=None)


def _active_news_claims(claims: dict[str, dict], now: datetime) -> dict[str, dict]:
    active: dict[str, dict] = {}
    for doc_id, claim in claims.items():
        expires_at = _parse_claim_timestamp(claim.get("expires_at"))
        if expires_at is not None and expires_at > now:
            active[doc_id] = claim
    return active


def _normalize_news_docs(all_docs: list[dict]) -> list[dict]:
    normalized_docs: list[dict] = []
    batch_ids: set[str] = set()
    for doc in all_docs:
        if not isinstance(doc, dict):
            continue
        doc_id = str(doc.get("id", "") or "").strip()
        if not doc_id or doc_id in batch_ids:
            continue
        normalized = dict(doc)
        normalized["id"] = doc_id
        normalized_docs.append(normalized)
        batch_ids.add(doc_id)
    return normalized_docs


def _claim_news_docs_for_attempt(all_docs: list[dict]) -> tuple[str, list[dict], dict[str, int]]:
    """Create temporary durable claims for docs this attempt may process."""
    owner = str(uuid.uuid4())
    candidate_docs = _normalize_news_docs(all_docs)
    data_path, lock_path = _news_dedup_paths()
    timeout_seconds, poll_seconds, stale_seconds = _news_dedup_lock_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=_news_claim_ttl_seconds())
    claimed_docs: list[dict] = []
    skipped_seen = 0
    skipped_claimed = 0

    with shared_data_lock(
        lock_path,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        stale_seconds=stale_seconds,
    ):
        ids, seen_at, claims = _load_news_dedup_state(data_path)
        seen_ids = set(ids)
        claims = _active_news_claims(claims, now)

        for doc in candidate_docs:
            doc_id = doc["id"]
            if doc_id in seen_ids:
                skipped_seen += 1
                continue
            if doc_id in claims:
                skipped_claimed += 1
                continue
            claims[doc_id] = {
                "owner": owner,
                "claimed_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            claimed_docs.append(doc)

        _write_news_dedup_state(data_path, ids, seen_at, claims)

    return owner, claimed_docs, {
        "candidates": len(candidate_docs),
        "claimed": len(claimed_docs),
        "skipped_seen": skipped_seen,
        "skipped_claimed": skipped_claimed,
    }


def _finalize_news_claims(
    owner: str,
    *,
    completed_ids: set[str] | None = None,
    release_ids: set[str] | None = None,
) -> None:
    """Finalize or release claims owned by this attempt."""
    completed_ids = completed_ids or set()
    release_ids = release_ids or set()
    if not completed_ids and not release_ids:
        return

    data_path, lock_path = _news_dedup_paths()
    timeout_seconds, poll_seconds, stale_seconds = _news_dedup_lock_settings()
    now = datetime.now(timezone.utc)

    with shared_data_lock(
        lock_path,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        stale_seconds=stale_seconds,
    ):
        ids, seen_at, claims = _load_news_dedup_state(data_path)
        seen_ids = set(ids)
        claims = _active_news_claims(claims, now)

        for doc_id in completed_ids:
            claim = claims.get(doc_id)
            if claim and claim.get("owner") != owner:
                continue
            if doc_id not in seen_ids:
                ids.append(doc_id)
                seen_ids.add(doc_id)
            seen_at[doc_id] = now.isoformat()
            claims.pop(doc_id, None)

        for doc_id in release_ids:
            claim = claims.get(doc_id)
            if claim and claim.get("owner") == owner:
                claims.pop(doc_id, None)

        _write_news_dedup_state(data_path, ids, seen_at, claims)


async def _fetch_single_rss(feed_name: str, feed_url: str) -> list[dict]:
    """Parse a single RSS feed and return serializable dicts."""
    docs = []
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(feed_url)
        if resp.status_code != 200:
            print(f"RSS [{feed_name}]: HTTP {resp.status_code}")
            return docs

    feed = feedparser.parse(resp.text)
    for entry in feed.entries[:20]:
        published = entry.get("published_parsed")
        if published:
            ts = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
        else:
            ts = datetime.now(timezone.utc).isoformat()

        content = entry.get("summary", entry.get("description", ""))
        title = entry.get("title", "")
        neighborhood = detect_neighborhood(f"{title} {content}")

        docs.append({
            "id": f"news-rss-{hashlib.md5((entry.get('link', '') or title).encode()).hexdigest()[:12]}",
            "source": SourceType.NEWS.value,
            "title": title,
            "content": content,
            "url": entry.get("link", ""),
            "timestamp": ts,
            "metadata": {
                "feed_name": feed_name,
                "author": entry.get("author", ""),
                "tags": [t.get("term", "") for t in entry.get("tags", [])],
            },
            "geo": {"neighborhood": neighborhood} if neighborhood else {},
        })
    return docs


async def _fetch_all_rss() -> list[dict]:
    """Fetch all RSS feeds in parallel."""
    coros = [_fetch_single_rss(name, url) for name, url in RSS_FEEDS]
    results = await gather_with_limit(coros, max_concurrent=5)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


async def _fetch_google_news_rss() -> list[dict]:
    """Fallback: fetch from Google News RSS."""
    coros = [_fetch_single_rss(name, url) for name, url in GOOGLE_NEWS_RSS]
    results = await gather_with_limit(coros, max_concurrent=3)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


async def _fetch_newsapi(api_key: str) -> list[dict]:
    """Fetch articles from NewsAPI matching Chicago business keywords."""
    docs = []
    if not api_key:
        print("NEWSAPI_KEY not set, skipping NewsAPI")
        return docs

    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    async def _fetch_keyword(keyword: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": keyword,
                    "from": since,
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                    "language": "en",
                },
                headers={"X-Api-Key": api_key},
            )
            if resp.status_code != 200:
                print(f"NewsAPI error for '{keyword}': {resp.status_code}")
                return []

            keyword_docs = []
            for article in resp.json().get("articles", []):
                content = article.get("description", "") or article.get("content", "")
                title = article.get("title", "")
                neighborhood = detect_neighborhood(f"{title} {content}")

                keyword_docs.append({
                    "id": f"news-api-{hashlib.md5((article.get('url', '') or '').encode()).hexdigest()[:12]}",
                    "source": SourceType.NEWS.value,
                    "title": title,
                    "content": content,
                    "url": article.get("url", ""),
                    "timestamp": (
                        datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00")).isoformat()
                        if article.get("publishedAt")
                        else datetime.now(timezone.utc).isoformat()
                    ),
                    "metadata": {
                        "source_name": article.get("source", {}).get("name", ""),
                        "author": article.get("author", ""),
                        "keyword": keyword,
                    },
                    "geo": {"neighborhood": neighborhood} if neighborhood else {},
                })
            return keyword_docs

    coros = [_fetch_keyword(kw) for kw in NEWSAPI_KEYWORDS[:3]]
    results = await gather_with_limit(coros, max_concurrent=3)
    for result in results:
        if result:
            docs.extend(result)
    return docs


async def _enqueue_news_docs_for_classification(docs: list[dict]) -> dict[str, object]:
    """Best-effort classification enqueue after raw ingestion is durable."""
    from modal_app.classify import doc_queue

    timeout_seconds = _classification_queue_timeout_seconds()
    try:
        failures = await asyncio.wait_for(
            safe_queue_push(doc_queue, docs, "news"),
            timeout=timeout_seconds,
        )
        return {
            "state": "enqueued" if failures == 0 else "partial_failure",
            "failures": failures,
            "timeout_seconds": timeout_seconds,
        }
    except TimeoutError:
        print(f"News classification enqueue timed out after {timeout_seconds:g}s; ingestion state is already persisted")
        return {
            "state": "timeout",
            "failures": len(docs),
            "timeout_seconds": timeout_seconds,
        }
    except Exception as e:
        print(f"News classification enqueue failed after persistence: {e}")
        return {
            "state": "failed",
            "failures": len(docs),
            "timeout_seconds": timeout_seconds,
            "error": str(e),
        }


async def _write_news_doc(doc_data: dict, out_dir) -> dict | None:
    """Write one raw news document without blocking the event loop."""

    def _write() -> dict:
        doc = build_document(doc_data)
        fpath = out_dir / f"{doc.id}.json"
        if isinstance(fpath, Path):
            fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(doc.model_dump_json(indent=2))
        return doc_data

    try:
        return await asyncio.to_thread(_write)
    except Exception as e:
        print(f"News raw write failed for {doc_data.get('id', '<missing-id>')}: {e}")
        return None


async def _persist_news_docs(all_docs: list[dict]) -> int:
    """Persist raw news docs and durable ingestion state before queueing."""
    claim_owner, new_docs, claim_stats = _claim_news_docs_for_attempt(all_docs)
    print(
        "News: "
        f"{len(all_docs)} fetched, {len(new_docs)} claimed "
        f"(seen {claim_stats['skipped_seen']}, active claims {claim_stats['skipped_claimed']})"
    )

    if not new_docs:
        if claim_stats["skipped_claimed"]:
            print("News ingester: no unclaimed documents; another attempt is already processing them")
        else:
            write_source_status("news", documents_seen=len(all_docs), documents_written=0)
            await safe_volume_commit(volume, "news")
            print("News ingester: no new documents")
        return 0

    ingested_at = datetime.now(timezone.utc).isoformat()
    for doc_data in new_docs:
        doc_data["status"] = "raw"
        metadata = dict(doc_data.get("metadata", {}) or {})
        metadata.setdefault("ingested_at", ingested_at)
        doc_data["metadata"] = metadata

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_dir = get_raw_data_dir() / "news" / date_str
    write_results = await gather_with_limit(
        [_write_news_doc(doc_data, out_dir) for doc_data in new_docs],
        max_concurrent=_raw_write_concurrency(),
    )
    written_docs = [doc for doc in write_results if isinstance(doc, dict)]
    raw_write_failures = len(new_docs) - len(written_docs)
    written_ids = {str(doc["id"]) for doc in written_docs if str(doc.get("id", "") or "")}
    failed_ids = {str(doc["id"]) for doc in new_docs if str(doc.get("id", "") or "")} - written_ids

    if failed_ids:
        _finalize_news_claims(claim_owner, release_ids=failed_ids)

    if not await safe_volume_commit(volume, "news"):
        print("News ingester: raw documents were written but commit failed before classification enqueue")
        return 0

    if not written_docs:
        print(f"News ingester incomplete: 0 documents saved to {out_dir} ({raw_write_failures} raw write failures)")
        return 0

    enqueue_result = await _enqueue_news_docs_for_classification(written_docs)
    if enqueue_result.get("state") != "enqueued":
        print(
            "News ingester incomplete: classification enqueue did not finish; "
            "claims will expire for retry"
        )
        return 0

    _finalize_news_claims(claim_owner, completed_ids=written_ids)
    write_source_status(
        "news",
        documents_seen=len(all_docs),
        documents_written=len(written_docs),
        metadata={
            "classification_queue": enqueue_result,
            "raw_write_failures": raw_write_failures,
            "new_documents": len(new_docs),
        },
    )
    await safe_volume_commit(volume, "news")

    failure_suffix = f" ({raw_write_failures} raw write failures)" if raw_write_failures else ""
    print(f"News ingester complete: {len(written_docs)} documents saved to {out_dir}{failure_suffix}")
    return len(written_docs)


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    schedule=modal.Period(minutes=30),
    timeout=120,
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0),
)
async def news_ingester():
    """Ingest Chicago news from RSS feeds and NewsAPI with fallback chains."""
    all_docs: list[dict] = []

    # RSS with fallback: direct RSS → Google News RSS → cache
    chain = FallbackChain("news", "rss_feeds", cache_ttl_hours=24)
    rss_docs = await chain.execute([
        _fetch_all_rss,
        _fetch_google_news_rss,
    ])
    if rss_docs:
        all_docs.extend(rss_docs)
        print(f"RSS: {len(rss_docs)} articles")

    # NewsAPI (separate, no fallback needed — RSS is the fallback)
    api_key = os.environ.get("NEWSAPI_KEY", "")
    try:
        api_docs = await _fetch_newsapi(api_key)
        all_docs.extend(api_docs)
        print(f"NewsAPI: {len(api_docs)} articles")
    except Exception as e:
        print(f"NewsAPI error: {e}")

    return await _persist_news_docs(all_docs)
