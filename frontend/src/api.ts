import type { DataSources, GeoJSON, NeighborhoodData, Document } from './types'

const BASE = '/api/data'

// Modal deployed endpoint — set via env or fallback to local proxy
const MODAL_BASE = import.meta.env.VITE_MODAL_URL || ''

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

async function fetchModalJSON<T>(path: string): Promise<T> {
  const base = MODAL_BASE || BASE
  const res = await fetch(`${base}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export interface StreamChatCallbacks {
  onStatus?: (content: string) => void
  onAgents?: (data: { agents_deployed: number; neighborhoods: string[]; data_points: number }) => void
  onToken?: (token: string) => void
  onDone?: () => void
  onError?: (error: string) => void
}

export async function streamChat(
  message: string,
  profile: { business_type: string; neighborhood: string },
  callbacks: StreamChatCallbacks,
  userId?: string,
): Promise<void> {
  const base = MODAL_BASE || ''
  const chatUrl = base ? `${base}/chat` : '/api/data/chat'

  const res = await fetch(chatUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      user_id: userId || `user_${Date.now()}`,
      business_type: profile.business_type,
      neighborhood: profile.neighborhood,
    }),
  })

  if (!res.ok) {
    callbacks.onError?.(`Chat API error: ${res.status}`)
    return
  }

  const reader = res.body?.getReader()
  if (!reader) {
    callbacks.onError?.('No response body')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        switch (data.type) {
          case 'status':
            callbacks.onStatus?.(data.content)
            break
          case 'agents':
            callbacks.onAgents?.(data)
            break
          case 'token':
            callbacks.onToken?.(data.content)
            break
          case 'done':
            callbacks.onDone?.()
            break
          case 'error':
            callbacks.onError?.(data.content)
            break
        }
      } catch {
        // Skip malformed lines
      }
    }
  }
}

export interface PipelineStatus {
  pipelines: Record<string, { doc_count: number; last_update: string | null; state: string }>
  enriched_docs: number
  gpu_status: Record<string, string>
  costs: Record<string, unknown>
  total_docs: number
}

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  return fetchModalJSON<PipelineStatus>('/status')
}

export async function fetchMetrics(): Promise<Record<string, number>> {
  return fetchModalJSON<Record<string, number>>('/metrics')
}

export const api = {
  sources: () => fetchJSON<DataSources>('/sources'),
  geo: () => fetchJSON<GeoJSON>('/geo'),
  summary: () => fetchJSON<Record<string, unknown>>('/summary'),
  neighborhood: (name: string) => fetchJSON<NeighborhoodData>(`/neighborhood/${encodeURIComponent(name)}`),
  inspections: (opts?: { neighborhood?: string; result?: string }) => {
    const params = new URLSearchParams()
    if (opts?.neighborhood) params.set('neighborhood', opts.neighborhood)
    if (opts?.result) params.set('result', opts.result)
    const qs = params.toString()
    return fetchJSON<Document[]>(`/inspections${qs ? `?${qs}` : ''}`)
  },
  permits: (neighborhood?: string) => {
    const qs = neighborhood ? `?neighborhood=${encodeURIComponent(neighborhood)}` : ''
    return fetchJSON<Document[]>(`/permits${qs}`)
  },
  licenses: (neighborhood?: string) => {
    const qs = neighborhood ? `?neighborhood=${encodeURIComponent(neighborhood)}` : ''
    return fetchJSON<Document[]>(`/licenses${qs}`)
  },
  news: () => fetchJSON<Document[]>('/news'),
  politics: () => fetchJSON<Document[]>('/politics'),
}
