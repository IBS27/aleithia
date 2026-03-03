import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from modal_app import web
import modal_app.openai_utils as openai_utils


class _DummyVolume:
    def reload(self):
        return None


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content
        self.last_kwargs: dict = {}

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = SimpleNamespace(completions=completions)


def test_social_trends_contract_no_data(monkeypatch) -> None:
    monkeypatch.setattr(web, "volume", _DummyVolume())
    monkeypatch.setattr(web, "_load_docs", lambda source, limit=200: [])

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert payload["neighborhood"] == "Loop"
    assert payload["business_type"] == "Coffee Shop"
    assert payload["trends"] == []
    assert payload["source_counts"] == {"reddit": 0, "tiktok": 0}


def test_social_trends_contract_with_mixed_data(monkeypatch) -> None:
    monkeypatch.setattr(web, "volume", _DummyVolume())

    reddit_docs = [
        {
            "id": "r1",
            "title": "Coffee demand in Loop",
            "content": "Office workers are looking for faster espresso service.",
            "timestamp": "2026-03-02T12:00:00+00:00",
            "metadata": {"score": 10, "num_comments": 4, "subreddit": "chicago"},
            "geo": {"neighborhood": "Loop"},
        }
    ]
    tiktok_docs = [
        {
            "id": "t1",
            "title": "Lunch rush downtown",
            "content": "Creators highlight long lines at quick-service storefronts.",
            "timestamp": "2026-03-02T12:00:00+00:00",
            "metadata": {"views": "25K", "views_normalized": 25000, "creator": "loopwatch"},
            "geo": {"neighborhood": "Loop"},
        }
    ]

    def _fake_load_docs(source: str, limit: int = 200):
        if source == "reddit":
            return reddit_docs
        if source == "tiktok":
            return tiktok_docs
        return []

    monkeypatch.setattr(web, "_load_docs", _fake_load_docs)
    monkeypatch.setattr(web, "rank_reddit_docs", lambda docs, **kwargs: docs)
    monkeypatch.setattr(web, "_rank_tiktok_docs", lambda docs, *_args, **_kwargs: docs)

    llm_content = json.dumps(
        [
            {"title": "Morning coffee queues", "detail": "Commuter demand is rising in Loop office corridors."},
            {"title": "Lunch service pressure", "detail": "Short-form posts show higher noon demand for fast service."},
            {"title": "Convenience-led choices", "detail": "Customers prioritize quick pickup over long dwell-time formats."},
        ]
    )
    fake_completions = _FakeCompletions(llm_content)
    fake_client = _FakeClient(fake_completions)

    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_social_trends_model", lambda: "gpt-5-test")

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert payload["neighborhood"] == "Loop"
    assert payload["business_type"] == "Coffee Shop"
    assert payload["source_counts"] == {"reddit": 1, "tiktok": 1}
    assert len(payload["trends"]) == 3
    for trend in payload["trends"]:
        assert set(trend.keys()) == {"title", "detail"}
        assert trend["title"].strip()
        assert trend["detail"].strip()
    assert fake_completions.last_kwargs["model"] == "gpt-5-test"


def test_vision_assess_contract_model_field(monkeypatch, tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    processed_root = tmp_path / "processed"
    frame_dir = raw_root / "vision" / "frames"
    frame_dir.mkdir(parents=True)
    (frame_dir / "loop_frame.jpg").write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(web, "RAW_DATA_PATH", str(raw_root))
    monkeypatch.setattr(web, "PROCESSED_DATA_PATH", str(processed_root))
    monkeypatch.setattr(web, "volume", _DummyVolume())

    assessment_payload = {
        "storefront_viability": {"score": 7, "available_spaces": "moderate", "condition": "good"},
        "competitor_presence": {"restaurants": "medium", "retail": "medium", "notable_businesses": []},
        "pedestrian_activity": {"level": "medium", "demographics": "mixed", "peak_indicators": "noon activity"},
        "infrastructure": {"transit_access": "strong", "parking": "limited", "road_condition": "good"},
        "overall_recommendation": "Viable with moderate competition.",
    }
    fake_completions = _FakeCompletions(json.dumps(assessment_payload))
    fake_client = _FakeClient(fake_completions)

    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_vision_assess_model", lambda: "gpt-5-mini-test")

    payload = asyncio.run(web.vision_assess("Loop"))

    assert payload["neighborhood"] == "Loop"
    assert payload["frame_count"] >= 1
    assert payload["model"] == "gpt-5-mini-test"
    assert "assessment" in payload
    assert fake_completions.last_kwargs["model"] == "gpt-5-mini-test"
