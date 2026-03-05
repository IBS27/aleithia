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
    def __init__(self, content: str | list[str]):
        self._content = content if isinstance(content, list) else [content]
        self.last_kwargs: dict = {}
        self.call_count = 0

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        idx = min(self.call_count, len(self._content) - 1)
        self.call_count += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content[idx]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        )


class _FakeClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = SimpleNamespace(completions=completions)


def _mock_social_docs(monkeypatch) -> tuple[list[dict], list[dict]]:
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
    return reddit_docs, tiktok_docs


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
    _mock_social_docs(monkeypatch)
    rank_called = {"value": False}

    def _fake_rank_social_docs(*args, **kwargs):
        rank_called["value"] = True
        return [
            ("reddit", {"id": "r1", "title": "Coffee demand in Loop", "content": "Office workers are looking for faster espresso service.", "metadata": {"score": 10, "num_comments": 4}, "geo": {"neighborhood": "Loop"}}, 0.9),
            ("tiktok", {"id": "t1", "title": "Lunch rush downtown", "content": "Creators highlight long lines at quick-service storefronts.", "metadata": {"views_normalized": 25000, "creator": "loopwatch"}, "geo": {"neighborhood": "Loop"}}, 0.8),
        ]

    monkeypatch.setattr(web, "_rank_social_docs_deterministic", _fake_rank_social_docs)

    llm_content = json.dumps(
        {"trends": [
            {"title": "Morning coffee queues", "detail": "Commuter demand is rising in Loop office corridors."},
            {"title": "Lunch service pressure", "detail": "Short-form posts show higher noon demand for fast service."},
            {"title": "Convenience-led choices", "detail": "Customers prioritize quick pickup over long dwell-time formats."},
        ]}
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
    assert rank_called["value"] is True
    assert fake_completions.last_kwargs["model"] == "gpt-5-test"
    # GPT-5 family should get 2048 tokens and reasoning_effort
    assert fake_completions.last_kwargs["max_completion_tokens"] == 2048
    assert fake_completions.last_kwargs["reasoning_effort"] == "low"
    assert "max_tokens" not in fake_completions.last_kwargs
    assert "temperature" not in fake_completions.last_kwargs


def test_social_trends_gpt4o_uses_legacy_kwargs(monkeypatch) -> None:
    """Non-GPT-5 models should use 512 tokens + temperature, no reasoning_effort."""
    monkeypatch.setattr(web, "volume", _DummyVolume())
    _mock_social_docs(monkeypatch)

    monkeypatch.setattr(web, "_rank_social_docs_deterministic", lambda *a, **kw: [
        ("reddit", {"id": "r1", "title": "Coffee demand in Loop", "content": "Office workers.", "metadata": {"score": 10, "num_comments": 4}, "geo": {"neighborhood": "Loop"}}, 0.9),
    ])

    llm_content = json.dumps(
        {"trends": [
            {"title": "A", "detail": "Detail A"},
            {"title": "B", "detail": "Detail B"},
            {"title": "C", "detail": "Detail C"},
        ]}
    )
    fake_completions = _FakeCompletions(llm_content)
    fake_client = _FakeClient(fake_completions)

    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_social_trends_model", lambda: "gpt-4o")

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert len(payload["trends"]) == 3
    assert fake_completions.last_kwargs["max_completion_tokens"] == 512
    assert fake_completions.last_kwargs["temperature"] == 0.4
    assert "reasoning_effort" not in fake_completions.last_kwargs


def test_social_trends_input_payload_matches_legacy_4o_shape(monkeypatch) -> None:
    monkeypatch.setattr(web, "volume", _DummyVolume())

    reddit_docs = []
    for i in range(12):
        reddit_docs.append(
            {
                "id": f"r{i}",
                "title": f"Reddit Title {i}",
                "content": f"Reddit content {i}",
                "timestamp": "2026-03-02T12:00:00+00:00",
                "metadata": {"score": 5 + i, "num_comments": i},
                "geo": {"neighborhood": "Loop"},
            }
        )

    tiktok_docs = []
    for i in range(7):
        tiktok_docs.append(
            {
                "id": f"t{i}",
                "title": f"TikTok Title {i}",
                "content": f"TikTok content {i}",
                "timestamp": "2026-03-02T12:00:00+00:00",
                "metadata": {"views": f"{i}K", "views_normalized": i * 1000, "creator": "loopwatch"},
                "geo": {"neighborhood": "Loop"},
            }
        )

    def _fake_load_docs(source: str, limit: int = 200):
        if source == "reddit":
            return reddit_docs
        if source == "tiktok":
            return tiktok_docs
        return []

    monkeypatch.setattr(web, "_load_docs", _fake_load_docs)
    monkeypatch.setattr(web, "rank_reddit_docs", lambda docs, **kwargs: docs)
    monkeypatch.setattr(web, "_rank_tiktok_docs", lambda docs, *_args, **_kwargs: docs)

    fake_completions = _FakeCompletions(
        json.dumps(
            {
                "trends": [
                    {"title": "Trend A", "detail": "Detail A"},
                    {"title": "Trend B", "detail": "Detail B"},
                    {"title": "Trend C", "detail": "Detail C"},
                ]
            }
        )
    )
    fake_client = _FakeClient(fake_completions)
    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_social_trends_model", lambda: "gpt-5-test")

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert len(payload["trends"]) == 3
    user_prompt = fake_completions.last_kwargs["messages"][1]["content"]

    # Uses legacy simple source-tagged snippets and correct source caps.
    assert "[Reddit] Reddit Title 0:" in user_prompt
    assert "[Reddit] Reddit Title 9:" in user_prompt
    assert "[Reddit] Reddit Title 10:" not in user_prompt
    assert "[TikTok] TikTok Title 0" in user_prompt
    assert "[TikTok] TikTok Title 4" in user_prompt
    assert "[TikTok] TikTok Title 5" not in user_prompt
    assert "relevance=" not in user_prompt
    assert "[Reddit #" not in user_prompt
    assert "[TikTok #" not in user_prompt


def test_social_trends_contract_malformed_model_output_uses_fallback(monkeypatch) -> None:
    monkeypatch.setattr(web, "volume", _DummyVolume())
    _mock_social_docs(monkeypatch)

    # First attempt and retry both fail to provide usable trends.
    fake_completions = _FakeCompletions(["{}", "{}"])
    fake_client = _FakeClient(fake_completions)
    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_social_trends_model", lambda: "gpt-5-test")

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert payload["source_counts"] == {"reddit": 1, "tiktok": 1}
    assert len(payload["trends"]) == 3
    assert fake_completions.call_count == 2
    for trend in payload["trends"]:
        assert set(trend.keys()) == {"title", "detail"}
        assert trend["title"].strip()
        assert trend["detail"].strip()


def test_social_trends_contract_partial_model_output_backfills_to_three(monkeypatch) -> None:
    monkeypatch.setattr(web, "volume", _DummyVolume())
    _mock_social_docs(monkeypatch)

    fake_completions = _FakeCompletions(
        json.dumps(
            {
                "trends": [
                    {"title": "Single trend", "detail": "Only one trend came back from model output."},
                ]
            }
        )
    )
    fake_client = _FakeClient(fake_completions)
    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_social_trends_model", lambda: "gpt-5-test")

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert payload["source_counts"] == {"reddit": 1, "tiktok": 1}
    assert len(payload["trends"]) == 3
    assert any(t["title"] == "Single trend" for t in payload["trends"])
    assert fake_completions.call_count == 1


def test_social_trends_truncated_response_triggers_retry(monkeypatch) -> None:
    """When GPT-5 truncates output (partial JSON), the retry should succeed."""
    monkeypatch.setattr(web, "volume", _DummyVolume())
    _mock_social_docs(monkeypatch)

    truncated_json = '{"trends": [{"title": "Partial", "detail": "Trun'  # cut off
    good_json = json.dumps(
        {"trends": [
            {"title": "Recovered A", "detail": "Detail A"},
            {"title": "Recovered B", "detail": "Detail B"},
            {"title": "Recovered C", "detail": "Detail C"},
        ]}
    )
    fake_completions = _FakeCompletions([truncated_json, good_json])
    fake_client = _FakeClient(fake_completions)

    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_social_trends_model", lambda: "gpt-5-test")

    payload = asyncio.run(web.social_trends("Loop", "Coffee Shop"))

    assert fake_completions.call_count == 2
    assert len(payload["trends"]) == 3
    assert payload["trends"][0]["title"] == "Recovered A"


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
    # GPT-5-mini should get 2048 tokens and reasoning_effort
    assert fake_completions.last_kwargs["max_completion_tokens"] == 2048
    assert fake_completions.last_kwargs["reasoning_effort"] == "low"
    assert "max_tokens" not in fake_completions.last_kwargs
    assert "temperature" not in fake_completions.last_kwargs
