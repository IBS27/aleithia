"""Tests for VectorAI DB service module."""
import os
from unittest.mock import patch


def test_vectordb_available_returns_true_by_default():
    """vectordb_available() returns True when VECTORDB_DISABLED is not set."""
    from modal_app.vectordb import vectordb_available
    with patch.dict(os.environ, {}, clear=False):
        # Remove VECTORDB_DISABLED if set
        os.environ.pop("VECTORDB_DISABLED", None)
        assert vectordb_available() is True


def test_vectordb_available_env_override():
    """VECTORDB_DISABLED=1 forces vectordb_available() to False."""
    from modal_app.vectordb import vectordb_available
    with patch.dict(os.environ, {"VECTORDB_DISABLED": "1"}):
        assert vectordb_available() is False


def test_build_payload_from_doc():
    """build_payload creates correct metadata dict from a document."""
    from modal_app.vectordb import build_payload

    doc = {
        "id": "test-123",
        "source": "news",
        "title": "Test Article",
        "content": "Some content about Loop neighborhood",
        "timestamp": "2026-03-01T00:00:00Z",
        "geo": {"neighborhood": "Loop"},
        "metadata": {},
    }
    classification = {"labels": ["regulatory", "economic"], "scores": [0.9, 0.7]}
    sentiment = {"label": "positive", "score": 0.85}

    payload = build_payload(doc, classification, sentiment)

    assert payload["doc_id"] == "test-123"
    assert payload["source"] == "news"
    assert payload["neighborhood"] == "Loop"
    assert payload["category"] == "regulatory"
    assert payload["sentiment_label"] == "positive"
    assert payload["sentiment_score"] == 0.85


def test_build_payload_handles_missing_fields():
    """build_payload handles docs with missing optional fields."""
    from modal_app.vectordb import build_payload

    doc = {"id": "bare-doc", "source": "reddit", "title": "Minimal", "content": ""}
    payload = build_payload(doc, {}, {})

    assert payload["doc_id"] == "bare-doc"
    assert payload["neighborhood"] == ""
    assert payload["category"] == ""
    assert payload["sentiment_label"] == "neutral"


def test_build_embed_text():
    """build_embed_text concatenates title + truncated content."""
    from modal_app.vectordb import build_embed_text

    doc = {"title": "My Title", "content": "A" * 2000}
    text = build_embed_text(doc)

    assert text.startswith("My Title ")
    assert len(text) <= len("My Title ") + 1000


def test_build_embed_text_handles_none_content():
    """build_embed_text handles None content gracefully."""
    from modal_app.vectordb import build_embed_text

    doc = {"title": "Title Only", "content": None}
    text = build_embed_text(doc)
    assert text == "Title Only"


def test_classify_vectordb_upsert_builds_correct_batch():
    """Verify classify pipeline builds correct embed texts and payloads for VectorDB."""
    from modal_app.vectordb import build_embed_text, build_payload

    docs = [
        {
            "id": "doc-1",
            "source": "news",
            "title": "New Restaurant Opens",
            "content": "A new restaurant in Wicker Park",
            "geo": {"neighborhood": "Wicker Park"},
            "timestamp": "2026-03-01T00:00:00Z",
        },
        {
            "id": "doc-2",
            "source": "reddit",
            "title": "Gym Review",
            "content": "Best gym in Logan Square",
            "geo": {"neighborhood": "Logan Square"},
            "timestamp": "2026-03-01T00:00:00Z",
        },
    ]
    classifications = [
        {"labels": ["economic", "community"], "scores": [0.8, 0.6]},
        {"labels": ["community"], "scores": [0.7]},
    ]
    sentiments = [
        {"label": "positive", "score": 0.9},
        {"label": "neutral", "score": 0.5},
    ]

    texts = [build_embed_text(d) for d in docs]
    payloads = [build_payload(d, c, s) for d, c, s in zip(docs, classifications, sentiments)]

    assert len(texts) == 2
    assert "New Restaurant Opens" in texts[0]
    assert payloads[0]["neighborhood"] == "Wicker Park"
    assert payloads[0]["category"] == "economic"
    assert payloads[1]["sentiment_label"] == "neutral"


def test_check_vectordb_health_returns_not_configured_when_disabled():
    """check_vectordb_health returns not_configured when VECTORDB_DISABLED=1."""
    from modal_app.vectordb import check_vectordb_health
    with patch.dict(os.environ, {"VECTORDB_DISABLED": "1"}):
        result = check_vectordb_health()
        assert result["status"] == "not_configured"
