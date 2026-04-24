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


def test_modal_status_is_runtime_only(monkeypatch):
    from modal_app.api.routes import core as core_routes
    from modal_app.web import web_app

    def _raise_modal_dict_unavailable(*args, **kwargs):
        raise RuntimeError

    monkeypatch.setattr(core_routes.modal.Dict, "from_name", _raise_modal_dict_unavailable)
    client = TestClient(web_app)

    status_resp = client.get("/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "gpu_status" in status_data
    assert "costs" in status_data
    assert status_data["gpu_status"]["h100_llm"] == "disabled"
    assert "pipelines" not in status_data
    assert "enriched_docs" not in status_data
    assert "total_docs" not in status_data


def test_modal_route_ownership_boundaries():
    from modal_app.web import web_app

    paths = {getattr(route, "path", None) for route in web_app.routes}
    modal_owned = {"/status", "/gpu-metrics", "/graph/full"}
    backend_owned = {
        "/metrics",
        "/user/settings",
        "/sources",
        "/summary",
        "/geo",
        "/news",
        "/politics",
        "/inspections",
        "/permits",
        "/licenses",
        "/reddit",
        "/reviews",
        "/realestate",
        "/tiktok",
    }

    assert modal_owned <= paths
    assert paths.isdisjoint(backend_owned)
