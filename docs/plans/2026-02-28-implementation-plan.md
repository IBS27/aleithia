# Alethia Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Alethia — an AI-powered regulatory intelligence platform for Chicago small businesses, with live data pipelines on Modal, RAG-based chat, and a polished dashboard UI.

**Architecture:** Monolith FastAPI backend + React SPA frontend. Modal handles all compute (7 data pipelines + Llama 3.1 8B + MiniLM embeddings). Supermemory stores user context. OpenAI generates chat responses. Cloudflare Pages hosts frontend.

**Tech Stack:** Python 3.11+, FastAPI, Modal, vLLM, sentence-transformers, OpenAI, Supermemory, React, Vite, Tailwind CSS, Cloudflare Pages

---

## Phase 1: Foundation

### Task 1: Scaffold FastAPI Backend

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/main.py`
- Create: `backend/config.py`
- Create: `backend/requirements.txt`
- Create: `backend/routers/__init__.py`
- Create: `backend/routers/health.py`
- Create: `backend/models/__init__.py`
- Create: `backend/services/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`

**Step 1: Create requirements.txt**

```
# backend/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
websockets==12.0
pydantic==2.9.0
pydantic-settings==2.5.0
httpx==0.27.0
openai==1.50.0
modal==0.64.0
python-dotenv==1.0.1
pytest==8.3.0
pytest-asyncio==0.24.0
```

**Step 2: Create config.py**

```python
# backend/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    supermemory_api_key: str = ""
    newsapi_key: str = ""
    yelp_api_key: str = ""
    google_places_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    modal_token_id: str = ""
    modal_token_secret: str = ""
    environment: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()
```

**Step 3: Create main.py with CORS and health router**

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import health

app = FastAPI(title="Alethia API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

**Step 4: Create health router**

```python
# backend/routers/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "alethia"}
```

**Step 5: Create empty __init__.py files**

Create empty `__init__.py` in: `backend/`, `backend/routers/`, `backend/models/`, `backend/services/`, `backend/tests/`

**Step 6: Write test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

**Step 7: Create .env.example**

```
# .env.example
OPENAI_API_KEY=
SUPERMEMORY_API_KEY=
NEWSAPI_KEY=
YELP_API_KEY=
GOOGLE_PLACES_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

**Step 8: Create .gitignore**

```
# .gitignore
__pycache__/
*.pyc
.env
venv/
node_modules/
dist/
.modal/
```

**Step 9: Run test**

```bash
cd /home/gt120/projects/hackillinois2026
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pytest backend/tests/test_health.py -v
```

Expected: PASS

**Step 10: Verify server starts**

```bash
uvicorn backend.main:app --reload --port 8000
# Visit http://localhost:8000/health → {"status": "ok", "service": "alethia"}
# Visit http://localhost:8000/docs → Swagger UI
```

**Step 11: Commit**

```bash
git add backend/ .env.example .gitignore
git commit -m "feat: scaffold FastAPI backend with health check"
```

---

### Task 2: Scaffold React Frontend with Tailwind

**Files:**
- Create: `frontend/` (via Vite scaffold)
- Modify: `frontend/src/App.jsx`
- Create: `frontend/src/components/Layout.jsx`
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`

**Step 1: Create Vite + React project**

```bash
cd /home/gt120/projects/hackillinois2026
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
```

**Step 2: Configure Tailwind via Vite plugin**

```javascript
// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

**Step 3: Set up Tailwind in index.css**

```css
/* frontend/src/index.css */
@import "tailwindcss";
```

**Step 4: Create Layout component**

```jsx
// frontend/src/components/Layout.jsx
export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center font-bold text-sm">
              A
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Alethia</h1>
          </div>
          <span className="text-sm text-gray-500">Regulatory Intelligence</span>
        </div>
      </header>
      <main className="max-w-7xl mx-auto">{children}</main>
      <footer className="border-t border-gray-800 px-6 py-3 text-center text-xs text-gray-600">
        This is not legal advice. Alethia provides informational analysis only.
      </footer>
    </div>
  );
}
```

**Step 5: Update App.jsx with layout**

```jsx
// frontend/src/App.jsx
import Layout from './components/Layout';

function App() {
  return (
    <Layout>
      <div className="flex h-[calc(100vh-8rem)]">
        <div className="w-2/5 border-r border-gray-800 p-4">
          <p className="text-gray-500">Chat panel</p>
        </div>
        <div className="w-3/5 p-4">
          <p className="text-gray-500">Dashboard panel</p>
        </div>
      </div>
    </Layout>
  );
}

export default App;
```

**Step 6: Verify frontend runs**

```bash
cd /home/gt120/projects/hackillinois2026/frontend
npm run dev
# Visit http://localhost:5173 → dark theme layout with Alethia header, two-panel split, footer disclaimer
```

**Step 7: Commit**

```bash
cd /home/gt120/projects/hackillinois2026
git add frontend/
git commit -m "feat: scaffold React frontend with Tailwind and split-panel layout"
```

---

## Phase 2: Modal Compute Layer

### Task 3: Deploy Embedding Model on Modal

**Files:**
- Create: `modal_app/__init__.py`
- Create: `modal_app/common.py`
- Create: `modal_app/embedding.py`

**Step 1: Create common Modal config**

```python
# modal_app/__init__.py
```

```python
# modal_app/common.py
import modal

app = modal.App("alethia")

volume = modal.Volume.from_name("alethia-data", create_if_missing=True)

VOLUME_PATH = "/data"
RAW_PATH = f"{VOLUME_PATH}/raw"
INDEX_PATH = f"{VOLUME_PATH}/index"
```

**Step 2: Create embedding service**

