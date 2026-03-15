import { useState, useEffect } from 'react'

/**
 * Animated Document Processing Flow shown during Dashboard data loading.
 * Steps through pipeline stages once, then holds the final state.
 * Designed to be large and readable for demo audiences.
 */

const FLOW_STAGES = [
  {
    id: 'ingest',
    label: 'PIPELINES',
    sub: '14 live sources',
    detail: 'Scraping news, permits, inspections, Reddit, Yelp, TikTok, IDOT cameras, satellite imagery',
    icon: 'db',
  },
  {
    id: 'enrich',
    label: 'CLASSIFY',
    sub: 'BART + RoBERTa on T4 GPU',
    detail: 'Zero-shot classification into regulatory, economic, safety, community + sentiment scoring',
    icon: 'gpu',
  },
  {
    id: 'vector',
    label: 'ENRICHED DOCS',
    sub: 'Processed data on Modal Volume',
    detail: 'Saving classified and sentiment-scored documents for downstream briefs, alerts, and analysis',
    icon: 'queue',
  },
  {
    id: 'score',
    label: 'RISK MODEL',
    sub: 'ISO 31000 WLC scoring',
    detail: 'Logistic normalization across 6 dimensions: regulatory, market, economic, accessibility, political, community',
    icon: 'filter',
  },
  {
    id: 'llm',
    label: 'LLM',
    sub: 'Qwen3-8B AWQ on H100',
    detail: 'Streaming intelligence synthesis via vLLM — 20 concurrent inputs, GPU memory snapshots',
    icon: 'brain',
  },
  {
    id: 'agents',
    label: 'AGENT SWARM',
    sub: '4 agents via .spawn()',
    detail: 'Neighborhood intel, regulatory, 2 comparison agents fan out in parallel across Modal containers',
    icon: 'fork',
  },
  {
    id: 'ready',
    label: 'DASHBOARD',
    sub: 'ready',
    detail: 'Loading real Chicago city data across 77 neighborhoods',
    icon: 'merge',
  },
] as const

function StageIcon({ type, className = '' }: { type: string; className?: string }) {
  const cls = `w-full h-full ${className}`
  switch (type) {
    case 'db':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" /><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" /></svg>
    case 'gpu':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h6v6H9z" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M20 9h3M1 15h3M20 15h3" /></svg>
    case 'queue':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><circle cx="8" cy="8" r="2" /><circle cx="16" cy="8" r="2" /><circle cx="12" cy="16" r="2" /><path d="M8 10l4 4M16 10l-4 4" opacity={0.5} /><path d="M10 8h4" opacity={0.5} /></svg>
    case 'filter':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" /></svg>
    case 'brain':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" /><path d="M9 21h6M10 17v4M14 17v4" /></svg>
    case 'fork':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><circle cx="12" cy="6" r="2" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="18" r="2" /><path d="M12 8v4M12 12l-6 4M12 12l6 4" /></svg>
    case 'merge':
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><circle cx="12" cy="18" r="2" /><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><path d="M12 16v-4M12 12L6 8M12 12l6-4" /></svg>
    default:
      return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><circle cx="12" cy="12" r="4" /></svg>
  }
}

interface Props {
  neighborhood: string
}

