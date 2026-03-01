import re

from modal_app.pipelines.reddit import RedditRetrievalService, _build_fallback_queries


def test_build_fallback_queries_shape_and_order() -> None:
    queries = _build_fallback_queries("fitness center", "Loop")

    assert len(queries) == 3
    assert "subreddit:AskChicago" in queries[0]
    assert "subreddit:chicago" in queries[0]
    assert "Loop" in queries[0]
    assert "subreddit:AskChicago" in queries[1]
    assert re.search(r"\(.*fitness center.*\)", queries[2], re.IGNORECASE)


def test_normalize_rss_entry_filters_meta_and_subreddit_home_links() -> None:
    service = RedditRetrievalService()

    meta_entry = {
        "title": "AskChicago",
        "id": "t5_2zham",
        "link": "https://www.reddit.com/r/AskChicago/",
        "summary": "<p>meta</p>",
    }
    assert service._normalize_rss_entry(
        meta_entry,
        default_subreddit="AskChicago",
        retrieval_method="rss_search",
        ingestion_mode="scheduled",
    ) is None

    post_entry = {
        "title": "Best gyms in Loop?",
        "id": "t3_abc123",
        "link": "https://www.reddit.com/r/AskChicago/comments/abc123/best_gyms_in_loop/",
        "summary": "<p>Looking for a fitness center in Chicago Loop</p>",
        "author": "example_user",
    }
    normalized = service._normalize_rss_entry(
        post_entry,
        default_subreddit="AskChicago",
        retrieval_method="rss_search",
        ingestion_mode="query_fallback",
        query_signature="fitness_loop",
    )

    assert normalized is not None
    assert normalized["id"] == "reddit-abc123"
    assert normalized["metadata"]["subreddit"] == "AskChicago"
    assert normalized["metadata"]["retrieval_method"] == "rss_search"
    assert normalized["metadata"]["ingestion_mode"] == "query_fallback"
    assert normalized["metadata"]["query_signature"] == "fitness_loop"
