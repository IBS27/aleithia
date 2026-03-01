import type { DataSources, GeoJSON, NeighborhoodData, Document } from './types'

// Modal deployed endpoint — set via VITE_MODAL_URL, fallback to local proxy
const API_BASE = import.meta.env.VITE_MODAL_URL || '/api/data'

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    const error = await res.text()
    throw new Error(`API error ${res.status}: ${error}`)
  }
  return res.json()
}

export interface SavedSettings {
  clerk_user_id: string
  business_type: string | null
  neighborhood: string | null
  risk_tolerance: string
  created_at: string
  updated_at: string
}

export interface UserQuery {
  id: number
  clerk_user_id: string
  query_text: string
  business_type: string
  neighborhood: string
  created_at: string
}

export interface StreamChatCallbacks {
  onStatus?: (content: string) => void
  onAgents?: (data: {
    agents_deployed: number
    neighborhoods: string[]
    data_points: number
    agent_summaries?: Array<{
      name: string
      data_points: number
      sources?: string[]
      regulation_count?: number
      error?: boolean
    }>
  }) => void
  onToken?: (token: string) => void
  onDone?: () => void
  onError?: (error: string) => void
}

export async function streamChat(
  message: string,
  profile: { business_type: string; neighborhood: string },
  callbacks: StreamChatCallbacks,
  token?: string,
): Promise<void> {
  const chatUrl = `${API_BASE}/chat`

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(chatUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message,
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

export interface DeepDiveResult {
  code: string
  result: { title?: string; summary?: string; stats?: Record<string, unknown>; raw_output?: string }
  chart: string | null
  stderr: string | null
}

export async function requestDeepDive(
  question: string,
  brief: string,
  neighborhood: string,
  businessType: string,
): Promise<DeepDiveResult> {
  return fetchJSON<DeepDiveResult>('/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      brief,
      neighborhood,
      business_type: businessType,
    }),
  })
}

export interface PipelineStatus {
  pipelines: Record<string, { doc_count: number; last_update: string | null; state: string }>
  enriched_docs: number
  gpu_status: Record<string, string>
  costs: Record<string, unknown>
  total_docs: number
}

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  return fetchJSON<PipelineStatus>('/status')
}

export async function fetchMetrics(): Promise<Record<string, number>> {
  return fetchJSON<Record<string, number>>('/metrics')
}

export interface GpuMetricsEntry {
  status: 'active' | 'cold' | 'error'
  inferred?: boolean
  reason?: 'idle' | 'no_data'
  enriched_count?: number
  last_run_ago_s?: number
  gpu_utilization?: number
  memory_utilization?: number
  memory_used_mb?: number
  memory_total_mb?: number
  temperature_c?: number
  power_draw_w?: number
  power_limit_w?: number
  gpu_name?: string
  timestamp?: string
}

export type GpuMetrics = Record<string, GpuMetricsEntry>

export async function fetchGpuMetrics(): Promise<GpuMetrics> {
  return fetchJSON<GpuMetrics>('/gpu-metrics')
}

export const api = {
  sources: () => fetchJSON<DataSources>('/sources'),
  geo: () => fetchJSON<GeoJSON>('/geo'),
  summary: () => fetchJSON<Record<string, unknown>>('/summary'),
  neighborhood: (name: string, businessType?: string) => {
    const qs = businessType ? `?business_type=${encodeURIComponent(businessType)}` : ''
    return fetchJSON<NeighborhoodData>(`/neighborhood/${encodeURIComponent(name)}${qs}`)
  },
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
  graph: (opts?: { page?: number; limit?: number }) => {
    const params = new URLSearchParams()
    if (opts?.page) params.set('page', String(opts.page))
    if (opts?.limit) params.set('limit', String(opts.limit))
    const qs = params.toString()
    return fetchJSON<Record<string, unknown>>(`/graph${qs ? `?${qs}` : ''}`)
  },
  
  // User profile endpoints (require Clerk token)
  getUserProfile: (token: string) => fetchJSON<SavedSettings>('/user/profile', {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  }),
  
  updateUserProfile: (token: string, businessType: string, neighborhood: string, riskTolerance?: string) =>
    fetchJSON<SavedSettings>('/user/profile', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        business_type: businessType,
        neighborhood,
        risk_tolerance: riskTolerance,
      }),
    }),

  getUserQueries: (token: string, limit = 10) =>
    fetchJSON<UserQuery[]>(`/user/queries?limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }),

  createUserQuery: (token: string, payload: { query_text: string; business_type: string; neighborhood: string }) =>
    fetchJSON<UserQuery>('/user/queries', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    }),

  cctvFrameUrl: (cameraId: string) =>
    `${API_BASE}/cctv/frame/${encodeURIComponent(cameraId)}`,
}
