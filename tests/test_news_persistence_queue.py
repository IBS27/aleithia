import asyncio
import json
import sys
import types
from pathlib import Path

from modal_app.pipelines import news as news_mod


class _FakeDoc:
    def __init__(self, payload: dict):
        self.id = payload["id"]
        self.payload = payload

    def model_dump_json(self, indent: int = 2) -> str:
        return json.dumps(self.payload, indent=indent)


def _news_doc(doc_id: str = "news-abc123") -> dict:
    return {
        "id": doc_id,
        "source": "news",
        "title": "Chicago zoning proposal advances",
        "content": "A zoning proposal affecting small businesses advanced.",
        "url": "https://example.test/story",
        "timestamp": "2026-03-01T00:00:00+00:00",
        "metadata": {"feed_name": "Example"},
        "geo": {"neighborhood": "Loop"},
    }


def test_persist_news_docs_saves_dedup_and_status_before_enqueue(monkeypatch, tmp_path: Path) -> None:
    events: list = []
    captured: dict = {}

    monkeypatch.setattr(news_mod, "get_dedup_data_dir", lambda: tmp_path / "dedup")
    monkeypatch.setattr(news_mod, "get_raw_data_dir", lambda: tmp_path / "raw")
    monkeypatch.setattr(news_mod, "build_document", lambda payload: _FakeDoc(payload))

    async def _fake_safe_volume_commit(_vol, _source):
        events.append("commit")
        return True

    def _fake_write_source_status(source, **kwargs):
        events.append(("status", kwargs.get("metadata")))
        return {"source": source, **kwargs}

    async def _fake_enqueue(docs):
        events.append("enqueue")
        captured["queue_docs"] = docs
        assert len(list((tmp_path / "raw" / "news").rglob("news-abc123.json"))) == 1
        state = json.loads((tmp_path / "dedup" / "news.json").read_text())
        assert "news-abc123" in state["claims"]
        assert "news-abc123" not in state["ids"]
        assert not any(isinstance(event, tuple) and event[0] == "status" for event in events)
        assert "commit" in events
        return {"state": "enqueued", "failures": 0, "timeout_seconds": 30.0}

    monkeypatch.setattr(news_mod, "safe_volume_commit", _fake_safe_volume_commit)
    monkeypatch.setattr(news_mod, "write_source_status", _fake_write_source_status)
    monkeypatch.setattr(news_mod, "_enqueue_news_docs_for_classification", _fake_enqueue)

    count = asyncio.run(news_mod._persist_news_docs([_news_doc(), _news_doc()]))

    assert count == 1
    assert len(captured["queue_docs"]) == 1
    assert captured["queue_docs"][0]["metadata"]["ingested_at"]
    assert len(list((tmp_path / "raw" / "news").rglob("news-abc123.json"))) == 1
    state = json.loads((tmp_path / "dedup" / "news.json").read_text())
    assert "news-abc123" in state["ids"]
    assert "news-abc123" not in state["claims"]

    enqueue_index = events.index("enqueue")
    status_index = next(
        i
        for i, event in enumerate(events)
        if isinstance(event, tuple)
        and event[0] == "status"
        and event[1].get("classification_queue", {}).get("state") == "enqueued"
    )
    assert enqueue_index < status_index


def test_persist_news_docs_timeout_retry_does_not_reenqueue_same_docs(monkeypatch, tmp_path: Path) -> None:
    enqueue_calls = 0

    monkeypatch.setattr(news_mod, "get_dedup_data_dir", lambda: tmp_path / "dedup")
    monkeypatch.setattr(news_mod, "get_raw_data_dir", lambda: tmp_path / "raw")
    monkeypatch.setattr(news_mod, "build_document", lambda payload: _FakeDoc(payload))
    monkeypatch.setattr(news_mod, "write_source_status", lambda source, **kwargs: {"source": source, **kwargs})

    async def _fake_safe_volume_commit(_vol, _source):
        return True

    async def _fake_enqueue(docs):
        nonlocal enqueue_calls
        enqueue_calls += 1
        return {"state": "timeout", "failures": len(docs), "timeout_seconds": 1.0}

    monkeypatch.setattr(news_mod, "safe_volume_commit", _fake_safe_volume_commit)
    monkeypatch.setattr(news_mod, "_enqueue_news_docs_for_classification", _fake_enqueue)

    docs = [_news_doc()]

    first_count = asyncio.run(news_mod._persist_news_docs(docs))
    retry_count = asyncio.run(news_mod._persist_news_docs(docs))

    assert first_count == 0
    assert retry_count == 0
    assert enqueue_calls == 1
    assert len(list((tmp_path / "raw" / "news").rglob("news-abc123.json"))) == 1
    state = json.loads((tmp_path / "dedup" / "news.json").read_text())
    assert "news-abc123" in state["claims"]
    assert "news-abc123" not in state["ids"]


def test_persist_news_docs_concurrent_attempts_enqueue_once(monkeypatch, tmp_path: Path) -> None:
    enqueue_calls = 0

    monkeypatch.setattr(news_mod, "get_dedup_data_dir", lambda: tmp_path / "dedup")
    monkeypatch.setattr(news_mod, "get_raw_data_dir", lambda: tmp_path / "raw")
    monkeypatch.setattr(news_mod, "build_document", lambda payload: _FakeDoc(payload))
    monkeypatch.setattr(news_mod, "write_source_status", lambda source, **kwargs: {"source": source, **kwargs})

    async def _fake_safe_volume_commit(_vol, _source):
        return True

    async def _fake_enqueue(docs):
        nonlocal enqueue_calls
        enqueue_calls += 1
        await asyncio.sleep(0.05)
        return {"state": "enqueued", "failures": 0, "timeout_seconds": 30.0}

    monkeypatch.setattr(news_mod, "safe_volume_commit", _fake_safe_volume_commit)
    monkeypatch.setattr(news_mod, "_enqueue_news_docs_for_classification", _fake_enqueue)

    async def _run_two_attempts():
        return await asyncio.gather(
            news_mod._persist_news_docs([_news_doc()]),
            news_mod._persist_news_docs([_news_doc()]),
        )

    results = asyncio.run(_run_two_attempts())

    assert sorted(results) == [0, 1]
    assert enqueue_calls == 1
    assert len(list((tmp_path / "raw" / "news").rglob("news-abc123.json"))) == 1
    state = json.loads((tmp_path / "dedup" / "news.json").read_text())
    assert "news-abc123" in state["ids"]
    assert "news-abc123" not in state["claims"]


def test_enqueue_news_docs_for_classification_times_out(monkeypatch) -> None:
    fake_classify = types.ModuleType("modal_app.classify")
    fake_classify.doc_queue = object()
    monkeypatch.setitem(sys.modules, "modal_app.classify", fake_classify)
    monkeypatch.setenv("NEWS_CLASSIFICATION_QUEUE_TIMEOUT_SECONDS", "0.01")

    async def _slow_queue_push(_queue, _docs, _source):
        await asyncio.sleep(1)
        return 0

    monkeypatch.setattr(news_mod, "safe_queue_push", _slow_queue_push)

    result = asyncio.run(news_mod._enqueue_news_docs_for_classification([_news_doc()]))

    assert result["state"] == "timeout"
    assert result["failures"] == 1
