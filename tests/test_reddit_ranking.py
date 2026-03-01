from modal_app.pipelines.reddit import _score_reddit_relevance, merge_rank_reddit_docs, rank_reddit_docs


def test_score_reddit_relevance_boosts_local_signal() -> None:
    doc = {
        "id": "reddit-1",
        "title": "Best fitness center in Loop",
        "content": "Looking for a gym in Chicago Loop with good classes",
        "timestamp": "2026-03-01T00:00:00+00:00",
        "metadata": {"subreddit": "AskChicago", "score": 10, "num_comments": 12},
        "geo": {"neighborhood": "Loop"},
    }

    score = _score_reddit_relevance(doc, business_type="fitness center", neighborhood="Loop")
    assert score >= 10


def test_rank_reddit_docs_dedups_and_prefers_higher_relevance() -> None:
    docs = [
        {
            "id": "reddit-dup",
            "title": "Chicago post",
            "content": "general content",
            "timestamp": "2026-02-27T00:00:00+00:00",
            "metadata": {"subreddit": "chicago", "score": 1, "num_comments": 0},
            "geo": {},
        },
        {
            "id": "reddit-dup",
            "title": "Fitness center in Loop",
            "content": "best gym in chicago loop",
            "timestamp": "2026-03-01T00:00:00+00:00",
            "metadata": {"subreddit": "AskChicago", "score": 9, "num_comments": 4},
            "geo": {"neighborhood": "Loop"},
        },
    ]

    ranked = rank_reddit_docs(docs, business_type="fitness center", neighborhood="Loop", min_score=0)
    assert len(ranked) == 1
    assert ranked[0]["id"] == "reddit-dup"
    assert ranked[0]["metadata"]["relevance_score"] >= 6


def test_merge_rank_reddit_docs_combines_and_sorts() -> None:
    local_docs = [
        {
            "id": "reddit-a",
            "title": "Generic Loop update",
            "content": "chicago loop event",
            "timestamp": "2026-03-01T00:00:00+00:00",
            "metadata": {"subreddit": "chicago", "score": 2, "num_comments": 1},
            "geo": {"neighborhood": "Loop"},
        }
    ]
    fallback_docs = [
        {
            "id": "reddit-b",
            "title": "Best gyms in Loop",
            "content": "fitness center and health club suggestions",
            "timestamp": "2026-03-01T00:00:00+00:00",
            "metadata": {"subreddit": "AskChicago", "score": 5, "num_comments": 4},
            "geo": {"neighborhood": "Loop"},
        }
    ]

    merged = merge_rank_reddit_docs(local_docs, fallback_docs, business_type="fitness center", neighborhood="Loop", min_score=0)
    assert len(merged) == 2
    assert merged[0]["id"] == "reddit-b"
