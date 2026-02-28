"""GPU classification pipeline — DocClassifier + SentimentAnalyzer on T4.

Uses modal.Queue for event bus between pipelines and classifiers.
Modal features: @modal.batched, modal.Queue, @modal.cls, @modal.enter, gpu=T4
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import modal

from modal_app.volume import app, volume, classify_image, VOLUME_MOUNT, PROCESSED_DATA_PATH

# Event bus: pipelines push raw docs, classifier drains and enriches
doc_queue = modal.Queue.from_name("new-docs", create_if_missing=True)


@app.cls(gpu="T4", image=classify_image, scaledown_window=120, secrets=[modal.Secret.from_name("arize-secrets")])
class DocClassifier:
    """Zero-shot document classifier using facebook/bart-large-mnli (406M params)."""

    @modal.enter()
    def load_model(self):
        from modal_app.instrumentation import init_tracing, get_tracer
        init_tracing()
        self._tracer = get_tracer("alethia.classify")

        from transformers import pipeline
        self.classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=0,
        )

    @modal.batched(max_batch_size=32, wait_ms=2000)
    async def classify(self, texts: list[str]) -> list[dict]:
        """Classify documents into city intelligence categories."""
        span_ctx = self._tracer.start_as_current_span("doc-classify-batch") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            if span:
                span.set_attribute("openinference.span.kind", "CHAIN")
                span.set_attribute("llm.model_name", "facebook/bart-large-mnli")
                span.set_attribute("classify.batch_size", len(texts))

            labels = ["regulatory", "economic", "safety", "infrastructure", "community", "business"]
            results = self.classifier(texts, candidate_labels=labels, multi_label=True)
            if not isinstance(results, list):
                results = [results]
            output = [
                {"labels": r["labels"][:3], "scores": [round(s, 4) for s in r["scores"][:3]]}
                for r in results
            ]
            if span:
                span.set_attribute("classify.results_count", len(output))
            return output
        except Exception as e:
            if span:
                span.set_attribute("error", str(e))
            raise
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)


@app.cls(gpu="T4", image=classify_image, scaledown_window=120, secrets=[modal.Secret.from_name("arize-secrets")])
class SentimentAnalyzer:
    """Sentiment analysis using cardiffnlp/twitter-roberta-base-sentiment-latest."""

    @modal.enter()
    def load_model(self):
        from modal_app.instrumentation import init_tracing, get_tracer
        init_tracing()
        self._tracer = get_tracer("alethia.sentiment")

        from transformers import pipeline
        self.sentiment = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            device=0,
        )

    @modal.batched(max_batch_size=32, wait_ms=2000)
    async def analyze(self, texts: list[str]) -> list[dict]:
        """Analyze sentiment of documents."""
        span_ctx = self._tracer.start_as_current_span("sentiment-analyze-batch") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            if span:
                span.set_attribute("openinference.span.kind", "CHAIN")
                span.set_attribute("llm.model_name", "cardiffnlp/twitter-roberta-base-sentiment-latest")
                span.set_attribute("sentiment.batch_size", len(texts))

            results = self.sentiment(texts, truncation=True, max_length=512)
            output = [
                {"label": r["label"], "score": round(r["score"], 4)}
                for r in results
            ]
            if span:
                span.set_attribute("sentiment.results_count", len(output))
            return output
        except Exception as e:
            if span:
                span.set_attribute("error", str(e))
            raise
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)


@app.function(
    image=classify_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("arize-secrets")],
    schedule=modal.Period(minutes=2),
    timeout=300,
)
async def process_queue_batch():
    """Drain doc_queue and classify/analyze documents in batch.

    Pattern A: Queue + manual batch — pipelines push to Queue,
    this scheduled function drains and enriches via GPU classifiers.
    """
    from modal_app.instrumentation import init_tracing, get_tracer
    init_tracing()
    tracer = get_tracer("alethia.classify")

    docs = []
    while len(docs) < 100:
        try:
            doc = await doc_queue.get.aio(timeout=5)
            docs.append(doc)
        except Exception:
            break

    if not docs:
        print("Queue empty, nothing to classify")
        return 0

    span_ctx = tracer.start_as_current_span("process-queue-batch") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("pipeline.batch_size", len(docs))

        print(f"Draining queue: {len(docs)} documents to classify")

        classifier = DocClassifier()
        analyzer = SentimentAnalyzer()

        texts = [d.get("content", d.get("title", ""))[:512] for d in docs]

        # Run classification and sentiment in parallel via asyncio.gather
        classifications = await asyncio.gather(
            *[classifier.classify.remote.aio(text) for text in texts],
            return_exceptions=True,
        )
        sentiments = await asyncio.gather(
            *[analyzer.analyze.remote.aio(text) for text in texts],
            return_exceptions=True,
        )

        # Enrich documents with classifications
        enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
        enriched_dir.mkdir(parents=True, exist_ok=True)

        for i, doc in enumerate(docs):
            cls_result = classifications[i]
            sent_result = sentiments[i]

            if isinstance(cls_result, Exception):
                print(f"Classification error for doc {doc.get('id', i)}: {cls_result}")
                doc["classification"] = {"labels": [], "scores": []}
            else:
                doc["classification"] = cls_result

            if isinstance(sent_result, Exception):
                print(f"Sentiment error for doc {doc.get('id', i)}: {sent_result}")
                doc["sentiment"] = {"label": "neutral", "score": 0.5}
            else:
                doc["sentiment"] = sent_result

            out_path = enriched_dir / f"{doc.get('id', f'doc-{i}')}.json"
            out_path.write_text(json.dumps(doc, indent=2, default=str))

        await volume.commit.aio()
        print(f"Classified {len(docs)} documents: saved to {enriched_dir}")

        if span:
            span.set_attribute("pipeline.docs_classified", len(docs))
        return len(docs)
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)
