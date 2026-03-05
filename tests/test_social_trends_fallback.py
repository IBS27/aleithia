from modal_app import web


def test_parse_social_trends_response_handles_invalid_json() -> None:
    parsed = web._parse_social_trends_response("not-json")
    assert parsed == []


def test_parse_social_trends_response_supports_wrapper_and_alias_fields() -> None:
    raw = (
        '{"insights":[{"name":"Coffee demand shift","description":"Posts show increased morning demand."},'
        '{"headline":"Lunch crowd growth","summary":"Creators report noon line growth."},'
        '{"title":"Value-seeking behavior","detail":"Users mention deals and budget options."}]}'
    )
    parsed = web._parse_social_trends_response(raw)

    assert len(parsed) == 3
    assert parsed[0]["title"] == "Coffee demand shift"
    assert parsed[0]["detail"] == "Posts show increased morning demand."
    assert parsed[1]["title"] == "Lunch crowd growth"
    assert parsed[1]["detail"] == "Creators report noon line growth."


def test_deterministic_social_fallback_returns_three_trends() -> None:
    ranked_docs = [
        (
            "reddit",
            {
                "id": "r1",
                "title": "Coffee demand near offices",
                "content": "People report strong weekday morning lines around commuter corridors.",
                "metadata": {"score": 8, "num_comments": 2},
                "geo": {"neighborhood": "Loop"},
            },
            0.92,
        ),
        (
            "tiktok",
            {
                "id": "t1",
                "title": "Lunch crowd growth",
                "content": "Short clips show rising noon foot traffic for quick-service food spots.",
                "metadata": {"views_normalized": 42000, "creator": "foodwatch"},
                "geo": {"neighborhood": "Loop"},
            },
            0.86,
        ),
    ]

    trends = web._deterministic_social_fallback_trends(
        ranked_docs=ranked_docs,
        business_type="Coffee Shop",
        neighborhood="Loop",
        count=3,
    )

    assert len(trends) == 3
    for trend in trends:
        assert isinstance(trend.get("title"), str) and trend["title"].strip()
        assert isinstance(trend.get("detail"), str) and trend["detail"].strip()