```python
# modal_app/embedding.py
import modal
from modal_app.common import app, volume, VOLUME_PATH, INDEX_PATH

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "sentence-transformers==3.0.0",
    "numpy",
    "faiss-cpu",
)


@app.cls(
    image=image,
    volumes={VOLUME_PATH: volume},
    gpu=None,  # MiniLM runs fine on CPU
    timeout=300,
)
class EmbeddingService:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    @modal.enter()
    def load_model(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(self.model_name)

    @modal.method()
    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    @modal.method()
    def embed_and_index(self, doc_id: str, text: str, metadata: dict) -> dict:
        import json
        import os

        embedding = self.model.encode([text], normalize_embeddings=True)[0]

        os.makedirs(f"{VOLUME_PATH}/embeddings", exist_ok=True)
        doc = {
            "id": doc_id,
            "text": text,
            "embedding": embedding.tolist(),
            "metadata": metadata,
        }
        with open(f"{VOLUME_PATH}/embeddings/{doc_id}.json", "w") as f:
            json.dump(doc, f)
        volume.commit()

        return {"id": doc_id, "status": "indexed"}

    @modal.method()
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        import json
        import glob
        import numpy as np

        query_emb = self.model.encode([query], normalize_embeddings=True)[0]

        results = []
        for path in glob.glob(f"{VOLUME_PATH}/embeddings/*.json"):
            with open(path) as f:
                doc = json.load(f)
            score = float(np.dot(query_emb, np.array(doc["embedding"])))
            results.append({
                "id": doc["id"],
                "text": doc["text"],
                "metadata": doc["metadata"],
                "score": score,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
```

**Step 3: Test locally with Modal**

```bash
cd /home/gt120/projects/hackillinois2026
modal run modal_app/embedding.py
```

**Step 4: Deploy to Modal**

```bash
modal deploy modal_app/embedding.py
```

**Step 5: Commit**

```bash
git add modal_app/
git commit -m "feat: deploy MiniLM embedding model on Modal with search"
```

---

### Task 4: Deploy Llama 3.1 8B on Modal

**Files:**
- Create: `modal_app/llm.py`

**Step 1: Create LLM service with vLLM**

```python
# modal_app/llm.py
import modal
from modal_app.common import app

vllm_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "vllm==0.6.0",
    "torch",
)

MODEL_ID = "meta-llama/Meta-Llama-3.1-8B-Instruct"


@app.cls(
    image=vllm_image,
    gpu=modal.gpu.A10G(),
    timeout=600,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    volumes={"/models": modal.Volume.from_name("alethia-models", create_if_missing=True)},
)
class LLMService:
    @modal.enter()
    def load_model(self):
        from vllm import LLM, SamplingParams
        self.llm = LLM(
            model=MODEL_ID,
            download_dir="/models",
            max_model_len=4096,
            dtype="half",
        )
        self.default_params = SamplingParams(
            temperature=0.3,
            max_tokens=1024,
            top_p=0.9,
        )

    @modal.method()
    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 1024) -> str:
        from vllm import SamplingParams

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Format as Llama 3.1 chat template
        formatted = self._format_chat(messages)

        params = SamplingParams(temperature=0.3, max_tokens=max_tokens, top_p=0.9)
        outputs = self.llm.generate([formatted], params)
        return outputs[0].outputs[0].text.strip()

    @modal.method()
    def analyze_document(self, text: str) -> dict:
        import json

        system = """You are a regulatory analyst. Analyze the given document and return a JSON object with:
- "category": one of "regulation", "news", "sentiment", "opportunity", "risk"
- "entities": list of businesses, neighborhoods, or regulation types mentioned
- "sentiment": "positive", "negative", or "neutral"
- "risk_score": 1-10 (10 = highest risk to small businesses)
- "summary": 2-3 sentence summary
- "action_items": list of recommended actions for a small business owner
Return ONLY valid JSON."""

        result = self.generate(text[:3000], system_prompt=system)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "category": "unknown",
                "entities": [],
                "sentiment": "neutral",
                "risk_score": 5,
                "summary": result[:200],
                "action_items": [],
            }

    def _format_chat(self, messages: list[dict]) -> str:
        formatted = "<|begin_of_text|>"
        for msg in messages:
            formatted += f"<|start_header_id|>{msg['role']}<|end_header_id|>\n\n{msg['content']}<|eot_id|>"
        formatted += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        return formatted
```

**Step 2: Create HuggingFace secret in Modal**

```bash
modal secret create huggingface-secret HUGGING_FACE_HUB_TOKEN=<your-hf-token>
```

Note: You need a HuggingFace account with access to Llama 3.1. Request access at https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct

**Step 3: Deploy**

```bash
modal deploy modal_app/llm.py
```

First deploy will download the model (~15GB). Subsequent cold starts use the cached model on the volume.

**Step 4: Commit**

```bash
git add modal_app/llm.py
git commit -m "feat: deploy Llama 3.1 8B on Modal with vLLM and document analysis"
```

---

## Phase 3: Data Pipelines

### Task 5: News Ingester Pipeline

**Files:**
- Create: `modal_app/pipelines/__init__.py`
- Create: `modal_app/pipelines/news.py`

**Step 1: Create news ingester**

```python
# modal_app/pipelines/__init__.py
```

