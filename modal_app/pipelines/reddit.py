"""Reddit ingester — monitors Chicago subreddits for business/regulation discussions.

Cadence: Hourly
Sources: r/chicago, r/chicagofood, r/ChicagoNWside, r/SouthSideChicago
Pattern: async + FallbackChain (asyncpraw → reddit JSON → cache) + detect_neighborhood
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import Document, SourceType, REDDIT_SUBREDDITS, detect_neighborhood, gather_with_limit
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
            subreddit = await reddit.subreddit(sub_name)
            seen_ids: set[str] = set()

            # Get hot + new posts
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

                    all_docs.append({
                        "id": doc_id,
                        "source": SourceType.REDDIT.value,
                        "title": submission.title,
                        "content": submission.selftext[:3000] if submission.selftext else submission.title,
                        "url": f"https://reddit.com{submission.permalink}",
                        "timestamp": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
                        "metadata": {
                            "subreddit": sub_name,
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                            "upvote_ratio": submission.upvote_ratio,
                            "flair": submission.link_flair_text or "",
                            "author": str(submission.author) if submission.author else "[deleted]",
                        },
                        "geo": {"neighborhood": neighborhood} if neighborhood else {},
                    })

            print(f"r/{sub_name}: found {sum(1 for d in all_docs if d.get('metadata', {}).get('subreddit') == sub_name)} relevant posts")

        except Exception as e:
            print(f"r/{sub_name} error: {e}")

    await reddit.close()
    return all_docs


async def _fetch_via_json(sub_name: str) -> list[dict]:
    """Fetch from reddit.com JSON API (no auth required)."""
    docs = []
    async with httpx.AsyncClient(timeout=15, headers={
        "User-Agent": "Mozilla/5.0 (compatible; Alethia/0.1; educational project)"
    }) as client:
        resp = await client.get(f"https://www.reddit.com/r/{sub_name}/hot.json", params={"limit": 50})
        if resp.status_code != 200:
            print(f"Reddit JSON [{sub_name}]: HTTP {resp.status_code}")
            return docs

        for child in resp.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            text = f"{post.get('title', '')}\n\n{post.get('selftext', '')}"
            if not _is_relevant(text):
                continue

            neighborhood = detect_neighborhood(text)

            docs.append({
                "id": f"reddit-{post.get('id', '')}",
                "source": SourceType.REDDIT.value,
                "title": post.get("title", ""),
                "content": (post.get("selftext", "") or post.get("title", ""))[:3000],
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "timestamp": datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc).isoformat(),
                "metadata": {
                    "subreddit": sub_name,
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                    "flair": post.get("link_flair_text", ""),
                    "author": post.get("author", "[deleted]"),
                },
                "geo": {"neighborhood": neighborhood} if neighborhood else {},
            })
    return docs


async def _fetch_all_json() -> list[dict]:
    """Fallback: fetch all subreddits via JSON API in parallel."""
    coros = [_fetch_via_json(sub) for sub in REDDIT_SUBREDDITS]
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

    # FallbackChain: asyncpraw OAuth → reddit.com JSON → cache
    chain = FallbackChain("reddit", "all_subs")
    all_docs = await chain.execute([
        lambda: _fetch_via_asyncpraw(client_id, client_secret),
        _fetch_all_json,
    ])

    if not all_docs:
        print("Reddit ingester: no data from any source")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_dir = Path(RAW_DATA_PATH) / "reddit" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_data in all_docs:
        doc = Document(**{k: v for k, v in doc_data.items() if k != "timestamp"})
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))

    # Push to classification queue
    from modal_app.classify import doc_queue
    for doc_data in all_docs:
        try:
            doc_queue.put(doc_data)
        except Exception:
            pass

    await volume.commit.aio()
    print(f"Reddit ingester complete: {len(all_docs)} documents saved to {out_dir}")
    return len(all_docs)
