import { useState, useEffect } from 'react'
import { fetchPipelineStatus, type PipelineStatus } from '../api.ts'

export default function PipelineMonitor() {
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

  if (error || !status) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-3">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">Pipeline Monitor</span>
          <span className="text-[10px] font-mono text-white/15">Connecting...</span>
        </div>
      </div>
    )
  }

  const stateColors: Record<string, string> = {
    idle: 'text-emerald-400/60',
    running: 'text-blue-400/60',
    queued: 'text-yellow-400/60',
    no_data: 'text-white/15',
    stale: 'text-red-400/60',
  }

  const stateIcons: Record<string, string> = {
    idle: 'bg-emerald-400',
    running: 'bg-blue-400 animate-pulse',
    queued: 'bg-yellow-400',
    no_data: 'bg-white/20',
    stale: 'bg-red-400',
  }

  const pipelines = Object.entries(status.pipelines)

  const hasRunning = Object.values(status.gpu_status).some((s) => s === 'available')
  return (
    <div className={`border overflow-hidden transition-shadow ${hasRunning ? 'border-[#2B95D6]/30 bg-white/[0.01]' : 'border-white/[0.06] bg-white/[0.01]'}`} style={hasRunning ? { boxShadow: '0 0 16px rgba(43, 149, 214, 0.12)' } : undefined}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/40">Pipeline Monitor</span>
          <span className="text-[10px] font-mono text-white/20">{status.total_docs} docs</span>
          <span className="text-[10px] font-mono text-white/20">{status.enriched_docs} enriched</span>
        </div>
        <div className="flex items-center gap-2">
          {Object.entries(status.gpu_status).map(([gpu, state]) => (
            <div key={gpu} className="flex items-center gap-1">
              <div className={`w-1.5 h-1.5 rounded-full ${state === 'available' ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <span className="text-[10px] font-mono text-white/20">{gpu.split('_')[0].toUpperCase()}</span>
            </div>
          ))}
          <svg
            className={`w-4 h-4 text-white/20 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-white/[0.06] p-3 space-y-2">
          {pipelines.map(([name, info]) => (
            <div key={name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full ${stateIcons[info.state] || stateIcons.idle}`} />
                <span className="text-white/50 capitalize font-mono text-[10px]">{name.replace('_', ' ')}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono text-white/20">{info.doc_count} docs</span>
                <span className={`text-[10px] font-mono ${stateColors[info.state] || 'text-white/20'}`}>
                  {info.state}
                </span>
                {info.last_update && (
                  <span className="text-[10px] font-mono text-white/15">
                    {new Date(info.last_update).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          ))}

          {Object.keys(status.costs).length > 0 && (
            <div className="border-t border-white/[0.06] pt-2 mt-2">
              <div className="text-[10px] font-mono text-white/25 mb-1">Compute Costs</div>
              {Object.entries(status.costs).map(([key, val]) => (
                <div key={key} className="flex justify-between text-[10px] font-mono">
                  <span className="text-white/30">{key}</span>
                  <span className="text-emerald-400/60">${typeof val === 'object' ? JSON.stringify(val) : String(val)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
