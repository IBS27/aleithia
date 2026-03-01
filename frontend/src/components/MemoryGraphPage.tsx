import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { MemoryGraph, injectStyles } from '@supermemory/memory-graph'
import '@supermemory/memory-graph/styles.css'
import type { DocumentWithMemories } from '@supermemory/memory-graph'

injectStyles()
import { api } from '../api.ts'

const PAGE_SIZE = 50

interface CityGraphData {
  nodes: Array<{ id: string; label?: string; type?: string; lat?: number; lng?: number; size?: number }>
  edges: Array<{ source: string; target: string; weight?: number }>
}

interface Props {
  onBack: () => void
}

function normalizeDocs(raw: Record<string, unknown>[]): DocumentWithMemories[] {
  return raw.map((doc) => {
    const entries = (doc.memoryEntries ?? doc.memories ?? []) as Record<string, unknown>[]
    const docId = String(doc.id ?? doc.customId ?? `doc-${Math.random().toString(36).slice(2)}`)
    const createdAt = typeof doc.createdAt === 'string' ? doc.createdAt : new Date().toISOString()
    const updatedAt = typeof doc.updatedAt === 'string' ? doc.updatedAt : createdAt
    const containerTags = doc.containerTags as string[] | undefined
    // Preserve full memory entries with status/relation fields (isForgotten, forgetAfter, relation, memoryRelations, etc.)
    const memoryEntries = entries.length > 0
      ? entries.map((m) => ({
          ...m,
          id: m.id ?? '',
          documentId: m.documentId ?? docId,
          content: m.memory ?? m.content ?? null,
          createdAt: m.createdAt ?? createdAt,
          updatedAt: m.updatedAt ?? updatedAt,
          isLatest: m.isLatest ?? true,
        })) as DocumentWithMemories['memoryEntries']
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

export default function MemoryGraphPage({ onBack }: Props) {
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const [cityGraph, setCityGraph] = useState<CityGraphData | null>(null)
  const [documents, setDocuments] = useState<DocumentWithMemories[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  // Search
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightsVisible, setHighlightsVisible] = useState(false)

  // Slideshow
  const [slideshowActive, setSlideshowActive] = useState(false)

  const showCityGraph = cityGraph && cityGraph.nodes.length > 0

  // Initial load: try /graph/full first (city graph), fallback to /graph (Supermemory)
  useEffect(() => {
    const base = import.meta.env.VITE_MODAL_URL || '/api/data'
    console.log('[MemoryGraph] Fetching graph/full from', `${base}/graph/full`)
    api
      .graphFull()
      .then((data) => {
        if (data?.nodes?.length) {
          console.log('[MemoryGraph] City graph loaded:', data.nodes.length, 'nodes', data.edges?.length ?? 0, 'edges')
          setCityGraph({ nodes: data.nodes, edges: data.edges ?? [] })
          setIsLoading(false)
          return
        }
        // Fallback to Supermemory graph
        return api.graph({ page: 1, limit: PAGE_SIZE })
      })
      .then((data) => {
        if (!data) return
        const d = data as Record<string, unknown>
        console.log('[MemoryGraph] Response keys:', Object.keys(d), 'pagination:', d.pagination)
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
        console.log('[MemoryGraph] Parsed', raw?.length ?? 0, 'docs. First doc keys:', raw?.[0] ? Object.keys(raw[0]) : 'none')
        if (raw && raw.length === 0) {
          console.log('[MemoryGraph] Empty docs. Full response:', JSON.stringify(d).slice(0, 500))
        }
        setDocuments(normalizeDocs(raw ?? []))
        setHasMore(pagination ? pagination.totalPages > 1 : false)
        setPage(1)
        setIsLoading(false)
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err)
        console.error('[MemoryGraph] Fetch error:', msg, err)
        // If graphFull failed (e.g. 404), try Supermemory graph
        if (msg.includes('404') || msg.includes('graph/full')) {
          api.graph({ page: 1, limit: PAGE_SIZE })
            .then((data) => {
              const d = data as Record<string, unknown>
              const pagination = d.pagination as { totalPages?: number } | undefined
              const top = d.documents ?? d.memories ?? d.data ?? d.result
              const raw = Array.isArray(top) ? top : Array.isArray((top as Record<string, unknown>)?.documents) ? (top as Record<string, unknown>).documents : []
              setDocuments(normalizeDocs((raw ?? []) as Record<string, unknown>[]))
              setHasMore(pagination ? (pagination.totalPages ?? 0) > 1 : false)
            })
            .catch(() => { setDocuments([]); setHasMore(false) })
        } else if (msg.includes('500') || msg.includes('API error')) {
          setDocuments([])
          setHasMore(false)
          setError(null)
        } else {
          setError(err instanceof Error ? err : new Error(String(err)))
        }
        setIsLoading(false)
      })
  }, [])

  // Pagination
  const loadMore = useCallback(async () => {
    if (isLoadingMore) return
    const nextPage = page + 1
    console.log('[MemoryGraph] loadMore page', nextPage)
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

  // Search — client-side filter for highlight IDs
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

  // Toggle highlights when search has results
  useEffect(() => {
    setHighlightsVisible(!!highlightDocumentIds && highlightDocumentIds.length > 0)
  }, [highlightDocumentIds])

  const matchCount = highlightDocumentIds?.length ?? 0

  return (
    <div className="min-h-screen bg-[#06080d] text-white flex flex-col">
      <nav className="flex items-center justify-between px-10 py-5 bg-[#06080d]/95 backdrop-blur-md border-b border-white/[0.06] shrink-0">
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

      {/* Toolbar */}
      <div className="flex items-center gap-4 px-10 py-3 bg-[#06080d]/95 backdrop-blur-md border-b border-white/[0.06] shrink-0">
        {!showCityGraph && (
          <>
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
          </>
        )}
        {/* Stats */}
        <span className="text-xs font-mono text-white/30 ml-auto">
          {showCityGraph
            ? `${cityGraph.nodes.length} nodes, ${cityGraph.edges.length} edges`
            : `${documents.length} docs loaded${hasMore ? ' (more available)' : ''}`}
        </span>
        {!showCityGraph && (
          <div className="ml-4 flex items-center gap-4 text-[10px] font-mono text-white/40">
            <span>Status: Forgotten · Expiring · New</span>
            <span>Connections: Doc→Memory · Similarity (weak/strong)</span>
            <span>Relations: updates · extends · derives</span>
          </div>
        )}
        {!showCityGraph && <div id="memory-graph-legend" className="sr-only" aria-hidden="true" />}
      </div>

      <div ref={containerRef} className="flex-1 min-h-[60vh] w-full">
        {showCityGraph ? (
          <ForceGraph2D
            graphData={{
              nodes: cityGraph.nodes.map((n) => ({ id: n.id, ...n })),
              links: cityGraph.edges.map((e) => ({ source: e.source, target: e.target })),
            }}
            width={typeof window !== 'undefined' ? window.innerWidth - 80 : 800}
            height={typeof window !== 'undefined' ? Math.max(500, window.innerHeight - 220) : 500}
            nodeLabel={(n) => (n as { label?: string }).label ?? (n as { id?: string }).id ?? ''}
            nodeColor={(n) => {
              const t = (n as { type?: string }).type
              if (t === 'neighborhood') return '#60a5fa'
              if (t === 'regulation') return '#f87171'
              if (t === 'business_type') return '#34d399'
              return '#94a3b8'
            }}
            linkColor={() => 'rgba(255,255,255,0.2)'}
            backgroundColor="#06080d"
          />
        ) : (
        <MemoryGraph
          documents={documents}
          isLoading={isLoading}
          error={error}
          variant="console"
          maxNodes={200}
          showSpacesSelector={true}
          legendId="memory-graph-legend"
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
          {!isLoading && documents.length === 0 && (
            <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
              <p className="text-sm font-mono text-white/40">
                No documents in the knowledge graph yet.
              </p>
              <p className="text-xs font-mono text-white/25 max-w-sm">
                Run analysis and ask a question in the chat to ingest documents.
              </p>
              <button
                type="button"
                onClick={() => navigate('/start')}
                className="pointer-events-auto px-6 py-2.5 text-sm font-medium !bg-white !text-[#06080d] hover:!bg-white/90 transition-colors cursor-pointer"
              >
                Get started
              </button>
            </div>
          )}
        </MemoryGraph>
        )}
      </div>
    </div>
  )
}
