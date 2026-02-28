import type { DataSources, GeoJSON, NeighborhoodData, Document } from './types'

const BASE = '/api/data'

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
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
