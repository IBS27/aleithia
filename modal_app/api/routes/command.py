"""Command-page synthesis endpoint."""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


def _trim_words(text: str, max_words: int) -> str:
    words = [word for word in re.split(r"\s+", text.strip()) if word]
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).strip(" -:;,")


def _candidate_ids(payload: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id", "") or "").strip()
        for item in payload.get("recommendations", [])
        if isinstance(item, dict) and str(item.get("id", "") or "").strip()
    }


def _fallback_command_synthesis(payload: dict[str, Any]) -> dict[str, Any]:
    recommendations = [item for item in payload.get("recommendations", []) if isinstance(item, dict)]
    recommendations.sort(key=lambda item: float(item.get("impactCentsPerWeek", 0) or 0), reverse=True)
    top = recommendations[:4]
    forecast = payload.get("forecast", {}) if isinstance(payload.get("forecast"), dict) else {}
    context = payload.get("context", {}) if isinstance(payload.get("context"), dict) else {}
    risk = payload.get("risk", {}) if isinstance(payload.get("risk"), dict) else {}
    opportunity = int(forecast.get("opportunityCentsPerWeek", 0) or 0)
    neighborhood = str(context.get("neighborhood", "") or "this market")
    risk_label = str(risk.get("label", "") or "UNKNOWN")

    return {
        "brief_lines": [
            f"Top actions point to ${round(opportunity / 100):,}/week in modeled opportunity.",
            f"{neighborhood} demand and operating signals support prioritizing the highest-impact action first.",
            f"Current risk level is {risk_label}; keep compliance and execution risk visible while testing changes.",
        ],
        "ranked_action_ids": [str(item.get("id")) for item in top if item.get("id")],
        "action_copy": [
            {
                "id": str(item.get("id", "")),
                "title": _trim_words(str(item.get("title", "")), 8),
                "detail": str(item.get("detail", "")),
                "why_now": str(item.get("whyNow", "")),
                "next_step_label": str(item.get("nextStepLabel", "Review action")),
            }
            for item in top
            if item.get("id")
        ],
        "uncertainty_notes": ["Generated from deterministic fallback because GPT-5 synthesis was unavailable."],
        "fallback_used": True,
    }


def _parse_command_synthesis_response(raw: str, allowed_ids: set[str]) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    parsed: Any = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                parsed = None

    if not isinstance(parsed, dict):
        return None

    brief_lines = [
        str(item).strip()
        for item in parsed.get("brief_lines", [])
        if isinstance(item, str) and item.strip()
    ][:5]

    ranked_action_ids = [
        str(item).strip()
        for item in parsed.get("ranked_action_ids", [])
        if str(item).strip() in allowed_ids
    ]

    action_copy = []
    for item in parsed.get("action_copy", []):
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("id", "") or "").strip()
        if action_id not in allowed_ids:
            continue
        title = _trim_words(str(item.get("title", "") or ""), 8)
        detail = str(item.get("detail", "") or "").strip()
        why_now = str(item.get("why_now", item.get("whyNow", "")) or "").strip()
        next_step_label = _trim_words(str(item.get("next_step_label", item.get("nextStepLabel", "")) or ""), 3)
        if title and detail:
            action_copy.append(
                {
                    "id": action_id,
                    "title": title,
                    "detail": detail,
                    "why_now": why_now,
                    "next_step_label": next_step_label or "Review action",
                }
            )

    uncertainty_notes = [
        str(item).strip()
        for item in parsed.get("uncertainty_notes", [])
        if isinstance(item, str) and item.strip()
    ][:3]

    if not brief_lines and not action_copy and not ranked_action_ids:
        return None

    return {
        "brief_lines": brief_lines,
        "ranked_action_ids": ranked_action_ids,
        "action_copy": action_copy,
        "uncertainty_notes": uncertainty_notes,
        "fallback_used": False,
    }


def _compact_command_payload(payload: dict[str, Any]) -> dict[str, Any]:
    recommendations = payload.get("recommendations", [])
    return {
        "business": payload.get("business", {}),
        "context": payload.get("context", {}),
        "metrics": payload.get("metrics", {}),
        "forecast": payload.get("forecast", {}),
        "risk": payload.get("risk", {}),
        "compliance": payload.get("compliance", {}),
        "market": payload.get("market", {}),
        "coverage": payload.get("coverage", {}),
        "recommendations": recommendations,
    }


@router.post("/command/synthesis")
async def command_synthesis(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        return _fallback_command_synthesis({})

    allowed_ids = _candidate_ids(payload)
    fallback = _fallback_command_synthesis(payload)
    if not allowed_ids:
        return fallback

    from modal_app.openai_utils import (
        build_chat_kwargs,
        get_command_synthesis_model,
        get_openai_client,
        openai_available,
    )

    if not openai_available():
        return fallback

    compact_payload = _compact_command_payload(payload)
    system_prompt = (
        "You are an SMB revenue operator. Rewrite and rank only the provided action candidates. "
        "Do not invent metrics, action ids, dollar values, confidence values, or source counts. "
        "Use the deterministic payload as the only source of truth. "
        "Respond only as JSON with keys brief_lines, ranked_action_ids, action_copy, uncertainty_notes. "
        "action_copy items must use known ids and include id, title, detail, why_now, next_step_label."
    )
    user_prompt = "Command analysis payload:\n" + json.dumps(compact_payload, default=str)[:12000]
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    try:
        client = get_openai_client()
        model = get_command_synthesis_model()
        kwargs = build_chat_kwargs(
            model,
            messages,
            max_completion_tokens=700,
            gpt5_max_completion_tokens=2200,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        response = await client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content or ""
        parsed = _parse_command_synthesis_response(raw, allowed_ids)
    except Exception as exc:
        print(f"[command-synthesis] OpenAI call failed: {exc!r}")
        parsed = None

    if parsed is None:
        try:
            retry_messages = [
                {
                    "role": "system",
                    "content": "Return valid JSON only. Use only known action ids. Shape: {\"brief_lines\":[],\"ranked_action_ids\":[],\"action_copy\":[{\"id\":\"\",\"title\":\"\",\"detail\":\"\",\"why_now\":\"\",\"next_step_label\":\"\"}],\"uncertainty_notes\":[]}",
                },
                {"role": "user", "content": user_prompt},
            ]
            model = get_command_synthesis_model()
            retry_kwargs = build_chat_kwargs(
                model,
                retry_messages,
                max_completion_tokens=700,
                gpt5_max_completion_tokens=2200,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            retry_response = await client.chat.completions.create(**retry_kwargs)
            retry_raw = retry_response.choices[0].message.content or ""
            parsed = _parse_command_synthesis_response(retry_raw, allowed_ids)
        except Exception as exc:
            print(f"[command-synthesis] retry failed: {exc!r}")

    return parsed or fallback
