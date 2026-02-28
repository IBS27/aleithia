"""Reddit ingester — monitors Chicago subreddits for business/regulation discussions.

Cadence: Hourly
Sources: r/chicago, r/chicagofood, r/ChicagoNWside, r/SouthSideChicago
Pattern: async + FallbackChain (asyncpraw → reddit JSON → cache) + detect_neighborhood
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import Document, SourceType, REDDIT_SUBREDDITS, detect_neighborhood, gather_with_limit, safe_queue_push, safe_volume_commit
from modal_app.dedup import SeenSet
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, reddit_image, RAW_DATA_PATH

# Keywords that indicate business/regulation relevance
BUSINESS_KEYWORDS = [
    "permit", "license", "zoning", "regulation", "inspection",
    "restaurant", "bar", "cafe", "shop", "store", "business",
    "opening", "closing", "new", "rent", "lease", "landlord",
    "tax", "fine", "violation", "health department", "alderman",
    "city council", "ordinance", "small business",
]


def _is_relevant(text: str) -> bool:
    """Check if post/comment text contains business-relevant keywords."""
    lower = text.lower()
    return any(kw in lower for kw in BUSINESS_KEYWORDS)


async def _fetch_via_asyncpraw(client_id: str, client_secret: str) -> list[dict]:
    """Primary: fetch via asyncpraw OAuth."""
    import asyncpraw

    if not client_id or not client_secret:
        raise ValueError("Reddit credentials not set")

    reddit = asyncpraw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="alethia:v0.1 (by /u/alethia_bot)",
    )

    all_docs: list[dict] = []

    for sub_name in REDDIT_SUBREDDITS:
        try:
            async def _fetch_subreddit(name: str) -> list[dict]:
                sub_docs = []
                subreddit = await reddit.subreddit(name)
                seen_ids: set[str] = set()

                for listing_fn in [subreddit.hot, subreddit.new]:
                    limit = 25 if listing_fn == subreddit.hot else 15
                    async for submission in listing_fn(limit=limit):
                        text = f"{submission.title}\n\n{submission.selftext}"
                        if not _is_relevant(text):
                            continue

                        doc_id = f"reddit-{submission.id}"
                        if doc_id in seen_ids:
                            continue
                        seen_ids.add(doc_id)

                        neighborhood = detect_neighborhood(text)

                        sub_docs.append({
                            "id": doc_id,
                            "source": SourceType.REDDIT.value,
                            "title": submission.title,
                            "content": submission.selftext[:3000] if submission.selftext else submission.title,
                            "url": f"https://reddit.com{submission.permalink}",
                            "timestamp": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
                            "metadata": {
                                "subreddit": name,
                                "score": submission.score,
                                "num_comments": submission.num_comments,
                                "upvote_ratio": submission.upvote_ratio,
                                "flair": submission.link_flair_text or "",
                                "author": str(submission.author) if submission.author else "[deleted]",
                            },
                            "geo": {"neighborhood": neighborhood} if neighborhood else {},
                        })
                return sub_docs

            sub_docs = await asyncio.wait_for(_fetch_subreddit(sub_name), timeout=30)
            all_docs.extend(sub_docs)
            print(f"r/{sub_name}: found {len(sub_docs)} relevant posts")

        except asyncio.TimeoutError:
            print(f"r/{sub_name}: timed out after 30s, skipping")
        except Exception as e:
            print(f"r/{sub_name} error: {e}")

    await reddit.close()
    return all_docs


async def _fetch_via_rss(sub_name: str) -> list[dict]:
    """Fetch from Reddit RSS feed (no auth, no API key needed)."""
    import feedparser

    docs = []
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (compatible; Alethia/0.1; educational project)"
    }) as client:
        resp = await client.get(f"https://www.reddit.com/r/{sub_name}/hot.rss")
        if resp.status_code != 200:
            print(f"Reddit RSS [{sub_name}]: HTTP {resp.status_code}")
            return docs

    feed = feedparser.parse(resp.text)
    for entry in feed.entries:
        title = entry.get("title", "")
        # RSS content is HTML — extract text
        content_html = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
        # Strip HTML tags for plain text
        import re
        content_text = re.sub(r"<[^>]+>", " ", content_html)
        content_text = re.sub(r"\s+", " ", content_text).strip()

        text = f"{title}\n\n{content_text}"
        if not _is_relevant(text):
            continue

        # Parse timestamp
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            from time import mktime
            ts = datetime.fromtimestamp(mktime(published), tz=timezone.utc).isoformat()
        else:
            ts = datetime.now(timezone.utc).isoformat()

        # Extract reddit post ID from link
        link = entry.get("link", "")
        post_id = link.rstrip("/").split("/")[-1] if "/comments/" in link else entry.get("id", "")

        neighborhood = detect_neighborhood(text)

        docs.append({
            "id": f"reddit-{post_id}",
            "source": SourceType.REDDIT.value,
            "title": title,
            "content": content_text[:3000] or title,
            "url": link,
            "timestamp": ts,
            "metadata": {
                "subreddit": sub_name,
                "score": 0,
                "num_comments": 0,
                "upvote_ratio": 0,
                "flair": entry.get("category", ""),
                "author": entry.get("author", entry.get("author_detail", {}).get("name", "[unknown]")),
            },
            "geo": {"neighborhood": neighborhood} if neighborhood else {},
        })

    print(f"Reddit RSS [{sub_name}]: {len(docs)} relevant posts")
    return docs


async def _fetch_all_rss() -> list[dict]:
    """Fallback: fetch all subreddits via RSS feeds in parallel."""
    coros = [_fetch_via_rss(sub) for sub in REDDIT_SUBREDDITS]
    results = await gather_with_limit(coros, max_concurrent=4)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


@app.function(
    image=reddit_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    schedule=modal.Period(hours=1),
    timeout=180,
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0),
)
async def reddit_ingester():
    """Ingest relevant posts from Chicago subreddits with fallback chain."""
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")

    # FallbackChain: asyncpraw OAuth → RSS feeds → cache
    chain = FallbackChain("reddit", "all_subs", cache_ttl_hours=48)
    all_docs = await chain.execute([
        lambda: _fetch_via_asyncpraw(client_id, client_secret),
        _fetch_all_rss,
    ])

    if not all_docs:
        print("Reddit ingester: no data from any source")
        return 0

    # Dedup: skip already-seen documents
    seen = SeenSet("reddit")
    new_docs = [d for d in all_docs if not seen.contains(d["id"])]
    print(f"Reddit: {len(all_docs)} fetched, {len(new_docs)} new (deduped {len(all_docs) - len(new_docs)})")

    if not new_docs:
        seen.save()
        await safe_volume_commit(volume, "reddit")
        print("Reddit ingester: no new documents")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_dir = Path(RAW_DATA_PATH) / "reddit" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_data in new_docs:
        doc_data["status"] = "raw"
        doc = Document(**{k: v for k, v in doc_data.items() if k != "timestamp"})
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))
        seen.add(doc_data["id"])

    # Push to classification queue
    from modal_app.classify import doc_queue
    await safe_queue_push(doc_queue, new_docs, "reddit")

    seen.save()
    await safe_volume_commit(volume, "reddit")
    print(f"Reddit ingester complete: {len(new_docs)} documents saved to {out_dir}")
    return len(new_docs)
