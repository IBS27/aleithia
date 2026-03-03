# Aleithia: Bridging the Regulatory and Analytical Divide

> **Democratizing data-driven expertise for small business owners.**

The modern operational environment for businesses is characterized by immense complexity. Entities must navigate a vast, interlocking web of constraints spanning multiple jurisdictions—federal, state, and local—covering everything from stringent employment law to evolving consumer safety standards and taxation requirements. 

**Aleithia** is designed to bridge the inequity between large firms with massive legal resources and small business owners who need the same data-driven insights to thrive.

---

## 🌟 Our Vision
Aleithia is an intelligent platform that:
* **Aggregates** disparate regulatory, political, and consumer sentiment data.
* **Analyzes** data using advanced AI/ML to identify critical risks.
* **Translates** complex findings into actionable, context-specific recommendations.

---

## 🏗️ Architecture Overview

The backend architecture leverages **Modal’s** asynchronous job functionalities. A swarm of jobs fetches news across relevant sources in Python, scheduled periodically, while distributed AI inference parses this data into detailed assessments in seconds.

### ⚡ Modal — Elastic Serverless Compute
The backbone of Aleithia consists of **33 serverless functions** leveraging 21 distinct Modal features:

* **GPU Inference:** * `Qwen3-8B AWQ (INT4)` self-hosted on **H100** via vLLM. 
    * `<3s cold starts` via `@modal.enter(snap=True)` memory snapshots.
    * `bart-large-mnli` + `roberta` classifiers on **T4 GPUs** using `@modal.batched` (10x cost efficiency).
* **Computer Vision:** `YOLOv8n` (CCTV) and `SegFormer-b5` + `YOLOv8m` (Satellite parking) on T4 instances.
* **Event Bus:** `modal.Queue` decouples CPU-bound ingestion from GPU enrichment.
* **Recursive Agents:** Lead Analyst scores docs; high-impact events (7+/10) trigger `.spawn()` fan-out to 4 parallel worker agents.
* **Self-Healing:** `modal.Period` reconciler checks health metrics every 5 min.

### 🧠 Supermemory — Unified Graph-RAG
Replaces the traditional Postgres + Pinecone + Redis stack with a single Graph-RAG system:
* **Hierarchical Isolation:** Separates `chicago_data` (world knowledge) from `user_{id}` (personal context).
* **State Mutation:** Handles temporal updates (changing regulations) without re-indexing.
* **Context Injection:** Automatically connects Reddit sentiment to City Council hearings for personalized responses.

### 🛠️ The Tech Stack
| Component | Technology | Role |
| :--- | :--- | :--- |
| **Vector DB** | Actian VectorAI | HNSW-indexed 384-dim embeddings for sub-15ms retrieval. |
| **Tracing** | OpenTelemetry | W3C trace context propagation across all Modal containers. |
| **Sandbox** | E2B | Isolated cloud sandboxes for untrusted agent analysis code. |
| **Hybrid LLM** | OpenAI GPT-4o | Specialized for Deep Dives, Python script generation, and Vision. |

---

## 🎨 Frontend
Built with **React 19 + TypeScript + Vite + Tailwind CSS v4**, featuring:
* **Streaming Chat:** Real-time responses with inline process flow traces.
* **Risk Scoring:** ISO 31000-aligned, 6 MCDA dimensions with sigmoid-normalization.
* **Visual Intelligence:** Satellite parking detection and live IDOT highway traffic cards.
* **Knowledge Graph:** Interactive drag-and-filter node visualization.
* **Professional Exports:** 9-section "Investment Committee" proposal format in PDF.

---

## 🚧 Challenges
* **Heatmap Rendering:** Required a custom compression pipeline for Mapbox GeoJSON to aggregate per-neighborhood stats.
* **Data Scarcity:** Solved for lack of street-level CCTV by sourcing "walk-in potential" from CTA L-station ridership data.
* **Observability:** Built W3C context propagation from scratch to link spans across the serverless orchestrator.

---

## 🚀 What's Next?
* **Global Expansion:** Identifying higher-quality data sources beyond the Chicago area to support global regions.
* **Predictive Analytics:** Developing deeper anomaly detection to provide founders with prospective locale-specific insights.
