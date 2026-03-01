import MemGraph from './MemGraph'

interface Props {
  onBack: () => void
}

const SECTION_HEADER = 'text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/30 mb-4'
const SECTION_TITLE = 'text-2xl sm:text-3xl font-bold tracking-tight text-white mb-6'
const BODY = 'text-sm text-white/60 leading-relaxed space-y-3'
const CODE = 'font-mono text-xs bg-white/[0.06] border border-white/[0.08] rounded px-2 py-1 text-white/80'
const CARD = 'border border-white/[0.06] rounded-lg p-6 bg-white/[0.02]'

export default function HowItWorks({ onBack }: Props) {
  return (
    <div className="min-h-screen bg-[#06080d] text-white">
      {/* Nav */}
      <nav className="sticky top-0 z-50 flex items-center justify-between px-10 py-5 bg-[#06080d]/95 backdrop-blur-md border-b border-white/[0.06]">
        <button
          type="button"
          onClick={onBack}
          className="text-lg font-semibold tracking-tight text-white uppercase hover:text-white/80 transition-colors cursor-pointer"
        >
          Aleithia
        </button>
        <button
          type="button"
          onClick={onBack}
          className="px-4 py-2 text-sm font-medium border border-white/20 text-white/80 hover:text-white hover:border-white/40 transition-colors cursor-pointer"
        >
          Back
        </button>
      </nav>

      <main className="max-w-4xl mx-auto px-10 py-16">
        <p className={SECTION_HEADER}>Pipeline Overview</p>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white mb-4">
          Architecture & Backend Logic
        </h1>
        <p className="text-base text-white/50 mb-16">
          Aleithia ingests Chicago-area data, enriches it with GPU models, and delivers insights through an agent swarm. All compute runs on Modal.
        </p>

        {/* Architecture overview */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Architecture Overview</h2>
          <div className={CARD}>
            <pre className="text-xs font-mono text-white/70 overflow-x-auto whitespace-pre">
{`User → FastAPI (Modal @modal.asgi_app)
         ↓
    Modal Layer
    ├── Ingestion (10 pipelines) → doc_queue
    ├── Enrichment (DocClassifier + SentimentAnalyzer on T4)
    ├── LLM (Qwen3 8B on H100 via vLLM)
    └── Agent Swarm (.spawn() fan-out)
         ↓
    Supermemory (RAG, user profiles, doc sync)`}
            </pre>
          </div>
          <p className={`${BODY} mt-4`}>
            Pipelines push documents to <span className={CODE}>modal.Queue</span>. The classifier drains the queue every 2 minutes. Enriched docs are written to Modal Volume. The agent swarm fans out at query time via <span className={CODE}>.spawn()</span>, gathers results, and synthesizes with the LLM.
          </p>
        </section>
      </main>

      <MemGraph />

      <div className="max-w-4xl mx-auto px-10 py-16">
        {/* Ingestion layer */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Ingestion Layer</h2>
          <p className={BODY}>
            10 Modal cron/on-demand functions scrape heterogeneous sources and normalize into a common <span className={CODE}>Document</span> schema. Each pipeline uses <span className={CODE}>FallbackChain</span> for resilient fetching and <span className={CODE}>SeenSet</span> for deduplication (10k cap per source).
          </p>
          <div className="mt-6 space-y-4">
            {[
              { name: 'news_ingester', schedule: '30 min cron', file: 'pipelines/news.py', desc: 'RSS + NewsAPI (Block Club, Tribune, Sun-Times, Crain\'s, Patch)' },
              { name: 'reddit_ingester', schedule: '1 hr cron', file: 'pipelines/reddit.py', desc: 'r/chicago, r/chicagofood, r/ChicagoNWside, r/SouthSideChicago' },
              { name: 'public_data_ingester', schedule: 'Daily cron', file: 'pipelines/public_data.py', desc: 'Chicago Data Portal (permits, licenses, inspections, CTA ridership)' },
              { name: 'politics_ingester', schedule: 'On-demand', file: 'pipelines/politics.py', desc: 'Legistar, Zoning Board PDFs, Plan Commission transcripts' },
              { name: 'demographics_ingester', schedule: 'On-demand', file: 'pipelines/demographics.py', desc: 'Census ACS 5-year estimates per community area' },
              { name: 'review_ingester', schedule: 'On-demand', file: 'pipelines/reviews.py', desc: 'Yelp + Google Places (8 neighborhoods, 9 categories)' },
              { name: 'realestate_ingester', schedule: 'On-demand', file: 'pipelines/realestate.py', desc: 'LoopNet + placeholder listings' },
              { name: 'federal_register_ingester', schedule: 'On-demand', file: 'pipelines/federal_register.py', desc: 'SBA, FDA, OSHA, EPA regulations' },
              { name: 'tiktok_ingester', schedule: 'Daily', file: 'pipelines/tiktok.py', desc: 'Playwright + Whisper transcription' },
              { name: 'vision_ingester', schedule: 'On-demand', file: 'pipelines/vision.py', desc: 'YouTube → YOLO frame analysis' },
            ].map((p) => (
              <div key={p.name} className={CARD}>
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className={CODE}>{p.name}</span>
                  <span className="text-xs text-white/40">{p.schedule}</span>
                </div>
                <p className="text-sm text-white/60">{p.desc}</p>
                <p className="text-xs font-mono text-white/30 mt-2">{p.file}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Enrichment layer */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Enrichment Layer</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/classify.py</span> drains the doc queue every 2 minutes. Two GPU services run in parallel:
          </p>
          <ul className="list-disc list-inside text-sm text-white/60 space-y-2 mt-4">
            <li><span className={CODE}>DocClassifier</span> — bart-large-mnli (T4): zero-shot classification into regulatory, economic, safety, infrastructure, community, business</li>
            <li><span className={CODE}>SentimentAnalyzer</span> — twitter-roberta-base-sentiment (T4): positive/negative/neutral</li>
          </ul>
          <p className={`${BODY} mt-4`}>
            Batch processing via <span className={CODE}>@modal.batched</span> + <span className={CODE}>asyncio.gather()</span>. Enriched docs saved to <span className={CODE}>/data/processed/enriched/</span>.
          </p>
          <p className={`${BODY} mt-4`}>
            <span className={CODE}>modal_app/llm.py</span> — AleithiaLLM runs Qwen3 8B via vLLM on H100 for streaming chat and intelligence briefs. 20 concurrent inputs via <span className={CODE}>@modal.concurrent</span>.
          </p>
        </section>

        {/* Agent swarm */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Agent Swarm</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/agents.py</span> — At query time, <span className={CODE}>orchestrate_query()</span> fans out 4 agent types via <span className={CODE}>.spawn()</span>, each gathering data from Volume + Supermemory. Results are synthesized by the LLM.
          </p>
          <div className="mt-6 grid sm:grid-cols-2 gap-4">
            {[
              { name: 'neighborhood_intel_agent', desc: 'Single-neighborhood brief: permits, sentiment, competition, safety, demographics' },
              { name: 'regulatory_agent', desc: 'Regulatory and policy signals for a neighborhood' },
              { name: 'comparison_agent', desc: 'Compares target neighborhood vs adjacent neighborhoods' },
              { name: 'synthesis', desc: 'LLM merges findings, identifies conflicts, produces recommendation with confidence' },
            ].map((a) => (
              <div key={a.name} className={CARD}>
                <span className={CODE}>{a.name}</span>
                <p className="text-sm text-white/60 mt-2">{a.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* API endpoints */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>API Endpoints</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/web.py</span> — Modal-hosted FastAPI via <span className={CODE}>@modal.asgi_app()</span>. CORS enabled for all origins.
          </p>
          <div className="mt-6 space-y-2">
            {[
              { method: 'POST', path: '/chat', desc: 'Streaming SSE chat (agent swarm + LLM)' },
              { method: 'GET', path: '/brief/{neighborhood}', desc: 'Neighborhood intelligence brief' },
              { method: 'GET', path: '/alerts', desc: 'Regulatory alerts' },
              { method: 'GET', path: '/status', desc: 'Pipeline status' },
              { method: 'GET', path: '/metrics', desc: 'Neighborhood metrics' },
              { method: 'GET', path: '/sources', desc: 'Data source catalog' },
              { method: 'GET', path: '/neighborhood/{name}', desc: 'Full neighborhood data' },
              { method: 'GET', path: '/news', desc: 'News documents' },
              { method: 'GET', path: '/politics', desc: 'Politics documents' },
              { method: 'GET', path: '/inspections', desc: 'Food establishment inspections' },
              { method: 'GET', path: '/permits', desc: 'Building permits' },
              { method: 'GET', path: '/licenses', desc: 'Business licenses' },
              { method: 'GET', path: '/summary', desc: 'Demographics summary' },
              { method: 'GET', path: '/geo', desc: 'GeoJSON for Mapbox' },
              { method: 'GET', path: '/health', desc: 'Health check' },
            ].map((e) => (
              <div key={e.path} className="flex flex-wrap items-baseline gap-2 py-2 border-b border-white/[0.04] last:border-0">
                <span className={`${CODE} w-14`}>{e.method}</span>
                <span className="font-mono text-sm text-white/80">{e.path}</span>
                <span className="text-sm text-white/40">{e.desc}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Data flow */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Data Flow</h2>
          <p className={BODY}>
            Document schema: <span className={CODE}>Document(id, source, title, content, url, timestamp, metadata, geo, status)</span>
          </p>
          <p className={BODY}>
            Ingestion flow: <span className={CODE}>_fetch_*()</span> → FallbackChain → SeenSet dedup → save to volume → push to <span className={CODE}>doc_queue</span> → classify.py enriches.
          </p>
          <p className={BODY}>
            Volume paths:
          </p>
          <ul className="list-disc list-inside text-sm text-white/60 space-y-1 mt-2">
            <li><span className={CODE}>/data/raw/{'{source}/{date}/'}</span> — raw documents</li>
            <li><span className={CODE}>/data/processed/enriched/</span> — classified + sentiment</li>
            <li><span className={CODE}>/data/cache/</span> — HTTP cache</li>
            <li><span className={CODE}>/data/dedup/</span> — seen-URL sets</li>
          </ul>
          <p className={`${BODY} mt-4`}>
            <span className={CODE}>modal_app/compress.py</span> — Raw data → neighborhood summaries + GeoJSON for Mapbox. <span className={CODE}>modal_app/reconciler.py</span> runs every 5 min: checks pipeline freshness, auto-restarts stale ingesters, cost tracking via <span className={CODE}>modal.Dict</span>.
          </p>
        </section>
      </div>

      {/* Footer */}
      <footer className="px-10 py-8 border-t border-white/[0.04]">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-mono text-white/20">
            Built at HackIllinois 2026 · Mission-critical city intelligence.
          </p>
        </div>
      </footer>
    </div>
  )
}
