import { useState, useEffect } from 'react'
import { fetchPipelineStatus, type PipelineStatus } from '../api.ts'

interface Props {
  sourcesReady?: boolean
  sourcesWarning?: string | null
  activeSources?: number
  totalSources?: number
}

export default function PipelineMonitor({ sourcesReady, sourcesWarning, activeSources, totalSources }: Props) {
  const [status, setStatus] = useState<PipelineStatus | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const data = await fetchPipelineStatus()
        if (!cancelled) {
          setStatus(data)
          setError(false)
        }
      } catch {
        if (!cancelled) setError(true)
      }
    }

    poll()
    const interval = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const stateColors: Record<string, string> = {
    idle: 'text-emerald-400/70',
    running: 'text-blue-400/80',
    queued: 'text-yellow-400/70',
    no_data: 'text-white/20',
    stale: 'text-amber-400/70',
  }

  const stateIcons: Record<string, string> = {
    idle: 'bg-emerald-400',
    running: 'bg-blue-400 animate-pulse',
    queued: 'bg-yellow-400',
    no_data: 'bg-white/20',
    stale: 'bg-amber-400',
  }

  // Top-level state chip
  const metadataReady = status?.metadata_ready ?? false
  const runtimeHealthy = status ? Object.values(status.gpu_status).some((s) => s === 'available') : false
  const staleCount = status ? Object.values(status.pipelines).filter((p) => p.state === 'stale').length : 0
  const runningCount = status ? Object.values(status.pipelines).filter((p) => p.state === 'running').length : 0

  const overallState: { label: string; color: string; dot: string } = (() => {
    if (error || !status) return { label: 'CONNECTING', color: 'text-white/30', dot: 'bg-white/20' }
    if (!metadataReady) return { label: 'WARMING', color: 'text-amber-300/80', dot: 'bg-amber-400 animate-pulse' }
    if (runningCount > 0) return { label: 'PROCESSING', color: 'text-blue-300/80', dot: 'bg-blue-400 animate-pulse' }
    if (staleCount > 0) return { label: 'STALE SOURCES', color: 'text-amber-300/80', dot: 'bg-amber-400' }
    return { label: 'NOMINAL', color: 'text-emerald-300/80', dot: 'bg-emerald-400' }
  })()

  const pipelines = status ? Object.entries(status.pipelines) : []

  return (
    <div
      className={`border transition-all ${runtimeHealthy ? 'border-[#2B95D6]/25 bg-gradient-to-r from-white/[0.02] to-[#2B95D6]/[0.02]' : 'border-white/[0.06] bg-white/[0.01]'}`}
      style={runtimeHealthy ? { boxShadow: '0 0 20px rgba(43, 149, 214, 0.08)' } : undefined}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-0 hover:bg-white/[0.015] transition-colors cursor-pointer"
      >
        {/* Overall state cell */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-r border-white/[0.04] min-w-[180px]">
          <span className={`w-1.5 h-1.5 rounded-full ${overallState.dot}`} />
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">Pipeline</span>
          <span className={`text-[10px] font-mono font-semibold tracking-wider ${overallState.color}`}>
            {overallState.label}
          </span>
        </div>

        {/* Source readiness */}
        <div className="hidden md:flex items-center gap-2 px-4 py-2.5 border-r border-white/[0.04]">
          <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">Sources</span>
          {sourcesReady && totalSources ? (
            <span className="text-[10px] font-mono text-white/60">
              <span className="text-emerald-400/80">{activeSources ?? 0}</span>
              <span className="text-white/20"> / </span>
              <span>{totalSources}</span>
            </span>
          ) : (
            <span className="text-[10px] font-mono text-amber-300/60">
              {sourcesWarning ? 'warming' : '…'}
            </span>
          )}
        </div>

        {/* Metadata readiness */}
        <div className="hidden md:flex items-center gap-2 px-4 py-2.5 border-r border-white/[0.04]">
          <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">Metadata</span>
          <span className={`text-[10px] font-mono ${metadataReady ? 'text-emerald-400/80' : 'text-amber-300/80'}`}>
            {metadataReady ? 'READY' : 'WARMING'}
          </span>
        </div>

        {/* Docs */}
        {status && (
          <div className="hidden lg:flex items-center gap-3 px-4 py-2.5 border-r border-white/[0.04]">
            <span className="text-[10px] font-mono text-white/25">
              <span className="text-white/55">{status.total_docs.toLocaleString()}</span> docs
            </span>
            <span className="text-[10px] font-mono text-white/25">
              <span className="text-white/55">{status.enriched_docs.toLocaleString()}</span> enriched
            </span>
          </div>
        )}

        <div className="flex-1" />

        {/* Runtime GPUs */}
        {status && (
          <div className="flex items-center gap-3 px-4 py-2.5 border-l border-white/[0.04]">
            {Object.entries(status.gpu_status).map(([gpu, state]) => (
              <div key={gpu} className="flex items-center gap-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${state === 'available' ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <span className="text-[9px] font-mono uppercase tracking-wider text-white/30">{gpu.split('_')[0]}</span>
              </div>
            ))}
          </div>
        )}

        {/* Expand toggle */}
        <div className="px-4 py-2.5 border-l border-white/[0.04]">
          <svg
            className={`w-3.5 h-3.5 text-white/25 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Source warning - non-blocking warning row */}
      {sourcesWarning && (
        <div className="border-t border-white/[0.04] px-4 py-2 flex items-center gap-2 bg-amber-500/[0.03]">
          <div className="w-1 h-1 rounded-full bg-amber-400" />
          <span className="text-[10px] font-mono text-amber-300/70">{sourcesWarning}</span>
        </div>
      )}

      {expanded && status && (
        <div className="border-t border-white/[0.06] p-4 grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-1.5">
          {pipelines.map(([name, info]) => (
            <div key={name} className="flex items-center justify-between text-xs px-1">
              <div className="flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full ${stateIcons[info.state] || stateIcons.idle}`} />
                <span className="text-white/50 capitalize font-mono text-[10px]">{name.replace(/_/g, ' ')}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono text-white/25">{info.doc_count}</span>
                <span className={`text-[10px] font-mono uppercase ${stateColors[info.state] || 'text-white/20'}`}>
                  {info.state}
                </span>
                {info.last_update && (
                  <span className="text-[10px] font-mono text-white/15 shrink-0">
                    {new Date(info.last_update).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
              </div>
            </div>
          ))}

        </div>
      )}
    </div>
  )
}
