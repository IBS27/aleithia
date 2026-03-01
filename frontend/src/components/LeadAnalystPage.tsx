interface Props {
  onBack: () => void
}

const SH = 'text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/30 mb-4'
const ST = 'text-2xl sm:text-3xl font-bold tracking-tight text-white mb-6'
const BODY = 'text-sm text-white/60 leading-relaxed'
const CARD = 'border border-white/[0.06] rounded-lg p-6 bg-white/[0.02]'
const CODE = 'font-mono text-[11px] bg-white/[0.06] border border-white/[0.08] rounded px-1.5 py-0.5 text-white/70'
const TAG = 'text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border'

const WORKERS = [
  {
    name: 'Real Estate',
    color: 'cyan',
    border: 'border-cyan-500/25',
    text: 'text-cyan-400',
    bg: 'bg-cyan-500/[0.06]',
    source: '/data/raw/realestate/',
    desc: 'Cross-references the trigger event against LoopNet property data. Identifies price trends, vacancy shifts, and zoning implications for affected neighborhoods.',
  },
  {
    name: 'Legal',
    color: 'violet',
    border: 'border-violet-500/25',
    text: 'text-violet-400',
    bg: 'bg-violet-500/[0.06]',
    source: '/data/raw/politics/ + /data/raw/federal_register/',
    desc: 'Compares new regulations against existing state and federal law. Identifies compliance deadlines, enforcement risks, and potential conflicts.',
  },
  {
    name: 'Economic',
    color: 'amber',
    border: 'border-amber-500/25',
    text: 'text-amber-400',
    bg: 'bg-amber-500/[0.06]',
    source: '/data/raw/demographics/ + /data/raw/public_data/',
    desc: 'Reviews Census/ACS demographics and economic indicators. Projects revenue impact, estimates disruption timelines, and evaluates market readiness.',
  },
  {
    name: 'Community',
    color: 'emerald',
    border: 'border-emerald-500/25',
    text: 'text-emerald-400',
    bg: 'bg-emerald-500/[0.06]',
    source: '/data/raw/reddit/ + /data/raw/reviews/ + /data/raw/news/',
    desc: 'Aggregates Reddit, Yelp/Google reviews, and local news sentiment. Detects community reactions, trending concerns, and public perception shifts.',
  },
]

const FILTER_RULES = [
  { rule: 'regulatory + negative sentiment > 0.7', example: 'Health dept shutting down restaurants in an area' },
  { rule: 'politics/federal_register + regulatory label', example: 'New city ordinance affecting outdoor dining permits' },
  { rule: 'safety + classification confidence > 0.8', example: 'Spike in crime reports near a commercial corridor' },
  { rule: 'any category + confidence > 0.85 + negative > 0.75', example: 'Highly negative economic report about a neighborhood' },
]