```python
# modal_app/pipelines/news.py
import modal
from modal_app.common import app, volume, VOLUME_PATH, RAW_PATH

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "httpx",
    "feedparser",
)

CHICAGO_RSS_FEEDS = [
    "https://chicago.suntimes.com/rss/index.xml",
    "https://blockclubchicago.org/feed/",
]


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    schedule=modal.Period(minutes=30),
    secrets=[modal.Secret.from_name("alethia-api-keys")],
    timeout=120,
)
async def news_ingester():
    import httpx
    import feedparser
    import json
    import os
    from datetime import datetime
    from hashlib import sha256

    os.makedirs(f"{RAW_PATH}/news", exist_ok=True)
    ingested = []

    # RSS feeds
    for feed_url in CHICAGO_RSS_FEEDS:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(feed_url, timeout=15)
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:10]:
                doc_id = sha256(entry.get("link", entry.title).encode()).hexdigest()[:16]
                doc = {
                    "id": f"news-{doc_id}",
                    "source": feed_url,
                    "title": entry.get("title", ""),
                    "text": entry.get("summary", entry.get("description", "")),
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "ingested_at": datetime.utcnow().isoformat(),
                    "type": "news",
                    "geo": "chicago",
                }
                path = f"{RAW_PATH}/news/{doc['id']}.json"
                with open(path, "w") as f:
                    json.dump(doc, f)
                ingested.append(doc["id"])
        except Exception as e:
            print(f"Error fetching {feed_url}: {e}")

    # NewsAPI (if key available)
    newsapi_key = os.environ.get("NEWSAPI_KEY", "")
    if newsapi_key:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": "Chicago business OR Chicago regulation OR Chicago zoning",
                        "sortBy": "publishedAt",
                        "pageSize": 20,
                        "apiKey": newsapi_key,
                    },
                    timeout=15,
                )
            data = resp.json()
            for article in data.get("articles", []):
                doc_id = sha256(article["url"].encode()).hexdigest()[:16]
                doc = {
                    "id": f"news-{doc_id}",
                    "source": "newsapi",
                    "title": article.get("title", ""),
                    "text": article.get("description", "") + " " + (article.get("content", "") or ""),
                    "url": article["url"],
                    "published": article.get("publishedAt", ""),
                    "ingested_at": datetime.utcnow().isoformat(),
                    "type": "news",
                    "geo": "chicago",
                }
                path = f"{RAW_PATH}/news/{doc['id']}.json"
                with open(path, "w") as f:
                    json.dump(doc, f)
                ingested.append(doc["id"])
        except Exception as e:
            print(f"Error fetching NewsAPI: {e}")

    volume.commit()
    print(f"Ingested {len(ingested)} news articles")
    return ingested
```

**Step 2: Create Modal secret for API keys**

```bash
modal secret create alethia-api-keys \
  NEWSAPI_KEY=<your-key> \
  YELP_API_KEY=<your-key> \
  REDDIT_CLIENT_ID=<your-id> \
  REDDIT_CLIENT_SECRET=<your-secret> \
  GOOGLE_PLACES_API_KEY=<your-key>
```

**Step 3: Test manually**

```bash
modal run modal_app/pipelines/news.py::news_ingester
```

**Step 4: Deploy (starts 30-min cron)**

```bash
modal deploy modal_app/pipelines/news.py
```

**Step 5: Commit**

```bash
git add modal_app/pipelines/
git commit -m "feat: add news ingester pipeline (NewsAPI + RSS feeds, 30min cron)"
```

---

### Task 6: Social & Reviews Ingester Pipeline

**Files:**
- Create: `modal_app/pipelines/social.py`

**Step 1: Create social + reviews ingester**

```python
# modal_app/pipelines/social.py
import modal
from modal_app.common import app, volume, VOLUME_PATH, RAW_PATH

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "asyncpraw",
    "httpx",
)

CHICAGO_SUBREDDITS = ["chicago", "chicagofood", "ChicagoSuburbs"]


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    schedule=modal.Period(hours=1),
    secrets=[modal.Secret.from_name("alethia-api-keys")],
    timeout=180,
)
async def social_ingester():
    import json
    import os
    from datetime import datetime
    from hashlib import sha256

    os.makedirs(f"{RAW_PATH}/reddit", exist_ok=True)
    os.makedirs(f"{RAW_PATH}/reviews", exist_ok=True)
    ingested = []

    # Reddit
    reddit_id = os.environ.get("REDDIT_CLIENT_ID", "")
    reddit_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if reddit_id and reddit_secret:
        import asyncpraw
        reddit = asyncpraw.Reddit(
            client_id=reddit_id,
            client_secret=reddit_secret,
            user_agent="alethia/0.1",
        )
        try:
            for sub_name in CHICAGO_SUBREDDITS:
                subreddit = await reddit.subreddit(sub_name)
                async for post in subreddit.hot(limit=15):
                    doc_id = sha256(post.id.encode()).hexdigest()[:16]
                    doc = {
                        "id": f"reddit-{doc_id}",
                        "source": f"r/{sub_name}",
                        "title": post.title,
                        "text": post.selftext[:2000] if post.selftext else post.title,
                        "url": f"https://reddit.com{post.permalink}",
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": post.created_utc,
                        "ingested_at": datetime.utcnow().isoformat(),
                        "type": "social",
                        "geo": "chicago",
                    }
                    path = f"{RAW_PATH}/reddit/{doc['id']}.json"
                    with open(path, "w") as f:
                        json.dump(doc, f)
                    ingested.append(doc["id"])
        except Exception as e:
            print(f"Reddit error: {e}")
        finally:
            await reddit.close()

    # Yelp Fusion API
    yelp_key = os.environ.get("YELP_API_KEY", "")
    if yelp_key:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.yelp.com/v3/businesses/search",
                    headers={"Authorization": f"Bearer {yelp_key}"},
                    params={
                        "location": "Chicago, IL",
                        "sort_by": "rating",
                        "limit": 20,
                    },
                    timeout=15,
                )
            data = resp.json()
            for biz in data.get("businesses", []):
                doc_id = sha256(biz["id"].encode()).hexdigest()[:16]
                doc = {
                    "id": f"yelp-{doc_id}",
                    "source": "yelp",
                    "title": biz["name"],
                    "text": f"{biz['name']} - {', '.join(c['title'] for c in biz.get('categories', []))} - Rating: {biz.get('rating', 'N/A')} ({biz.get('review_count', 0)} reviews) - {biz.get('location', {}).get('display_address', [''])[0]}",
                    "rating": biz.get("rating"),
                    "review_count": biz.get("review_count"),
                    "location": biz.get("location", {}),
                    "ingested_at": datetime.utcnow().isoformat(),
                    "type": "review",
                    "geo": "chicago",
                }
                path = f"{RAW_PATH}/reviews/{doc['id']}.json"
                with open(path, "w") as f:
                    json.dump(doc, f)
                ingested.append(doc["id"])
        except Exception as e:
            print(f"Yelp error: {e}")

    volume.commit()
    print(f"Ingested {len(ingested)} social/review items")
    return ingested
```

