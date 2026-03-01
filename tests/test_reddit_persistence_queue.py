import asyncio
import json
from pathlib import Path

from modal_app.pipelines import reddit as reddit_mod


class _FakeSeenSet:
    def __init__(self):
        self._seen: set[str] = set()

    def contains(self, doc_id: str) -> bool:
        return doc_id in self._seen

    def add(self, doc_id: str) -> None:
        self._seen.add(doc_id)

    def save(self) -> None:
        return None


class _FakeDoc:
    def __init__(self, payload: dict):
        self.id = payload["id"]
        self.metadata = payload.get("metadata", {})

    def model_dump_json(self, indent: int = 2) -> str:
        return json.dumps({"id": self.id, "metadata": self.metadata}, indent=indent)


def test_persist_reddit_docs_dedups_and_enqueues_once(monkeypatch, tmp_path: Path) -> None:
    seen = _FakeSeenSet()
    captured: dict = {}

    monkeypatch.setattr(reddit_mod, "RAW_DATA_PATH", str(tmp_path / "raw"))
    monkeypatch.setattr(reddit_mod, "SeenSet", lambda _name: seen)
    monkeypatch.setattr(reddit_mod, "build_document", lambda payload: _FakeDoc(payload))

    async def _fake_safe_queue_push(_queue, docs, source):
        captured["queue_docs"] = docs
        captured["source"] = source
        return 0

    async def _fake_safe_volume_commit(_vol, _source):
        captured["committed"] = True
        return True

    monkeypatch.setattr(reddit_mod, "safe_queue_push", _fake_safe_queue_push)
    monkeypatch.setattr(reddit_mod, "safe_volume_commit", _fake_safe_volume_commit)

    docs = [
        {
            "id": "reddit-abc123",
            "source": "reddit",
            "title": "Best fitness center in Loop",
            "content": "Looking for gym suggestions in Chicago",
            "timestamp": "2026-03-01T00:00:00+00:00",
            "metadata": {"subreddit": "AskChicago", "retrieval_method": "rss_search"},
            "geo": {"neighborhood": "Loop"},
        },
        {
            "id": "reddit-abc123",
            "source": "reddit",
            "title": "duplicate",
            "content": "duplicate",
            "timestamp": "2026-03-01T00:00:00+00:00",
            "metadata": {"subreddit": "AskChicago", "retrieval_method": "rss_search"},
            "geo": {"neighborhood": "Loop"},
        },
    ]

    count = asyncio.run(reddit_mod._persist_reddit_docs(docs, ingestion_mode="query_fallback"))

    assert count == 1
    assert captured["source"] == "reddit-query_fallback"
    assert captured["committed"] is True
    assert len(captured["queue_docs"]) == 1
    assert captured["queue_docs"][0]["metadata"]["ingestion_mode"] == "query_fallback"

    files = list((tmp_path / "raw" / "reddit").rglob("reddit-abc123.json"))
    assert len(files) == 1
    assert "_fallback" in str(files[0].parent)
