from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient


def test_modal_web_routes_are_unique():
    from modal_app.web import web_app

    paths = []
    for route in web_app.routes:
        path = getattr(route, "path", None)
        methods = tuple(sorted(getattr(route, "methods", []) or []))
        if path:
            paths.append((path, methods))

    duplicates = {
        (path, methods): count
        for (path, methods), count in Counter(paths).items()
        if count > 1
    }
    assert duplicates == {}


def test_modal_runtime_contracts_are_centralized():
    from modal_app import runtime

    assert runtime.MODAL_APP_NAME == "alethia"
    assert runtime.RAW_DOC_QUEUE_NAME == "new-docs"
    assert runtime.IMPACT_QUEUE_NAME == "impact-docs"


def test_graph_full_endpoint_contract(monkeypatch):
    from modal_app.api.routes import graph as graph_routes
    from modal_app.web import web_app

    async def fake_load_full_graph():
        return {"nodes": [{"id": "nb:Loop"}], "edges": [{"source": "nb:Loop", "target": "nb:West Loop"}]}

    monkeypatch.setattr(graph_routes, "load_full_graph", fake_load_full_graph)
    client = TestClient(web_app)

    resp = client.get("/graph/full")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


def test_core_aggregate_endpoints_keep_contract(monkeypatch):
    from modal_app.api.routes import core as core_routes
    from modal_app.web import web_app

    fake_stats = {
        "news": {
            "doc_count": 3,
            "active": True,
            "last_update": "2026-03-07T00:00:00+00:00",
            "neighborhoods_covered": {"Loop", "West Loop"},
        },
        "politics": {
            "doc_count": 0,
            "active": False,
            "last_update": None,
            "neighborhoods_covered": set(),
        },
    }

    monkeypatch.setattr(core_routes, "get_source_stats", lambda: fake_stats)
    monkeypatch.setattr(core_routes, "aggregate_city_demographics", lambda: {"population": 10})
    monkeypatch.setattr(core_routes, "ENABLE_ALETHIA_LLM", False)

    client = TestClient(web_app)

    status_resp = client.get("/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "pipelines" in status_data
    assert "enriched_docs" in status_data
    assert "gpu_status" in status_data
    assert "total_docs" in status_data

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert set(metrics_data) == {
        "total_documents",
        "active_pipelines",
        "neighborhoods_covered",
        "data_sources",
        "neighborhoods_total",
    }

    sources_resp = client.get("/sources")
    assert sources_resp.status_code == 200
    assert sources_resp.json()["news"] == {"count": 3, "active": True}

    summary_resp = client.get("/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert set(summary_data) == {"total_documents", "source_counts", "demographics"}


def test_modal_legacy_routes_no_longer_own_user_settings():
    from modal_app.web import web_app

    paths = {getattr(route, "path", None) for route in web_app.routes}
    assert "/user/settings" not in paths