**Step 2: Test and deploy**

```bash
modal run modal_app/pipelines/social.py::social_ingester
modal deploy modal_app/pipelines/social.py
```

**Step 3: Commit**

```bash
git add modal_app/pipelines/social.py
git commit -m "feat: add social ingester (Reddit + Yelp, hourly cron)"
```

---

### Task 7: Public Data Ingester Pipeline

**Files:**
- Create: `modal_app/pipelines/public_data.py`

**Step 1: Create Socrata/city data ingester**

```python
# modal_app/pipelines/public_data.py
import modal
from modal_app.common import app, volume, VOLUME_PATH, RAW_PATH

image = modal.Image.debian_slim(python_version="3.11").pip_install("httpx")

# Chicago Open Data Portal - Socrata API endpoints
DATASETS = {
    "business_licenses": "r5kz-chrr",
    "building_permits": "ydr8-5enu",
    "food_inspections": "4ijn-s7e5",
    "crimes": "ijzp-q8t2",
}

SOCRATA_BASE = "https://data.cityofchicago.org/resource"


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    schedule=modal.Period(days=1),
    timeout=300,
)
async def public_data_ingester():
    import httpx
    import json
    import os
    from datetime import datetime

    os.makedirs(f"{RAW_PATH}/public", exist_ok=True)
    ingested = []

    async with httpx.AsyncClient() as client:
        for name, dataset_id in DATASETS.items():
            try:
                resp = await client.get(
                    f"{SOCRATA_BASE}/{dataset_id}.json",
                    params={
                        "$limit": 50,
                        "$order": ":updated_at DESC",
                    },
                    timeout=30,
                )
                records = resp.json()
                doc = {
                    "id": f"public-{name}-{datetime.utcnow().strftime('%Y%m%d')}",
                    "source": f"data.cityofchicago.org/{dataset_id}",
                    "title": f"Chicago {name.replace('_', ' ').title()} - Latest",
                    "text": json.dumps(records[:10], indent=2)[:3000],
                    "record_count": len(records),
                    "dataset": name,
                    "ingested_at": datetime.utcnow().isoformat(),
                    "type": "public_data",
                    "geo": "chicago",
                }
                path = f"{RAW_PATH}/public/{doc['id']}.json"
                with open(path, "w") as f:
                    json.dump(doc, f)
                ingested.append(doc["id"])
            except Exception as e:
                print(f"Error fetching {name}: {e}")

    volume.commit()
    print(f"Ingested {len(ingested)} public datasets")
    return ingested
```

**Step 2: Test and deploy**

```bash
modal run modal_app/pipelines/public_data.py::public_data_ingester
modal deploy modal_app/pipelines/public_data.py
```

**Step 3: Commit**

```bash
git add modal_app/pipelines/public_data.py
git commit -m "feat: add public data ingester (Chicago Socrata API, daily cron)"
```

---

### Task 8: Processing Pipeline (Embed + Analyze + Index)

**Files:**
- Create: `modal_app/processing.py`

**Step 1: Create processing pipeline**

```python
# modal_app/processing.py
import modal
from modal_app.common import app, volume, VOLUME_PATH, RAW_PATH

image = modal.Image.debian_slim(python_version="3.11").pip_install("httpx")


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    schedule=modal.Period(hours=1),
    timeout=600,
)
async def process_new_documents():
    import json
    import os
    import glob

    processed_path = f"{VOLUME_PATH}/processed"
    os.makedirs(processed_path, exist_ok=True)

    # Find unprocessed docs
    raw_files = glob.glob(f"{RAW_PATH}/**/*.json", recursive=True)
    processed_ids = set()
    if os.path.exists(f"{processed_path}/manifest.json"):
        with open(f"{processed_path}/manifest.json") as f:
            processed_ids = set(json.load(f))

    new_docs = []
    for path in raw_files:
        with open(path) as f:
            doc = json.load(f)
        if doc["id"] not in processed_ids:
            new_docs.append(doc)

    if not new_docs:
        print("No new documents to process")
        return []

    print(f"Processing {len(new_docs)} new documents...")

    # Call embedding service
    from modal_app.embedding import EmbeddingService
    embedder = EmbeddingService()

    # Call LLM for analysis
    from modal_app.llm import LLMService
    llm = LLMService()

    results = []
    for doc in new_docs[:50]:  # batch limit
        text = f"{doc.get('title', '')} {doc.get('text', '')}"

        # Embed
        embed_result = embedder.embed_and_index.remote(
            doc_id=doc["id"],
            text=text[:1000],
            metadata={
                "type": doc.get("type", "unknown"),
                "source": doc.get("source", ""),
                "geo": doc.get("geo", ""),
                "ingested_at": doc.get("ingested_at", ""),
            },
        )

        # Analyze with LLM
        analysis = llm.analyze_document.remote(text[:3000])

        # Save processed result
        processed = {**doc, "analysis": analysis, "embedded": True}
        with open(f"{processed_path}/{doc['id']}.json", "w") as f:
            json.dump(processed, f)

        processed_ids.add(doc["id"])
        results.append(doc["id"])

    # Update manifest
    with open(f"{processed_path}/manifest.json", "w") as f:
        json.dump(list(processed_ids), f)

    volume.commit()
    print(f"Processed {len(results)} documents")
    return results
```

