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
      <div className="bg-gray-900/50 rounded-xl border border-gray-800 p-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Pipeline Monitor</span>
          <span className="text-xs text-gray-600">Connecting...</span>
        </div>
      </div>
    )
  }

  const stateColors: Record<string, string> = {
    idle: 'text-green-400',
    running: 'text-blue-400',
    queued: 'text-yellow-400',
    no_data: 'text-gray-600',
    stale: 'text-red-400',
  }

  const stateIcons: Record<string, string> = {
    idle: 'bg-green-500',
    running: 'bg-blue-500 animate-pulse',
    queued: 'bg-yellow-500',
    no_data: 'bg-gray-600',
    stale: 'bg-red-500',
  }

  const pipelines = Object.entries(status.pipelines)

  return (
    <div className="bg-gray-900/50 rounded-xl border border-gray-800 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-gray-300">Pipeline Monitor</span>
          <span className="text-xs text-gray-500">{status.total_docs} docs</span>
          <span className="text-xs text-gray-500">{status.enriched_docs} enriched</span>
        </div>
        <div className="flex items-center gap-2">
          {/* GPU indicators */}
          {Object.entries(status.gpu_status).map(([gpu, state]) => (
            <div key={gpu} className="flex items-center gap-1">
              <div className={`w-1.5 h-1.5 rounded-full ${state === 'available' ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-[10px] text-gray-500">{gpu.split('_')[0].toUpperCase()}</span>
            </div>
          ))}
          <svg
            className={`w-4 h-4 text-gray-500 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-800 p-3 space-y-2">
          {pipelines.map(([name, info]) => (
            <div key={name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${stateIcons[info.state] || stateIcons.idle}`} />
                <span className="text-gray-300 capitalize">{name.replace('_', ' ')}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-gray-500">{info.doc_count} docs</span>
                <span className={stateColors[info.state] || 'text-gray-500'}>
                  {info.state}
                </span>
                {info.last_update && (
                  <span className="text-gray-600 text-[10px]">
                    {new Date(info.last_update).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          ))}

          {/* Cost tracking */}
          {Object.keys(status.costs).length > 0 && (
            <div className="border-t border-gray-800 pt-2 mt-2">
              <div className="text-[10px] text-gray-500 mb-1">Compute Costs</div>
              {Object.entries(status.costs).map(([key, val]) => (
                <div key={key} className="flex justify-between text-[10px]">
                  <span className="text-gray-400">{key}</span>
                  <span className="text-green-400">${typeof val === 'object' ? JSON.stringify(val) : String(val)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
