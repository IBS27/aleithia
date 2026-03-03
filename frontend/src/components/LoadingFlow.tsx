import { useState, useEffect } from 'react'

/**
 * Animated Document Processing Flow shown during Dashboard data loading.
 * Steps through pipeline stages once, then holds the final state.
 */

const FLOW_STAGES = [
  { id: 'ingest',  label: 'PIPELINES',     sub: '14 sources',       icon: 'db' },
  { id: 'enrich',  label: 'CLASSIFY',      sub: 'bart + roberta',   icon: 'gpu' },
  { id: 'queue',   label: 'ENRICHMENT',    sub: 'modal.Queue',      icon: 'queue' },
  { id: 'filter',  label: 'SCORING',       sub: 'risk model',       icon: 'filter' },
  { id: 'score',   label: 'LLM',           sub: 'Qwen3-8B',        icon: 'brain' },
  { id: 'workers', label: 'AGENTS',        sub: '4 domains',        icon: 'fork' },
  { id: 'synth',   label: 'DASHBOARD',     sub: 'ready',            icon: 'merge' },
] as const

function StageIcon({ type, className = '' }: { type: string; className?: string }) {
  const cls = `w-4 h-4 ${className}`
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

interface Props {
  neighborhood: string
}

export default function LoadingFlow({ neighborhood }: Props) {
  const [activeIdx, setActiveIdx] = useState(0)

  // Step through stages at 400ms each
  useEffect(() => {
    if (activeIdx >= FLOW_STAGES.length - 1) return
    const timer = setTimeout(() => setActiveIdx(prev => prev + 1), 400)
    return () => clearTimeout(timer)
  }, [activeIdx])

  return (
    <div className="border border-white/[0.06] p-10 flex flex-col items-center gap-8">
      {/* Spinner + text */}
      <div className="text-center">
        <div className="w-6 h-6 border border-white/20 border-t-white/60 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-xs text-white/30 font-mono uppercase tracking-wider">
          Analyzing {neighborhood}
        </p>
        <p className="text-[10px] text-white/15 font-mono mt-1">
          {activeIdx < FLOW_STAGES.length - 1
            ? FLOW_STAGES[activeIdx].label.toLowerCase() + '...'
            : 'Loading real Chicago city data'}
        </p>
      </div>

      {/* Flow stages — horizontal strip */}
      <div className="flex items-center gap-0 w-full max-w-[700px] overflow-x-auto">
        {FLOW_STAGES.map((stage, i) => {
          const isActive = i === activeIdx
          const isPast = i < activeIdx
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
                  w-9 h-9 rounded-full border flex items-center justify-center mb-1.5 transition-all duration-500
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
                  ${isActive ? 'text-cyan-300' : isPast ? 'text-white/40' : 'text-white/20'}
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
                  {isPast && (
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-cyan-400/60"
                      style={{
                        animation: 'loadFlowParticle 1.2s ease-in-out infinite',
                        animationDelay: `${i * 0.15}s`,
                      }}
                    />
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <style>{`
        @keyframes loadFlowParticle {
          0%   { left: 0; opacity: 0; }
          15%  { opacity: 1; }
          85%  { opacity: 1; }
          100% { left: calc(100% - 6px); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