**Step 2: Test and deploy**

```bash
modal run modal_app/processing.py::process_new_documents
modal deploy modal_app/processing.py
```

**Step 3: Commit**

```bash
git add modal_app/processing.py
git commit -m "feat: add document processing pipeline (embed + analyze + index)"
```

---

## Phase 4: Backend Services

### Task 9: Supermemory Integration Service

**Files:**
- Create: `backend/services/supermemory.py`
- Create: `backend/models/business.py`
- Create: `backend/routers/business.py`
- Create: `backend/tests/test_business.py`

**Step 1: Create business models**

```python
# backend/models/business.py
from pydantic import BaseModel


class BusinessProfile(BaseModel):
    name: str
    business_type: str  # e.g., "restaurant", "retail", "tech startup"
    neighborhood: str  # e.g., "Lincoln Park", "Wicker Park"
    industry: str = ""
    size: str = "small"  # small, medium
    concerns: list[str] = []  # e.g., ["zoning", "food permits", "employment"]


class BusinessProfileResponse(BaseModel):
    user_id: str
    profile: BusinessProfile
    message: str
```

**Step 2: Create Supermemory service**

```python
# backend/services/supermemory.py
import httpx
from backend.config import settings

SUPERMEMORY_BASE = "https://api.supermemory.ai/v1"


class SupermemoryService:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {settings.supermemory_api_key}",
            "Content-Type": "application/json",
        }

    async def create_user_profile(self, user_id: str, profile: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPERMEMORY_BASE}/profiles",
                headers=self.headers,
                json={"userId": user_id, "profile": profile},
                timeout=10,
            )
            return resp.json()

    async def get_user_profile(self, user_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPERMEMORY_BASE}/profiles/{user_id}",
                headers=self.headers,
                timeout=10,
            )
            return resp.json()

    async def add_memory(self, user_id: str, content: str, metadata: dict = None) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPERMEMORY_BASE}/memories",
                headers=self.headers,
                json={
                    "userId": user_id,
                    "content": content,
                    "metadata": metadata or {},
                },
                timeout=10,
            )
            return resp.json()

    async def retrieve(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPERMEMORY_BASE}/retrieve",
                headers=self.headers,
                json={
                    "userId": user_id,
                    "query": query,
                    "topK": top_k,
                },
                timeout=10,
            )
            data = resp.json()
            return data.get("results", [])


supermemory = SupermemoryService()
```

**Step 3: Create business router**

```python
# backend/routers/business.py
import uuid
from fastapi import APIRouter, HTTPException

from backend.models.business import BusinessProfile, BusinessProfileResponse
from backend.services.supermemory import supermemory

router = APIRouter(prefix="/api/business", tags=["business"])


@router.post("/profile", response_model=BusinessProfileResponse)
async def create_profile(profile: BusinessProfile):
    user_id = str(uuid.uuid4())
    try:
        await supermemory.create_user_profile(user_id, profile.model_dump())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Supermemory error: {e}")

    return BusinessProfileResponse(
        user_id=user_id,
        profile=profile,
        message="Profile created successfully",
    )


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    try:
        return await supermemory.get_user_profile(user_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Supermemory error: {e}")
```

**Step 4: Register router in main.py**

Add to `backend/main.py`:

```python
from backend.routers import health, business

app.include_router(health.router)
app.include_router(business.router)
```

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat: add Supermemory integration and business profile endpoints"
```

---

### Task 10: RAG Query Service + Chat Router

**Files:**
- Create: `backend/services/rag.py`
- Create: `backend/services/openai_chat.py`
- Create: `backend/routers/chat.py`
- Modify: `backend/main.py`

**Step 1: Create OpenAI chat service**

```python
# backend/services/openai_chat.py
from openai import AsyncOpenAI
from backend.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are Alethia, a regulatory intelligence assistant for small business owners in Chicago.

You help users understand regulations, identify risks and opportunities, and make informed decisions.

Guidelines:
- Be direct and actionable
- Cite specific regulations or data sources when possible
- Always mention that this is not legal advice
- Focus on what the user should DO, not just what the rules say
- Be encouraging — small business owners are often overwhelmed

