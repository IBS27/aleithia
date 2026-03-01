import { useState, useEffect } from 'react'
import { fetchPipelineStatus, fetchGpuMetrics, type PipelineStatus, type GpuMetrics, type GpuMetricsEntry } from '../api.ts'

interface ModelCard {
  name: string
  provider: string
  gpu: string
  task: string
  params: string
  maxBatch?: number
  contextLen?: number
  gpuKey: string
  warmContainer?: boolean
}

const MODELS: ModelCard[] = [
  {
    name: 'Qwen3-8B-AWQ',
    provider: 'Qwen / Alibaba',
    gpu: 'H100',
    task: 'LLM — Chat & Reasoning',
    params: '8B (INT4)',
    contextLen: 8192,
    gpuKey: 'h100_llm',
    warmContainer: true,
  },
  {
    name: 'BART-large-MNLI',
    provider: 'facebook',
    gpu: 'T4',
    task: 'Zero-shot Classification',
    params: '407M',
    maxBatch: 32,
    gpuKey: 't4_classifier',
  },
  {
    name: 'twitter-roberta-base-sentiment',
    provider: 'cardiffnlp',
    gpu: 'T4',
    task: 'Sentiment Analysis',
    params: '125M',
    maxBatch: 32,
    gpuKey: 't4_sentiment',
  },
  {
    name: 'YOLOv8n',
    provider: 'Ultralytics',
    gpu: 'T4',
    task: 'CCTV Object Detection',
    params: '3.2M',
    maxBatch: 1,
    gpuKey: 't4_cctv',
    warmContainer: true,
  },
]

const TRAINING_DATA = {
  script: 'generate_training_data.py',
  model: 'Qwen3-8B-AWQ',
  gpu: 'H100',
  sourceDocsTarget: 300,
  outputPath: '/data/training_pairs.jsonl',
  format: 'Instruction-tuning JSONL',
}

function GpuBar({ label, value, max, unit, color }: { label: string; value: number; max: number; unit: string; color: string }) {
  const pct = Math.min(100, Math.round((value / max) * 100))
  return (
    <div className="flex items-center gap-2 text-[10px] font-mono">
      <span className="text-white/25 w-10 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-white/40 w-16 text-right tabular-nums">{value}{unit}</span>
    </div>
  )
}

function _formatAgo(seconds?: number): string {
  if (seconds == null) return ''
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return `${Math.round(seconds / 86400)}d ago`
}

function GpuCard({ gpuKey, entry, taskName, warm }: { gpuKey: string; entry: GpuMetricsEntry; taskName: string; warm?: boolean }) {
  const gpuLabel = gpuKey.startsWith('h100') ? 'H100' : 'T4'
  const isActive = entry.status === 'active'
  const isInferred = isActive && entry.inferred

  if (!isActive) {
    const isWarm = warm && entry.status === 'cold'
    const hasEnrichedData = entry.reason === 'idle' && (entry.enriched_count ?? 0) > 0
    const coldReason = entry.reason === 'no_data'
      ? 'no data'
      : hasEnrichedData
        ? 'enriched data'
        : isWarm ? 'warm standby' : 'cold standby'
    const coldColor = entry.reason === 'no_data'
      ? 'text-white/15'
      : hasEnrichedData
        ? 'text-emerald-400/40'
        : isWarm ? 'text-amber-400/40' : 'text-white/15'
    const dotColor = hasEnrichedData
      ? 'bg-emerald-400/50'
      : isWarm ? 'bg-amber-400/50' : 'bg-white/15'
    return (
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
          <span className="text-xs font-mono font-medium text-white/70">{gpuLabel}</span>
        </div>
        <div className="text-[10px] font-mono text-white/25">{taskName}</div>
        <div className={`text-[10px] font-mono mt-1 ${coldColor}`}>
          {coldReason}
        </div>
        {entry.enriched_count != null && entry.enriched_count > 0 && (
          <div className="text-[9px] font-mono mt-0.5 text-white/10">
            {entry.enriched_count} docs enriched
          </div>
        )}
      </div>
    )
  }

  // Inferred active: we know the cron ran recently but can't query nvidia-smi
  if (isInferred) {
    return (
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400/60" />
          <span className="text-xs font-mono font-medium text-white/70">{entry.gpu_name ?? gpuLabel}</span>
        </div>
        <div className="text-[10px] font-mono text-white/25">{taskName}</div>
        <div className="text-[10px] font-mono mt-1 text-emerald-400/40">recently active</div>
      </div>
    )
  }

  const utilColor = (entry.gpu_utilization ?? 0) > 80 ? 'bg-red-400' : (entry.gpu_utilization ?? 0) > 40 ? 'bg-amber-400' : 'bg-emerald-400'
  const memColor = (entry.memory_utilization ?? 0) > 80 ? 'bg-red-400' : 'bg-sky-400'

  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs font-mono font-medium text-white/70">{entry.gpu_name ?? gpuLabel}</span>
      </div>
      <div className="text-[10px] font-mono text-white/25 mb-2">{taskName}</div>
      <div className="space-y-1.5">
        <GpuBar label="GPU" value={entry.gpu_utilization ?? 0} max={100} unit="%" color={utilColor} />
        <GpuBar label="MEM" value={entry.memory_used_mb ?? 0} max={entry.memory_total_mb ?? 1} unit="MB" color={memColor} />
        <div className="flex items-center justify-between text-[10px] font-mono text-white/20 mt-1">
          <span>{entry.temperature_c ?? 0}&deg;C</span>
          <span>{entry.power_draw_w ?? 0}W / {entry.power_limit_w ?? 0}W</span>
        </div>
      </div>
    </div>
  )
}

