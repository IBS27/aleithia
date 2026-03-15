from modal_app.agents import (
    _append_regulation_entry,
    _parse_timestamp_sort_key,
    _score_enriched_regulatory_doc,
)


def test_score_enriched_regulatory_doc_accepts_matching_regulatory_doc() -> None:
    doc = {
        "id": "doc-1",
        "title": "New liquor permit rules for restaurants",
        "content": "Restaurant owners must update food service permits in Chicago.",
        "timestamp": "2026-03-10T12:00:00+00:00",
        "classification": {"labels": ["regulatory", "business"], "scores": [0.92, 0.4]},
        "metadata": {"agency": "City of Chicago", "status": "active"},
    }

    scored = _score_enriched_regulatory_doc(doc, "restaurant")

    assert scored is not None
    assert scored["top_label"] == "regulatory"
    assert scored["business_hits"] >= 1
    assert scored["score"] > 0


def test_score_enriched_regulatory_doc_rejects_non_regulatory_doc() -> None:
    doc = {
        "id": "doc-2",
        "title": "Restaurant opening draws large crowds",
        "content": "Food service buzz continues across the neighborhood.",
        "timestamp": "2026-03-10T12:00:00+00:00",
        "classification": {"labels": ["community", "business"], "scores": [0.8, 0.6]},
    }

    assert _score_enriched_regulatory_doc(doc, "restaurant") is None


def test_score_enriched_regulatory_doc_rejects_regulatory_doc_without_business_match() -> None:
    doc = {
        "id": "doc-3",
        "title": "Updated construction permit checklist",
        "content": "Builders must follow new zoning review timelines.",
        "timestamp": "2026-03-10T12:00:00+00:00",
        "classification": {"labels": ["regulatory", "infrastructure"], "scores": [0.95, 0.5]},
    }

    assert _score_enriched_regulatory_doc(doc, "gym") is None


def test_append_regulation_entry_dedups_missing_ids() -> None:
    regulations: list[dict] = []
    seen_ids: set[str] = set()
    doc = {
        "title": "Bakery permit change",
        "timestamp": "2026-03-11T08:00:00+00:00",
    }

    first = _append_regulation_entry(
        regulations,
        seen_ids,
        doc,
        type_value="legal",
        date=doc["timestamp"],
        relevance="related",
    )
    second = _append_regulation_entry(
        regulations,
        seen_ids,
        doc,
        type_value="legal",
        date=doc["timestamp"],
        relevance="related",
    )

    assert first is True
    assert second is False
    assert len(regulations) == 1


def test_append_regulation_entry_handles_missing_optional_fields() -> None:
    regulations: list[dict] = []
    seen_ids: set[str] = set()
    doc = {"id": "doc-4", "title": "Fitness compliance update"}

    added = _append_regulation_entry(regulations, seen_ids, doc)

    assert added is True
    assert regulations[0] == {
        "title": "Fitness compliance update",
        "type": "",
        "status": "",
        "agency": "",
        "date": "",
        "relevance": "related",
        "freshness": "cached",
    }


def test_enriched_matches_sort_by_score_then_recency() -> None:
    docs = [
        {
            "id": "older",
            "title": "Gym permit rules update",
            "content": "Gym operators must renew permits.",
            "timestamp": "2026-03-09T12:00:00+00:00",
            "classification": {"labels": ["regulatory"], "scores": [0.8]},
        },
        {
            "id": "newer",
            "title": "Gym permit and fitness compliance changes",
            "content": "Fitness centers face updated permit compliance rules.",
            "timestamp": "2026-03-10T12:00:00+00:00",
            "classification": {"labels": ["regulatory"], "scores": [0.8]},
        },
    ]

    ranked = sorted(
        [_score_enriched_regulatory_doc(doc, "gym") for doc in docs],
        key=lambda item: (item["score"], item["timestamp"]),
        reverse=True,
    )

    assert [item["doc"]["id"] for item in ranked] == ["newer", "older"]
    assert ranked[0]["timestamp"] > ranked[1]["timestamp"]
    assert _parse_timestamp_sort_key("not-a-timestamp") == 0.0
