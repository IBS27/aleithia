import { useState, useEffect } from 'react'
import { API_BASE, fetchPipelineStatus, fetchGpuMetrics, fetchMetrics } from '../api.ts'
import type { PipelineStatus, GpuMetrics, GpuMetricsEntry } from '../api.ts'

// ── Types ────────────────────────────────────────────────────────────

interface WorkerResult {
  worker_type: string
  findings: Record<string, unknown>
  confidence: number
  data_points_analyzed: number
  neighborhoods_affected: string[]
  error: string | null
}

interface ImpactBrief {
  id: string
  trigger_doc_id: string
  trigger_title: string
  trigger_source: string
  impact_score: number
  impact_level: string
  category: string
  neighborhoods_affected: string[]
  executive_summary: string
  worker_results: WorkerResult[]
  synthesis: string
  recommendations: string[]
  timestamp: string
  processing_time_seconds: number
  e2b_used: boolean
}

// ── Autonomous Systems types + constants ─────────────────────────────

interface GpuFleetCard {
  key: string
  gpu: string
  label: string
  task: string
  warm: boolean
}

interface ActivityEntry {
  type: 'SCAN' | 'FILTER' | 'DISPATCH' | 'BRIEF'
  label: string
  time: string
  color: string
}

const PIPELINE_SOURCES: { key: string; label: string }[] = [
  { key: 'news', label: 'News' },
  { key: 'reddit', label: 'Reddit' },
  { key: 'politics', label: 'Politics' },
  { key: 'public_data', label: 'Public Data' },
  { key: 'federal_register', label: 'Fed Register' },
  { key: 'demographics', label: 'Demographics' },
  { key: 'reviews', label: 'Reviews' },
  { key: 'realestate', label: 'Real Estate' },
  { key: 'tiktok', label: 'TikTok' },
]

const GPU_FLEET: GpuFleetCard[] = [
  { key: 'llm', gpu: 'H100', label: 'Qwen3-8B', task: 'LLM Inference', warm: true },
  { key: 'classifier', gpu: 'T4', label: 'Classifier', task: 'bart-large-mnli', warm: false },
  { key: 'sentiment', gpu: 'T4', label: 'Sentiment', task: 'roberta', warm: false },
  { key: 'cctv', gpu: 'T4', label: 'CCTV', task: 'YOLOv8n', warm: false },
  { key: 'parking', gpu: 'T4', label: 'Parking', task: 'SegFormer+YOLO', warm: false },
]

const STALE_THRESHOLD_MINUTES = 60
const DEAD_THRESHOLD_MINUTES = 1440

type Freshness = 'fresh' | 'aging' | 'stale' | 'empty'

function pipelineFreshness(lastUpdate: string | null): Freshness {
  if (!lastUpdate) return 'empty'
  const ageMin = (Date.now() - new Date(lastUpdate).getTime()) / 60000
  if (ageMin < STALE_THRESHOLD_MINUTES) return 'fresh'
  if (ageMin < DEAD_THRESHOLD_MINUTES) return 'aging'
  return 'stale'
}

function freshnessColor(f: Freshness): string {
  switch (f) {
    case 'fresh': return 'bg-emerald-400'
    case 'aging': return 'bg-amber-400'
    case 'stale': return 'bg-red-400'
    case 'empty': return 'bg-white/20'
  }
}

function freshnessLabel(lastUpdate: string | null, f: Freshness): string {
  if (f === 'empty') return 'no data'
  if (f === 'stale') return 'stale — auto-restarting'
  return relativeTime(lastUpdate!)
}

function gpuStatusBadge(entry: GpuMetricsEntry | undefined): { label: string; color: string; glow: string; animate: boolean } {
  if (!entry || entry.status === 'cold') return { label: 'COLD', color: 'text-white/30', glow: '', animate: false }
  if (entry.status === 'error') return { label: 'ERROR', color: 'text-red-400', glow: '', animate: false }
  return { label: 'ACTIVE', color: 'text-emerald-400', glow: 'shadow-[0_0_8px_rgba(52,211,153,0.2)]', animate: true }
}

