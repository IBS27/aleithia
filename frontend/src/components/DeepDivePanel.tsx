import { useState, useEffect } from 'react'
import type { DeepDiveResult } from '../api.ts'

interface Props {
  result: DeepDiveResult | null
  loading: boolean
  error: string | null
  onRequest: () => void
  requested: boolean
}

// ── Pipeline step definitions ──────────────────────────────────────────

interface PipelineStep {
  id: string
  label: string
  detail: string
  icon: string        // SVG path
  durationMs: number  // estimated time for this step
}

const PIPELINE_STEPS: PipelineStep[] = [
  {
    id: 'discover',
    label: 'Data Discovery',
    detail: 'Scanning 13 pipeline sources on Modal volume...',
    icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
    durationMs: 2000,
  },
  {
    id: 'codegen',
    label: 'Code Generation',
    detail: 'Qwen3-8B writing Python analysis script...',
    icon: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4',
    durationMs: 5000,
  },
  {
    id: 'sandbox',
    label: 'Sandbox Execution',
    detail: 'Running in isolated Modal container...',
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    durationMs: 6000,
  },
  {
    id: 'parse',
    label: 'Result Parsing',
    detail: 'Extracting stats, rendering charts...',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    durationMs: 2000,
  },
]

// ── Pipeline Loading Viz ───────────────────────────────────────────────

function PipelineLoading() {
  const [activeStep, setActiveStep] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [stepStart, setStepStart] = useState(Date.now())

  // Advance steps based on estimated durations
  useEffect(() => {
    if (activeStep >= PIPELINE_STEPS.length) return
    const timer = setTimeout(() => {
      setActiveStep(prev => Math.min(prev + 1, PIPELINE_STEPS.length - 1))
      setStepStart(Date.now())
    }, PIPELINE_STEPS[activeStep].durationMs)
    return () => clearTimeout(timer)
  }, [activeStep])

  // Global elapsed timer
  useEffect(() => {
    const interval = setInterval(() => setElapsed(prev => prev + 100), 100)
    return () => clearInterval(interval)
  }, [])

  // Per-step progress (0-100)
  const stepProgress = Math.min(
    100,
    ((Date.now() - stepStart) / PIPELINE_STEPS[activeStep]?.durationMs) * 100
  )

  return (
    <div className="mt-2 bg-white/[0.02] border border-white/[0.06] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="relative w-3 h-3">
            <div className="absolute inset-0 bg-emerald-400/20 rounded-full animate-ping" />
            <div className="absolute inset-0.5 bg-emerald-400/60 rounded-full" />
          </div>
          <span className="text-[10px] font-mono text-white/50 uppercase tracking-wider">
            Deep Dive — Analyzing
          </span>
        </div>
        <span className="text-[10px] font-mono text-white/25 tabular-nums">
          {(elapsed / 1000).toFixed(1)}s
        </span>
      </div>

      {/* Pipeline steps */}
      <div className="px-4 py-3 space-y-0">
        {PIPELINE_STEPS.map((step, i) => {
          const isActive = i === activeStep
          const isDone = i < activeStep
          const isPending = i > activeStep

          return (
            <div key={step.id} className="flex items-stretch gap-3">
              {/* Vertical connector line + icon */}
              <div className="flex flex-col items-center w-5 shrink-0">
                {/* Icon circle */}
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center border transition-all duration-500 ${
                    isDone
                      ? 'bg-emerald-400/20 border-emerald-400/40'
                      : isActive
                        ? 'bg-emerald-400/10 border-emerald-400/30 shadow-[0_0_8px_rgba(52,211,153,0.15)]'
                        : 'bg-white/[0.02] border-white/[0.08]'
                  }`}
                >
                  {isDone ? (
                    <svg className="w-2.5 h-2.5 text-emerald-400/80" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg
                      className={`w-2.5 h-2.5 transition-colors duration-500 ${
                        isActive ? 'text-emerald-400/70' : 'text-white/15'
                      }`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d={step.icon} />
                    </svg>
                  )}
                </div>
                {/* Connector line */}
                {i < PIPELINE_STEPS.length - 1 && (
                  <div className={`w-px flex-1 min-h-[16px] transition-colors duration-500 ${
                    isDone ? 'bg-emerald-400/20' : 'bg-white/[0.06]'
                  }`} />
                )}
              </div>

              {/* Step content */}
              <div className={`pb-3 flex-1 min-w-0 transition-opacity duration-500 ${
                isPending ? 'opacity-30' : 'opacity-100'
              }`}>
                <div className="flex items-center gap-2">
                  <span className={`text-[11px] font-mono font-medium transition-colors duration-500 ${
                    isDone ? 'text-emerald-400/60' : isActive ? 'text-white/70' : 'text-white/25'
                  }`}>
                    {step.label}
                  </span>
                  {isActive && (
                    <div className="animate-spin w-2.5 h-2.5 border border-emerald-400/30 border-t-emerald-400/70 rounded-full" />
                  )}
                </div>
                {(isActive || isDone) && (
                  <p className={`text-[10px] font-mono mt-0.5 transition-colors duration-500 ${
                    isDone ? 'text-emerald-400/30' : 'text-white/30'
                  }`}>
                    {step.detail}
                  </p>
                )}
                {/* Progress bar for active step */}
                {isActive && (
                  <div className="mt-1.5 h-[2px] bg-white/[0.04] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-400/30 rounded-full transition-[width] duration-300 ease-linear"
                      style={{ width: `${stepProgress}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Data sources being scanned (animated list) */}
      <DataSourceTicker activeStep={activeStep} />
    </div>
  )
}

// ── Animated data source ticker ────────────────────────────────────────

const DATA_SOURCES = [
  'food_inspections', 'building_permits', 'business_licenses', 'news_articles',
  'reddit_posts', 'yelp_reviews', 'politics_legistar', 'federal_register',
  'cta_ridership', 'traffic_flow', 'cctv_highway', 'census_demographics', 'vision_analysis',
]

function DataSourceTicker({ activeStep }: { activeStep: number }) {
  const [visibleSources, setVisibleSources] = useState<string[]>([])

  useEffect(() => {
    if (activeStep !== 0) {
      // Show all sources once discovery is done
      setVisibleSources(DATA_SOURCES)
      return
    }
    // Progressively reveal sources during discovery
    let idx = 0
    const interval = setInterval(() => {
      if (idx < DATA_SOURCES.length) {
        setVisibleSources(prev => [...prev, DATA_SOURCES[idx]])
        idx++
      } else {
        clearInterval(interval)
      }
    }, 140)
    return () => clearInterval(interval)
  }, [activeStep])

  if (activeStep > 1) return null // Hide after codegen starts

  return (
    <div className="px-4 pb-3 border-t border-white/[0.04]">
      <div className="flex flex-wrap gap-1 mt-2">
        {visibleSources.map((src) => (
          <span
            key={src}
            className="inline-block text-[9px] font-mono px-1.5 py-0.5 bg-white/[0.03] border border-white/[0.06] text-white/30 animate-[fadeIn_0.3s_ease-in]"
          >
            {src}
          </span>
        ))}
      </div>
      <p className="text-[9px] font-mono text-white/15 mt-1.5">
        {visibleSources.length} / {DATA_SOURCES.length} sources indexed
      </p>
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────

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

  // Loading state — pipeline visualization
  if (loading) {
    return <PipelineLoading />
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
