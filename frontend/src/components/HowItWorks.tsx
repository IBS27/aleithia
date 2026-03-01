import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MemoryGraph, injectStyles } from '@supermemory/memory-graph'
import '@supermemory/memory-graph/styles.css'
import type { DocumentWithMemories } from '@supermemory/memory-graph'
import { api } from '../api.ts'

injectStyles()

const PAGE_SIZE = 50

interface Props {
  onBack: () => void
}

const SECTION_HEADER = 'text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/30 mb-4'
const SECTION_TITLE = 'text-2xl sm:text-3xl font-bold tracking-tight text-white mb-6'
const BODY = 'text-sm text-white/60 leading-relaxed space-y-3'
const CODE = 'font-mono text-xs bg-white/[0.06] border border-white/[0.08] rounded px-2 py-1 text-white/80'
const CARD = 'border border-white/[0.06] rounded-lg p-6 bg-white/[0.02]'

function normalizeEntries(docId: string, entries: Record<string, unknown>[]): DocumentWithMemories['memoryEntries'] {
  return entries.map((e) => ({
    ...e,
    id: (e.id ?? '') as string,
    documentId: (e.documentId ?? docId) as string,
    content: (e.content ?? e.memory ?? '') as string | null,
    createdAt: (e.createdAt ?? new Date().toISOString()) as string | Date,
    updatedAt: (e.updatedAt ?? new Date().toISOString()) as string | Date,
  })) as DocumentWithMemories['memoryEntries']
}

function normalizeDocs(raw: Record<string, unknown>[]): DocumentWithMemories[] {
  return raw.map((doc) => {
    const docId = String(doc.id ?? doc.customId ?? `doc-${Math.random().toString(36).slice(2)}`)
    const createdAt = typeof doc.createdAt === 'string' ? doc.createdAt : new Date().toISOString()
    const updatedAt = typeof doc.updatedAt === 'string' ? doc.updatedAt : createdAt
    const containerTags = doc.containerTags as string[] | undefined
    const rawEntries = (doc.memoryEntries ?? doc.memories ?? []) as Record<string, unknown>[]
    const memoryEntries = rawEntries.length > 0
      ? normalizeEntries(docId, rawEntries)
      : [{
          id: `${docId}-m0`,
          documentId: docId,
          content: (doc.content ?? doc.summary ?? '') as string | null,
          title: (doc.title ?? null) as string | null,
          createdAt,
          updatedAt,
          metadata: (doc.metadata ?? null) as Record<string, string | number | boolean> | null,
        }] as DocumentWithMemories['memoryEntries']
    return {
      ...doc,
      id: docId,
      memoryEntries,
      contentHash: (doc.contentHash ?? null) as string | null,
      orgId: String(doc.orgId ?? ''),
      userId: String(doc.userId ?? containerTags?.[0] ?? ''),
      status: (doc.status ?? 'done') as DocumentWithMemories['status'],
      createdAt,
      updatedAt,
    } as DocumentWithMemories
  })
}

