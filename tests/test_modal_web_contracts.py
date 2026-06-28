from __future__ import annotations

import json
from collections import Counter

import pytest
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
        "/user/profile",
        "/user/queries",
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


def test_streetscape_empty_response_includes_neighborhood(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from modal_app.api.routes import vision as vision_routes
    from modal_app.web import web_app

    (tmp_path / "vision" / "analysis").mkdir(parents=True)
    monkeypatch.setattr(vision_routes, "volume", SimpleNamespace(reload=lambda: None))
    monkeypatch.setattr(vision_routes, "PROCESSED_DATA_PATH", tmp_path)

    resp = TestClient(web_app).get("/vision/streetscape/Loop")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "neighborhood": "Loop",
        "counts": None,
        "indicators": None,
        "analysis_count": 0,
    }


@pytest.mark.asyncio
async def test_generated_analysis_reads_outputs_before_sandbox_cleanup(monkeypatch):
    from modal_app.api.routes import analysis as analysis_routes

    calls: list[tuple] = []
    result_payload = {"title": "Available sources", "summary": "Done", "stats": {"raw": 3}}

    class FakeAsyncMethod:
        def __init__(self, fn):
            self._fn = fn

        async def aio(self, *args, **kwargs):
            return self._fn(*args, **kwargs)

    class FakeStream:
        def __init__(self, value: str):
            self.read = FakeAsyncMethod(lambda: value)

    class FakeFile:
        def __init__(self, value):
            self._value = value
            self.read = FakeAsyncMethod(lambda: value)
            self.close = FakeAsyncMethod(lambda: calls.append(("file_close", self._value)))

    class FakeProcess:
        stdout = FakeStream("script stdout")
        stderr = FakeStream("")
        returncode = 0
        wait = FakeAsyncMethod(lambda: 0)

    class FakeSandbox:
        def __init__(self):
            self.exec = FakeAsyncMethod(self._exec)
            self.open = FakeAsyncMethod(self._open)
            self.terminate = FakeAsyncMethod(self._terminate)

        def _exec(self, *args, **kwargs):
            calls.append(("exec", args, kwargs))
            return FakeProcess()

        def _open(self, path: str, mode: str):
            calls.append(("open", path, mode))
            if path == "/output/result.json":
                return FakeFile(json.dumps(result_payload))
            if path == "/output/chart.png":
                return FakeFile(b"png")
            raise FileNotFoundError(path)

        def _terminate(self, **kwargs):
            calls.append(("terminate", kwargs))

    async def fake_create(*args, **kwargs):
        calls.append(("create", args, kwargs))
        return FakeSandbox()

    monkeypatch.setattr(analysis_routes.modal.Sandbox.create, "aio", fake_create)

    result = await analysis_routes.execute_generated_analysis("print('ok')")

    assert result.result == result_payload
    assert result.chart_b64 == "cG5n"
    assert result.stdout == "script stdout"
    assert ("open", "/output/result.json", "r") in calls
    assert calls[-1][0] == "terminate"