export default function LeadAnalystPage({ onBack }: Props) {
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
        <p className={SH}>Recursive Agent Architecture</p>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white mb-4">
          The Lead Analyst
        </h1>
        <p className="text-base text-white/50 mb-6 max-w-2xl">
          An autonomous agent that monitors every enriched document, detects high-impact
          business events, and spawns specialized workers to investigate — without any human trigger.
        </p>

        {/* Stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-16">
          {[
            { value: '5 min', label: 'Scan Cycle' },
            { value: '4', label: 'Worker Types' },
            { value: '50', label: 'Docs / Batch' },
            { value: '907', label: 'Lines of Code' },
          ].map(s => (
            <div key={s.label} className="text-center py-3 border border-white/[0.06] rounded-lg bg-white/[0.02]">
              <p className="text-xl font-bold text-white">{s.value}</p>
              <p className="text-[10px] font-mono text-white/30 uppercase tracking-wider">{s.label}</p>
            </div>
          ))}
        </div>

        {/* ── Why It Exists ── */}
        <section className="mb-20">
          <h2 className={ST}>Why It Exists</h2>
          <div className={`${BODY} space-y-3`}>
            <p>
              Aleithia's 14 data pipelines ingest thousands of documents — news articles, city
              ordinances, inspection reports, Reddit posts, federal regulations. The enrichment
              layer (BART-large-MNLI + RoBERTa) classifies and scores every document, but this
              data sits in storage until a user asks about it.
            </p>
            <p>
              The Lead Analyst closes this gap. It continuously scans enriched documents, scores
              them for business significance using Qwen3-8B, and when it detects something
              high-impact — a new zoning ordinance, a wave of health inspection failures, a major
              business closure — it autonomously spawns 4 specialized worker agents to investigate
              from every angle.
            </p>
          </div>
        </section>

        {/* ── The 4-Phase Pipeline ── */}
        <section className="mb-20">
          <h2 className={ST}>The 4-Phase Pipeline</h2>
          <p className={`${BODY} mb-8`}>
            Every 5 minutes, the Lead Analyst runs a 4-phase pipeline. Each phase is designed
            to minimize GPU cost by filtering aggressively before expensive LLM calls.
          </p>

          {/* Phase 1 */}
          <div className={`${CARD} mb-4`}>
            <div className="flex items-center gap-3 mb-3">
              <span className={`${TAG} border-green-500/30 text-green-400`}>Phase 1</span>
              <h3 className="text-base font-semibold text-white">Fast Rule-Based Filter</h3>
              <span className="text-[10px] font-mono text-white/20 ml-auto">No GPU</span>
            </div>
            <p className={`${BODY} mb-4`}>
              Before any LLM call, documents are filtered through hard-coded rules that catch
              the most common high-impact patterns. This eliminates 90%+ of documents with zero
              compute cost.
            </p>
            <div className="space-y-2">
              {FILTER_RULES.map(r => (
                <div key={r.rule} className="flex items-start gap-3 text-xs">
                  <span className="text-white/10 mt-0.5">&#9679;</span>
                  <div>
                    <code className={CODE}>{r.rule}</code>
                    <p className="text-white/25 mt-0.5 text-[11px]">{r.example}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 text-[10px] font-mono text-white/15">
              Implementation: <code className={CODE}>_fast_filter()</code> in lead_analyst.py
            </div>
          </div>

          {/* Phase 2 */}
          <div className={`${CARD} mb-4`}>
            <div className="flex items-center gap-3 mb-3">
              <span className={`${TAG} border-violet-500/30 text-violet-400`}>Phase 2</span>
              <h3 className="text-base font-semibold text-white">LLM Significance Scoring</h3>
              <span className="text-[10px] font-mono text-white/20 ml-auto">Qwen3-8B on H100</span>
            </div>
            <p className={`${BODY} mb-4`}>
              Candidates that pass the fast filter are batched into a single Qwen3-8B call.
              The LLM evaluates each document on a 1–10 scale for business impact, returning
              structured JSON with a score, reasoning, category, and affected neighborhoods.
            </p>
            <div className={`border border-white/[0.06] rounded p-4 bg-black/20 font-mono text-[11px] text-white/50 overflow-x-auto`}>
              <pre>{`{
  "evaluations": [
    {
      "index": 0,
      "score": 8,
      "reasoning": "New ordinance restricts sidewalk signage in 3 wards...",
      "category": "regulatory",
      "neighborhoods": ["West Loop", "River North", "Gold Coast"]
    }
  ]
}`}</pre>
            </div>
            <p className="mt-3 text-[11px] text-white/30">
              Documents scoring <span className="text-white/60 font-semibold">&#8805; 7</span> are
              classified as high-impact and proceed to worker dispatch. The threshold balances
              signal quality against coverage.
            </p>
            <div className="mt-3 text-[10px] font-mono text-white/15">
              Implementation: <code className={CODE}>_evaluate_significance()</code> in lead_analyst.py
            </div>
          </div>

          {/* Phase 3 */}
          <div className={`${CARD} mb-4`}>
            <div className="flex items-center gap-3 mb-3">
              <span className={`${TAG} border-amber-500/30 text-amber-400`}>Phase 3</span>
              <h3 className="text-base font-semibold text-white">Parallel Worker Dispatch</h3>
              <span className="text-[10px] font-mono text-white/20 ml-auto">4 &times; E2B Sandbox</span>
            </div>
            <p className={`${BODY} mb-4`}>
              For each high-impact document, 4 specialized workers are spawned in parallel
              via <code className={CODE}>asyncio.gather()</code>. Each worker receives the
              trigger document plus relevant context data from the volume.
            </p>

            {/* Worker cards */}
            <div className="grid sm:grid-cols-2 gap-3">
              {WORKERS.map(w => (
                <div key={w.name} className={`border ${w.border} ${w.bg} rounded-lg p-4`}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-2 h-2 rounded-full ${w.text.replace('text-', 'bg-')} animate-pulse`} />
                    <span className={`text-xs font-semibold ${w.text}`}>{w.name}</span>
                  </div>
                  <p className="text-[11px] text-white/40 leading-relaxed mb-2">{w.desc}</p>
                  <div className="text-[9px] font-mono text-white/15">
                    Source: <code className={CODE}>{w.source}</code>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 text-[10px] font-mono text-white/15">
              Implementation: <code className={CODE}>_dispatch_workers()</code> &rarr; <code className={CODE}>_run_worker()</code> in lead_analyst.py
            </div>
          </div>

          {/* Phase 4 */}
          <div className={`${CARD}`}>
            <div className="flex items-center gap-3 mb-3">
              <span className={`${TAG} border-emerald-500/30 text-emerald-400`}>Phase 4</span>
              <h3 className="text-base font-semibold text-white">Synthesis &amp; Impact Brief</h3>
              <span className="text-[10px] font-mono text-white/20 ml-auto">Qwen3-8B on H100</span>
            </div>
            <p className={`${BODY} mb-4`}>
              All 4 worker results are fed back to Qwen3-8B for synthesis. The LLM produces
              a unified Impact Brief containing an executive summary, narrative analysis,
              and 3–5 actionable recommendations for affected business owners.
            </p>
            <div className={`border border-white/[0.06] rounded p-4 bg-black/20 font-mono text-[11px] text-white/50 overflow-x-auto`}>
              <pre>{`{
  "id": "a7f3c...",
  "trigger_title": "Ordinance: Revised Outdoor Dining Permits",
  "impact_score": 8.5,
  "impact_level": "high",
  "category": "regulatory",
  "neighborhoods_affected": ["West Loop", "River North"],
  "executive_summary": "...",
  "worker_results": [ ... ],  // 4 WorkerResult objects
  "synthesis": "The revised ordinance presents...",
  "recommendations": ["Review permit status before June 1...", ...],
  "e2b_used": true
}`}</pre>
            </div>
            <p className="mt-3 text-[11px] text-white/30">
              Briefs are persisted to <code className={CODE}>/data/processed/impact_briefs/</code> on
              the Modal Volume and served via the <code className={CODE}>/impact-briefs</code> API endpoint.
            </p>
            <div className="mt-3 text-[10px] font-mono text-white/15">
              Implementation: <code className={CODE}>_synthesize_brief()</code> in lead_analyst.py
            </div>
          </div>
        </section>

        {/* ── How Workers Execute ── */}
        <section className="mb-20">
          <h2 className={ST}>How Workers Execute Code</h2>
          <p className={`${BODY} mb-6`}>
            Each worker doesn't just read data — it writes and executes a custom Python analysis
            script generated specifically for the trigger event.
          </p>

          <div className="space-y-4">
            {/* Step 1: Code gen */}
            <div className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full border border-white/[0.1] bg-white/[0.03] flex items-center justify-center text-xs font-mono text-white/40 shrink-0">1</div>
                <div className="flex-1 w-px bg-white/[0.06] mt-2" />
              </div>
              <div className="pb-6">
                <h3 className="text-sm font-semibold text-white mb-1">Code Generation</h3>
                <p className={`${BODY} text-[12px]`}>
                  GPT-4o receives the worker type template, trigger document summary, and context
                  data summary. It generates a self-contained Python script that reads <code className={CODE}>/data/input.json</code> and
                  writes findings to <code className={CODE}>/data/output.json</code>. If no OpenAI
                  key is available, a hardcoded template script is used instead.
                </p>
              </div>
            </div>

            {/* Step 2: Sandbox */}
            <div className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full border border-white/[0.1] bg-white/[0.03] flex items-center justify-center text-xs font-mono text-white/40 shrink-0">2</div>
                <div className="flex-1 w-px bg-white/[0.06] mt-2" />
              </div>
              <div className="pb-6">
                <h3 className="text-sm font-semibold text-white mb-1">Sandbox Execution</h3>
                <p className={`${BODY} text-[12px] mb-3`}>
                  If <code className={CODE}>E2B_API_KEY</code> is set, the script runs in
                  an E2B cloud sandbox — a fully isolated Linux container with a 120-second
                  timeout. Input data is written to the sandbox filesystem, the script executes,
                  and results are read back.
                </p>
                <div className={`border border-white/[0.06] rounded p-3 bg-black/20 font-mono text-[11px] text-white/40 overflow-x-auto`}>
                  <pre>{`sandbox = await AsyncSandbox.create(template="base", timeout=120)
await sandbox.filesystem.write("/data/input.json", input_json)
result = await sandbox.run_code(generated_script)
output = await sandbox.filesystem.read("/data/output.json")
await sandbox.close()`}</pre>
                </div>
              </div>
            </div>

            {/* Step 3: Fallback */}
            <div className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full border border-white/[0.1] bg-white/[0.03] flex items-center justify-center text-xs font-mono text-white/40 shrink-0">3</div>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white mb-1">Fallback: In-Process Exec</h3>
                <p className={`${BODY} text-[12px]`}>
                  Without E2B, workers fall back to Python's <code className={CODE}>exec()</code> in
                  a temporary directory with restricted globals. File paths in the generated code
                  are patched from <code className={CODE}>/data/</code> to the actual temp directory.
                  Less isolated, but functional — the system never stops working.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Where It Lives ── */}
        <section className="mb-20">
          <h2 className={ST}>Where It Lives</h2>
          <p className={`${BODY} mb-6`}>
            The entire Lead Analyst runs as serverless functions on Modal. Nothing runs locally.
          </p>

          <div className="space-y-3">
            {[
              { file: 'modal_app/lead_analyst.py', lines: '907', desc: 'Core module — scanning, filtering, scoring, worker dispatch, synthesis', tag: '@app.function', tagColor: 'border-violet-500/30 text-violet-400' },
              { file: 'modal_app/e2b_utils.py', lines: '20', desc: 'E2B sandbox factory with availability guard', tag: 'utility', tagColor: 'border-white/[0.1] text-white/30' },
              { file: 'modal_app/classify.py', lines: '+8', desc: 'Pushes high-confidence docs to impact_queue after enrichment', tag: 'modified', tagColor: 'border-amber-500/30 text-amber-400' },
              { file: 'modal_app/volume.py', lines: '+4', desc: 'lead_analyst_image with e2b-code-interpreter dependency', tag: 'modified', tagColor: 'border-amber-500/30 text-amber-400' },
              { file: 'modal_app/web.py', lines: '+30', desc: '/impact-briefs, /impact-briefs/:id, /impact-briefs/analyze endpoints', tag: '3 endpoints', tagColor: 'border-cyan-500/30 text-cyan-400' },
            ].map(f => (
              <div key={f.file} className={`${CARD} flex items-start gap-4`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <code className="font-mono text-xs text-white/70">{f.file}</code>
                    <span className={`${TAG} ${f.tagColor}`}>{f.tag}</span>
                  </div>
                  <p className="text-[11px] text-white/35">{f.desc}</p>
                </div>
                <span className="text-[10px] font-mono text-white/15 shrink-0">{f.lines} lines</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Data Flow Diagram ── */}
        <section className="mb-20">
          <h2 className={ST}>Data Flow</h2>
          <div className={`${CARD} overflow-x-auto`}>
            <pre className="text-[11px] font-mono text-white/50 whitespace-pre leading-relaxed">
{`14 Pipelines  ──►  doc_queue  ──►  classify.py (BART + RoBERTa on T4)
                                         │
                                         ▼
                                    impact_queue  (modal.Queue)
                                         │
                                         ▼
                              ┌─── lead_analyst.py ───┐
                              │                       │
                              │  Phase 1: Rule Filter  │   ← no GPU
                              │  Phase 2: Qwen3-8B     │   ← H100
                              │        score ≥ 7?      │
                              │          │             │
                              │    ┌─────┼─────┐      │
                              │    ▼     ▼     ▼      │
                              │  Real  Legal  Econ    │   ← 4× E2B sandbox
                              │  Estate       omic    │     (or in-process)
                              │    │     │     │      │
                              │    ▼     ▼     ▼      │
                              │ Community Sentiment   │
                              │          │            │
                              │          ▼            │
                              │  Phase 4: Synthesize  │   ← H100
                              └──────────┬────────────┘
                                         │
                                         ▼
                              /data/processed/impact_briefs/
                                         │
                                         ▼
                              web.py  ──►  /impact-briefs API
                                         │
                                         ▼
                              Frontend (Dashboard → Models tab)`}</pre>
          </div>
        </section>

        {/* ── Graceful Degradation ── */}
        <section className="mb-20">
          <h2 className={ST}>Graceful Degradation</h2>
          <p className={`${BODY} mb-6`}>
            The system is designed to never fully break. Every dependency has a fallback.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.08]">
                  <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/25">Condition</th>
                  <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/25">Behavior</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['E2B_API_KEY missing', 'Workers run in-process via exec() instead of E2B sandbox'],
                  ['OPENAI_API_KEY missing', 'Worker code generated by hardcoded templates instead of GPT-4o'],
                  ['Both keys missing', 'Workers use template scripts executed in-process'],
                  ['Qwen3-8B unavailable', 'Only rule-based fast filter runs (no LLM scoring)'],
                  ['Impact queue empty', 'Scheduled function returns immediately (no-op)'],
                  ['Worker throws error', 'Error captured in WorkerResult; other workers continue'],
                ].map(([cond, behavior]) => (
                  <tr key={cond} className="border-b border-white/[0.04]">
                    <td className="p-3 text-white/50 font-mono">{cond}</td>
                    <td className="p-3 text-white/35">{behavior}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Deduplication ── */}
        <section className="mb-20">
          <h2 className={ST}>Deduplication</h2>
          <div className={`${BODY} space-y-3`}>
            <p>
              Every analyzed document ID is tracked in a JSON-backed dedup set
              at <code className={CODE}>/data/dedup/impact_analyzed.json</code>, capped
              at 5,000 entries (rolling window). This prevents re-analyzing the same document
              across scan cycles.
            </p>
            <p>
              The dedup mechanism uses the same <code className={CODE}>SeenSet</code> pattern
              as the ingestion pipelines — proven at scale across all 14 data sources.
            </p>
          </div>
        </section>

        {/* ── Observability ── */}
        <section className="mb-20">
          <h2 className={ST}>Observability</h2>
          <p className={`${BODY} mb-6`}>
            Every operation is traced via OpenTelemetry and exported to Arize AX. Spans follow
            the same pattern as the rest of the platform.
          </p>

          <div className="flex flex-wrap gap-2">
            {[
              'scan-enriched-docs',
              'evaluate-significance',
              'impact-dispatch-workers',
              'impact-worker-real_estate',
              'impact-worker-legal',
              'impact-worker-economic',
              'impact-worker-community_sentiment',
              'e2b-sandbox-execute',
              'impact-synthesize',
            ].map(span => (
              <span key={span} className={`${TAG} border-white/[0.08] text-white/30`}>
                {span}
              </span>
            ))}
          </div>
        </section>

        {/* ── API Endpoints ── */}
        <section className="mb-20">
          <h2 className={ST}>API Endpoints</h2>
          <div className="space-y-2">
            {[
              { method: 'GET', path: '/impact-briefs', desc: 'List recent briefs. Params: limit, min_score' },
              { method: 'GET', path: '/impact-briefs/{brief_id}', desc: 'Single brief detail with full worker results' },
              { method: 'POST', path: '/impact-briefs/analyze', desc: 'Manual trigger. Body: {"doc_id": "..."}' },
            ].map(ep => (
              <div key={ep.path} className={`${CARD} flex items-center gap-4`}>
                <span className={`${TAG} ${ep.method === 'POST' ? 'border-amber-500/30 text-amber-400' : 'border-green-500/30 text-green-400'}`}>
                  {ep.method}
                </span>
                <code className="font-mono text-xs text-white/60">{ep.path}</code>
                <span className="text-[11px] text-white/25 ml-auto">{ep.desc}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Pydantic Models ── */}
        <section className="mb-20">
          <h2 className={ST}>Output Schema</h2>
          <p className={`${BODY} mb-6`}>
            All outputs are defined as Pydantic v2 models with strict type validation.
          </p>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className={CARD}>
              <h3 className="text-sm font-semibold text-white mb-3">WorkerResult</h3>
              <div className="space-y-1.5 font-mono text-[11px]">
                {[
                  ['worker_type', 'str', '"real_estate" | "legal" | ...'],
                  ['findings', 'dict', 'Analysis output JSON'],
                  ['confidence', 'float', '0.0 – 1.0'],
                  ['data_points_analyzed', 'int', 'Input doc count'],
                  ['neighborhoods_affected', 'list[str]', 'Impacted areas'],
                  ['error', 'str | None', 'Failure message'],
                ].map(([field, type, note]) => (
                  <div key={field} className="flex items-center gap-2">
                    <span className="text-white/50 w-40 shrink-0">{field}</span>
                    <span className="text-white/20 w-20 shrink-0">{type}</span>
                    <span className="text-white/15 truncate">{note}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className={CARD}>
              <h3 className="text-sm font-semibold text-white mb-3">ImpactBrief</h3>
              <div className="space-y-1.5 font-mono text-[11px]">
                {[
                  ['id', 'str', 'UUID v4'],
                  ['impact_score', 'float', '1–10 significance'],
                  ['impact_level', 'str', '"high" | "critical"'],
                  ['category', 'str', 'regulatory | economic | ...'],
                  ['executive_summary', 'str', '2-3 sentence summary'],
                  ['worker_results', 'list', '4 WorkerResult objects'],
                  ['synthesis', 'str', 'Narrative analysis'],
                  ['recommendations', 'list[str]', '3-5 action items'],
                  ['e2b_used', 'bool', 'Sandbox vs in-process'],
                ].map(([field, type, note]) => (
                  <div key={field} className="flex items-center gap-2">
                    <span className="text-white/50 w-40 shrink-0">{field}</span>
                    <span className="text-white/20 w-20 shrink-0">{type}</span>
                    <span className="text-white/15 truncate">{note}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── Modal Configuration ── */}
        <section className="mb-16">
          <h2 className={ST}>Modal Configuration</h2>
          <div className={`${CARD} overflow-x-auto`}>
            <pre className="text-[11px] font-mono text-white/50 whitespace-pre leading-relaxed">
{`# Scheduled scan — runs every 5 minutes
@app.function(
    image=lead_analyst_image,
    volumes={"/data": volume},
    secrets=[
        modal.Secret.from_name("alethia-secrets"),
        modal.Secret.from_name("arize-secrets"),
    ],
    schedule=modal.Period(minutes=5),
    timeout=300,
)
async def scan_enriched_docs():
    ...

# Manual trigger — on-demand analysis of a single document
@app.function(
    image=lead_analyst_image,
    volumes={"/data": volume},
    secrets=[...],
    timeout=300,
)
async def analyze_impact(doc_id: str) -> dict:
    ...`}</pre>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="px-10 py-8 border-t border-white/[0.04]">
        <p className="text-xs font-mono text-white/20 text-center">
          Built at HackIllinois 2026
        </p>
      </footer>
    </div>
  )
}