export default function LoadingFlow({ neighborhood }: Props) {
  const [activeIdx, setActiveIdx] = useState(0)

  // Step through stages at 900ms each — slower so audience can read
  useEffect(() => {
    if (activeIdx >= FLOW_STAGES.length - 1) return
    const timer = setTimeout(() => setActiveIdx(prev => prev + 1), 900)
    return () => clearTimeout(timer)
  }, [activeIdx])

  return (
    <div className="border border-white/[0.06] p-8 sm:p-12 flex flex-col items-center gap-10">
      {/* Header */}
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-white/20 border-t-cyan-400/70 rounded-full animate-spin mx-auto mb-5" />
        <p className="text-base sm:text-lg text-white/50 font-mono uppercase tracking-wider">
          Analyzing {neighborhood}
        </p>
        <p className="text-sm text-white/25 font-mono mt-2">
          {activeIdx < FLOW_STAGES.length - 1
            ? FLOW_STAGES[activeIdx].detail
            : 'Loading real Chicago city data'}
        </p>
      </div>

      {/* Flow stages — vertical on mobile, horizontal on desktop */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-start gap-0 w-full max-w-5xl">
        {FLOW_STAGES.map((stage, i) => {
          const isActive = i === activeIdx
          const isPast = i < activeIdx
          const isFuture = i > activeIdx
          return (
            <div key={stage.id} className="flex flex-col sm:flex-row items-center flex-1 min-w-0">
              {/* Stage card */}
              <div className={`
                relative flex flex-col items-center text-center px-3 py-4 sm:py-5 rounded-lg transition-all duration-700 w-full
                ${isActive ? 'bg-cyan-500/[0.08] scale-105' : ''}
              `}>
                {/* Pulse ring on active */}
                {isActive && (
                  <div className="absolute inset-0 rounded-lg border border-cyan-500/25 animate-ping" style={{ animationDuration: '2.5s' }} />
                )}

                {/* Icon circle */}
                <div className={`
                  w-14 h-14 sm:w-16 sm:h-16 rounded-full border-2 flex items-center justify-center mb-3 transition-all duration-700 p-3
                  ${isActive
                    ? 'border-cyan-400/70 bg-cyan-500/[0.15] shadow-[0_0_24px_rgba(34,211,238,0.25)]'
                    : isPast
                      ? 'border-emerald-500/30 bg-emerald-500/[0.06]'
                      : 'border-white/[0.08] bg-transparent'
                  }
                `}>
                  {isPast ? (
                    <svg className="w-6 h-6 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                      <path d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <StageIcon
                      type={stage.icon}
                      className={`transition-colors duration-700 ${isActive ? 'text-cyan-400' : isFuture ? 'text-white/15' : 'text-white/40'}`}
                    />
                  )}
                </div>

                {/* Label */}
                <span className={`
                  text-xs sm:text-sm font-mono font-bold uppercase tracking-wider transition-colors duration-700
                  ${isActive ? 'text-cyan-300' : isPast ? 'text-white/50' : 'text-white/20'}
                `}>
                  {stage.label}
                </span>

                {/* Sub label */}
                <span className={`
                  text-[10px] sm:text-xs font-mono transition-colors duration-700 mt-1
                  ${isActive ? 'text-cyan-400/60' : isPast ? 'text-white/30' : 'text-white/12'}
                `}>
                  {stage.sub}
                </span>

                {/* Detail text — only visible on active */}
                <p className={`
                  text-[10px] sm:text-[11px] leading-relaxed mt-2 max-w-[160px] transition-all duration-500
                  ${isActive ? 'text-white/40 opacity-100' : 'text-transparent opacity-0 h-0 mt-0 overflow-hidden'}
                `}>
                  {stage.detail}
                </p>
              </div>

              {/* Connector */}
              {i < FLOW_STAGES.length - 1 && (
                <>
                  {/* Vertical connector (mobile) */}
                  <div className="sm:hidden relative w-px h-6 flex-shrink-0">
                    <div className={`absolute inset-0 ${isPast ? 'bg-emerald-500/20' : 'bg-white/[0.06]'}`} />
                    {isPast && (
                      <div
                        className="absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-cyan-400/60"
                        style={{
                          animation: 'loadFlowParticleV 1.5s ease-in-out infinite',
                          animationDelay: `${i * 0.2}s`,
                        }}
                      />
                    )}
                  </div>
                  {/* Horizontal connector (desktop) */}
                  <div className="hidden sm:block relative h-px flex-shrink-0" style={{ width: 24, marginTop: 40 }}>
                    <div className={`absolute inset-0 ${isPast ? 'bg-emerald-500/20' : 'bg-white/[0.06]'}`} />
                    {isPast && (
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-cyan-400/60"
                        style={{
                          animation: 'loadFlowParticle 1.5s ease-in-out infinite',
                          animationDelay: `${i * 0.2}s`,
                        }}
                      />
                    )}
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div className="w-full max-w-md">
        <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500/60 to-cyan-400/40 rounded-full transition-all duration-700"
            style={{ width: `${((activeIdx + 1) / FLOW_STAGES.length) * 100}%` }}
          />
        </div>
        <p className="text-[10px] font-mono text-white/20 text-center mt-2">
          {activeIdx + 1} / {FLOW_STAGES.length}
        </p>
      </div>

      <style>{`
        @keyframes loadFlowParticle {
          0%   { left: 0; opacity: 0; }
          15%  { opacity: 1; }
          85%  { opacity: 1; }
          100% { left: calc(100% - 8px); opacity: 0; }
        }
        @keyframes loadFlowParticleV {
          0%   { top: 0; opacity: 0; }
          15%  { opacity: 1; }
          85%  { opacity: 1; }
          100% { top: calc(100% - 6px); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
