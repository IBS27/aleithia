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


# ---------------------------------------------------------------------------
# VectorAI DB Modal Service
# ---------------------------------------------------------------------------

import modal

from modal_app.volume import app, volume, vectordb_image


VECTORDB_DATA_PATH = "/data/vectordb"

# Source-specific collections + unified enriched collection
COLLECTIONS = [
    "news", "politics", "reddit", "reviews", "realestate",
    "federal_register", "tiktok", "demographics", "public_data",
    "traffic", "cctv", "vision", "parking", "worldpop", "enriched",
]


@app.cls(
    image=vectordb_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("arize-secrets")],
    min_containers=1,
    scaledown_window=300,
    timeout=120,
)
class VectorDBService:
    """Actian VectorAI DB service with sentence-transformer embeddings.

    Manages the VectorAI DB process, creates collections, and provides
    embed/upsert/search methods for the agent swarm and enrichment pipeline.
    """

    @modal.enter()
    def startup(self):
        """Start VectorAI DB process and connect client."""
        import subprocess
        from pathlib import Path
        from sentence_transformers import SentenceTransformer

        from modal_app.instrumentation import init_tracing, get_tracer
        init_tracing()
        self._tracer = get_tracer("alethia.vectordb")

        # Ensure data directory exists
        Path(VECTORDB_DATA_PATH).mkdir(parents=True, exist_ok=True)

        # Start VectorAI DB server process (background)
        self._server_proc = subprocess.Popen(
            ["vectoraidb", "--data-dir", VECTORDB_DATA_PATH, "--port", "50051"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Load embedding model
        self._embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        # Wait for server to be ready, then connect
        import time
        from cortex.client import CortexClient
        from cortex.models import DistanceMetric

        for attempt in range(30):
            try:
                self._client = CortexClient(host="localhost", port=50051)
                self._client.health_check()
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("VectorAI DB failed to start within 30s")

        # Create collections if they don't exist
        for collection_name in COLLECTIONS:
            if not self._client.has_collection(collection_name):
                self._client.create_collection(
                    name=collection_name,
                    dimension=VECTOR_DIMENSION,
                    distance_metric=DistanceMetric.COSINE,
                )

        # Mark as healthy
        global _vectordb_healthy
        _vectordb_healthy = True
        print(f"VectorAI DB ready: {len(COLLECTIONS)} collections initialized")

    @modal.method()
    def embed_text(self, text: str) -> list[float]:
        """Embed text using all-MiniLM-L6-v2. Returns 384-dim float vector."""
        span_ctx = self._tracer.start_as_current_span("vectordb.embed") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            embedding = self._embedder.encode(text, normalize_embeddings=True)
            if span:
                span.set_attribute("vectordb.text_length", len(text))
            return embedding.tolist()
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts. Returns list of 384-dim float vectors."""
        span_ctx = self._tracer.start_as_current_span("vectordb.embed_batch") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            embeddings = self._embedder.encode(texts, normalize_embeddings=True, batch_size=32)
            if span:
                span.set_attribute("vectordb.batch_size", len(texts))
            return [e.tolist() for e in embeddings]
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def upsert_doc(self, doc_id: str, embedding: list[float], payload: dict, collection: str = "enriched"):
        """Upsert a single document vector + payload into a collection."""
        span_ctx = self._tracer.start_as_current_span("vectordb.upsert") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            self._client.upsert(
                collection=collection,
                id=doc_id,
                vector=embedding,
                payload=payload,
            )
            if span:
                span.set_attribute("vectordb.collection", collection)
                span.set_attribute("vectordb.doc_id", doc_id)
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def batch_upsert_docs(self, doc_ids: list[str], embeddings: list[list[float]], payloads: list[dict], collection: str = "enriched"):
        """Batch upsert documents into a collection."""
        span_ctx = self._tracer.start_as_current_span("vectordb.batch_upsert") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            self._client.batch_upsert(
                collection=collection,
                ids=doc_ids,
                vectors=embeddings,
                payloads=payloads,
            )
            self._client.flush(collection)
            if span:
                span.set_attribute("vectordb.collection", collection)
                span.set_attribute("vectordb.batch_size", len(doc_ids))
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def search(self, query_embedding: list[float], collection: str = "enriched", top_k: int = 20, filter_dict: dict | None = None) -> list[dict]:
        """Semantic search with optional payload filters.

        Args:
            query_embedding: 384-dim query vector
            collection: Collection name to search
            top_k: Number of results to return
            filter_dict: Optional filter spec, e.g. {"neighborhood": "Loop"}

        Returns:
            List of dicts with keys: id, score, payload
        """
        span_ctx = self._tracer.start_as_current_span("vectordb.search") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            if filter_dict:
                from cortex.filters import Filter, Field
                f = Filter()
                for key, value in filter_dict.items():
                    f = f.must(Field(key).eq(value))
                results = self._client.search_filtered(collection, query_embedding, f, top_k=top_k)
            else:
                results = self._client.search(collection, query_embedding, top_k=top_k)

            output = [
                {"id": r.id, "score": r.score, "payload": r.payload}
                for r in results
            ]
            if span:
                span.set_attribute("vectordb.collection", collection)
                span.set_attribute("vectordb.top_k", top_k)
                span.set_attribute("vectordb.results_count", len(output))
                span.set_attribute("vectordb.has_filter", bool(filter_dict))
            return output
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def search_neighborhood(self, query_embedding: list[float], neighborhood: str, top_k: int = 50) -> list[dict]:
        """Convenience: search enriched collection filtered by neighborhood."""
        span_ctx = self._tracer.start_as_current_span("vectordb.search_neighborhood") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            results = self.search.local(
                query_embedding=query_embedding,
                collection="enriched",
                top_k=top_k,
                filter_dict={"neighborhood": neighborhood},
            )
            if span:
                span.set_attribute("vectordb.neighborhood", neighborhood)
                span.set_attribute("vectordb.results_count", len(results))
            return results
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def health_check(self) -> dict:
        """Return health status and collection stats."""
        span_ctx = self._tracer.start_as_current_span("vectordb.health_check") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            self._client.health_check()
            stats = {}
            for name in COLLECTIONS:
                try:
                    count = self._client.count(name)
                    stats[name] = count
                except Exception:
                    stats[name] = -1
            if span:
                span.set_attribute("vectordb.status", "healthy")
            return {"status": "healthy", "collections": stats}
        except Exception as e:
            if span:
                span.set_attribute("vectordb.status", "unhealthy")
                span.set_attribute("error", str(e))
            return {"status": "unhealthy", "error": str(e)}
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)


@app.function(
    image=vectordb_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("arize-secrets")],
    timeout=600,
)
async def backfill_vectordb():
    """One-time backfill: read all enriched docs from volume and upsert to VectorAI DB.

    Run manually after initial deployment:
        modal run -m modal_app modal_app.vectordb::backfill_vectordb
    """
    import json
    from pathlib import Path

    enriched_dir = Path("/data/processed/enriched")
    if not enriched_dir.exists():
        print("No enriched directory found")
        return 0

    json_files = list(enriched_dir.rglob("*.json"))
    print(f"Backfill: found {len(json_files)} enriched documents")

    vdb = VectorDBService()
    batch_size = 32
    total_upserted = 0

    for i in range(0, len(json_files), batch_size):
        batch_files = json_files[i:i + batch_size]
        docs = []
        for f in batch_files:
            try:
                doc = json.loads(f.read_text())
                if isinstance(doc, dict):
                    docs.append(doc)
            except Exception:
                continue

        if not docs:
            continue

        texts = [build_embed_text(d) for d in docs]
        embeddings = vdb.embed_batch.remote(texts)
        doc_ids = [d.get("id", f"backfill-{i+j}") for j, d in enumerate(docs)]
        payloads = [
            build_payload(d, d.get("classification", {}), d.get("sentiment", {}))
            for d in docs
        ]
        vdb.batch_upsert_docs.remote(doc_ids, embeddings, payloads, "enriched")
        total_upserted += len(docs)
        print(f"Backfill: {total_upserted}/{len(json_files)} upserted")

    print(f"Backfill complete: {total_upserted} documents indexed")
    return total_upserted