You will be given relevant context from regulatory databases, news, and public data. Use this context to ground your answers."""


async def generate_chat_response(query: str, context: str, user_profile: dict = None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_context = ""
    if user_profile:
        user_context = f"\nUser's business: {user_profile.get('business_type', 'unknown')} in {user_profile.get('neighborhood', 'Chicago')}\n"

    messages.append({
        "role": "user",
        "content": f"{user_context}\nRelevant context:\n{context}\n\nUser question: {query}",
    })

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        stream=True,
        max_tokens=1024,
    )
    return response


async def generate_chat_response_full(query: str, context: str, user_profile: dict = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_context = ""
    if user_profile:
        user_context = f"\nUser's business: {user_profile.get('business_type', 'unknown')} in {user_profile.get('neighborhood', 'Chicago')}\n"

    messages.append({
        "role": "user",
        "content": f"{user_context}\nRelevant context:\n{context}\n\nUser question: {query}",
    })

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=1024,
    )
    return response.choices[0].message.content
```

**Step 2: Create RAG orchestration service**

```python
# backend/services/rag.py
import modal
from backend.services.supermemory import supermemory


async def query_rag(user_id: str, query: str, top_k: int = 5) -> dict:
    """Orchestrate RAG: Modal search + Supermemory context → combined context"""

    # 1. Search Modal vector index
    embedding_cls = modal.Cls.lookup("alethia", "EmbeddingService")
    embedder = embedding_cls()
    modal_results = embedder.search.remote(query, top_k=top_k)

    # 2. Retrieve from Supermemory (user-specific context)
    try:
        sm_results = await supermemory.retrieve(user_id, query, top_k=3)
    except Exception:
        sm_results = []

    # 3. Get user profile from Supermemory
    try:
        profile = await supermemory.get_user_profile(user_id)
    except Exception:
        profile = {}

    # 4. Combine context
    context_parts = []

    for doc in modal_results:
        source = doc.get("metadata", {}).get("source", "unknown")
        context_parts.append(f"[{source}] {doc['text']}")

    for mem in sm_results:
        context_parts.append(f"[user memory] {mem.get('content', '')}")

    combined_context = "\n\n---\n\n".join(context_parts)

    return {
        "context": combined_context,
        "sources": modal_results,
        "memories": sm_results,
        "profile": profile,
    }
```

**Step 3: Create chat WebSocket router**

```python
# backend/routers/chat.py
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.rag import query_rag
from backend.services.openai_chat import generate_chat_response
from backend.services.supermemory import supermemory

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat/{user_id}")
async def chat_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            query = message.get("query", "")

            if not query:
                continue

            # 1. RAG: retrieve relevant context
            rag_result = await query_rag(user_id, query)

            # 2. Send sources first
            await websocket.send_text(json.dumps({
                "type": "sources",
                "sources": [
                    {"text": s["text"][:200], "source": s.get("metadata", {}).get("source", "")}
                    for s in rag_result["sources"][:3]
                ],
            }))

            # 3. Stream OpenAI response
            response = await generate_chat_response(
                query=query,
                context=rag_result["context"],
                user_profile=rag_result.get("profile"),
            )

            full_response = ""
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token
                    await websocket.send_text(json.dumps({
                        "type": "token",
                        "content": token,
                    }))

            # 4. Send completion signal
            await websocket.send_text(json.dumps({"type": "done"}))

            # 5. Save to Supermemory memory
            try:
                await supermemory.add_memory(
                    user_id,
                    f"Q: {query}\nA: {full_response[:500]}",
                    {"type": "chat"},
                )
            except Exception:
                pass  # Non-critical

    except WebSocketDisconnect:
        pass
```

**Step 4: Create REST analysis router**

```python
# backend/routers/analysis.py
from fastapi import APIRouter

from backend.services.rag import query_rag
from backend.services.openai_chat import generate_chat_response_full

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/dashboard/{user_id}")
async def get_dashboard_data(user_id: str):
    """Get dashboard data: risk scores, action items, local pulse"""
    rag_result = await query_rag(user_id, "What are the latest regulatory risks and opportunities for my business?")

    summary = await generate_chat_response_full(
        query="Provide a brief risk analysis with action items",
        context=rag_result["context"],
        user_profile=rag_result.get("profile"),
    )

    return {
        "risk_summary": summary,
        "sources": rag_result["sources"][:5],
        "source_count": len(rag_result["sources"]),
    }
```

**Step 5: Register all routers in main.py**

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import health, business, chat, analysis

app = FastAPI(title="Alethia API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(business.router)
app.include_router(chat.router)
app.include_router(analysis.router)
```

**Step 6: Commit**

```bash
git add backend/
git commit -m "feat: add RAG query service, OpenAI chat, and WebSocket streaming"
```

---

## Phase 5: Frontend

### Task 11: Onboarding Flow

**Files:**
- Create: `frontend/src/components/Onboarding/Onboarding.jsx`
- Create: `frontend/src/api/client.js`
- Modify: `frontend/src/App.jsx`

**Step 1: Create API client**

```javascript
// frontend/src/api/client.js
const API_BASE = '/api';

export async function createProfile(profile) {
  const resp = await fetch(`${API_BASE}/business/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  return resp.json();
}

export async function getDashboard(userId) {
  const resp = await fetch(`${API_BASE}/analysis/dashboard/${userId}`);
  return resp.json();
}

export function connectChat(userId, onMessage) {
  const ws = new WebSocket(`ws://${window.location.host}/ws/chat/${userId}`);
  ws.onmessage = (event) => onMessage(JSON.parse(event.data));
  return ws;
}
```

**Step 2: Create Onboarding component**

```jsx
// frontend/src/components/Onboarding/Onboarding.jsx
import { useState } from 'react';
import { createProfile } from '../../api/client';

const BUSINESS_TYPES = [
  'Restaurant / Food Service',
  'Retail Store',
  'Tech Startup',
  'Professional Services',
  'Construction / Trades',
  'Health & Wellness',
  'Other',
];

const NEIGHBORHOODS = [
  'Lincoln Park', 'Wicker Park', 'Logan Square', 'Hyde Park',
  'Loop', 'River North', 'Pilsen', 'Bridgeport',
  'Andersonville', 'Lakeview', 'West Loop', 'South Loop',
];

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState({
    name: '',
    business_type: '',
    neighborhood: '',
    concerns: [],
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const result = await createProfile(profile);
      onComplete(result.user_id, result.profile);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[80vh]">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-bold">Welcome to Alethia</h2>
          <p className="text-gray-400">Tell us about your business so we can find what matters to you.</p>
        </div>

        {step === 0 && (
          <div className="space-y-4">
            <input
              type="text"
              placeholder="Business name"
              value={profile.name}
              onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              className="w-full px-4 py-3 bg-gray-900 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500"
            />
            <div className="grid grid-cols-2 gap-2">
              {BUSINESS_TYPES.map((type) => (
                <button
                  key={type}
                  onClick={() => { setProfile({ ...profile, business_type: type }); setStep(1); }}
                  className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
                    profile.business_type === type
                      ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                      : 'border-gray-700 hover:border-gray-500'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">Where is your business located?</p>
            <div className="grid grid-cols-3 gap-2">
              {NEIGHBORHOODS.map((n) => (
                <button
                  key={n}
                  onClick={() => { setProfile({ ...profile, neighborhood: n }); setStep(2); }}
                  className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
                    profile.neighborhood === n
                      ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                      : 'border-gray-700 hover:border-gray-500'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">Ready to go!</p>
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-700 space-y-2">
              <p><span className="text-gray-500">Business:</span> {profile.name || 'Unnamed'}</p>
              <p><span className="text-gray-500">Type:</span> {profile.business_type}</p>
              <p><span className="text-gray-500">Location:</span> {profile.neighborhood}</p>
            </div>
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {loading ? 'Setting up...' : 'Start Exploring'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Update App.jsx with routing**

```jsx
// frontend/src/App.jsx
import { useState } from 'react';
import Layout from './components/Layout';
import Onboarding from './components/Onboarding/Onboarding';

function App() {
  const [userId, setUserId] = useState(null);
  const [profile, setProfile] = useState(null);

  const handleOnboardComplete = (id, prof) => {
    setUserId(id);
    setProfile(prof);
  };

  if (!userId) {
    return (
      <Layout>
        <Onboarding onComplete={handleOnboardComplete} />
      </Layout>
    );
  }

  return (
    <Layout businessName={profile?.name} neighborhood={profile?.neighborhood}>
      <div className="flex h-[calc(100vh-8rem)]">
        <div className="w-2/5 border-r border-gray-800 p-4">
          <p className="text-gray-500">Chat panel — Task 12</p>
        </div>
        <div className="w-3/5 p-4">
          <p className="text-gray-500">Dashboard panel — Task 13</p>
        </div>
      </div>
    </Layout>
  );
}

export default App;
```

**Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add onboarding flow with business type and neighborhood selection"
```

---

### Task 12: Chat Panel with WebSocket Streaming

**Files:**
- Create: `frontend/src/components/Chat/ChatPanel.jsx`
- Create: `frontend/src/components/Chat/ChatMessage.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create ChatMessage component**

```jsx
// frontend/src/components/Chat/ChatMessage.jsx
export default function ChatMessage({ role, content, sources }) {
  return (
    <div className={`flex gap-3 ${role === 'user' ? 'justify-end' : ''}`}>
      {role === 'assistant' && (
        <div className="w-7 h-7 bg-indigo-500 rounded-full flex items-center justify-center text-xs font-bold shrink-0">A</div>
      )}
      <div className={`max-w-[80%] space-y-2 ${
        role === 'user'
          ? 'bg-gray-800 rounded-2xl rounded-br-md px-4 py-2'
          : 'text-gray-200'
      }`}>
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
        {sources && sources.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {sources.map((s, i) => (
              <span key={i} className="text-xs px-2 py-0.5 bg-gray-800 rounded text-gray-400">
                {s.source}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Create ChatPanel component**

```jsx
// frontend/src/components/Chat/ChatPanel.jsx
import { useState, useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';

export default function ChatPanel({ userId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const wsRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws/chat/${userId}`);
    wsRef.current = ws;
    return () => ws.close();
  }, [userId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = () => {
    if (!input.trim() || isStreaming) return;
    const query = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setIsStreaming(true);

    let currentResponse = '';
    let currentSources = [];

    const handler = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'sources') {
        currentSources = data.sources;
      } else if (data.type === 'token') {
        currentResponse += data.content;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant') {
            updated[updated.length - 1] = { ...last, content: currentResponse, sources: currentSources };
          } else {
            updated.push({ role: 'assistant', content: currentResponse, sources: currentSources });
          }
          return updated;
        });
      } else if (data.type === 'done') {
        setIsStreaming(false);
        wsRef.current.removeEventListener('message', handler);
      }
    };

    wsRef.current.addEventListener('message', handler);
    wsRef.current.send(JSON.stringify({ query }));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-4 p-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-600 mt-20 space-y-2">
            <p className="text-lg">Ask Alethia anything</p>
            <p className="text-sm">e.g. "What permits do I need to open a restaurant in Lincoln Park?"</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <ChatMessage key={i} {...msg} />
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="p-4 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Ask about regulations, permits, risks..."
            className="flex-1 px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500 text-sm"
            disabled={isStreaming}
          />
          <button
            onClick={sendMessage}
            disabled={isStreaming || !input.trim()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Wire into App.jsx**

Replace the chat placeholder in `App.jsx`:

```jsx
import ChatPanel from './components/Chat/ChatPanel';
// ... in the main view:
<div className="w-2/5 border-r border-gray-800">
  <ChatPanel userId={userId} />
</div>
```

**Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add chat panel with WebSocket streaming and source citations"
```

---

### Task 13: Dashboard Panel

**Files:**
- Create: `frontend/src/components/Dashboard/DashboardPanel.jsx`
- Create: `frontend/src/components/Dashboard/RiskCard.jsx`
- Create: `frontend/src/components/Dashboard/LocalPulse.jsx`
- Modify: `frontend/src/App.jsx`

**Step 1: Create RiskCard**

```jsx
// frontend/src/components/Dashboard/RiskCard.jsx
export default function RiskCard({ title, score, description, items }) {
  const color = score >= 7 ? 'red' : score >= 4 ? 'yellow' : 'green';
  const colors = {
    red: 'border-red-500/30 bg-red-500/5',
    yellow: 'border-yellow-500/30 bg-yellow-500/5',
    green: 'border-green-500/30 bg-green-500/5',
  };

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${colors[color]}`}>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">{title}</h3>
        <div className="flex items-center gap-2">
          <div className="w-16 h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${color === 'red' ? 'bg-red-500' : color === 'yellow' ? 'bg-yellow-500' : 'bg-green-500'}`}
              style={{ width: `${score * 10}%` }}
            />
          </div>
          <span className="text-xs text-gray-400">{score}/10</span>
        </div>
      </div>
      {description && <p className="text-xs text-gray-400">{description}</p>}
      {items && items.length > 0 && (
        <ul className="space-y-1">
          {items.map((item, i) => (
            <li key={i} className="flex items-center gap-2 text-xs text-gray-300">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-600" />
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

**Step 2: Create LocalPulse**

```jsx
// frontend/src/components/Dashboard/LocalPulse.jsx
export default function LocalPulse({ sources }) {
  if (!sources || sources.length === 0) {
    return (
      <div className="rounded-xl border border-gray-800 p-4">
        <h3 className="font-semibold text-sm mb-2">Local Pulse</h3>
        <p className="text-xs text-gray-500">Loading latest data...</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-800 p-4 space-y-3">
      <h3 className="font-semibold text-sm">Local Pulse</h3>
      <div className="space-y-2">
        {sources.map((s, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-500 shrink-0">
              {s.source}
            </span>
            <p className="text-gray-300 line-clamp-2">{s.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 3: Create DashboardPanel**

```jsx
// frontend/src/components/Dashboard/DashboardPanel.jsx
import { useState, useEffect } from 'react';
import { getDashboard } from '../../api/client';
import RiskCard from './RiskCard';
import LocalPulse from './LocalPulse';

export default function DashboardPanel({ userId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboard(userId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-pulse text-gray-500">Analyzing your regulatory landscape...</div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold">Your Dashboard</h2>

      <RiskCard
        title="Regulatory Risk Score"
        score={7}
        description={data?.risk_summary?.slice(0, 150)}
        items={["Review latest zoning changes", "Check permit renewal dates", "Monitor new employment regulations"]}
      />

      <RiskCard
        title="Opportunities"
        score={3}
        description="New small business grants available in your area"
        items={["Chicago Small Business Improvement Fund", "Neighborhood Opportunity Fund"]}
      />

      <LocalPulse sources={data?.sources?.slice(0, 5)} />
    </div>
  );
}
```

**Step 4: Wire into App.jsx**

Replace dashboard placeholder:

```jsx
import DashboardPanel from './components/Dashboard/DashboardPanel';
// ... in main view:
<div className="w-3/5">
  <DashboardPanel userId={userId} />
</div>
```

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: add dashboard panel with risk cards and local pulse feed"
```

---

## Phase 6: Deployment

### Task 14: Deploy to Cloudflare Pages + Railway

**Step 1: Build frontend**

```bash
cd /home/gt120/projects/hackillinois2026/frontend
npm run build
```

**Step 2: Deploy frontend to Cloudflare Pages**

```bash
npx wrangler pages project create alethia
npx wrangler pages deploy dist/ --project-name alethia
```

**Step 3: Deploy backend to Railway**

Create `Procfile` in project root:
```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Create `runtime.txt`:
```
python-3.11
```

Push to Railway via GitHub integration or CLI.

**Step 4: Register alethia.tech domain**

Register at get.tech, point DNS to Cloudflare Pages.

**Step 5: Commit**

```bash
git add Procfile runtime.txt
git commit -m "feat: add deployment config (Cloudflare Pages + Railway)"
```

---

### Task 15: Politics Ingester Pipeline (Stretch)

**Files:**
- Create: `modal_app/pipelines/politics.py`

This task is a stretch goal — implement if time permits after core features work end-to-end. Uses Chicago Legistar API + PDF parsing with pymupdf for city council transcripts.

---

### Task 16: Final Polish + Demo Prep

**Step 1:** Verify all data pipelines are running on Modal cron
**Step 2:** Test full user flow: onboard → chat → dashboard
**Step 3:** Add loading states, error boundaries, transitions
**Step 4:** Test on mobile viewport (responsive)
**Step 5:** Prepare demo script per `docs/agent/learnings.md` Demo Script Framework
**Step 6:** Record backup demo video in case of live issues

---

## Execution Order & Dependencies

```
Task 1 (Backend) ──┐
                   ├──→ Task 9 (Supermemory) ──→ Task 10 (RAG + Chat) ──→ Task 14 (Deploy)
Task 2 (Frontend) ─┤
                   │
Task 3 (Embedding) ┤
Task 4 (Llama)    ─┼──→ Task 8 (Processing) ──→ Task 10 (RAG + Chat)
Task 5 (News)     ─┤
Task 6 (Social)   ─┤
Task 7 (Public)   ─┘

Task 11 (Onboarding) ──→ Task 12 (Chat UI) ──→ Task 13 (Dashboard) ──→ Task 14 (Deploy)
```

**Parallelizable:** Tasks 1-7 can all run in parallel. Tasks 11-13 are sequential (frontend). Task 8 depends on Tasks 3-7. Task 10 depends on Tasks 8-9.
