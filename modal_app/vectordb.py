"""Actian VectorAI DB integration — local vector search layer.

Complements Supermemory with fast local semantic retrieval using
HNSW-indexed vectors. Documents are embedded with all-MiniLM-L6-v2 (384d)
at ingestion time and queried by the agent swarm at search time.

All operations degrade gracefully via vectordb_available().
"""
import os


# ---------------------------------------------------------------------------
# Availability guard (same pattern as openai_utils.py)
# ---------------------------------------------------------------------------

_vectordb_healthy = False


def vectordb_available() -> bool:
    """Check if VectorAI DB service is reachable and healthy.

    Returns False if VECTORDB_DISABLED=1 env var is set or if no
    VectorDB container has registered as healthy.
    """
    if os.environ.get("VECTORDB_DISABLED", "").strip() == "1":
        return False
    return _vectordb_healthy


# ---------------------------------------------------------------------------
# Payload + text helpers (pure functions, no DB dependency)
# ---------------------------------------------------------------------------

EMBED_CONTENT_LIMIT = 1000
VECTOR_DIMENSION = 384


def build_payload(doc: dict, classification: dict, sentiment: dict) -> dict:
    """Build VectorAI DB payload dict from a document + enrichment results."""
    geo = doc.get("geo", {}) or {}
    labels = classification.get("labels", [])
    return {
        "doc_id": doc.get("id", ""),
        "source": doc.get("source", ""),
        "title": doc.get("title", ""),
        "neighborhood": geo.get("neighborhood", ""),
        "timestamp": doc.get("timestamp", ""),
        "category": labels[0] if labels else "",
        "sentiment_label": sentiment.get("label", "neutral"),
        "sentiment_score": sentiment.get("score", 0.5),
    }


def build_embed_text(doc: dict) -> str:
    """Build text string for embedding from doc title + truncated content."""
    title = doc.get("title", "")
    content = doc.get("content", "")[:EMBED_CONTENT_LIMIT]
    return f"{title} {content}".strip()
