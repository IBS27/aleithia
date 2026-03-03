import MemGraph from './MemGraph'

interface Props {
  onBack: () => void
}

const SECTION_TITLE = 'text-2xl sm:text-3xl font-bold tracking-tight text-white mb-6'
const BODY = 'text-sm text-white/60 leading-relaxed space-y-3'
const CODE = 'font-mono text-xs bg-white/[0.06] border border-white/[0.08] rounded px-2 py-1 text-white/80'
const CARD = 'border border-white/[0.06] rounded-lg p-6 bg-white/[0.02]'
const TAG = 'text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border'

// ── Architecture flow nodes ──
const ARCH_FLOW: { id: string; label: string; sub: string; color: string; accent: string }[] = [
  { id: 'ingest', label: 'Ingestion', sub: '14 pipelines', color: 'text-cyan-400', accent: 'border-cyan-500/30 bg-cyan-500/[0.04]' },
  { id: 'queue', label: 'doc_queue', sub: 'modal.Queue', color: 'text-white/50', accent: 'border-white/[0.08] bg-white/[0.02]' },
  { id: 'enrich', label: 'Enrichment', sub: 'T4 GPUs', color: 'text-amber-400', accent: 'border-amber-500/30 bg-amber-500/[0.04]' },
  { id: 'vector', label: 'VectorAI DB', sub: '384d HNSW', color: 'text-emerald-400', accent: 'border-emerald-500/30 bg-emerald-500/[0.04]' },
  { id: 'llm', label: 'Qwen3-8B', sub: 'H100 vLLM', color: 'text-violet-400', accent: 'border-violet-500/30 bg-violet-500/[0.04]' },
  { id: 'agents', label: 'Agent Swarm', sub: '4 types .spawn()', color: 'text-pink-400', accent: 'border-pink-500/30 bg-pink-500/[0.04]' },
]

// ── GPU fleet data ──
const GPU_CLASSES: { name: string; gpu: string; model: string; features: string; color: string; accent: string; utilization: number }[] = [
  { name: 'AlethiaLLM', gpu: 'H100', model: 'Qwen3-8B AWQ (INT4) via vLLM', features: 'min_containers=1, @modal.concurrent(20)', color: 'text-violet-400', accent: 'border-violet-500/30', utilization: 72 },
  { name: 'DocClassifier', gpu: 'T4', model: 'bart-large-mnli (406M)', features: '@modal.batched, scaledown_window=300', color: 'text-cyan-400', accent: 'border-cyan-500/30', utilization: 45 },
  { name: 'SentimentAnalyzer', gpu: 'T4', model: 'roberta-base-sentiment', features: '@modal.batched, scaledown_window=300', color: 'text-cyan-400', accent: 'border-cyan-500/30', utilization: 38 },
  { name: 'TrafficAnalyzer', gpu: 'T4', model: 'YOLOv8n detection', features: 'min_containers=1', color: 'text-amber-400', accent: 'border-amber-500/30', utilization: 55 },
  { name: 'ParkingAnalyzer', gpu: 'T4', model: 'SegFormer-b5 + YOLOv8m + SAHI', features: 'scaledown_window=300', color: 'text-emerald-400', accent: 'border-emerald-500/30', utilization: 60 },
]

