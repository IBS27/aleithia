from __future__ import annotations

import asyncio


def test_review_ingester_searches_loop_and_all_configured_neighborhoods(monkeypatch) -> None:
    from modal_app.pipelines import reviews

    google_locations: list[str] = []
    yelp_calls: list[tuple[str, str]] = []

    async def fake_google_location(api_key: str, location: str) -> list[dict]:
        google_locations.append(location)
        return []

    async def fake_yelp_location(api_key: str, location: str, category: str) -> list[dict]:
        yelp_calls.append((location, category))
        return []

    monkeypatch.setattr(reviews, "_fetch_google_location", fake_google_location)
    monkeypatch.setattr(reviews, "_fetch_yelp_location", fake_yelp_location)

    asyncio.run(reviews._fetch_google_places("google-key"))
    asyncio.run(reviews._fetch_yelp("yelp-key"))

    assert "Loop, Chicago, IL" in reviews.SEARCH_NEIGHBORHOODS
    assert google_locations == reviews.SEARCH_NEIGHBORHOODS
    assert {location for location, _category in yelp_calls} == set(reviews.SEARCH_NEIGHBORHOODS)
