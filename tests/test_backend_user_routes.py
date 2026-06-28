from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from tests.backend_test_helpers import make_user_client


def test_backend_user_profile_routes_use_local_user_id(tmp_path) -> None:
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
    assert created["user_id"] == "user-123"
    assert created["business_type"] == "Cafe"
    assert created["neighborhood"] == "Loop"
    assert created["risk_tolerance"] == "high"

    update = client.put(
        "/api/data/user/profile",
        headers=headers,
        json={
            "business_type": "Bakery",
            "neighborhood": "West Loop",
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["user_id"] == "user-123"
    assert updated["business_type"] == "Bakery"
    assert updated["neighborhood"] == "West Loop"
    assert updated["risk_tolerance"] == "high"

    profile = client.get("/api/data/user/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json() == updated

    old_alias = client.get("/api/data/user/settings", headers=headers)
    assert old_alias.status_code == 404


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
    assert first.json()["user_id"] == "user-a"

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


def test_init_db_migrates_legacy_clerk_user_id_columns(tmp_path, monkeypatch) -> None:
    import database

    db_path = tmp_path / "legacy-user-data.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE user_profiles ("
                "clerk_user_id VARCHAR(255) PRIMARY KEY, "
                "business_type VARCHAR(255), "
                "neighborhood VARCHAR(255), "
                "risk_tolerance VARCHAR(50) NOT NULL, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE query_results ("
                "id INTEGER PRIMARY KEY, "
                "clerk_user_id VARCHAR(255) NOT NULL, "
                "business_type VARCHAR(255) NOT NULL, "
                "neighborhood VARCHAR(255) NOT NULL, "
                "query_text VARCHAR(1000) NOT NULL, "
                "result_summary VARCHAR(5000), "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO user_profiles "
                "(clerk_user_id, business_type, neighborhood, risk_tolerance, created_at, updated_at) "
                "VALUES ('user-123', 'Cafe', 'Loop', 'medium', '2026-06-01 00:00:00', '2026-06-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO query_results "
                "(id, clerk_user_id, business_type, neighborhood, query_text, created_at, updated_at) "
                "VALUES (1, 'user-123', 'Cafe', 'Loop', 'Coffee demand', "
                "'2026-06-01 00:00:00', '2026-06-01 00:00:00')"
            )
        )

    monkeypatch.setattr(database, "engine", engine)
    database.init_db()

    inspector = inspect(engine)
    profile_columns = {column["name"] for column in inspector.get_columns("user_profiles")}
    query_columns = {column["name"] for column in inspector.get_columns("query_results")}
    assert "user_id" in profile_columns
    assert "clerk_user_id" not in profile_columns
    assert "user_id" in query_columns
    assert "clerk_user_id" not in query_columns

    with engine.connect() as conn:
        profile_user_id = conn.execute(text("SELECT user_id FROM user_profiles")).scalar_one()
        query_user_id = conn.execute(text("SELECT user_id FROM query_results")).scalar_one()

    assert profile_user_id == "user-123"
    assert query_user_id == "user-123"
