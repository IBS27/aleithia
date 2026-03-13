import type { DataSources, GeoJSON, NeighborhoodData, Document, CCTVTimeseries, StreetscapeData, VisionAssessData, ParkingData, SocialTrendsData } from './types'

// Modal deployed endpoint — set via VITE_MODAL_URL, fallback to local proxy
export const API_BASE = import.meta.env.VITE_MODAL_URL || '/api/data'
const LOCAL_USER_ID_KEY = 'aleithia.localUserId'

function getLocalUserId(): string {
  if (typeof window === 'undefined') {
    return 'local-user'
  }

  const existing = window.localStorage.getItem(LOCAL_USER_ID_KEY)?.trim()
  if (existing) {
    return existing
  }

  const generated = `local-${crypto.randomUUID()}`
  window.localStorage.setItem(LOCAL_USER_ID_KEY, generated)
  return generated
}

function withLocalUserId(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers)
  headers.set('x-user-id', getLocalUserId())
  return { ...init, headers }
}

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
  status: 'active' | 'cold' | 'error' | 'disabled'
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

export interface TrendData {
  foot_traffic: { trend: 'up' | 'down' | 'stable'; change_pct: number; current_avg: number; prior_avg: number }
  congestion: { trend: 'up' | 'down' | 'stable'; change_pct: number; anomalies: Array<{ type: string; description: string; road: string }> }
  news_activity: { trend: 'up' | 'down' | 'stable'; change_pct: number }
  hours: Array<{ hour: number; pedestrians: number; vehicles: number; congestion: number }>
}

export async function fetchTrends(neighborhood: string): Promise<TrendData> {
  return fetchJSON<TrendData>(`/trends/${encodeURIComponent(neighborhood)}`)
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
  graphFull: async () => {
    const url = `${API_BASE}/graph/full`
    console.log('[api.graphFull] GET', url)
    const res = await fetch(url)
    const text = await res.text()
    console.log('[api.graphFull] status', res.status, 'nodes:', text.includes('"nodes"') ? 'yes' : 'no')
    if (!res.ok) throw new Error(`API error ${res.status}: ${text}`)
    return JSON.parse(text) as { nodes: Array<{ id: string; label?: string; type?: string }>; edges: Array<{ source: string; target: string }> }
  },
  graph: async (opts?: { page?: number; limit?: number }) => {
    const params = new URLSearchParams()
    if (opts?.page) params.set('page', String(opts.page))
    if (opts?.limit) params.set('limit', String(opts.limit))
    const qs = params.toString()
    const path = `/graph${qs ? `?${qs}` : ''}`
    const url = `${API_BASE}${path}`
    console.log('[api.graph] GET', url)
    const res = await fetch(url)
    const text = await res.text()
    console.log('[api.graph] status', res.status, 'body length', text.length, 'body preview', text.slice(0, 200))
    if (!res.ok) {
      throw new Error(`API error ${res.status}: ${text}`)
    }
    try {
      return JSON.parse(text) as Record<string, unknown>
    } catch {
      console.error('[api.graph] Invalid JSON:', text.slice(0, 500))
      throw new Error('Invalid JSON response from /graph')
    }
  },
  
  getUserProfile: () => fetchJSON<SavedSettings>('/user/profile', withLocalUserId()),
  
  updateUserProfile: (businessType: string, neighborhood: string, riskTolerance?: string) =>
    fetchJSON<SavedSettings>('/user/profile', withLocalUserId({
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        business_type: businessType,
        neighborhood,
        risk_tolerance: riskTolerance,
      }),
    })),

  getUserQueries: (limit = 10) =>
    fetchJSON<UserQuery[]>(`/user/queries?limit=${limit}`, withLocalUserId()),

  createUserQuery: (payload: { query_text: string; business_type: string; neighborhood: string }) =>
    fetchJSON<UserQuery>('/user/queries', withLocalUserId({
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })),

  cctvFrameUrl: (cameraId: string) =>
    `${API_BASE}/cctv/frame/${encodeURIComponent(cameraId)}`,

  cctvTimeseries: (neighborhood: string) =>
    fetchJSON<CCTVTimeseries>(`/cctv/timeseries/${encodeURIComponent(neighborhood)}`),

  streetscape: (neighborhood: string) =>
    fetchJSON<StreetscapeData>(`/vision/streetscape/${encodeURIComponent(neighborhood)}`),

  visionAssess: (neighborhood: string) =>
    fetchJSON<VisionAssessData>(`/vision/assess/${encodeURIComponent(neighborhood)}`),

  parkingLatest: () =>
    fetchJSON<{ neighborhoods: ParkingData[]; count: number }>('/parking/latest'),

  parking: (neighborhood: string) =>
    fetchJSON<ParkingData>(`/parking/${encodeURIComponent(neighborhood)}`),

  parkingAnnotatedUrl: (neighborhood: string) =>
    `${API_BASE}/parking/annotated/${encodeURIComponent(neighborhood)}`,

  socialTrends: (neighborhood: string, businessType?: string) => {
    const qs = businessType ? `?business_type=${encodeURIComponent(businessType)}` : ''
    return fetchJSON<SocialTrendsData>(`/social-trends/${encodeURIComponent(neighborhood)}${qs}`)
  },
}

export interface GraphNode {
  id: string
  type: 'neighborhood' | 'regulation' | 'entity' | 'business_type'
  label: string
  size: number
  lat?: number
  lng?: number
  sentiment?: number
}

export interface GraphEdge {
  source: string
  target: string
  type: 'regulates' | 'sentiment' | 'competes_in' | 'affects' | 'trending'
  weight: number
}

export interface CityGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats?: {
    total_nodes: number
    total_edges: number
    neighborhoods: number
    regulations: number
    entities: number
    business_types: number
    built_at: string
  }
  center?: string
}

export async function fetchCityGraph(): Promise<CityGraphData> {
  return fetchJSON<CityGraphData>('/graph/full')
}

export async function fetchNeighborhoodGraph(neighborhood: string): Promise<CityGraphData> {
  return fetchJSON<CityGraphData>(`/graph/neighborhood/${encodeURIComponent(neighborhood)}`)
}

export interface UserMemoryData {
  profile: { static?: string[]; dynamic?: string[] }
  memories: Array<{ content: string; type: string }>
  memory_count: number
}

export async function fetchUserMemories(userId: string): Promise<UserMemoryData> {
  return fetchJSON<UserMemoryData>(`/user/memories?user_id=${encodeURIComponent(userId)}`)
}
