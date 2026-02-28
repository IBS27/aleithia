"""News ingester — pulls local Chicago news from RSS feeds and NewsAPI.

Cadence: Every 30 minutes
Sources: RSS (Block Club Chicago, Chicago Tribune, Crain's), NewsAPI
Pattern: async + FallbackChain + gather_with_limit + detect_neighborhood
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx
import modal

from modal_app.common import Document, SourceType, detect_neighborhood, gather_with_limit
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

# RSS feeds for Chicago local news
RSS_FEEDS = [
    ("Block Club Chicago", "https://blockclubchicago.org/feed/"),
    ("Chicago Tribune Local", "https://www.chicagotribune.com/arcio/rss/category/news/local/"),
    ("Crain's Chicago Business", "https://www.chicagobusiness.com/section/news.rss"),
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


async def _fetch_single_rss(feed_name: str, feed_url: str) -> list[dict]:
    """Parse a single RSS feed and return serializable dicts."""
    docs = []
    async with httpx.AsyncClient(timeout=15) as client:
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
            "id": f"news-rss-{hash(entry.get('link', title))}",
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
        async with httpx.AsyncClient(timeout=15) as client:
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
                    "id": f"news-api-{hash(article.get('url', ''))}",
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
    chain = FallbackChain("news", "rss_feeds")
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

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_dir = Path(RAW_DATA_PATH) / "news" / date_str
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
    print(f"News ingester complete: {len(all_docs)} documents saved to {out_dir}")
    return len(all_docs)
