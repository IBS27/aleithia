import { useCallback, useEffect, useMemo, useState } from 'react'
import { MemoryGraph } from '@supermemory/memory-graph'
import type { DocumentWithMemories } from '@supermemory/memory-graph'
import { api } from '../api.ts'

const PAGE_SIZE = 50

interface Props {
  onBack: () => void
}

function normalizeDocs(raw: Record<string, unknown>[]): DocumentWithMemories[] {
  return raw.map((doc) => ({
    ...doc,
    memoryEntries: (doc.memoryEntries ?? []) as DocumentWithMemories['memoryEntries'],
    contentHash: (doc.contentHash ?? null) as string | null,
    orgId: (doc.orgId ?? '') as string,
    userId: (doc.userId ?? '') as string,
    status: (doc.status ?? 'done') as DocumentWithMemories['status'],
    createdAt: (doc.createdAt ?? new Date().toISOString()) as string,
    updatedAt: (doc.updatedAt ?? new Date().toISOString()) as string,
  })) as DocumentWithMemories[]
}

export default function MemoryGraphPage({ onBack }: Props) {
  const [documents, setDocuments] = useState<DocumentWithMemories[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  // Search
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightsVisible, setHighlightsVisible] = useState(false)

  // Space filter
  const [selectedSpace, setSelectedSpace] = useState('')

  // Slideshow
  const [slideshowActive, setSlideshowActive] = useState(false)

  // Initial load
  useEffect(() => {
    api
      .graph({ page: 1, limit: PAGE_SIZE })
      .then((data) => {
        const raw = (data as { documents?: Record<string, unknown>[]; pagination?: { totalPages: number } }).documents ?? []
        const pagination = (data as { pagination?: { totalPages: number } }).pagination
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

  // Pagination
  const loadMore = useCallback(async () => {
    if (isLoadingMore) return
    const nextPage = page + 1
    setIsLoadingMore(true)
    try {
      const data = await api.graph({ page: nextPage, limit: PAGE_SIZE })
      const raw = (data as { documents?: Record<string, unknown>[]; pagination?: { totalPages: number } }).documents ?? []
      const pagination = (data as { pagination?: { totalPages: number } }).pagination
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
        {/* Search */}
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

        {/* Slideshow toggle */}
        <button
          type="button"
          onClick={() => setSlideshowActive((prev) => !prev)}
          className={`px-4 py-1.5 text-sm font-medium border transition-colors cursor-pointer ${
            slideshowActive
              ? 'bg-white text-[#06080d] border-white'
              : 'border-white/20 text-white/60 hover:text-white hover:border-white/40'
          }`}
        >
          {slideshowActive ? 'Stop Slideshow' : 'Slideshow'}
        </button>

        {/* Stats */}
        <span className="text-xs font-mono text-white/30 ml-auto">
          {documents.length} docs loaded{hasMore ? ' (more available)' : ''}
        </span>
      </div>

      <div className="flex-1 min-h-[60vh] w-full">
        <MemoryGraph
          documents={documents}
          isLoading={isLoading}
          error={error}
          variant="console"
          maxNodes={80}
          showSpacesSelector
          selectedSpace={selectedSpace}
          onSpaceChange={setSelectedSpace}
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
        />
      </div>
    </div>
  )
}