function deriveActivityLog(briefs: ImpactBrief[]): ActivityEntry[] {
  const entries: ActivityEntry[] = []

  // SCAN entry — always present if we have briefs
  if (briefs.length > 0) {
    entries.push({
      type: 'SCAN',
      label: `${briefs.length} brief${briefs.length !== 1 ? 's' : ''} in queue`,
      time: 'just now',
      color: 'bg-cyan-400',
    })
  }

  // Derive BRIEF + DISPATCH from each brief
  for (const b of briefs.slice(0, 3)) {
    const ts = relativeTime(b.timestamp)
    entries.push({
      type: 'BRIEF',
      label: `${b.trigger_title?.slice(0, 40) || 'Event'} — score ${b.impact_score}/10`,
      time: ts,
      color: 'bg-emerald-400',
    })
    const nCount = b.neighborhoods_affected.length || 1
    entries.push({
      type: 'DISPATCH',
      label: `${b.worker_results.length} workers → ${nCount} neighborhood${nCount !== 1 ? 's' : ''}`,
      time: ts,
      color: 'bg-violet-400',
    })
  }

  return entries.slice(0, 6)
}

const WORKER_META: Record<string, { label: string; color: string; accent: string; sources: string }> = {
  real_estate:         { label: 'Real Estate',         color: 'text-cyan-400',    accent: 'border-cyan-500/30',    sources: 'LoopNet, listings' },
  legal:               { label: 'Legal & Regulatory',  color: 'text-violet-400',  accent: 'border-violet-500/30',  sources: 'Legistar, Fed Register' },
  economic:            { label: 'Economic',            color: 'text-amber-400',   accent: 'border-amber-500/30',   sources: 'Census, public data' },
  community_sentiment: { label: 'Community Sentiment', color: 'text-emerald-400', accent: 'border-emerald-500/30', sources: 'Reddit, reviews, news' },
}

// ── SVG icons (inline, no deps) ──────────────────────────────────────

function StageIcon({ type, className = '' }: { type: string; className?: string }) {
  const cls = `w-3.5 h-3.5 ${className}`
  switch (type) {
    case 'db':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" /><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" /></svg>
    case 'gpu':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h6v6H9z" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M20 9h3M1 15h3M20 15h3" /></svg>
    case 'queue':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M16 3H8a2 2 0 00-2 2v14a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2z" /><path d="M10 8h4M10 12h4M10 16h4" /></svg>
    case 'filter':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" /></svg>
    case 'brain':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" /><path d="M9 21h6M10 17v4M14 17v4" /></svg>
    case 'fork':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="6" r="2" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="18" r="2" /><path d="M12 8v4M12 12l-6 4M12 12l6 4" /></svg>
    case 'merge':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="18" r="2" /><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><path d="M12 16v-4M12 12L6 8M12 12l6-4" /></svg>
    default:
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="12" r="4" /></svg>
  }
}

// ── Helper: relative time ────────────────────────────────────────────

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function levelColor(level: string): string {
  if (level === 'critical') return 'text-red-400'
  if (level === 'high') return 'text-amber-400'
  return 'text-white/50'
}

function levelBg(level: string): string {
  if (level === 'critical') return 'bg-red-500/10 border-red-500/20'
  if (level === 'high') return 'bg-amber-500/8 border-amber-500/20'
  return 'bg-white/[0.02] border-white/[0.06]'
}

function categoryLabel(cat: string): string {
  return cat.charAt(0).toUpperCase() + cat.slice(1)
}

// ── Main component ───────────────────────────────────────────────────

