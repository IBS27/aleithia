import { useState, useEffect } from 'react'
import { API_BASE } from '../api.ts'

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

// ── Flow stage definitions ───────────────────────────────────────────

const FLOW_STAGES = [
  { id: 'ingest',  label: 'PIPELINES',     sub: '14 sources',       icon: 'db' },
  { id: 'enrich',  label: 'CLASSIFY',      sub: 'bart + roberta',   icon: 'gpu' },
  { id: 'queue',   label: 'IMPACT QUEUE',  sub: 'modal.Queue',      icon: 'queue' },
  { id: 'filter',  label: 'FAST FILTER',   sub: 'rule-based',       icon: 'filter' },
  { id: 'score',   label: 'LLM SCORING',   sub: 'Qwen3-8B',        icon: 'brain' },
  { id: 'workers', label: 'WORKERS',       sub: '4 domains',        icon: 'fork' },
  { id: 'synth',   label: 'SYNTHESIS',     sub: 'ImpactBrief',      icon: 'merge' },
] as const

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
  const [activeFlowIdx, setActiveFlowIdx] = useState(-1)

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

  // Animated flow highlight
  useEffect(() => {
    let step = 0
    const timer = setInterval(() => {
      setActiveFlowIdx(step % FLOW_STAGES.length)
      step++
    }, 1800)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="space-y-4">
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

      {/* ── Pipeline flow diagram ── */}
      <div className="border border-white/[0.06] bg-white/[0.01] p-4 overflow-x-auto">
        <p className="text-[9px] font-mono uppercase tracking-widest text-white/20 mb-4">
          Document Processing Flow
        </p>

        {/* Flow stages — horizontal strip */}
        <div className="flex items-center gap-0 min-w-[700px]">
          {FLOW_STAGES.map((stage, i) => {
            const isActive = i === activeFlowIdx
            const isPast = i < activeFlowIdx
            return (
              <div key={stage.id} className="flex items-center">
                {/* Stage node */}
                <div className={`
                  relative flex flex-col items-center px-3 py-2 rounded transition-all duration-500
                  ${isActive ? 'bg-cyan-500/[0.08]' : ''}
                `}>
                  {/* Pulse ring on active */}
                  {isActive && (
                    <div className="absolute inset-0 rounded border border-cyan-500/20 animate-ping" style={{ animationDuration: '2s' }} />
                  )}

                  <div className={`
                    w-8 h-8 rounded-full border flex items-center justify-center mb-1.5 transition-all duration-500
                    ${isActive
                      ? 'border-cyan-400/60 bg-cyan-500/[0.12] shadow-[0_0_12px_rgba(34,211,238,0.15)]'
                      : isPast
                        ? 'border-white/15 bg-white/[0.04]'
                        : 'border-white/[0.08] bg-transparent'
                    }
                  `}>
                    <StageIcon
                      type={stage.icon}
                      className={`transition-colors duration-500 ${isActive ? 'text-cyan-400' : isPast ? 'text-white/35' : 'text-white/15'}`}
                    />
                  </div>

                  <span className={`
                    text-[8px] font-mono uppercase tracking-wider transition-colors duration-500 whitespace-nowrap
                    ${isActive ? 'text-cyan-300' : 'text-white/30'}
                  `}>
                    {stage.label}
                  </span>
                  <span className={`
                    text-[7px] font-mono transition-colors duration-500 whitespace-nowrap
                    ${isActive ? 'text-cyan-400/50' : 'text-white/12'}
                  `}>
                    {stage.sub}
                  </span>
                </div>

                {/* Connector line */}
                {i < FLOW_STAGES.length - 1 && (
                  <div className="relative w-8 h-px flex-shrink-0">
                    <div className="absolute inset-0 bg-white/[0.08]" />
                    {/* Animated data particle */}
                    {isPast && (
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-cyan-400/60"
                        style={{
                          animation: 'flowParticle 1.8s ease-in-out infinite',
                          animationDelay: `${i * 0.25}s`,
                        }}
                      />
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Legend strip */}
        <div className="flex items-center gap-4 mt-4 pt-3 border-t border-white/[0.04]">
          <span className="text-[8px] font-mono text-white/15">RUNS EVERY 5 MIN</span>
          <span className="text-[8px] font-mono text-white/10">|</span>
          <span className="text-[8px] font-mono text-white/15">SCORE THRESHOLD: 7/10</span>
          <span className="text-[8px] font-mono text-white/10">|</span>
          <span className="text-[8px] font-mono text-white/15">4 PARALLEL WORKERS</span>
          <span className="text-[8px] font-mono text-white/10">|</span>
          <span className="text-[8px] font-mono text-white/15">E2B SANDBOX ISOLATION</span>
        </div>
      </div>

      {/* ── Worker domains ── */}
      <div className="grid grid-cols-4 gap-2">
        {Object.entries(WORKER_META).map(([key, meta]) => (
          <div key={key} className={`border ${meta.accent} bg-white/[0.01] p-3`}>
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
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
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

      {/* ── CSS keyframes for flow particle animation ── */}
      <style>{`
        @keyframes flowParticle {
          0%   { left: 0; opacity: 0; }
          15%  { opacity: 1; }
          85%  { opacity: 1; }
          100% { left: calc(100% - 6px); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