export default function MLMonitor() {
  const [status, setStatus] = useState<PipelineStatus | null>(null)
  const [gpuMetrics, setGpuMetrics] = useState<GpuMetrics | null>(null)
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
    const interval = setInterval(poll, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function pollGpu() {
      try {
        const data = await fetchGpuMetrics()
        if (!cancelled) setGpuMetrics(data)
      } catch {
        // GPU metrics are best-effort
      }
    }
    pollGpu()
    const interval = setInterval(pollGpu, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  const gpuTaskMap: Record<string, string> = {
    h100_llm: 'Qwen3-8B LLM',
    t4_classifier: 'Doc Classifier',
    t4_sentiment: 'Sentiment Analyzer',
    t4_cctv: 'CCTV Detector',
  }

  const defaultEntry: GpuMetricsEntry = { status: 'cold' }

  return (
    <div className="space-y-4">
      {/* GPU Fleet — live metrics */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">GPU Fleet — Live</h3>
          {gpuMetrics && (
            <span className="text-[10px] font-mono text-white/20">
              {Object.values(gpuMetrics).filter(m => m.status === 'active').length}/4 active
            </span>
          )}
        </div>
        <div className="grid grid-cols-4 divide-x divide-white/[0.06]">
          {MODELS.map(model => (
            <GpuCard
              key={model.gpuKey}
              gpuKey={model.gpuKey}
              entry={gpuMetrics?.[model.gpuKey] ?? defaultEntry}
              taskName={gpuTaskMap[model.gpuKey]}
              warm={model.warmContainer}
            />
          ))}
        </div>
      </div>

      {/* Deployed Models */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Deployed Models</h3>
        </div>
        <div className="divide-y divide-white/[0.06]">
          {MODELS.map((model) => {
            const liveEntry = gpuMetrics?.[model.gpuKey]
            const isOnline = liveEntry?.status === 'active'
            const isInferred = isOnline && liveEntry?.inferred
            const isLoading = !gpuMetrics && !error

            const hasEnrichedData = liveEntry?.reason === 'idle' && (liveEntry?.enriched_count ?? 0) > 0
            const statusLabel = isOnline
              ? (isInferred ? 'recently active' : 'online')
              : liveEntry?.reason === 'no_data'
                ? 'no data'
                : hasEnrichedData
                  ? 'enriched data'
                  : (model.warmContainer ? 'warm standby' : 'cold standby')
            const statusColor = isOnline
              ? (isInferred ? 'text-emerald-400/40' : 'text-emerald-400/60')
              : hasEnrichedData
                ? 'text-emerald-400/40'
                : (model.warmContainer ? 'text-amber-400/40' : 'text-white/15')
            const dotColor = isLoading
              ? 'bg-amber-400/80 animate-pulse'
              : isOnline
                ? (isInferred ? 'bg-emerald-400/60' : 'bg-emerald-400')
                : hasEnrichedData
                  ? 'bg-emerald-400/50'
                  : (model.warmContainer ? 'bg-amber-400/50' : 'bg-white/20')

            return (
              <div key={model.name} className="px-4 py-3 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
                    <span className="text-xs font-medium text-white/80 truncate">{model.name}</span>
                    <span className="text-[10px] font-mono text-white/15 border border-white/[0.06] px-1.5 py-0.5">{model.gpu}</span>
                    {isOnline && !isInferred && liveEntry?.gpu_utilization != null && (
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        liveEntry.gpu_utilization > 80 ? 'text-red-400/70 border-red-400/20' :
                        liveEntry.gpu_utilization > 40 ? 'text-amber-400/70 border-amber-400/20' :
                        'text-emerald-400/70 border-emerald-400/20'
                      }`}>
                        {liveEntry.gpu_utilization}%
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] font-mono text-white/25 mt-1 pl-3.5">{model.task}</div>
                </div>
                <div className="flex items-center gap-4 text-right shrink-0">
                  <div>
                    <div className="text-[10px] font-mono text-white/30">{model.params}</div>
                    <div className="text-[10px] font-mono text-white/15">
                      {model.contextLen ? `${model.contextLen.toLocaleString()} ctx` : `batch ${model.maxBatch}`}
                    </div>
                  </div>
                  {isLoading ? (
                    <span className="flex items-center gap-1.5 text-[10px] font-mono text-amber-400/70">
                      <span className="w-2.5 h-2.5 border border-amber-400/40 border-t-amber-400 rounded-full animate-spin" />
                      checking…
                    </span>
                  ) : (
                    <span className={`text-[10px] font-mono ${statusColor}`}>
                      {statusLabel}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Classification Pipeline */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Classification Pipeline</h3>
        </div>
        <div className="px-4 py-3">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-2xl font-bold font-mono text-white">
                {status?.total_docs?.toLocaleString() ?? '—'}
              </div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/25 mt-1">Total Documents</div>
            </div>
            <div>
              <div className="text-2xl font-bold font-mono text-white">
                {status?.enriched_docs?.toLocaleString() ?? '—'}
              </div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/25 mt-1">Enriched (GPU)</div>
            </div>
            <div>
              <div className="text-2xl font-bold font-mono text-white">
                {status ? Math.round((status.enriched_docs / Math.max(status.total_docs, 1)) * 100) : '—'}
                <span className="text-sm text-white/30">%</span>
              </div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/25 mt-1">Coverage</div>
            </div>
          </div>

          {/* Pipeline queue info */}
          <div className="mt-4 pt-3 border-t border-white/[0.06]">
            <div className="flex items-center justify-between text-[10px] font-mono">
              <span className="text-white/25">Queue: modal.Queue &ldquo;new-docs&rdquo;</span>
              <span className="text-white/25">Drain interval: 2 min</span>
            </div>
            <div className="flex items-center justify-between text-[10px] font-mono mt-1">
              <span className="text-white/25">Batch size: 32 docs / GPU pass</span>
              <span className="text-white/25">Labels: regulatory, economic, safety, infrastructure, community, business</span>
            </div>
          </div>
        </div>
      </div>

      {/* Training Data */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Training Data Generation</h3>
        </div>
        <div className="px-4 py-3 space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] font-mono text-white/25 mb-1">Model</div>
              <div className="text-xs font-mono text-white/60">{TRAINING_DATA.model}</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-white/25 mb-1">GPU</div>
              <div className="text-xs font-mono text-white/60">{TRAINING_DATA.gpu}</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-white/25 mb-1">Source Documents</div>
              <div className="text-xs font-mono text-white/60">{TRAINING_DATA.sourceDocsTarget} docs (first N from /data/raw)</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-white/25 mb-1">Output Format</div>
              <div className="text-xs font-mono text-white/60">{TRAINING_DATA.format}</div>
            </div>
          </div>

          <div className="pt-2 border-t border-white/[0.06]">
            <div className="text-[10px] font-mono text-white/25 mb-1">Pipeline</div>
            <div className="text-[10px] font-mono text-white/15 space-y-0.5">
              <div>1. Load raw documents from /data/raw/*.json</div>
              <div>2. Generate questions via vLLM (Chicago business advisor persona)</div>
              <div>3. Generate answers with source context (Alethia persona)</div>
              <div>4. Filter pairs (q &gt; 10 chars, a &gt; 20 chars) &rarr; {TRAINING_DATA.outputPath}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Modal Infrastructure */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Modal Infrastructure</h3>
        </div>
        <div className="px-4 py-3">
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-[10px] font-mono">
            <div className="flex justify-between">
              <span className="text-white/25">Feature</span>
              <span className="text-white/25">Usage</span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/25">Feature</span>
              <span className="text-white/25">Usage</span>
            </div>
            {[
              ['@modal.cls', 'LLM + Classifiers'],
              ['@modal.enter', 'Model loading'],
              ['@modal.concurrent', '20 concurrent inputs'],
              ['@modal.batched', '32-doc GPU batch'],
              ['modal.Queue', 'Document pipeline'],
              ['modal.Dict', 'Cost tracking'],
              ['modal.Volume', 'Data + weights'],
              ['modal.Secret', 'API keys'],
              ['.spawn()', 'Agent fan-out'],
              ['@modal.asgi_app', 'FastAPI server'],
              ['modal.Period', '5 cron schedules'],
              ['modal.Retries', 'Pipeline resilience'],
              ['gpu="H100"', 'LLM inference'],
              ['gpu="T4"', 'Classification x2 + CCTV'],
              ['enable_memory_snapshot', 'GPU snapshots'],
              ['experimental_options', 'GPU cold start 10x'],
            ].map(([feature, usage]) => (
              <div key={feature} className="flex justify-between">
                <span className="text-white/40">{feature}</span>
                <span className="text-white/20">{usage}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-2 border-t border-white/[0.06] flex items-center justify-between">
            <span className="text-[10px] font-mono text-white/25">Total Modal features</span>
            <span className="text-xs font-mono font-bold text-white/60">20</span>
          </div>
        </div>
      </div>

      {/* Compute Costs */}
      {status && Object.keys(status.costs).length > 0 && (
        <div className="border border-white/[0.06] bg-white/[0.01]">
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Compute Costs</h3>
          </div>
          <div className="px-4 py-3 space-y-1">
            {Object.entries(status.costs).map(([key, val]) => (
              <div key={key} className="flex justify-between text-[10px] font-mono">
                <span className="text-white/30">{key}</span>
                <span className="text-emerald-400/60">
                  ${typeof val === 'object' ? JSON.stringify(val) : String(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
