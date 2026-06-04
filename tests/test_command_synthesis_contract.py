import asyncio
import json
from types import SimpleNamespace

from modal_app import web
import modal_app.openai_utils as openai_utils


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
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content[idx]), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )


class _FakeClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = SimpleNamespace(completions=completions)


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _payload():
    return {
        "business": {"name": "Cafe Con Leche"},
        "context": {"neighborhood": "Pilsen"},
        "forecast": {"opportunityCentsPerWeek": 142000},
        "risk": {"label": "MEDIUM"},
        "recommendations": [
            {
                "id": "extend-hours",
                "title": "Extend hours",
                "detail": "Capture late demand.",
                "whyNow": "Evening demand is high.",
                "nextStepLabel": "Schedule hours",
                "impactCentsPerWeek": 142000,
            },
            {
                "id": "bundle-pastry",
                "title": "Bundle pastry",
                "detail": "Lift high-margin attachment.",
                "whyNow": "Attach rate is low.",
                "nextStepLabel": "Update menu",
                "impactCentsPerWeek": 98000,
            },
        ],
    }


def test_command_synthesis_filters_unknown_action_ids(monkeypatch) -> None:
    llm_content = json.dumps(
        {
            "brief_lines": ["Late demand is under-captured."],
            "ranked_action_ids": ["unknown", "bundle-pastry", "extend-hours"],
            "action_copy": [
                {"id": "unknown", "title": "Invented", "detail": "No.", "why_now": "No.", "next_step_label": "No"},
                {"id": "bundle-pastry", "title": "Bundle pastry", "detail": "Use the high-margin item.", "why_now": "Attach rate is low.", "next_step_label": "Update menu"},
            ],
            "uncertainty_notes": [],
        }
    )
    fake_completions = _FakeCompletions(llm_content)
    fake_client = _FakeClient(fake_completions)
    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_command_synthesis_model", lambda: "gpt-5-test")

    result = asyncio.run(web.command_synthesis(_FakeRequest(_payload())))

    assert result["fallback_used"] is False
    assert result["ranked_action_ids"] == ["bundle-pastry", "extend-hours"]
    assert [item["id"] for item in result["action_copy"]] == ["bundle-pastry"]
    assert fake_completions.last_kwargs["model"] == "gpt-5-test"
    assert fake_completions.last_kwargs["reasoning_effort"] == "low"


def test_command_synthesis_retries_invalid_json(monkeypatch) -> None:
    retry_content = json.dumps(
        {
            "brief_lines": ["Prioritize late demand."],
            "ranked_action_ids": ["extend-hours"],
            "action_copy": [{"id": "extend-hours", "title": "Extend Friday hours", "detail": "Test a later close.", "why_now": "Demand is high.", "next_step_label": "Schedule hours"}],
            "uncertainty_notes": [],
        }
    )
    fake_completions = _FakeCompletions(["not-json", retry_content])
    fake_client = _FakeClient(fake_completions)
    monkeypatch.setattr(openai_utils, "openai_available", lambda: True)
    monkeypatch.setattr(openai_utils, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_utils, "get_command_synthesis_model", lambda: "gpt-5-test")

    result = asyncio.run(web.command_synthesis(_FakeRequest(_payload())))

    assert fake_completions.call_count == 2
    assert result["fallback_used"] is False
    assert result["ranked_action_ids"] == ["extend-hours"]


def test_command_synthesis_missing_openai_uses_fallback(monkeypatch) -> None:
    monkeypatch.setattr(openai_utils, "openai_available", lambda: False)

    result = asyncio.run(web.command_synthesis(_FakeRequest(_payload())))

    assert result["fallback_used"] is True
    assert result["ranked_action_ids"] == ["extend-hours", "bundle-pastry"]
    assert result["action_copy"][0]["id"] == "extend-hours"
