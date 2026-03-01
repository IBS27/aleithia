"""Reddit ingestion + query-time fallback for Chicago business intelligence.

Cadence: Hourly ingestion
Primary adapters: asyncpraw listings/search
Fallback adapters: RSS search/hot feeds + cache
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import mktime
from urllib.parse import urlparse

import httpx
import modal

from modal_app.common import (
    REDDIT_SIGNAL_SUBREDDITS,
    REDDIT_SUBREDDITS,
    SourceType,
    build_document,
    detect_neighborhood,
    gather_with_limit,
    reddit_business_terms,
    safe_queue_push,
    safe_volume_commit,
)
from modal_app.dedup import SeenSet
from modal_app.fallback import FallbackChain
from modal_app.volume import RAW_DATA_PATH, app, reddit_image, volume

HOURLY_HOT_LIMIT = 25
HOURLY_NEW_LIMIT = 15
HOURLY_SEARCH_LIMIT = 10
GLOBAL_SEARCH_LIMIT = 25
FALLBACK_TARGET_RESULTS = 5
FALLBACK_PER_ATTEMPT_TIMEOUT_SECONDS = 0.9
FALLBACK_BUDGET_MS = 3000
FALLBACK_MIN_SCORE = 3
INGEST_MIN_SCORE = 2

HOURLY_SEARCH_TERMS = [
    "opening OR closing chicago",
    "permit OR license OR zoning chicago",
    "gym OR fitness OR health club chicago",
]


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return _collapse_whitespace(text)


def _query_signature(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return cleaned[:96] or "q"


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_post_id_from_link(link: str, fallback_id: str = "") -> str:
    parsed = urlparse(link or "")
    path = parsed.path.strip("/")
    if "/comments/" in path:
        parts = path.split("/")
        if "comments" in parts:
            idx = parts.index("comments")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    fallback = str(fallback_id or "").strip()
    if fallback.startswith("t3_"):
        return fallback[3:]
    if fallback:
        return fallback
    return ""


def _is_subreddit_home_link(link: str) -> bool:
    parsed = urlparse(link or "")
    path = parsed.path.strip("/")
    if not path:
        return True
    parts = [p for p in path.split("/") if p]
    # /r/foo or /r/foo/about or /r/foo/new etc. are subreddit pages, not posts.
    if len(parts) >= 2 and parts[0].lower() == "r" and "comments" not in parts:
        return True
    return False


def _is_meta_entry(post_id: str) -> bool:
    return (post_id or "").lower().startswith("t5_")


def _timestamp_to_sort_key(timestamp: object) -> float:
    raw = str(timestamp or "").strip()
    if not raw:
        return 0.0
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _build_business_clause(business_type: str) -> str:
    terms = reddit_business_terms(business_type)
    cleaned_terms = [t.replace('"', "").strip() for t in terms if t]
    escaped = [f'"{t}"' for t in cleaned_terms if t]
    if not escaped:
        escaped = ['"small business"']
    return " OR ".join(escaped[:8])


def _build_scoped_subreddit_clause() -> str:
    scoped = ["AskChicago", "chicago", "chicagofitness", "chicagoapartments"]
    return " OR ".join(f"subreddit:{sub}" for sub in scoped)


def _build_fallback_queries(business_type: str, neighborhood: str) -> list[str]:
    biz_clause = _build_business_clause(business_type)
    nb = _collapse_whitespace(neighborhood)
    nb_clause = f'"{nb}" OR "West Loop" OR "South Loop"' if nb else '"West Loop" OR "South Loop"'
    nb_exact = f'"{nb}" ' if nb else ""
    scoped = _build_scoped_subreddit_clause()

    return [
        f"({biz_clause}) ({nb_clause}) chicago ({scoped})",
        f"({biz_clause}) {nb_exact}chicago subreddit:AskChicago".strip(),
        f"({biz_clause}) chicago",
    ]


def _is_likely_self_promo(text: str) -> bool:
    lower = (text or "").lower()
    promo_markers = [
        "follow me",
        "dm me",
        "book now",
        "discount code",
        "promo code",
        "link in bio",
        "check out my",
    ]
    return any(marker in lower for marker in promo_markers)


def _score_reddit_relevance(doc: dict, business_type: str, neighborhood: str) -> int:
    """Unified relevance score used by ingest filtering and fallback ranking."""
    title = str(doc.get("title", "") or "")
    content = str(doc.get("content", "") or "")
    geo_nb = str((doc.get("geo", {}) or {}).get("neighborhood", "") or "")
    metadata = doc.get("metadata", {}) or {}
    subreddit = str(metadata.get("subreddit", "") or "")

    text = f"{title} {content} {geo_nb}".lower()
    score = 0

    business_norm = _collapse_whitespace((business_type or "").lower()) or "small business"
    if business_norm and business_norm in text:
        score += 4

    terms = reddit_business_terms(business_type)
    if any(term in text for term in terms if term and term != business_norm):
        score += 3

    nb_norm = _collapse_whitespace((neighborhood or "").lower())
    if nb_norm and (nb_norm == geo_nb.lower() or nb_norm in text):
        score += 3

    if "chicago" in text:
        score += 2

    if subreddit.lower() in REDDIT_SIGNAL_SUBREDDITS:
        score += 2

    post_score = _safe_int(metadata.get("score", 0))
    num_comments = _safe_int(metadata.get("num_comments", 0))
    if post_score >= 5 or num_comments >= 3:
        score += 1

    if _is_likely_self_promo(text) and (post_score <= 1 and num_comments <= 1):
        score -= 2

    return max(score, 0)


def rank_reddit_docs(
    docs: list[dict],
    business_type: str,
    neighborhood: str,
    min_score: int = 0,
) -> list[dict]:
    """Score, deduplicate, and rank Reddit documents."""
    best_by_id: dict[str, dict] = {}

    for raw_doc in docs:
        if not isinstance(raw_doc, dict):
            continue

        doc = dict(raw_doc)
        doc_id = str(doc.get("id", "") or "").strip()
        if not doc_id:
            continue

        meta = dict(doc.get("metadata", {}) or {})
        relevance = _score_reddit_relevance(doc, business_type, neighborhood)
        meta["relevance_score"] = relevance
        doc["metadata"] = meta

        if relevance < min_score:
            continue

        prev = best_by_id.get(doc_id)
        if prev is None:
            best_by_id[doc_id] = doc
            continue

        prev_score = _safe_int((prev.get("metadata", {}) or {}).get("relevance_score", 0))
        if relevance > prev_score:
            best_by_id[doc_id] = doc
            continue

        if relevance == prev_score and _timestamp_to_sort_key(doc.get("timestamp")) > _timestamp_to_sort_key(prev.get("timestamp")):
            best_by_id[doc_id] = doc

    ranked = list(best_by_id.values())
    ranked.sort(
        key=lambda d: (
            -_safe_int((d.get("metadata", {}) or {}).get("relevance_score", 0)),
            -_timestamp_to_sort_key(d.get("timestamp")),
        )
    )
    return ranked


def merge_rank_reddit_docs(
    local_docs: list[dict],
    fallback_docs: list[dict],
    business_type: str,
    neighborhood: str,
    min_score: int = 0,
) -> list[dict]:
    return rank_reddit_docs([*local_docs, *fallback_docs], business_type, neighborhood, min_score=min_score)


def reddit_docs_are_weak(
    docs: list[dict],
    business_type: str,
    neighborhood: str,
    min_count: int = 3,
    median_threshold: float = 2.0,
) -> bool:
    if not docs:
        return True

    ranked = rank_reddit_docs(docs, business_type, neighborhood, min_score=0)
    scores = [_safe_int((d.get("metadata", {}) or {}).get("relevance_score", 0)) for d in ranked]
    if len(scores) < min_count:
        return True
    return median(scores) < median_threshold


class RedditRetrievalService:
    """Unified retrieval service for scheduled ingest and query-time fallback."""

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.user_agent = "alethia:v0.2 (by /u/alethia_bot)"

    @classmethod
    def from_env(cls) -> "RedditRetrievalService":
        return cls(
            client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
            client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def normalize_and_score(
        self,
        docs: list[dict],
        business_type: str,
        neighborhood: str,
        min_score: int,
    ) -> list[dict]:
        return rank_reddit_docs(docs, business_type, neighborhood, min_score=min_score)

    async def _normalize_submission(
        self,
        submission,
        subreddit: str,
        retrieval_method: str,
        ingestion_mode: str,
        query_signature: str = "",
    ) -> dict | None:
        title = _collapse_whitespace(str(getattr(submission, "title", "") or ""))
        selftext = _collapse_whitespace(str(getattr(submission, "selftext", "") or ""))
        if not title and not selftext:
            return None

        post_id = str(getattr(submission, "id", "") or "").strip()
        if not post_id:
            return None

        doc_id = f"reddit-{post_id}"
        permalink = str(getattr(submission, "permalink", "") or "")
        url = f"https://reddit.com{permalink}" if permalink.startswith("/") else permalink
        text = f"{title}\n\n{selftext}".strip()
        neighborhood = detect_neighborhood(text)

        doc = {
            "id": doc_id,
            "source": SourceType.REDDIT.value,
            "title": title,
            "content": (selftext or title)[:3000],
            "url": url,
            "timestamp": datetime.fromtimestamp(
                _safe_float(getattr(submission, "created_utc", 0.0)),
                tz=timezone.utc,
            ).isoformat(),
            "metadata": {
                "subreddit": subreddit,
                "score": _safe_int(getattr(submission, "score", 0)),
                "num_comments": _safe_int(getattr(submission, "num_comments", 0)),
                "upvote_ratio": _safe_float(getattr(submission, "upvote_ratio", 0.0)),
                "flair": str(getattr(submission, "link_flair_text", "") or ""),
                "author": str(getattr(submission, "author", "") or "[deleted]"),
                "retrieval_method": retrieval_method,
                "ingestion_mode": ingestion_mode,
            },
            "geo": {"neighborhood": neighborhood} if neighborhood else {},
        }
        if query_signature:
            doc["metadata"]["query_signature"] = query_signature
        return doc

    def _normalize_rss_entry(
        self,
        entry,
        default_subreddit: str,
        retrieval_method: str,
        ingestion_mode: str,
        query_signature: str = "",
    ) -> dict | None:
        title = _collapse_whitespace(str(entry.get("title", "") or ""))
        link = str(entry.get("link", "") or "")

        post_id = _extract_post_id_from_link(link, fallback_id=str(entry.get("id", "") or ""))
        if not post_id or _is_meta_entry(post_id):
            return None
        if _is_subreddit_home_link(link):
            return None

        content_html = ""
        if entry.get("summary"):
            content_html = str(entry.get("summary", "") or "")
        elif entry.get("content"):
            content = entry.get("content") or []
            if content and isinstance(content, list):
                content_html = str((content[0] or {}).get("value", "") or "")

        content_text = _strip_html(content_html)
        text = f"{title}\n\n{content_text}".strip()
        if not text:
            return None

        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            ts = datetime.fromtimestamp(mktime(published), tz=timezone.utc).isoformat()
        else:
            ts = datetime.now(timezone.utc).isoformat()

        category = entry.get("category_detail") or {}
        label = str(category.get("label", "") or "")
        subreddit = default_subreddit
        if label.lower().startswith("r/"):
            subreddit = label[2:]
        elif entry.get("tags"):
            tags = entry.get("tags") or []
            if tags and isinstance(tags, list):
                term = str((tags[0] or {}).get("term", "") or "")
                if term and not term.startswith("r/"):
                    subreddit = term

        neighborhood = detect_neighborhood(text)
        doc = {
            "id": f"reddit-{post_id}",
            "source": SourceType.REDDIT.value,
            "title": title or f"Reddit post {post_id}",
            "content": (content_text or title)[:3000],
            "url": link,
            "timestamp": ts,
            "metadata": {
                "subreddit": subreddit,
                "score": 0,
                "num_comments": 0,
                "upvote_ratio": 0,
                "flair": str(entry.get("category", "") or ""),
                "author": str(entry.get("author", "") or "[unknown]"),
                "retrieval_method": retrieval_method,
                "ingestion_mode": ingestion_mode,
            },
            "geo": {"neighborhood": neighborhood} if neighborhood else {},
        }
        if query_signature:
            doc["metadata"]["query_signature"] = query_signature
        return doc

    async def _fetch_subreddit_stream(self, subreddit_name: str) -> list[dict]:
        import asyncpraw

        reddit = asyncpraw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
        )
        docs: list[dict] = []
        seen_ids: set[str] = set()
        try:
            subreddit = await reddit.subreddit(subreddit_name)
            for listing_fn in [subreddit.hot, subreddit.new]:
                limit = HOURLY_HOT_LIMIT if listing_fn == subreddit.hot else HOURLY_NEW_LIMIT
                async for submission in listing_fn(limit=limit):
                    doc = await self._normalize_submission(
                        submission,
                        subreddit=subreddit_name,
                        retrieval_method="subreddit_hot_new",
                        ingestion_mode="scheduled",
                    )
                    if not doc:
                        continue
                    if doc["id"] in seen_ids:
                        continue
                    seen_ids.add(doc["id"])
                    docs.append(doc)
        finally:
            await reddit.close()
        return docs

    async def _search_subreddit(self, subreddit_name: str, query: str, limit: int) -> list[dict]:
        import asyncpraw

        reddit = asyncpraw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
        )
        docs: list[dict] = []
        sig = _query_signature(query)
        try:
            subreddit = await reddit.subreddit(subreddit_name)
            async for submission in subreddit.search(query=query, sort="new", time_filter="month", limit=limit):
                doc = await self._normalize_submission(
                    submission,
                    subreddit=subreddit_name,
                    retrieval_method="subreddit_search",
                    ingestion_mode="scheduled",
                    query_signature=sig,
                )
                if doc:
                    docs.append(doc)
        finally:
            await reddit.close()
        return docs

    async def _search_global_asyncpraw(self, query: str, limit: int, ingestion_mode: str) -> list[dict]:
        if not self.has_credentials:
            return []

        import asyncpraw

        reddit = asyncpraw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
        )
        docs: list[dict] = []
        sig = _query_signature(query)
        try:
            subreddit = await reddit.subreddit("all")
            async for submission in subreddit.search(query=query, sort="relevance", time_filter="year", limit=limit):
                sub_name = ""
                try:
                    sub_name = str(getattr(getattr(submission, "subreddit", None), "display_name", "") or "")
                except Exception:
                    sub_name = ""
                doc = await self._normalize_submission(
                    submission,
                    subreddit=sub_name,
                    retrieval_method="subreddit_search",
                    ingestion_mode=ingestion_mode,
                    query_signature=sig,
                )
                if doc:
                    docs.append(doc)
        finally:
            await reddit.close()
        return docs

    async def _fetch_subreddit_rss(self, subreddit_name: str) -> list[dict]:
        import feedparser

        headers = {"User-Agent": "Mozilla/5.0 (compatible; Alethia/0.2)"}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = await client.get(f"https://www.reddit.com/r/{subreddit_name}/hot.rss")
            if resp.status_code != 200:
                print(f"Reddit RSS [{subreddit_name}]: HTTP {resp.status_code}")
                return []

        parsed = feedparser.parse(resp.text)
        docs: list[dict] = []
        for entry in parsed.entries:
            doc = self._normalize_rss_entry(
                entry,
                default_subreddit=subreddit_name,
                retrieval_method="rss_search",
                ingestion_mode="scheduled",
            )
            if doc:
                docs.append(doc)
        return docs

    async def _search_rss(self, query: str, timeout_seconds: float, ingestion_mode: str) -> list[dict]:
        import feedparser

        headers = {"User-Agent": "Mozilla/5.0 (compatible; Alethia/0.2)"}
        params = {
            "q": query,
            "sort": "relevance",
            "t": "year",
            "type": "link",
        }
        timeout = max(0.2, timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = await client.get("https://www.reddit.com/search.rss", params=params)
            if resp.status_code == 429:
                raise RuntimeError("rate_limited")
            if resp.status_code != 200:
                raise RuntimeError(f"rss_http_{resp.status_code}")

        parsed = feedparser.parse(resp.text)
        sig = _query_signature(query)
        docs: list[dict] = []
        for entry in parsed.entries:
            doc = self._normalize_rss_entry(
                entry,
                default_subreddit="",
                retrieval_method="rss_search",
                ingestion_mode=ingestion_mode,
                query_signature=sig,
            )
            if doc:
                docs.append(doc)
        return docs

    async def _search_rss_with_retry(self, query: str, timeout_seconds: float, ingestion_mode: str) -> list[dict]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await self._search_rss(query, timeout_seconds=timeout_seconds, ingestion_mode=ingestion_mode)
            except RuntimeError as exc:
                last_error = exc
                if str(exc) != "rate_limited" or attempt == 1:
                    break
                print(
                    "rate_limit_events",
                    {
                        "source": "reddit_rss_search",
                        "query_signature": _query_signature(query),
                        "attempt": attempt + 1,
                    },
                )
                await asyncio.sleep(random.uniform(0.05, 0.2))
            except Exception as exc:
                last_error = exc
                break
        if last_error:
            print(f"Reddit RSS search failed for '{query}': {last_error}")
        return []

    async def fetch_hourly_candidates(self) -> list[dict]:
        """Primary hourly adapter: asyncpraw subreddit streams + targeted subreddit search."""
        if not self.has_credentials:
            raise ValueError("Reddit credentials not set")

        stream_coros = [self._fetch_subreddit_stream(sub) for sub in REDDIT_SUBREDDITS]
        stream_results = await gather_with_limit(stream_coros, max_concurrent=4)

        search_coros = [
            self._search_subreddit(sub, term, HOURLY_SEARCH_LIMIT)
            for sub in REDDIT_SUBREDDITS
            for term in HOURLY_SEARCH_TERMS
        ]
        search_results = await gather_with_limit(search_coros, max_concurrent=6)

        docs: list[dict] = []
        for result in [*stream_results, *search_results]:
            if result:
                docs.extend(result)

        ranked = self.normalize_and_score(docs, business_type="small business", neighborhood="", min_score=INGEST_MIN_SCORE)
        print(f"Reddit asyncpraw: {len(docs)} raw -> {len(ranked)} kept")
        return ranked

    async def fetch_hourly_candidates_via_rss(self) -> list[dict]:
        """Secondary hourly adapter: subreddit RSS + global RSS search."""
        sub_coros = [self._fetch_subreddit_rss(sub) for sub in REDDIT_SUBREDDITS]
        scoped_clause = " OR ".join(f"subreddit:{sub}" for sub in REDDIT_SUBREDDITS)
        search_coros = [
            self._search_rss_with_retry(f"({term}) ({scoped_clause})", timeout_seconds=4.0, ingestion_mode="scheduled")
            for term in HOURLY_SEARCH_TERMS
        ]

        results = await gather_with_limit([*sub_coros, *search_coros], max_concurrent=5)
        docs: list[dict] = []
        for result in results:
            if result:
                docs.extend(result)

        ranked = self.normalize_and_score(docs, business_type="small business", neighborhood="", min_score=INGEST_MIN_SCORE)
        print(f"Reddit RSS: {len(docs)} raw -> {len(ranked)} kept")
        return ranked

    async def _search_query_with_adapters(self, query: str, timeout_seconds: float) -> list[dict]:
        docs: list[dict] = []

        if self.has_credentials:
            try:
                docs = await asyncio.wait_for(
                    self._search_global_asyncpraw(query, limit=GLOBAL_SEARCH_LIMIT, ingestion_mode="query_fallback"),
                    timeout=max(0.2, timeout_seconds),
                )
            except Exception as exc:
                print(f"Reddit asyncpraw fallback search failed for '{query}': {exc}")

        if docs:
            return docs

        return await self._search_rss_with_retry(query, timeout_seconds=timeout_seconds, ingestion_mode="query_fallback")

    async def _execute_fallback_queries(self, queries: list[str], business_type: str, neighborhood: str, budget_ms: int) -> list[dict]:
        start = time.monotonic()
        combined: list[dict] = []

        for query in queries:
            elapsed_ms = (time.monotonic() - start) * 1000
            remaining_seconds = max((budget_ms - elapsed_ms) / 1000.0, 0.0)
            if remaining_seconds <= 0.2:
                break

            timeout_seconds = min(FALLBACK_PER_ATTEMPT_TIMEOUT_SECONDS, max(0.25, remaining_seconds - 0.05))
            attempt_docs = await self._search_query_with_adapters(query, timeout_seconds=timeout_seconds)
            if not attempt_docs:
                continue

            combined = self.normalize_and_score(
                [*combined, *attempt_docs],
                business_type=business_type,
                neighborhood=neighborhood,
                min_score=FALLBACK_MIN_SCORE,
            )

            if len(combined) >= FALLBACK_TARGET_RESULTS:
                break

        return combined

    async def fallback_search(self, business_type: str, neighborhood: str, budget_ms: int = FALLBACK_BUDGET_MS) -> list[dict]:
        """Query-time fallback search with bounded latency and cached safety net."""
        queries = _build_fallback_queries(business_type, neighborhood)
        cache_key = _query_signature(f"{business_type}|{neighborhood}|fallback")
        chain = FallbackChain("reddit", f"query_fallback_{cache_key}", cache_ttl_hours=24)

        async def _live_search() -> list[dict]:
            return await self._execute_fallback_queries(
                queries=queries,
                business_type=business_type,
                neighborhood=neighborhood,
                budget_ms=budget_ms,
            )

        docs = await chain.execute([_live_search])
        if not docs:
            return []

        ranked = self.normalize_and_score(
            docs,
            business_type=business_type,
            neighborhood=neighborhood,
            min_score=FALLBACK_MIN_SCORE,
        )
        return ranked[:20]


async def search_reddit_fallback_runtime(
    business_type: str,
    neighborhood: str,
    budget_ms: int = FALLBACK_BUDGET_MS,
) -> list[dict]:
    service = RedditRetrievalService.from_env()
    return await service.fallback_search(business_type=business_type, neighborhood=neighborhood, budget_ms=budget_ms)


async def _persist_reddit_docs(docs: list[dict], ingestion_mode: str) -> int:
    if not docs:
        return 0

    seen = SeenSet("reddit")
    new_docs: list[dict] = []

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        doc_id = str(doc.get("id", "") or "").strip()
        if not doc_id or seen.contains(doc_id):
            continue

        normalized = dict(doc)
        normalized["status"] = "raw"
        metadata = dict(normalized.get("metadata", {}) or {})
        metadata.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
        metadata["ingestion_mode"] = ingestion_mode
        normalized["metadata"] = metadata
        new_docs.append(normalized)
        seen.add(doc_id)

    print(f"Reddit persist [{ingestion_mode}]: {len(docs)} received, {len(new_docs)} new")
    if not new_docs:
        seen.save()
        await safe_volume_commit(volume, "reddit")
        return 0

    suffix = "_fallback" if ingestion_mode == "query_fallback" else ""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M") + suffix
    out_dir = Path(RAW_DATA_PATH) / "reddit" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, doc_data in enumerate(new_docs):
        doc = build_document(doc_data)
        out_path = out_dir / f"{doc.id}.json"
        out_path.write_text(doc.model_dump_json(indent=2))
        if i < 2:
            print(
                "Reddit persist sample:",
                {
                    "id": doc.id,
                    "score": doc.metadata.get("relevance_score", 0),
                    "method": doc.metadata.get("retrieval_method", ""),
                    "mode": doc.metadata.get("ingestion_mode", ""),
                },
            )

    from modal_app.classify import doc_queue

    await safe_queue_push(doc_queue, new_docs, f"reddit-{ingestion_mode}")
    seen.save()
    await safe_volume_commit(volume, "reddit")
    print(f"Reddit persist [{ingestion_mode}] complete: {len(new_docs)} saved to {out_dir}")
    return len(new_docs)


@app.function(
    image=reddit_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=120,
)
async def persist_reddit_fallback_batch(docs: list[dict]) -> int:
    """Persist query-time fallback Reddit hits into normal raw->queue flow."""
    return await _persist_reddit_docs(docs, ingestion_mode="query_fallback")


@app.function(
    image=reddit_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    schedule=modal.Period(hours=1),
    timeout=180,
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0),
)
async def reddit_ingester() -> int:
    """Ingest relevant Reddit posts with adapter fallback and cache safety."""
    service = RedditRetrievalService.from_env()

    # Fallback chain order: asyncpraw -> RSS -> cache
    chain = FallbackChain("reddit", "hourly_candidates_v2", cache_ttl_hours=48)
    all_docs = await chain.execute([
        service.fetch_hourly_candidates,
        service.fetch_hourly_candidates_via_rss,
    ])

    if not all_docs:
        print("Reddit ingester: no data from any source")
        return 0

    return await _persist_reddit_docs(all_docs, ingestion_mode="scheduled")