// ── Risk scoring dimensions ──
const RISK_DIMS: { dim: string; weight: number; input: string; color: string }[] = [
  { dim: 'Regulatory', weight: 0.25, input: 'Inspection fail rate', color: 'bg-red-400' },
  { dim: 'Market', weight: 0.20, input: 'License density + reviews', color: 'bg-amber-400' },
  { dim: 'Economic', weight: 0.20, input: 'Permit activity', color: 'bg-emerald-400' },
  { dim: 'Accessibility', weight: 0.15, input: 'CCTV + CTA transit', color: 'bg-cyan-400' },
  { dim: 'Political', weight: 0.10, input: 'Legislative volume', color: 'bg-violet-400' },
  { dim: 'Community', weight: 0.10, input: 'News + social signals', color: 'bg-pink-400' },
]

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
        <p className={SECTION_TITLE}>Pipeline Overview</p>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white mb-4">
          Architecture & Backend Logic
        </h1>
        <p className="text-base text-white/50 mb-6">
          Aleithia ingests Chicago-area data from 14 pipelines, enriches it with 5 GPU model classes, indexes it in VectorAI DB, and delivers insights through an agent swarm and recursive analyst. All compute runs on Modal (33+ serverless functions, 21 Modal features).
        </p>

        {/* Live stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-16">
          {[
            { value: '14', label: 'Pipelines' },
            { value: '33+', label: 'Modal Functions' },
            { value: '5', label: 'GPU Classes' },
            { value: '25+', label: 'API Endpoints' },
          ].map(s => (
            <div key={s.label} className="text-center py-3 border border-white/[0.06] rounded-lg bg-white/[0.02]">
              <p className="text-xl font-bold text-white">{s.value}</p>
              <p className="text-[10px] font-mono text-white/30 uppercase tracking-wider">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Architecture overview — visual flow */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Architecture Overview</h2>

          {/* User entry point */}
          <div className="flex justify-center mb-4">
            <div className="border border-white/[0.12] bg-white/[0.04] px-6 py-2.5 text-center">
              <span className="text-[10px] font-mono font-bold text-white/60 uppercase tracking-wider">User → FastAPI</span>
              <p className="text-[8px] font-mono text-white/25 mt-0.5">@modal.asgi_app</p>
            </div>
          </div>

          {/* Vertical connector */}
          <div className="flex justify-center mb-4">
            <div className="relative w-px h-8 bg-gradient-to-b from-white/20 to-white/[0.06]">
              <div className="absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-white/30" style={{ animation: 'flowDot 2s ease-in-out infinite' }} />
            </div>
          </div>

          {/* Main pipeline flow: 6 nodes in 2 rows */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            {ARCH_FLOW.map((node, i) => (
              <div key={node.id} className={`relative border ${node.accent} p-4 text-center transition-all hover:scale-[1.02]`} style={{ animationDelay: `${i * 100}ms` }}>
                <div className={`w-2 h-2 rounded-full ${node.color.replace('text-', 'bg-')} mx-auto mb-2 animate-pulse`} />
                <span className={`text-[11px] font-mono font-bold ${node.color} uppercase tracking-wider`}>{node.label}</span>
                <p className="text-[8px] font-mono text-white/25 mt-1">{node.sub}</p>
                {/* Horizontal connector to next */}
                {i < ARCH_FLOW.length - 1 && i !== 2 && (
                  <div className="absolute right-0 top-1/2 translate-x-full -translate-y-1/2 w-3 h-px bg-white/[0.08] hidden sm:block" />
                )}
              </div>
            ))}
          </div>

          {/* Downstream connectors */}
          <div className="flex justify-center mb-4">
            <div className="relative w-px h-8 bg-gradient-to-b from-white/[0.08] to-white/[0.04]">
              <div className="absolute left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-emerald-400/50" style={{ animation: 'flowDot 2.5s ease-in-out infinite' }} />
            </div>
          </div>

          {/* Supporting services row */}
          <div className="grid grid-cols-3 gap-3 mb-6">
            {[
              { label: 'Supermemory', sub: 'RAG, user profiles, doc sync', color: 'text-blue-400', accent: 'border-blue-500/20 bg-blue-500/[0.03]' },
              { label: 'Arize AX', sub: 'OpenTelemetry tracing', color: 'text-orange-400', accent: 'border-orange-500/20 bg-orange-500/[0.03]' },
              { label: 'Reconciler', sub: 'Self-healing every 5 min', color: 'text-red-400', accent: 'border-red-500/20 bg-red-500/[0.03]' },
            ].map(svc => (
              <div key={svc.label} className={`border ${svc.accent} p-3 text-center`}>
                <span className={`text-[10px] font-mono font-bold ${svc.color} uppercase tracking-wider`}>{svc.label}</span>
                <p className="text-[8px] font-mono text-white/20 mt-0.5">{svc.sub}</p>
              </div>
            ))}
          </div>

          <p className={`${BODY}`}>
            Pipelines push documents to <span className={CODE}>modal.Queue</span>. The classifier drains the queue every 2 minutes, enriches with classification + sentiment, then upserts to VectorAI DB. The agent swarm fans out at query time via <span className={CODE}>.spawn()</span>, queries VectorAI DB for semantic retrieval, gathers results, and synthesizes with the LLM.
          </p>
        </section>
      </main>

      <MemGraph />

      <div className="max-w-4xl mx-auto px-10 py-16">
        {/* GPU classes — visual fleet */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>GPU Infrastructure</h2>
          <p className={BODY}>
            5 GPU model classes deployed across H100 and T4 instances. All use <span className={CODE}>@modal.enter(snap=True)</span> for GPU memory snapshots (fast cold starts).
          </p>

          <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {GPU_CLASSES.map((g, i) => (
              <div
                key={g.name}
                className={`relative border ${g.accent} bg-white/[0.02] p-5 transition-all hover:bg-white/[0.04] overflow-hidden`}
                style={{ animationDelay: `${i * 80}ms` }}
              >
                {/* GPU badge */}
                <div className="absolute top-3 right-3">
                  <span className={`text-[9px] font-mono font-bold px-2 py-0.5 border ${g.accent} ${g.color} uppercase tracking-wider`}>
                    {g.gpu}
                  </span>
                </div>

                {/* Status dot + name */}
                <div className="flex items-center gap-2 mb-3">
                  <div className={`w-2 h-2 rounded-full ${g.color.replace('text-', 'bg-')} animate-pulse`} />
                  <span className={`text-xs font-mono font-bold ${g.color}`}>{g.name}</span>
                </div>

                <p className="text-[11px] text-white/50 mb-1">{g.model}</p>
                <p className="text-[9px] font-mono text-white/20 mb-4">{g.features}</p>

                {/* Utilization bar */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[8px] font-mono text-white/20 uppercase">Utilization</span>
                    <span className="text-[8px] font-mono text-white/30 tabular-nums">{g.utilization}%</span>
                  </div>
                  <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${g.color.replace('text-', 'bg-')}/50 transition-all`}
                      style={{ width: `${g.utilization}%`, animation: 'gpuBarFill 1.5s ease-out forwards', animationDelay: `${i * 150}ms` }}
                    />
                  </div>
                </div>

                {/* Snapshot badge */}
                <div className="mt-3 flex items-center gap-1.5">
                  <div className="w-1 h-1 rounded-full bg-emerald-400/50" />
                  <span className="text-[7px] font-mono text-emerald-400/40 uppercase tracking-wider">Memory Snapshot Enabled</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Ingestion layer — compact visual grid */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Ingestion Layer</h2>
          <p className={BODY}>
            14 Modal cron/on-demand functions scrape heterogeneous sources and normalize into a common <span className={CODE}>Document</span> schema. <span className={CODE}>FallbackChain</span> for resilience, <span className={CODE}>SeenSet</span> for dedup (10k cap).
          </p>
          <div className="mt-6 grid sm:grid-cols-2 gap-2">
            {[
              { name: 'news', schedule: '30m cron', desc: 'RSS + NewsAPI', color: 'text-cyan-400', accent: 'border-cyan-500/20' },
              { name: 'reddit', schedule: '1hr cron', desc: 'r/chicago + 9 subs', color: 'text-orange-400', accent: 'border-orange-500/20' },
              { name: 'public_data', schedule: 'Daily', desc: 'Chicago Data Portal', color: 'text-blue-400', accent: 'border-blue-500/20' },
              { name: 'politics', schedule: 'On-demand', desc: 'Legistar + Zoning PDFs', color: 'text-violet-400', accent: 'border-violet-500/20' },
              { name: 'demographics', schedule: 'On-demand', desc: 'Census ACS 5-year', color: 'text-emerald-400', accent: 'border-emerald-500/20' },
              { name: 'reviews', schedule: 'On-demand', desc: 'Yelp + Google Places', color: 'text-yellow-400', accent: 'border-yellow-500/20' },
              { name: 'realestate', schedule: 'On-demand', desc: 'LoopNet commercial', color: 'text-pink-400', accent: 'border-pink-500/20' },
              { name: 'federal_register', schedule: 'On-demand', desc: 'SBA/FDA/OSHA/EPA', color: 'text-red-400', accent: 'border-red-500/20' },
              { name: 'tiktok', schedule: 'On-demand', desc: 'Playwright + Whisper', color: 'text-fuchsia-400', accent: 'border-fuchsia-500/20' },
              { name: 'traffic', schedule: 'On-demand', desc: 'TomTom Flow API', color: 'text-amber-400', accent: 'border-amber-500/20' },
              { name: 'cctv', schedule: 'On-demand', desc: 'IDOT cameras + YOLO', color: 'text-teal-400', accent: 'border-teal-500/20' },
              { name: 'vision', schedule: 'On-demand', desc: 'YouTube → YOLO training', color: 'text-indigo-400', accent: 'border-indigo-500/20' },
              { name: 'parking', schedule: 'On-demand', desc: 'Satellite + SegFormer', color: 'text-lime-400', accent: 'border-lime-500/20' },
              { name: 'worldpop', schedule: 'On-demand', desc: 'Earth Engine population', color: 'text-sky-400', accent: 'border-sky-500/20' },
            ].map((p) => (
              <div key={p.name} className={`border ${p.accent} bg-white/[0.01] p-3 flex items-center gap-3 transition-all hover:bg-white/[0.03]`}>
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${p.color.replace('text-', 'bg-')} ${p.schedule.includes('cron') ? 'animate-pulse' : 'opacity-60'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-mono font-bold ${p.color} uppercase tracking-wider`}>{p.name}</span>
                    <span className={`text-[8px] font-mono px-1.5 py-0.5 border border-white/[0.06] text-white/25 ${p.schedule.includes('cron') ? 'text-emerald-400/50 border-emerald-500/15' : ''}`}>
                      {p.schedule}
                    </span>
                  </div>
                  <p className="text-[9px] font-mono text-white/25 mt-0.5">{p.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Enrichment layer */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Enrichment Layer</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/classify.py</span> drains the doc queue every 2 minutes. Two GPU services run in parallel via <span className={CODE}>asyncio.gather()</span>:
          </p>
          <ul className="list-disc list-inside text-sm text-white/60 space-y-2 mt-4">
            <li><span className={CODE}>DocClassifier</span> — bart-large-mnli (T4): zero-shot classification into regulatory, economic, safety, infrastructure, community, business</li>
            <li><span className={CODE}>SentimentAnalyzer</span> — twitter-roberta-base-sentiment (T4): positive/negative/neutral with confidence score</li>
          </ul>
          <p className={`${BODY} mt-4`}>
            After enrichment, documents are upserted to VectorAI DB (<span className={CODE}>build_embed_text</span> + <span className={CODE}>batch_upsert_docs</span>) and pushed to <span className={CODE}>impact_queue</span> for Lead Analyst scoring. Enriched docs saved to <span className={CODE}>/data/processed/enriched/</span>.
          </p>
        </section>

        {/* VectorAI DB — visual */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>VectorAI DB — Semantic Search</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/vectordb.py</span> — Actian VectorAI DB with HNSW-indexed vectors for sub-15ms semantic retrieval.
          </p>

          <div className="mt-6 border border-emerald-500/20 bg-emerald-500/[0.02] p-5">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-[11px] font-mono font-bold text-emerald-300 uppercase tracking-wider">VectorDBService</span>
              </div>
              <span className="text-[8px] font-mono text-white/20">@modal.cls, min_containers=1</span>
            </div>

            {/* Config grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
              {[
                { label: 'Embeddings', value: '384-dim', sub: 'all-MiniLM-L6-v2' },
                { label: 'Index', value: 'HNSW', sub: 'cosine similarity' },
                { label: 'Collections', value: '15', sub: '14 sources + enriched' },
                { label: 'Latency', value: '<15ms', sub: 'search p95' },
              ].map(c => (
                <div key={c.label} className="text-center border border-white/[0.04] bg-white/[0.02] p-2.5">
                  <p className="text-sm font-mono font-bold text-white/50">{c.value}</p>
                  <p className="text-[8px] font-mono text-white/25 uppercase tracking-wider">{c.label}</p>
                  <p className="text-[7px] font-mono text-white/15 mt-0.5">{c.sub}</p>
                </div>
              ))}
            </div>

            {/* API methods */}
            <div className="space-y-1.5">
              {[
                { method: 'embed_batch(texts)', desc: '→ list[384-dim vectors]' },
                { method: 'batch_upsert_docs(...)', desc: '→ write to collection + flush' },
                { method: 'search(embedding, filter)', desc: '→ top-K results with payloads' },
                { method: 'search_neighborhood(...)', desc: '→ enriched collection, filtered' },
                { method: 'health_check()', desc: '→ status + per-collection counts' },
              ].map(m => (
                <div key={m.method} className="flex items-center gap-2 py-1.5 border-b border-white/[0.03] last:border-0">
                  <span className={CODE}>{m.method}</span>
                  <span className="text-[10px] font-mono text-white/25">{m.desc}</span>
                </div>
              ))}
            </div>
          </div>

          <p className={`${BODY} mt-4`}>
            Documents embedded at ingestion in <span className={CODE}>classify.py</span>. At query time, <span className={CODE}>orchestrate_query()</span> pre-computes the embedding once and shares it across all agent spawns. All operations guarded by <span className={CODE}>vectordb_available()</span>.
          </p>
        </section>

        {/* LLM layer */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>LLM Layer</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/llm.py</span> — AlethiaLLM runs Qwen3 8B AWQ (INT4) via vLLM on H100 for streaming chat responses and intelligence briefs. 20 concurrent inputs via <span className={CODE}>@modal.concurrent</span>. GPU memory snapshots for fast cold starts.
          </p>
          <div className={`${CARD} mt-6`}>
            <p className="text-xs font-mono font-bold text-white/50 mb-3">OpenAI Hybrid Layer (GPT-4o)</p>
            <p className="text-sm text-white/60 mb-3">
              <span className={CODE}>modal_app/openai_utils.py</span> provides shared client factory. GPT-4o is used for 4 targeted enhancements — all degrade gracefully without <span className={CODE}>OPENAI_API_KEY</span>:
            </p>
            <ul className="list-disc list-inside text-sm text-white/60 space-y-1">
              <li>Deep Dive code generation (<span className={CODE}>/analyze</span> endpoint)</li>
              <li>Chat follow-up suggestion chips</li>
              <li>Regulatory impact summaries (in regulatory_agent)</li>
              <li>Vision-powered street assessment (<span className={CODE}>/vision/assess/&#123;neighborhood&#125;</span>)</li>
            </ul>
          </div>
        </section>

        {/* Agent swarm — visual spawn diagram */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Agent Swarm</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/agents.py</span> — At query time, <span className={CODE}>orchestrate_query()</span> pre-computes a VectorDB embedding, fans out 4 agent types via <span className={CODE}>.spawn()</span>. W3C trace context propagation links spans across containers.
          </p>

          {/* Visual fan-out diagram */}
          <div className="mt-8 relative flex flex-col items-center">
            {/* Orchestrator node */}
            <div className="border border-white/[0.12] bg-white/[0.04] px-6 py-3 text-center z-10">
              <span className="text-[10px] font-mono font-bold text-white/60 uppercase tracking-wider">orchestrate_query()</span>
              <p className="text-[8px] font-mono text-white/20 mt-0.5">pre-compute embedding → .spawn() × 4</p>
            </div>

            {/* Trunk line */}
            <div className="relative w-px h-8">
              <div className="absolute inset-0 bg-gradient-to-b from-white/20 to-white/[0.06]" />
              <div className="absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-pink-400/70" style={{ animation: 'flowDot 2s ease-in-out infinite' }} />
            </div>

            {/* Horizontal fan-out bar */}
            <div className="relative w-full h-8">
              <div className="absolute top-0 left-[12.5%] right-[12.5%] h-px bg-white/[0.08]" />
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="absolute top-0 h-full w-px bg-white/[0.06]" style={{ left: `${12.5 + i * 25}%` }}>
                  <div className="absolute left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-cyan-400/50" style={{ animation: 'flowDot 1.8s ease-in-out infinite', animationDelay: `${i * 0.15}s` }} />
                </div>
              ))}
            </div>

            {/* 4 Agent cards */}
            <div className="grid grid-cols-4 gap-2 w-full">
              {[
                { name: 'neighborhood_intel', label: 'Intel Agent', desc: 'Permits, sentiment, competition, safety, demographics — 10+ sources', color: 'text-cyan-400', accent: 'border-cyan-500/30 bg-cyan-500/[0.04]' },
                { name: 'regulatory', label: 'Regulatory', desc: 'Legistar + Fed Register + GPT-4o impact enrichment', color: 'text-violet-400', accent: 'border-violet-500/30 bg-violet-500/[0.04]' },
                { name: 'comparison', label: 'Comparison', desc: 'Target vs 2 adjacent neighborhoods auto-selected', color: 'text-amber-400', accent: 'border-amber-500/30 bg-amber-500/[0.04]' },
                { name: 'synthesis', label: 'Synthesis', desc: 'LLM merges findings → recommendation with confidence', color: 'text-emerald-400', accent: 'border-emerald-500/30 bg-emerald-500/[0.04]' },
              ].map((a, idx) => (
                <div key={a.name} className={`border ${a.accent} p-3 text-center`}>
                  <div className={`w-2 h-2 rounded-full ${a.color.replace('text-', 'bg-')} mx-auto mb-2 animate-pulse`} />
                  <span className={`text-[9px] font-mono font-bold ${a.color} uppercase tracking-wider`}>{a.label}</span>
                  <p className="text-[7px] font-mono text-white/20 mt-1.5 leading-relaxed">{a.desc}</p>
                  {/* Working bar */}
                  <div className="mt-2 h-0.5 bg-white/[0.04] rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${a.color.replace('text-', 'bg-')}/40`} style={{ animation: 'workerBar 3s ease-in-out infinite', animationDelay: `${idx * 0.4}s` }} />
                  </div>
                </div>
              ))}
            </div>

            {/* Merge lines */}
            <div className="relative w-full h-6">
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="absolute bottom-0 h-full w-px bg-white/[0.04]" style={{ left: `${12.5 + i * 25}%` }} />
              ))}
              <div className="absolute bottom-0 left-[12.5%] right-[12.5%] h-px bg-white/[0.04]" />
            </div>
            <div className="w-px h-4 bg-white/[0.06]" />

            {/* Synthesis output */}
            <div className="border border-emerald-500/25 bg-emerald-500/[0.03] px-6 py-2.5 text-center z-10">
              <span className="text-[10px] font-mono font-bold text-emerald-300 uppercase tracking-wider">Synthesized Response</span>
              <p className="text-[8px] font-mono text-white/20 mt-0.5">Executive Summary, Analysis, Risks, Opportunities, Next Steps</p>
            </div>
          </div>
        </section>

        {/* Lead Analyst — visual pipeline */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Recursive Agent Architecture</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/lead_analyst.py</span> — Autonomous impact detection pipeline running every 5 minutes. An AI agent that deploys AI agents.
          </p>

          {/* 4-phase visual pipeline */}
          <div className="mt-8 relative flex flex-col items-center">
            {/* Phase 1: Scan */}
            <div className="w-full max-w-md border border-cyan-500/25 bg-cyan-500/[0.03] p-4 text-center">
              <div className="flex items-center justify-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                <span className="text-[10px] font-mono font-bold text-cyan-300 uppercase tracking-wider">Phase 1 — Fast Filter</span>
              </div>
              <div className="flex justify-center gap-3 text-[8px] font-mono text-white/25">
                <span>regulatory + neg sentiment &gt;0.7</span>
                <span className="text-white/10">|</span>
                <span>safety + conf &gt;0.8</span>
              </div>
            </div>

            <div className="relative w-px h-6 bg-white/[0.08]">
              <div className="absolute left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-cyan-400/50" style={{ animation: 'flowDot 2s ease-in-out infinite' }} />
            </div>

            {/* Phase 2: LLM Scoring */}
            <div className="w-full max-w-md border border-violet-500/25 bg-violet-500/[0.03] p-4 text-center">
              <div className="flex items-center justify-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
                <span className="text-[10px] font-mono font-bold text-violet-300 uppercase tracking-wider">Phase 2 — LLM Scoring</span>
              </div>
              <p className="text-[8px] font-mono text-white/25">Qwen3-8B scores 1–10 per document · 7+ = high impact</p>
            </div>

            <div className="relative w-px h-6 bg-white/[0.08]">
              <div className="absolute left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-violet-400/50" style={{ animation: 'flowDot 2s ease-in-out infinite', animationDelay: '0.3s' }} />
            </div>

            {/* Phase 3: Score gate */}
            <div className="border border-amber-500/25 bg-amber-500/[0.04] px-5 py-2 mb-0">
              <span className="text-[9px] font-mono uppercase tracking-wider text-amber-400/70">score ≥ 7 → spawn 4 workers</span>
            </div>

            {/* Fan-out to 4 workers */}
            <div className="relative w-full h-8">
              <div className="absolute top-0 left-[12.5%] right-[12.5%] h-px bg-white/[0.06]" />
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="absolute top-0 h-full w-px bg-white/[0.06]" style={{ left: `${12.5 + i * 25}%` }}>
                  <div className="absolute left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-amber-400/50" style={{ animation: 'flowDot 2s ease-in-out infinite', animationDelay: `${i * 0.15}s` }} />
                </div>
              ))}
            </div>

            <div className="grid grid-cols-4 gap-2 w-full">
              {[
                { label: 'Real Estate', sub: 'price/vacancy/zoning', color: 'text-cyan-400', accent: 'border-cyan-500/30 bg-cyan-500/[0.03]' },
                { label: 'Legal', sub: 'compliance/enforcement', color: 'text-violet-400', accent: 'border-violet-500/30 bg-violet-500/[0.03]' },
                { label: 'Economic', sub: 'revenue impact/timeline', color: 'text-amber-400', accent: 'border-amber-500/30 bg-amber-500/[0.03]' },
                { label: 'Community', sub: 'Reddit/reviews/news', color: 'text-emerald-400', accent: 'border-emerald-500/30 bg-emerald-500/[0.03]' },
              ].map((w, idx) => (
                <div key={w.label} className={`border ${w.accent} p-2.5 text-center`}>
                  <div className="absolute top-1 right-1.5 relative">
                    <span className="text-[6px] font-mono text-cyan-400/30 uppercase tracking-wider">E2B</span>
                  </div>
                  <span className={`text-[9px] font-mono font-bold ${w.color} uppercase tracking-wider`}>{w.label}</span>
                  <p className="text-[7px] font-mono text-white/20 mt-1">{w.sub}</p>
                  <div className="mt-2 h-0.5 bg-white/[0.04] rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${w.color.replace('text-', 'bg-')}/40`} style={{ animation: 'workerBar 3s ease-in-out infinite', animationDelay: `${idx * 0.5}s` }} />
                  </div>
                </div>
              ))}
            </div>

            {/* Merge */}
            <div className="relative w-full h-6">
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="absolute bottom-0 h-full w-px bg-white/[0.04]" style={{ left: `${12.5 + i * 25}%` }} />
              ))}
              <div className="absolute bottom-0 left-[12.5%] right-[12.5%] h-px bg-white/[0.04]" />
            </div>
            <div className="w-px h-4 bg-white/[0.06]" />

            {/* Phase 4: Synthesis */}
            <div className="w-full max-w-md border border-emerald-500/25 bg-emerald-500/[0.03] p-4 text-center">
              <div className="flex items-center justify-center gap-2 mb-1.5">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-[10px] font-mono font-bold text-emerald-300 uppercase tracking-wider">Phase 4 — Synthesis</span>
              </div>
              <p className="text-[8px] font-mono text-white/25">Qwen3-8B → ImpactBrief: executive_summary, synthesis, recommendations</p>
              <p className="text-[7px] font-mono text-white/15 mt-1">→ /data/processed/impact_briefs/</p>
            </div>
          </div>

          <p className={`${BODY} mt-6`}>
            Workers execute GPT-4o-generated Python scripts in isolated E2B sandboxes. Falls back to in-process exec without <span className={CODE}>E2B_API_KEY</span>.
          </p>
        </section>

        {/* Risk scoring — visual bars */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Risk Scoring Model</h2>
          <p className={BODY}>
            Weighted Linear Combination (WLC), ISO 31000-aligned. Logistic (sigmoid) normalization with Chicago-calibrated midpoints. Same model runs on frontend and backend.
          </p>

          {/* Formula */}
          <div className="mt-6 border border-white/[0.08] bg-white/[0.02] p-4 text-center mb-6">
            <span className="font-mono text-sm text-white/60">risk = Σ(wᵢ · sigmoid(xᵢ)) / Σ(wᵢ)</span>
            <p className="text-[8px] font-mono text-white/20 mt-1">Output: 0–10 scale · Confidence: 60% dimensional coverage + 40% data depth</p>
          </div>

          {/* Dimension bars */}
          <div className="space-y-3">
            {RISK_DIMS.map((d, i) => (
              <div key={d.dim} className="border border-white/[0.04] bg-white/[0.01] p-3.5">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${d.color}`} />
                    <span className="text-[11px] font-mono font-bold text-white/60">{d.dim}</span>
                  </div>
                  <span className="text-[10px] font-mono text-white/30 tabular-nums">{(d.weight * 100).toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 bg-white/[0.04] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${d.color}/60`}
                      style={{ width: `${d.weight * 100 * 4}%`, animation: 'gpuBarFill 1.2s ease-out forwards', animationDelay: `${i * 100}ms` }}
                    />
                  </div>
                  <span className="text-[9px] font-mono text-white/20 w-32 text-right">{d.input}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Deep Dive */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Deep Dive Analysis</h2>
          <p className={BODY}>
            <span className={CODE}>/analyze</span> endpoint generates Python analysis scripts via GPT-4o (with Qwen3-8B fallback), runs them in <span className={CODE}>modal.Sandbox</span> against real pipeline data. Returns stats, charts (base64 PNG), generated code, and <span className={CODE}>model_used</span> indicator. Sandbox image includes pandas, matplotlib, numpy, seaborn.
          </p>
        </section>

        {/* Observability */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Observability</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/instrumentation.py</span> — Arize AX tracing via OpenTelemetry. Connected spans across web → orchestrator → agents → LLM. OpenAI auto-instrumentor for all GPT-4o calls.
          </p>
          <ul className="list-disc list-inside text-sm text-white/60 space-y-2 mt-4">
            <li><span className={CODE}>init_tracing()</span> — Arize register with space ID + API key</li>
            <li><span className={CODE}>get_tracer(name)</span> — Named tracer per module (alethia.web, alethia.agents, alethia.vectordb, etc.)</li>
            <li><span className={CODE}>inject_context()</span> / <span className={CODE}>extract_context()</span> — W3C trace context propagation across Modal containers via <span className={CODE}>.spawn()</span></li>
            <li>VectorDB operations traced: embed, batch_upsert, search, health_check</li>
          </ul>
        </section>

        {/* API endpoints */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>API Endpoints</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/web.py</span> — Modal-hosted FastAPI via <span className={CODE}>@modal.asgi_app()</span>. 25+ endpoints. CORS enabled for all origins.
          </p>
          <div className="mt-6 space-y-2">
            {[
              { method: 'POST', path: '/chat', desc: 'Streaming SSE chat (agent swarm + LLM + follow-up suggestions)' },
              { method: 'GET', path: '/brief/{neighborhood}', desc: 'Neighborhood intelligence brief' },
              { method: 'POST', path: '/analyze', desc: 'Deep Dive: GPT-4o code gen → modal.Sandbox execution' },
              { method: 'GET', path: '/neighborhood/{name}', desc: 'Full neighborhood data (includes transit + parking fields)' },
              { method: 'GET', path: '/alerts', desc: 'Regulatory alerts' },
              { method: 'GET', path: '/status', desc: 'Pipeline status + VectorDB health' },
              { method: 'GET', path: '/metrics', desc: 'Neighborhood metrics' },
              { method: 'GET', path: '/sources', desc: 'Data source catalog' },
              { method: 'GET', path: '/news', desc: 'News documents' },
              { method: 'GET', path: '/politics', desc: 'Politics documents' },
              { method: 'GET', path: '/inspections', desc: 'Food establishment inspections' },
              { method: 'GET', path: '/permits', desc: 'Building permits' },
              { method: 'GET', path: '/licenses', desc: 'Business licenses' },
              { method: 'GET', path: '/summary', desc: 'Demographics summary' },
              { method: 'GET', path: '/geo', desc: 'GeoJSON for Mapbox' },
              { method: 'GET', path: '/cctv/latest', desc: 'Latest CCTV analysis results' },
              { method: 'GET', path: '/cctv/frame/{camera_id}', desc: 'Raw CCTV camera frame' },
              { method: 'GET', path: '/vision/streetscape/{nbhd}', desc: 'Vision pipeline streetscape intelligence' },
              { method: 'GET', path: '/vision/assess/{nbhd}', desc: 'GPT-4o vision-powered street assessment' },
              { method: 'GET', path: '/parking/latest', desc: 'Latest parking analysis across all neighborhoods' },
              { method: 'GET', path: '/parking/{neighborhood}', desc: 'Parking analysis for specific neighborhood' },
              { method: 'GET', path: '/parking/annotated/{nbhd}', desc: 'Annotated satellite overlay JPEG' },
              { method: 'GET', path: '/impact-briefs', desc: 'List all impact briefs from Lead Analyst' },
              { method: 'GET', path: '/impact-briefs/{id}', desc: 'Single impact brief by ID' },
              { method: 'POST', path: '/impact-briefs/analyze', desc: 'Manually trigger impact analysis' },
              { method: 'GET', path: '/gpu-metrics', desc: 'Live GPU utilization and model stats' },
              { method: 'GET', path: '/health', desc: 'Health check (includes VectorDB status)' },
            ].map((e) => (
              <div key={e.path} className="flex flex-wrap items-baseline gap-2 py-2 border-b border-white/[0.04] last:border-0">
                <span className={`${CODE} w-14`}>{e.method}</span>
                <span className="font-mono text-sm text-white/80">{e.path}</span>
                <span className="text-sm text-white/40">{e.desc}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Data flow — visual pipeline */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Data Flow</h2>

          {/* Horizontal pipeline flow */}
          <div className="flex items-center gap-0 overflow-x-auto pb-2 mb-6">
            {[
              { label: '_fetch_*()', color: 'text-cyan-400', accent: 'border-cyan-500/25 bg-cyan-500/[0.03]' },
              { label: 'FallbackChain', color: 'text-white/40', accent: 'border-white/[0.08] bg-white/[0.02]' },
              { label: 'SeenSet dedup', color: 'text-white/40', accent: 'border-white/[0.08] bg-white/[0.02]' },
              { label: 'Modal Volume', color: 'text-amber-400', accent: 'border-amber-500/25 bg-amber-500/[0.03]' },
              { label: 'doc_queue', color: 'text-violet-400', accent: 'border-violet-500/25 bg-violet-500/[0.03]' },
              { label: 'classify.py', color: 'text-pink-400', accent: 'border-pink-500/25 bg-pink-500/[0.03]' },
              { label: 'VectorDB', color: 'text-emerald-400', accent: 'border-emerald-500/25 bg-emerald-500/[0.03]' },
              { label: 'Lead Analyst', color: 'text-violet-400', accent: 'border-violet-500/25 bg-violet-500/[0.03]' },
            ].map((step, i, arr) => (
              <div key={step.label} className="flex items-center flex-shrink-0">
                <div className={`border ${step.accent} px-3 py-2 text-center`}>
                  <span className={`text-[9px] font-mono font-bold ${step.color} uppercase tracking-wider whitespace-nowrap`}>{step.label}</span>
                </div>
                {i < arr.length - 1 && (
                  <div className="relative w-6 h-px bg-white/[0.08] flex-shrink-0">
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-l-[4px] border-l-white/15 border-y-[3px] border-y-transparent" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Volume paths grid */}
          <p className="text-[10px] font-mono uppercase tracking-wider text-white/25 mb-3">Volume Paths</p>
          <div className="grid sm:grid-cols-2 gap-1.5">
            {[
              { path: '/data/raw/{source}/{date}/', desc: 'Raw documents' },
              { path: '/data/processed/enriched/', desc: 'Classified + sentiment' },
              { path: '/data/processed/vision/analysis/', desc: 'Streetscape results' },
              { path: '/data/processed/parking/', desc: 'Parking analysis + annotated' },
              { path: '/data/processed/impact_briefs/', desc: 'Lead Analyst briefs' },
              { path: '/data/processed/geo/', desc: 'GeoJSON for Mapbox' },
              { path: '/data/cache/', desc: 'HTTP cache' },
              { path: '/data/vectordb/', desc: 'VectorAI DB data' },
            ].map(v => (
              <div key={v.path} className="flex items-center gap-2 py-1.5 px-2 border border-white/[0.03] bg-white/[0.01]">
                <span className="text-[9px] font-mono text-white/40">{v.path}</span>
                <span className="text-[8px] font-mono text-white/15">— {v.desc}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Cron schedule */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Cron Schedules</h2>
          <p className={BODY}>
            6 scheduled functions with <span className={CODE}>modal.Period</span>. All other pipelines are on-demand (triggered by reconciler or manual invocation).
          </p>
          <div className="mt-6 space-y-2">
            {[
              { fn: 'news_ingester', interval: '30 min', purpose: 'RSS + NewsAPI polling' },
              { fn: 'reddit_ingester', interval: '1 hr', purpose: 'Reddit subreddit scraping' },
              { fn: 'public_data_ingester', interval: 'Daily', purpose: 'Chicago Data Portal sync' },
              { fn: 'process_queue_batch', interval: '2 min', purpose: 'Drain doc_queue → GPU classification + VectorDB upsert' },
              { fn: 'data_reconciler', interval: '5 min', purpose: 'Pipeline freshness check, auto-restart stale ingesters, cost tracking' },
              { fn: 'scan_enriched_docs', interval: '5 min', purpose: 'Lead Analyst impact scanning → E2B worker dispatch' },
            ].map(c => (
              <div key={c.fn} className="flex flex-wrap items-baseline gap-2 py-2 border-b border-white/[0.04] last:border-0">
                <span className={CODE}>{c.fn}</span>
                <span className={`${TAG} text-white/40 border-white/10`}>{c.interval}</span>
                <span className="text-sm text-white/40">{c.purpose}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Self-healing */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Self-Healing Reconciler</h2>
          <p className={BODY}>
            <span className={CODE}>modal_app/reconciler.py</span> runs every 5 minutes. Checks freshness per data source against configurable thresholds. Auto-spawns stale pipelines with backoff (max 3 restarts per source per hour). Includes VectorDB health monitoring. Cost tracking via <span className={CODE}>modal.Dict</span> (per-function GPU seconds × rate).
          </p>
        </section>

        {/* Modal features */}
        <section className="mb-20">
          <h2 className={SECTION_TITLE}>Modal Features Used (21)</h2>
          <div className="flex flex-wrap gap-2">
            {[
              'modal.App', 'modal.Volume (2)', 'modal.Secret', 'modal.Image (15)',
              'modal.Period', '.map()', 'gpu="T4"', 'gpu="H100"',
              '@modal.cls + @modal.enter(snap=True)', '@modal.concurrent',
              '@modal.batched', 'modal.Queue', 'modal.Retries', '.spawn()',
              '@modal.asgi_app', 'modal.Dict', 'Function.from_name',
              'Cls.from_name', 'min_containers', 'enable_memory_snapshot',
              'modal.Sandbox',
            ].map(f => (
              <span key={f} className={CODE}>{f}</span>
            ))}
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer className="px-10 py-8 border-t border-white/[0.04]">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-mono text-white/20">
            Built at HackIllinois 2026 &middot; Mission-critical city intelligence.
          </p>
        </div>
      </footer>

      {/* CSS keyframes for visual components */}
      <style>{`
        @keyframes flowDot {
          0%   { top: 0; opacity: 0; }
          20%  { opacity: 1; }
          80%  { opacity: 1; }
          100% { top: calc(100% - 6px); opacity: 0; }
        }
        @keyframes gpuBarFill {
          0%   { width: 0%; }
          100% { width: var(--target-width, 100%); }
        }
        @keyframes workerBar {
          0%   { width: 0%; }
          50%  { width: 100%; }
          100% { width: 0%; }
        }
      `}</style>
    </div>
  )
}
