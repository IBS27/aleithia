import { useState } from 'react'
import type { DeepDiveResult } from '../api.ts'

interface Props {
  result: DeepDiveResult | null
  loading: boolean
  error: string | null
  onRequest: () => void
  requested: boolean
}

export default function DeepDivePanel({ result, loading, error, onRequest, requested }: Props) {
  const [showCode, setShowCode] = useState(false)

  // Pre-request state
  if (!requested) {
    return (
      <button
        onClick={onRequest}
        className="flex items-center gap-1.5 mt-2 px-3 py-1.5 text-[10px] font-mono text-emerald-400/70 hover:text-emerald-400 bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.06] hover:border-emerald-400/20 transition-colors cursor-pointer"
      >
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        Deep Dive Analysis
      </button>
    )
  }

  // Loading state
  if (loading) {
    return (
      <div className="mt-2 bg-white/[0.02] border border-white/[0.06] px-4 py-3">
        <div className="flex items-center gap-2 text-[10px] font-mono text-white/40">
          <div className="animate-spin w-3 h-3 border border-emerald-400/30 border-t-emerald-400/60 rounded-full" />
          Running data analysis in sandbox...
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="mt-2 bg-red-500/[0.05] border border-red-500/20 px-4 py-3">
        <p className="text-[10px] font-mono text-red-400/80">{error}</p>
      </div>
    )
  }

  // No result yet
  if (!result) return null

  const { code, result: data, chart, stderr } = result
  const stats = data?.stats || {}
  const statEntries = Object.entries(stats)

  return (
    <div className="mt-2 bg-white/[0.02] border border-white/[0.06] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-1.5">
        <svg className="w-3 h-3 text-emerald-400/60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <span className="text-[10px] font-mono text-white/50 uppercase tracking-wider">
          {data?.title || 'Deep Dive Analysis'}
        </span>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Summary */}
        {data?.summary && (
          <p className="text-xs text-white/60 leading-relaxed">{data.summary}</p>
        )}

        {/* Stats grid */}
        {statEntries.length > 0 && (
          <div className="grid grid-cols-2 gap-2">
            {statEntries.map(([key, value]) => (
              <div key={key} className="bg-white/[0.03] border border-white/[0.04] px-3 py-2">
                <div className="text-sm font-bold font-mono text-white/80">
                  {typeof value === 'number' ? value.toLocaleString() : String(value)}
                </div>
                <div className="text-[9px] font-mono text-white/30 uppercase tracking-wider mt-0.5">
                  {key.replace(/_/g, ' ')}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Chart */}
        {chart && (
          <div className="border border-white/[0.06] bg-white/[0.02] p-2">
            <img
              src={`data:image/png;base64,${chart}`}
              alt="Analysis chart"
              className="w-full h-auto"
            />
          </div>
        )}

        {/* Stderr warning */}
        {stderr && (
          <div className="bg-yellow-500/[0.05] border border-yellow-500/20 px-3 py-2">
            <p className="text-[9px] font-mono text-yellow-400/60 break-all">{stderr}</p>
          </div>
        )}

        {/* Code toggle */}
        <button
          onClick={() => setShowCode(!showCode)}
          className="text-[10px] font-mono text-white/25 hover:text-white/50 transition-colors cursor-pointer"
        >
          {showCode ? 'Hide' : 'Show'} generated code
        </button>
        {showCode && (
          <pre className="bg-black/30 border border-white/[0.06] p-3 text-[10px] font-mono text-white/40 overflow-x-auto max-h-60 overflow-y-auto leading-relaxed">
            {code}
          </pre>
        )}
      </div>
    </div>
  )
}