export default function HowItWorks({ onBack }: Props) {
  const navigate = useNavigate()
  // Memory graph state
  const [documents, setDocuments] = useState<DocumentWithMemories[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightsVisible, setHighlightsVisible] = useState(false)
  const [selectedSpace, setSelectedSpace] = useState('')
  const [slideshowActive, setSlideshowActive] = useState(false)

  useEffect(() => {
    api
      .graph({ page: 1, limit: PAGE_SIZE })
      .then((data) => {
        const d = data as Record<string, unknown>
        const pagination = d.pagination as { totalPages?: number } | undefined
        let raw: Record<string, unknown>[] | undefined
        const top = d.documents ?? d.memories ?? d.data ?? d.result
        if (Array.isArray(top)) {
          raw = top
        } else if (top && typeof top === 'object' && !Array.isArray(top)) {
          const inner = (top as Record<string, unknown>).documents ?? (top as Record<string, unknown>).memories ?? (top as Record<string, unknown>).items
          raw = Array.isArray(inner) ? inner : []
        } else {
          raw = []
        }
        setDocuments(normalizeDocs(raw))
        setHasMore(pagination ? pagination.totalPages > 1 : false)
        setPage(1)
        setIsLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err : new Error(String(err)))
        setIsLoading(false)
      })
  }, [])

  const loadMore = useCallback(async () => {
    if (isLoadingMore) return
    const nextPage = page + 1
    setIsLoadingMore(true)
    try {
      const data = await api.graph({ page: nextPage, limit: PAGE_SIZE })
      const d = data as Record<string, unknown>
      const pagination = d.pagination as { totalPages?: number } | undefined
      let raw: Record<string, unknown>[] | undefined
      const top = d.documents ?? d.memories ?? d.data ?? d.result
      if (Array.isArray(top)) {
        raw = top
      } else if (top && typeof top === 'object' && !Array.isArray(top)) {
        const inner = (top as Record<string, unknown>).documents ?? (top as Record<string, unknown>).memories ?? (top as Record<string, unknown>).items
        raw = Array.isArray(inner) ? inner : []
      } else {
        raw = []
      }
      setDocuments((prev) => [...prev, ...normalizeDocs(raw)])
      setHasMore(pagination ? nextPage < pagination.totalPages : false)
      setPage(nextPage)
    } catch (err) {
      console.error('Failed to load more documents:', err)
    } finally {
      setIsLoadingMore(false)
    }
  }, [page, isLoadingMore])

  const highlightDocumentIds = useMemo(() => {
    if (!searchQuery.trim()) return undefined
    const q = searchQuery.toLowerCase()
    return documents
      .filter((doc) => {
        const title = ((doc as Record<string, unknown>).title as string) ?? ''
        const content = ((doc as Record<string, unknown>).content as string) ?? ''
        const source = ((doc as Record<string, unknown>).source as string) ?? ''
        return title.toLowerCase().includes(q) || content.toLowerCase().includes(q) || source.toLowerCase().includes(q)
      })
      .map((doc) => doc.id)
  }, [searchQuery, documents])

  useEffect(() => {
    setHighlightsVisible(!!highlightDocumentIds && highlightDocumentIds.length > 0)
  }, [highlightDocumentIds])

  const matchCount = highlightDocumentIds?.length ?? 0

  return (
    <div className="min-h-screen bg-[#06080d] text-white">
      {/* Nav */}
      <nav className="sticky top-0 z-50 flex items-center justify-between px-10 py-5 bg-[#06080d]/95 backdrop-blur-md border-b border-white/[0.06]">
        <button
          type="button"
          onClick={onBack}
          className="text-lg font-semibold tracking-tight text-white uppercase hover:text-white/80 transition-colors cursor-pointer"
        >
          Alethia
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
          Alethia ingests Chicago-area data, enriches it with GPU models, and delivers insights through an agent swarm. All compute runs on Modal.
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
            <span className={CODE}>modal_app/llm.py</span> — AlethiaLLM runs Qwen3 8B via vLLM on H100 for streaming chat and intelligence briefs. 20 concurrent inputs via <span className={CODE}>@modal.concurrent</span>.
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
      </main>

      {/* Memory Graph — full-width, outside max-w container */}
      <section className="border-t border-white/[0.04]">
        <div className="max-w-4xl mx-auto px-10 pt-20 pb-6">
          <p className={SECTION_HEADER}>Knowledge layer</p>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight text-white leading-[1.1] mb-4">
            Memory Graph
          </h2>
          <p className="text-base text-white/50 mb-8 max-w-2xl">
            Every ingested document is stored in Supermemory and connected by semantic similarity. Search, filter by source, or run a slideshow to explore the knowledge graph.
          </p>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-4 px-10 py-3 bg-[#06080d]/95 backdrop-blur-md border-y border-white/[0.06]">
          <div className="relative flex-1 max-w-sm">
            <input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-1.5 text-sm bg-white/[0.06] border border-white/[0.1] text-white placeholder-white/30 focus:outline-none focus:border-white/30 transition-colors"
            />
            {searchQuery && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-mono text-white/40">
                {matchCount} found
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => setSlideshowActive((prev) => !prev)}
            className={`px-4 py-1.5 text-sm font-medium border transition-colors cursor-pointer ${
              slideshowActive
                ? '!bg-white !text-[#06080d] border-white'
                : 'border-white/20 text-white/60 hover:text-white hover:border-white/40'
            }`}
          >
            {slideshowActive ? 'Stop Slideshow' : 'Slideshow'}
          </button>
          <span className="text-xs font-mono text-white/30 ml-auto">
            {documents.length} docs loaded{hasMore ? ' (more available)' : ''}
          </span>
        </div>

        <div className="h-[700px] w-full">
          <MemoryGraph
            documents={documents}
            isLoading={isLoading}
            error={error}
            variant="console"
            maxNodes={200}
            showSpacesSelector={false}
            hasMore={hasMore}
            loadMoreDocuments={loadMore}
            isLoadingMore={isLoadingMore}
            totalLoaded={documents.length}
            autoLoadOnViewport
            highlightDocumentIds={highlightDocumentIds}
            highlightsVisible={highlightsVisible}
            isSlideshowActive={slideshowActive}
            onSlideshowNodeChange={() => {}}
            onSlideshowStop={() => setSlideshowActive(false)}
          >
            <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
              <p className="text-sm font-mono text-white/40">No documents in the knowledge graph yet.</p>
              <p className="text-xs font-mono text-white/25 max-w-sm">Run analysis and ask a question in the chat to ingest documents.</p>
              <button
                type="button"
                onClick={() => navigate('/start')}
                className="pointer-events-auto px-6 py-2.5 text-sm font-medium !bg-white !text-[#06080d] hover:!bg-white/90 transition-colors cursor-pointer"
              >
                Initialize Session
              </button>
            </div>
          </MemoryGraph>
        </div>
      </section>

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