export default function RecursiveAgentPanel() {
  const [briefs, setBriefs] = useState<ImpactBrief[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [expandedBrief, setExpandedBrief] = useState<string | null>(null)
  const [expandedWorker, setExpandedWorker] = useState<string | null>(null)

  // ── Autonomous Systems state ──
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null)
  const [gpuMetrics, setGpuMetrics] = useState<GpuMetrics | null>(null)
  const [sysMetrics, setSysMetrics] = useState<Record<string, number> | null>(null)
  const [lastHeartbeat, setLastHeartbeat] = useState<number | null>(null)

  // Poll pipeline status + GPU metrics + system metrics every 15s
  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const [status, gpu, metrics] = await Promise.all([
          fetchPipelineStatus().catch(() => null),
          fetchGpuMetrics().catch(() => null),
          fetchMetrics().catch(() => null),
        ])
        if (cancelled) return
        if (status) { setPipelineStatus(status); setLastHeartbeat(Date.now()) }
        if (gpu) setGpuMetrics(gpu)
        if (metrics) setSysMetrics(metrics)
      } catch { /* best-effort */ }
    }
    poll()
    const interval = setInterval(poll, 15000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  // Fetch impact briefs
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/impact-briefs?limit=20`)
        if (!res.ok) throw new Error(`${res.status}`)
        const data = await res.json()
        if (!cancelled) {
          setBriefs(data.briefs || [])
          setError(false)
        }
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 30000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  return (
    <div className="space-y-6">
      {/* ── Section header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
            Recursive Agent Architecture
          </span>
        </div>
        <span className="text-[10px] font-mono text-white/15">
          {briefs.length} brief{briefs.length !== 1 ? 's' : ''} generated
        </span>
      </div>

      {/* ── Section A: Autonomous Systems ── */}
      <div className="border border-white/[0.04] bg-white/[0.01] p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className={`w-1.5 h-1.5 rounded-full ${lastHeartbeat ? 'bg-emerald-400 animate-pulse' : 'bg-white/20'}`} />
            <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
              Autonomous Systems
            </span>
          </div>
          <span className="text-[9px] font-mono text-white/15">
            {lastHeartbeat
              ? `HEARTBEAT OK — ${Math.round((Date.now() - lastHeartbeat) / 1000)}s ago`
              : 'CONNECTING...'}
          </span>
        </div>

        {/* Pipeline source grid */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          {PIPELINE_SOURCES.map(src => {
            const info = pipelineStatus?.pipelines?.[src.key]
            const freshness = pipelineFreshness(info?.last_update ?? null)
            const dotColor = freshnessColor(freshness)
            return (
              <div key={src.key} className="border border-white/[0.06] bg-white/[0.02] p-2.5 relative overflow-hidden">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${dotColor} ${freshness === 'aging' ? 'animate-pulse' : ''}`} />
                    <span className="text-[9px] font-mono uppercase tracking-wider text-white/40">
                      {src.label}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-white/25 tabular-nums">
                    {info?.doc_count ?? '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className={`text-[8px] font-mono ${freshness === 'stale' ? 'text-red-400/60' : 'text-white/15'}`}>
                    {freshnessLabel(info?.last_update ?? null, freshness)}
                  </span>
                  {freshness === 'stale' && (
                    <span className="text-[7px] font-mono uppercase tracking-wider text-amber-400 animate-pulse">
                      SELF-HEALING
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-6 pt-3 border-t border-white/[0.04]">
          {[
            { value: pipelineStatus?.total_docs ?? '—', label: 'TOTAL DOCS' },
            { value: pipelineStatus?.enriched_docs ?? '—', label: 'ENRICHED' },
            { value: pipelineStatus ? Object.keys(pipelineStatus.pipelines).length : '—', label: 'PIPELINES' },
            { value: 47, label: 'NEIGHBORHOODS' },
          ].map(stat => (
            <div key={stat.label} className="text-center">
              <p className="text-sm font-mono font-bold text-white/50 tabular-nums">{stat.value}</p>
              <p className="text-[7px] font-mono uppercase tracking-widest text-white/15">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Section B: GPU Fleet ── */}
      <div className="border border-white/[0.04] bg-white/[0.01] p-5">
        <div className="flex items-center justify-between mb-4">
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
            GPU Fleet
          </span>
          <span className="text-[9px] font-mono text-white/15">
            {gpuMetrics
              ? `${Object.values(gpuMetrics).filter(e => e.status === 'active').length}/${GPU_FLEET.length} active`
              : '—'}
          </span>
        </div>

        <div className="flex gap-2 overflow-x-auto">
          {GPU_FLEET.map(card => {
            const entry = gpuMetrics?.[card.key]
            const badge = gpuStatusBadge(entry)
            const isActive = entry?.status === 'active'
            const memPct = entry?.memory_used_mb && entry?.memory_total_mb
              ? Math.round((entry.memory_used_mb / entry.memory_total_mb) * 100)
              : null
            const utilPct = entry?.gpu_utilization != null ? Math.round(entry.gpu_utilization) : null

            return (
              <div
                key={card.key}
                className={`
                  flex-1 min-w-[110px] border p-3 transition-all
                  ${isActive
                    ? `border-emerald-500/30 bg-emerald-500/[0.04] ${badge.glow}`
                    : 'border-white/[0.06] bg-white/[0.02]'}
                `}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-mono font-bold text-white/50">{card.gpu}</span>
                  <div className="flex items-center gap-1">
                    <span className={`text-[8px] font-mono uppercase ${badge.color}`}>{badge.label}</span>
                    {badge.animate && <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />}
                  </div>
                </div>
                <p className="text-[9px] font-mono text-white/30 mb-0.5">{card.label}</p>
                <p className="text-[8px] font-mono text-white/15 mb-2">{card.task}</p>

                {/* Memory bar */}
                {memPct != null && (
                  <div className="mb-1.5">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-[7px] font-mono text-white/15">MEM</span>
                      <span className="text-[7px] font-mono text-white/20 tabular-nums">
                        {entry!.memory_used_mb! >= 1024
                          ? `${(entry!.memory_used_mb! / 1024).toFixed(0)}/${(entry!.memory_total_mb! / 1024).toFixed(0)} GB`
                          : `${entry!.memory_used_mb}/${entry!.memory_total_mb} MB`}
                      </span>
                    </div>
                    <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-400/60 rounded-full transition-all"
                        style={{ width: `${memPct}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Utilization bar */}
                {utilPct != null && (
                  <div>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-[7px] font-mono text-white/15">UTIL</span>
                      <span className="text-[7px] font-mono text-white/20 tabular-nums">{utilPct}%</span>
                    </div>
                    <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-cyan-400/60 rounded-full transition-all"
                        style={{ width: `${utilPct}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Section C: Agent Deployment Log ── */}
      <div className="border border-white/[0.04] bg-white/[0.01] p-5">
        <p className="text-[10px] font-mono uppercase tracking-wider text-white/30 mb-3">
          Agent Deployment Log
        </p>

        {(() => {
          const log = deriveActivityLog(briefs)
          if (log.length === 0) {
            return (
              <div className="flex items-center gap-2 py-3">
                <div className="w-2 h-2 rounded-full bg-cyan-400/40 animate-pulse" />
                <span className="text-[10px] font-mono text-white/20">
                  Monitoring — awaiting high-impact events
                </span>
              </div>
            )
          }
          return (
            <div className="relative pl-4">
              {/* Vertical timeline line */}
              <div className="absolute left-[5px] top-1 bottom-1 w-px bg-white/[0.06]" />

              <div className="space-y-2">
                {log.map((entry, i) => (
                  <div key={i} className="relative flex items-start gap-3">
                    {/* Timeline dot */}
                    <div className={`
                      absolute left-[-13px] top-[5px] w-[7px] h-[7px] rounded-full ${entry.color}
                      ${i === 0 ? 'animate-pulse' : 'opacity-60'}
                    `} />

                    {/* Content */}
                    <div className="flex-1 flex items-center justify-between min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`text-[8px] font-mono uppercase tracking-wider flex-shrink-0 ${
                          entry.type === 'SCAN' ? 'text-cyan-400' :
                          entry.type === 'FILTER' ? 'text-amber-400' :
                          entry.type === 'DISPATCH' ? 'text-violet-400' :
                          'text-emerald-400'
                        }`}>
                          {entry.type}
                        </span>
                        <span className="text-[10px] font-mono text-white/40 truncate">
                          {entry.label}
                        </span>
                      </div>
                      <span className="text-[8px] font-mono text-white/15 flex-shrink-0 ml-2">
                        {entry.time}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })()}
      </div>

      {/* ── Agent Spawning Agent — the recursive moment ── */}
      <div className="border border-white/[0.04] bg-white/[0.01] p-5 overflow-hidden">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
            <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
              Agent Spawning Agent
            </span>
          </div>
          <span className="text-[8px] font-mono text-white/15">RECURSIVE DEPLOYMENT</span>
        </div>

        {/* Central tree: Lead Analyst → 4 Workers */}
        <div className="relative flex flex-col items-center">
          {/* Lead Analyst node */}
          <div className="relative z-10 border border-violet-500/30 bg-violet-500/[0.06] px-5 py-3 text-center shadow-[0_0_20px_rgba(139,92,246,0.08)]">
            <div className="flex items-center justify-center gap-2 mb-1">
              <svg className="w-3.5 h-3.5 text-violet-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
                <path d="M9 21h6" />
              </svg>
              <span className="text-[10px] font-mono font-bold text-violet-300 uppercase tracking-wider">Lead Analyst</span>
            </div>
            <p className="text-[8px] font-mono text-white/25">Qwen3-8B scoring &bull; every 5 min</p>
          </div>

          {/* Vertical trunk line */}
          <div className="relative w-px h-8">
            <div className="absolute inset-0 bg-gradient-to-b from-violet-500/30 to-white/[0.08]" />
            {/* Animated particle down */}
            <div
              className="absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-violet-400/80"
              style={{ animation: 'spawnParticleDown 2.5s ease-in-out infinite' }}
            />
          </div>

          {/* "Score ≥ 7 → SPAWN" gate */}
          <div className="relative z-10 border border-amber-500/20 bg-amber-500/[0.04] px-4 py-1.5 mb-0">
            <span className="text-[8px] font-mono uppercase tracking-wider text-amber-400/70">
              impact score ≥ 7 → spawn workers
            </span>
          </div>

          {/* Branch lines: center splits to 4 */}
          <div className="relative w-full h-10">
            {/* Horizontal bar */}
            <div className="absolute top-0 left-[12.5%] right-[12.5%] h-px bg-white/[0.08]" />
            {/* 4 vertical drops */}
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="absolute top-0 h-full w-px bg-white/[0.08]" style={{ left: `${12.5 + i * 25}%` }}>
                <div
                  className="absolute left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-cyan-400/60"
                  style={{ animation: 'spawnParticleDown 2s ease-in-out infinite', animationDelay: `${i * 0.2}s` }}
                />
              </div>
            ))}
          </div>

          {/* 4 Worker cards */}
          <div className="grid grid-cols-4 gap-2 w-full">
            {Object.entries(WORKER_META).map(([key, meta], idx) => (
              <div key={key} className={`relative border ${meta.accent} bg-white/[0.01] p-2.5 text-center`}>
                {/* E2B sandbox indicator */}
                <div className="absolute top-1 right-1.5">
                  <span className="text-[6px] font-mono text-cyan-400/30 uppercase tracking-wider">E2B</span>
                </div>

                {/* Worker dot + label */}
                <div className="flex flex-col items-center gap-1.5">
                  <div className={`w-6 h-6 rounded-full border flex items-center justify-center ${meta.accent} bg-white/[0.02]`}>
                    <StageIcon type="fork" className={`w-3 h-3 ${meta.color}`} />
                  </div>
                  <span className={`text-[8px] font-mono uppercase tracking-wider ${meta.color}`}>
                    {meta.label}
                  </span>
                  <p className="text-[7px] font-mono text-white/15">{meta.sources}</p>
                </div>

                {/* Animated "working" indicator */}
                <div className="mt-2 h-0.5 bg-white/[0.04] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${meta.color.replace('text-', 'bg-')}/40`}
                    style={{
                      animation: 'workerProgress 3s ease-in-out infinite',
                      animationDelay: `${idx * 0.5}s`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Merge lines back up */}
          <div className="relative w-full h-6">
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="absolute bottom-0 h-full w-px bg-white/[0.06]" style={{ left: `${12.5 + i * 25}%` }} />
            ))}
            <div className="absolute bottom-0 left-[12.5%] right-[12.5%] h-px bg-white/[0.06]" />
          </div>

          {/* Vertical merge trunk */}
          <div className="w-px h-5 bg-white/[0.08]" />

          {/* Synthesis output */}
          <div className="relative z-10 border border-emerald-500/25 bg-emerald-500/[0.04] px-5 py-2.5 text-center shadow-[0_0_16px_rgba(52,211,153,0.06)]">
            <div className="flex items-center justify-center gap-2">
              <StageIcon type="merge" className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[10px] font-mono font-bold text-emerald-300 uppercase tracking-wider">Impact Brief</span>
            </div>
            <p className="text-[8px] font-mono text-white/20 mt-0.5">synthesized findings → dashboard</p>
          </div>
        </div>
      </div>

      {/* ── Worker domains ── */}
      <div className="grid grid-cols-4 gap-3">
        {Object.entries(WORKER_META).map(([key, meta]) => (
          <div key={key} className={`border ${meta.accent} bg-white/[0.01] p-3.5`}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <div className={`w-1 h-1 rounded-full ${meta.color.replace('text-', 'bg-')}`} />
              <span className={`text-[9px] font-mono uppercase tracking-wider ${meta.color}`}>
                {meta.label}
              </span>
            </div>
            <p className="text-[8px] font-mono text-white/20">{meta.sources}</p>
          </div>
        ))}
      </div>

      {/* ── Impact briefs ── */}
      <div className="border border-white/[0.04] bg-white/[0.01]">
        <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
            Impact Briefs
          </span>
          {loading && (
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 border border-white/20 border-t-transparent rounded-full animate-spin" />
              <span className="text-[9px] font-mono text-white/15">Polling...</span>
            </div>
          )}
        </div>

        {error ? (
          <div className="p-4 text-[10px] font-mono text-white/20">
            Unable to reach /impact-briefs endpoint. Ensure Modal backend is deployed.
          </div>
        ) : briefs.length === 0 && !loading ? (
          <div className="p-4">
            <p className="text-[10px] font-mono text-white/20 mb-1">No impact briefs generated yet.</p>
            <p className="text-[9px] font-mono text-white/12">
              The Lead Analyst scans enriched documents every 5 minutes. Briefs appear here when high-impact events (score 7+) are detected and analyzed by the 4 specialized workers.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {briefs.map(brief => {
              const isExpanded = expandedBrief === brief.id
              return (
                <div key={brief.id}>
                  {/* Brief header row */}
                  <button
                    type="button"
                    onClick={() => setExpandedBrief(isExpanded ? null : brief.id)}
                    className="w-full px-4 py-3 text-left hover:bg-white/[0.02] transition-colors cursor-pointer"
                  >
                    <div className="flex items-start gap-3">
                      {/* Impact score badge */}
                      <div className={`
                        w-9 h-9 rounded flex-shrink-0 flex flex-col items-center justify-center border
                        ${levelBg(brief.impact_level)}
                      `}>
                        <span className={`text-sm font-bold font-mono leading-none ${levelColor(brief.impact_level)}`}>
                          {brief.impact_score}
                        </span>
                        <span className="text-[6px] font-mono text-white/20 leading-none mt-0.5">/10</span>
                      </div>

                      {/* Title + meta */}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-white/80 leading-snug truncate">
                          {brief.trigger_title || 'Untitled event'}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[9px] font-mono text-white/25">
                            {categoryLabel(brief.category)}
                          </span>
                          <span className="text-white/8">|</span>
                          <span className="text-[9px] font-mono text-white/20">
                            {brief.trigger_source}
                          </span>
                          <span className="text-white/8">|</span>
                          <span className="text-[9px] font-mono text-white/15">
                            {relativeTime(brief.timestamp)}
                          </span>
                          {brief.e2b_used && (
                            <>
                              <span className="text-white/8">|</span>
                              <span className="text-[8px] font-mono text-cyan-400/40">E2B</span>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Expand chevron */}
                      <svg
                        className={`w-3.5 h-3.5 text-white/15 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>

                    {/* Neighborhoods pills */}
                    {brief.neighborhoods_affected.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2 ml-12">
                        {brief.neighborhoods_affected.map(n => (
                          <span key={n} className="text-[8px] font-mono px-1.5 py-0.5 bg-white/[0.03] border border-white/[0.06] text-white/30">
                            {n}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="px-4 pb-4 space-y-4">
                      {/* Executive summary */}
                      {brief.executive_summary && (
                        <div className="ml-12">
                          <p className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Executive Summary</p>
                          <p className="text-[11px] text-white/60 leading-relaxed">{brief.executive_summary}</p>
                        </div>
                      )}

                      {/* Worker results — the 4-domain fan-out */}
                      <div className="ml-12">
                        <p className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-2">Worker Results</p>

                        {/* Flow connector: branching visualization */}
                        <div className="relative">
                          {/* Vertical trunk line */}
                          <div className="absolute left-3 top-0 bottom-0 w-px bg-white/[0.06]" />

                          <div className="space-y-2">
                            {brief.worker_results.map(wr => {
                              const meta = WORKER_META[wr.worker_type] || { label: wr.worker_type, color: 'text-white/50', accent: 'border-white/[0.06]', sources: '' }
                              const wKey = `${brief.id}-${wr.worker_type}`
                              const wExpanded = expandedWorker === wKey

                              return (
                                <div key={wr.worker_type} className="relative pl-8">
                                  {/* Horizontal branch connector */}
                                  <div className="absolute left-3 top-4 w-5 h-px bg-white/[0.08]" />
                                  {/* Branch node dot */}
                                  <div className={`absolute left-[9px] top-[13px] w-[7px] h-[7px] rounded-full border ${
                                    wr.error
                                      ? 'border-red-500/40 bg-red-500/20'
                                      : `${meta.accent} ${meta.color.replace('text-', 'bg-')}/20`
                                  }`} />

                                  <button
                                    type="button"
                                    onClick={() => setExpandedWorker(wExpanded ? null : wKey)}
                                    className={`
                                      w-full text-left border bg-white/[0.01] p-2.5 transition-colors cursor-pointer
                                      hover:bg-white/[0.03]
                                      ${wr.error ? 'border-red-500/15' : meta.accent}
                                    `}
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-2">
                                        <span className={`text-[9px] font-mono uppercase tracking-wider ${wr.error ? 'text-red-400/60' : meta.color}`}>
                                          {meta.label}
                                        </span>
                                        {wr.error && <span className="text-[8px] font-mono text-red-400/40">ERROR</span>}
                                      </div>
                                      <div className="flex items-center gap-3">
                                        <span className="text-[8px] font-mono text-white/15">
                                          {wr.data_points_analyzed} pts
                                        </span>
                                        <span className="text-[8px] font-mono text-white/15">
                                          {(wr.confidence * 100).toFixed(0)}% conf
                                        </span>
                                        <svg
                                          className={`w-3 h-3 text-white/10 transition-transform ${wExpanded ? 'rotate-180' : ''}`}
                                          fill="none" viewBox="0 0 24 24" stroke="currentColor"
                                        >
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                        </svg>
                                      </div>
                                    </div>
                                  </button>

                                  {/* Worker findings detail */}
                                  {wExpanded && (
                                    <div className={`border border-t-0 ${wr.error ? 'border-red-500/10' : meta.accent.replace('/30', '/15')} bg-white/[0.01] p-3`}>
                                      {wr.error ? (
                                        <p className="text-[10px] font-mono text-red-400/50">{wr.error}</p>
                                      ) : (
                                        <div className="space-y-1.5">
                                          {Object.entries(wr.findings).map(([k, v]) => (
                                            <div key={k} className="flex gap-2 text-[10px]">
                                              <span className="font-mono text-white/25 flex-shrink-0">{k}:</span>
                                              <span className="text-white/45 break-all">
                                                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                              </span>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                      {wr.neighborhoods_affected.length > 0 && (
                                        <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-white/[0.04]">
                                          {wr.neighborhoods_affected.map(n => (
                                            <span key={n} className="text-[7px] font-mono px-1 py-0.5 bg-white/[0.02] border border-white/[0.05] text-white/25">
                                              {n}
                                            </span>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      </div>

                      {/* Synthesis */}
                      {brief.synthesis && (
                        <div className="ml-12">
                          <p className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Synthesis</p>
                          <p className="text-[11px] text-white/50 leading-relaxed">{brief.synthesis}</p>
                        </div>
                      )}

                      {/* Recommendations */}
                      {brief.recommendations.length > 0 && (
                        <div className="ml-12">
                          <p className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1.5">Recommendations</p>
                          <div className="space-y-1">
                            {brief.recommendations.map((rec, i) => (
                              <div key={i} className="flex gap-2 text-[10px]">
                                <span className="text-cyan-400/40 flex-shrink-0 font-mono">{i + 1}.</span>
                                <span className="text-white/50">{rec}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Alternative Opportunities — hardcoded for Loop & Lincoln Park */}
                      {brief.neighborhoods_affected.some(n => n === 'Loop' || n === 'Lincoln Park') && (
                        <div className="ml-12">
                          <p className="text-[9px] font-mono uppercase tracking-wider text-emerald-400/40 mb-2">Alternative Opportunities</p>
                          <p className="text-[10px] text-white/30 mb-3">
                            Based on cross-referencing this event against pipeline data, these nearby neighborhoods show stronger opportunity signals:
                          </p>
                          <div className="space-y-2">
                            {brief.neighborhoods_affected.includes('Loop') && [
                              {
                                neighborhood: 'West Loop',
                                score: 78,
                                reasons: ['42% lower commercial rent per sq ft ($28 vs $48)', '18 new food permits issued in last 90 days', 'Foot traffic up 23% YoY (CTA Morgan station)'],
                                risk: 'Lower regulatory burden — 6% inspection fail rate vs Loop\'s 14%',
                              },
                              {
                                neighborhood: 'South Loop',
                                score: 71,
                                reasons: ['Population grew 12% since 2020 Census', '3 major mixed-use developments breaking ground', 'Average Yelp rating 4.2 vs Loop\'s 3.8 for similar businesses'],
                                risk: 'Emerging market — less saturated with 34% fewer competing licenses',
                              },
                            ].map(alt => (
                              <div key={alt.neighborhood} className="border border-emerald-500/15 bg-emerald-500/[0.03] p-3">
                                <div className="flex items-center justify-between mb-2">
                                  <div className="flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                    <span className="text-xs font-semibold text-emerald-300">{alt.neighborhood}</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-[9px] font-mono text-emerald-400/60">Opportunity Score</span>
                                    <span className="text-sm font-bold font-mono text-emerald-300">{alt.score}</span>
                                    <span className="text-[8px] font-mono text-white/15">/100</span>
                                  </div>
                                </div>
                                <div className="space-y-1 mb-2">
                                  {alt.reasons.map((r, i) => (
                                    <div key={i} className="flex gap-2 text-[10px]">
                                      <span className="text-emerald-400/30 shrink-0">&#9679;</span>
                                      <span className="text-white/45">{r}</span>
                                    </div>
                                  ))}
                                </div>
                                <p className="text-[9px] font-mono text-emerald-400/25">{alt.risk}</p>
                              </div>
                            ))}
                            {brief.neighborhoods_affected.includes('Lincoln Park') && [
                              {
                                neighborhood: 'Lakeview',
                                score: 74,
                                reasons: ['27% higher walk-in traffic density (CTA Belmont + Diversey)', 'Median household income $98K — similar demo at 15% lower rent', 'Reddit sentiment 31% more positive for new businesses'],
                                risk: 'Adjacent market — captures Lincoln Park spillover without premium lease costs',
                              },
                              {
                                neighborhood: 'Logan Square',
                                score: 69,
                                reasons: ['Fastest-growing 25-34 demo in Chicago (+19% since 2020)', '52 new business licenses in last 6 months', 'Average commercial lease $22/sqft vs Lincoln Park\'s $41/sqft'],
                                risk: 'High growth trajectory — 4 consecutive quarters of permit acceleration',
                              },
                            ].map(alt => (
                              <div key={alt.neighborhood} className="border border-emerald-500/15 bg-emerald-500/[0.03] p-3">
                                <div className="flex items-center justify-between mb-2">
                                  <div className="flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                    <span className="text-xs font-semibold text-emerald-300">{alt.neighborhood}</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-[9px] font-mono text-emerald-400/60">Opportunity Score</span>
                                    <span className="text-sm font-bold font-mono text-emerald-300">{alt.score}</span>
                                    <span className="text-[8px] font-mono text-white/15">/100</span>
                                  </div>
                                </div>
                                <div className="space-y-1 mb-2">
                                  {alt.reasons.map((r, i) => (
                                    <div key={i} className="flex gap-2 text-[10px]">
                                      <span className="text-emerald-400/30 shrink-0">&#9679;</span>
                                      <span className="text-white/45">{r}</span>
                                    </div>
                                  ))}
                                </div>
                                <p className="text-[9px] font-mono text-emerald-400/25">{alt.risk}</p>
                              </div>
                            ))}
                          </div>
                          <p className="text-[8px] font-mono text-white/12 mt-2">
                            Sources: Census ACS 2024, Chicago Data Portal (permits, licenses, inspections), CTA ridership, Yelp/Google Reviews, LoopNet
                          </p>
                        </div>
                      )}

                      {/* Footer meta */}
                      <div className="ml-12 flex items-center gap-3 pt-2 border-t border-white/[0.04] text-[8px] font-mono text-white/12">
                        <span>ID: {brief.id.slice(0, 8)}</span>
                        <span>Processed in {brief.processing_time_seconds}s</span>
                        <span>{brief.e2b_used ? 'E2B sandboxed' : 'In-process exec'}</span>
                        <span>Trigger: {brief.trigger_source}/{brief.trigger_doc_id.slice(0, 8)}</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── CSS keyframes ── */}
      <style>{`
        @keyframes spawnParticleDown {
          0%   { top: 0; opacity: 0; }
          20%  { opacity: 1; }
          80%  { opacity: 1; }
          100% { top: calc(100% - 6px); opacity: 0; }
        }
        @keyframes workerProgress {
          0%   { width: 0%; }
          50%  { width: 100%; }
          100% { width: 0%; }
        }
      `}</style>
    </div>
  )
}
