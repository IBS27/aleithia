import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MemoryGraph, injectStyles } from '@supermemory/memory-graph'
import '@supermemory/memory-graph/styles.css'
import type { DocumentWithMemories } from '@supermemory/memory-graph'
import { api } from '../api.ts'
import memGraphImg from './mem-grap.png'

injectStyles()

const PAGE_SIZE = 50
const SECTION_HEADER = 'text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/30 mb-4'

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

export default function MemGraph() {
  const navigate = useNavigate()
  const [documents, setDocuments] = useState<DocumentWithMemories[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightsVisible, setHighlightsVisible] = useState(false)
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
    <section className="border-y border-white/[0.04]">
      <div className="max-w-4xl mx-auto px-10 pt-20 pb-12">
        <p className={SECTION_HEADER}>Knowledge layer</p>
        <h2 className="text-4xl sm:text-5xl font-bold tracking-tight text-white leading-[1.1] mb-4">
          Memory Graph
        </h2>
        <p className="text-base text-white/50 mb-6 max-w-2xl">
          Every ingested document is stored in Supermemory and connected by semantic similarity. Search, filter by source, or run a slideshow to explore the knowledge graph.
        </p>
        <img src={memGraphImg} alt="Memory Graph" className="w-full max-h-48 object-contain object-top rounded-lg" />
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-4 px-10 py-3 mt-8 bg-[#06080d]/95 backdrop-blur-md border-y border-white/[0.06]">
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

      <div className="h-[500px] max-w-4xl mx-auto px-10 pb-6">
        <div className="h-full w-full rounded-lg border border-white/[0.12] overflow-hidden bg-white/[0.02]">
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
                Get started
              </button>
            </div>
          </MemoryGraph>
        </div>
      </div>
    </section>
  )
}
