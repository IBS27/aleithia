import re

from modal_app.pipelines.reddit import reddit_docs_are_weak


def _doc(title: str, content: str, subreddit: str = "AskChicago") -> dict:
    stable_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:24] or "post"
    return {
        "id": f"reddit-{stable_id}",
        "title": title,
        "content": content,
        "timestamp": "2026-03-01T00:00:00+00:00",
        "metadata": {"subreddit": subreddit, "score": 8, "num_comments": 6},
        "geo": {"neighborhood": "Loop"},
    }


def test_reddit_docs_are_weak_for_small_or_low_relevance_sets() -> None:
    docs = [
        _doc("Random Chicago post", "nothing about business here", subreddit="chicago"),
        _doc("Another post", "still not very relevant"),
    ]

    assert reddit_docs_are_weak(docs, business_type="fitness center", neighborhood="Loop", min_count=3, median_threshold=2.0)


def test_reddit_docs_are_not_weak_when_relevance_is_sufficient() -> None:
    docs = [
        _doc("Best fitness center in Loop?", "Looking for a gym near Loop in Chicago"),
        _doc("Health club recommendations", "Chicago Loop gym and workout options"),
        _doc("Loop gym memberships", "Any fitness center with classes in Chicago?"),
    ]

    assert not reddit_docs_are_weak(docs, business_type="fitness center", neighborhood="Loop", min_count=3, median_threshold=2.0)
