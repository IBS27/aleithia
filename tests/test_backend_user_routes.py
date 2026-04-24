from __future__ import annotations

from tests.backend_test_helpers import make_user_client


def test_backend_user_profile_and_settings_alias_share_storage(tmp_path) -> None:
    client = make_user_client(tmp_path)
    headers = {"x-user-id": "user-123"}

    create = client.put(
        "/api/data/user/profile",
        headers=headers,
        json={
            "business_type": "Cafe",
            "neighborhood": "Loop",
            "risk_tolerance": "high",
        },
    )
    assert create.status_code == 200
    created = create.json()
    assert created["clerk_user_id"] == "user-123"
    assert created["business_type"] == "Cafe"
    assert created["neighborhood"] == "Loop"
    assert created["risk_tolerance"] == "high"

    alias = client.get("/api/data/user/settings", headers=headers)
    assert alias.status_code == 200
    assert alias.json() == created

    update_via_alias = client.put(
        "/api/data/user/settings",
        headers=headers,
        json={
            "business_type": "Bakery",
            "neighborhood": "West Loop",
        },
    )
    assert update_via_alias.status_code == 200
    updated = update_via_alias.json()
    assert updated["clerk_user_id"] == "user-123"
    assert updated["business_type"] == "Bakery"
    assert updated["neighborhood"] == "West Loop"
    assert updated["risk_tolerance"] == "high"

    profile = client.get("/api/data/user/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json() == updated


def test_backend_user_queries_are_scoped_by_user_id(tmp_path) -> None:
    client = make_user_client(tmp_path)
    user_headers = {"x-user-id": "user-a"}
    other_headers = {"x-user-id": "user-b"}

    first = client.post(
        "/api/data/user/queries",
        headers=user_headers,
        json={
            "query_text": "Coffee demand in Loop",
            "business_type": "Cafe",
            "neighborhood": "Loop",
        },
    )
    assert first.status_code == 200
    assert first.json()["clerk_user_id"] == "user-a"

    second = client.post(
        "/api/data/user/queries",
        headers=user_headers,
        json={
            "query_text": "Bakery permits in West Loop",
            "business_type": "Bakery",
            "neighborhood": "West Loop",
        },
    )
    assert second.status_code == 200

    third = client.post(
        "/api/data/user/queries",
        headers=other_headers,
        json={
            "query_text": "Salon outlook in Logan Square",
            "business_type": "Salon",
            "neighborhood": "Logan Square",
        },
    )
    assert third.status_code == 200

    user_queries = client.get("/api/data/user/queries?limit=5", headers=user_headers)
    assert user_queries.status_code == 200
    assert [query["query_text"] for query in user_queries.json()] == [
        "Bakery permits in West Loop",
        "Coffee demand in Loop",
    ]

    other_queries = client.get("/api/data/user/queries?limit=5", headers=other_headers)
    assert other_queries.status_code == 200
    assert [query["query_text"] for query in other_queries.json()] == [
        "Salon outlook in Logan Square",
    ]
