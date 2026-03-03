from modal_app import web


def _reddit_doc(doc_id: str, title: str, content: str, score: int = 0, comments: int = 0) -> dict:
    return {
        "id": doc_id,
        "title": title,
        "content": content,
        "timestamp": "2026-03-02T12:00:00+00:00",
        "metadata": {
            "score": score,
            "num_comments": comments,
            "subreddit": "chicago",
        },
        "geo": {"neighborhood": "Loop"},
    }


def _tiktok_doc(doc_id: str, title: str, content: str, views: str) -> dict:
    return {
        "id": doc_id,
        "title": title,
        "content": content,
        "timestamp": "2026-03-02T12:00:00+00:00",
        "metadata": {
            "views": views,
            "views_normalized": web._parse_view_count(views),
            "creator": "localcreator",
        },
        "geo": {"neighborhood": "Loop"},
    }


def test_score_social_doc_prefers_business_relevance() -> None:
    relevant = _reddit_doc(
        "r1",
        "Coffee shop demand in Loop",
        "Customers are asking for more espresso and pastry spots near offices.",
        score=10,
        comments=4,
    )
    irrelevant = _reddit_doc(
        "r2",
        "Baseball discussion",
        "Fans discussing game outcomes and player trades in detail.",
        score=30,
        comments=12,
    )

    relevant_score = web._score_social_doc(relevant, "Coffee Shop", "Loop", "reddit")
    irrelevant_score = web._score_social_doc(irrelevant, "Coffee Shop", "Loop", "reddit")

    assert relevant_score > irrelevant_score


def test_rank_social_docs_is_deterministic_and_balanced() -> None:
    reddit_docs = [
        _reddit_doc("r-high", "Best coffee options in Loop", "Coffee and cafe demand is rising.", score=45, comments=20),
        _reddit_doc("r-low", "Random city note", "General city comment with little business context.", score=3, comments=1),
    ]
    tiktok_docs = [
        _tiktok_doc("t-high", "Loop coffee rush", "Morning commuters line up for coffee shops downtown.", "125K"),
        _tiktok_doc("t-low", "Viral dance", "Entertainment-only clip unrelated to small business.", "10K"),
    ]

    first = web._rank_social_docs_deterministic(
        reddit_docs, tiktok_docs, business_type="Coffee Shop", neighborhood="Loop", max_total=4
    )
    second = web._rank_social_docs_deterministic(
        reddit_docs, tiktok_docs, business_type="Coffee Shop", neighborhood="Loop", max_total=4
    )

    first_ids = [entry[1]["id"] for entry in first]
    second_ids = [entry[1]["id"] for entry in second]
    first_sources = [entry[0] for entry in first[:2]]

    assert first_ids == second_ids
    assert first_ids[0] in {"r-high", "t-high"}
    assert set(first_sources) == {"reddit", "tiktok"}
