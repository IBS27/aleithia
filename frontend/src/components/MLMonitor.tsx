import { useState, useEffect } from 'react'
import { fetchPipelineStatus, type PipelineStatus } from '../api.ts'

interface ModelCard {
  name: string
  provider: string
  gpu: string
  task: string
  params: string
  maxBatch?: number
  contextLen?: number
  status: 'online' | 'offline' | 'loading'
}

const MODELS: ModelCard[] = [
  {
    name: 'Qwen3-8B',
    provider: 'Qwen / Alibaba',
    gpu: 'H100',
    task: 'LLM — Chat & Reasoning',
    params: '8B',
    contextLen: 8192,
    status: 'online',
  },
  {
    name: 'BART-large-MNLI',
    provider: 'facebook',
    gpu: 'T4',
    task: 'Zero-shot Classification',
    params: '407M',
    maxBatch: 32,
    status: 'online',
  },
  {
    name: 'twitter-roberta-base-sentiment',
    provider: 'cardiffnlp',
    gpu: 'T4',
    task: 'Sentiment Analysis',
    params: '125M',
    maxBatch: 32,
    status: 'online',
  },
  {
    name: 'YOLOv8n',
    provider: 'Ultralytics',
    gpu: 'T4',
    task: 'CCTV Object Detection',
    params: '3.2M',
    maxBatch: 1,
    status: 'online',
  },
]

const TRAINING_DATA = {
  script: 'generate_training_data.py',
  model: 'Qwen3-8B-FP8',
  gpu: 'H100',
  sourceDocsTarget: 300,
  outputPath: '/data/training_pairs.jsonl',
  format: 'Instruction-tuning JSONL',
}

export default function MLMonitor() {
  const [status, setStatus] = useState<PipelineStatus | null>(null)
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

  const gpuMap: Record<string, string> = {
    h100_llm: 'H100',
    t4_classifier: 'T4',
    t4_sentiment: 'T4',
    t4_cctv: 'T4',
  }

  const gpuTaskMap: Record<string, string> = {
    h100_llm: 'Qwen3-8B LLM',
    t4_classifier: 'Doc Classifier',
    t4_sentiment: 'Sentiment Analyzer',
    t4_cctv: 'CCTV Detector',
  }

  return (
    <div className="space-y-4">
      {/* GPU Fleet */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">GPU Fleet</h3>
          {status && (
            <span className="text-[10px] font-mono text-white/20">
              {Object.values(status.gpu_status).filter(s => s === 'available').length}/{Object.keys(status.gpu_status).length} online
            </span>
          )}
        </div>
        <div className="grid grid-cols-4 divide-x divide-white/[0.06]">
          {status ? Object.entries(status.gpu_status).map(([key, state]) => (
            <div key={key} className="px-4 py-3">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-1.5 h-1.5 rounded-full ${state === 'available' ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <span className="text-xs font-mono font-medium text-white/70">{gpuMap[key] || key}</span>
              </div>
              <div className="text-[10px] font-mono text-white/25">{gpuTaskMap[key] || key}</div>
              <div className={`text-[10px] font-mono mt-1 ${state === 'available' ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
                {state === 'available' ? 'ready' : state}
              </div>
            </div>
          )) : (
            <div className="col-span-4 px-4 py-6 text-center">
              <span className="text-[10px] font-mono text-white/20">{error ? 'Failed to connect' : 'Loading...'}</span>
            </div>
          )}
        </div>
      </div>

      {/* Deployed Models */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Deployed Models</h3>
        </div>
        <div className="divide-y divide-white/[0.06]">
          {MODELS.map((model) => {
            const gpuKey = model.gpu === 'H100' ? 'h100_llm' : model.task.includes('Classification') ? 't4_classifier' : model.task.includes('CCTV') ? 't4_cctv' : 't4_sentiment'
            const liveStatus = status?.gpu_status[gpuKey]
            const isOnline = liveStatus === 'available'

            return (
              <div key={model.name} className="px-4 py-3 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-white/20'}`} />
                    <span className="text-xs font-medium text-white/80 truncate">{model.name}</span>
                    <span className="text-[10px] font-mono text-white/15 border border-white/[0.06] px-1.5 py-0.5">{model.gpu}</span>
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
                  <span className={`text-[10px] font-mono ${isOnline ? 'text-emerald-400/60' : 'text-white/15'}`}>
                    {isOnline ? 'online' : 'offline'}
                  </span>
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
              ['Image.pip_install', '10 custom images'],
              ['modal.web_endpoint', 'SSE streaming'],
            ].map(([feature, usage]) => (
              <div key={feature} className="flex justify-between">
                <span className="text-white/40">{feature}</span>
                <span className="text-white/20">{usage}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-2 border-t border-white/[0.06] flex items-center justify-between">
            <span className="text-[10px] font-mono text-white/25">Total Modal features</span>
            <span className="text-xs font-mono font-bold text-white/60">18</span>
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
