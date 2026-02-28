/**
 * ProcessFlow — collapsible trace diagram showing pipeline stages
 * during a chat query. Collapsed: single summary line. Expanded:
 * vertical flow with agent fan-out details.
 */
import { useState } from 'react'

interface AgentSummary {
  name: string
  data_points: number
  sources?: string[]
  regulation_count?: number
  error?: boolean
}

interface AgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
  agent_summaries?: AgentSummary[]
}

export type ProcessStage =
  | 'idle'
  | 'deploying'
  | 'agents_complete'
  | 'synthesizing'
  | 'streaming'
  | 'complete'

interface Props {
  stage: ProcessStage
  question?: string
  agentInfo: AgentInfo | null
  elapsedMs?: number
  logs?: string[]
}

// ── Helpers ──────────────────────────────────────────────────────────────

function stageIndex(s: ProcessStage): number {
  return ['idle', 'deploying', 'agents_complete', 'synthesizing', 'streaming', 'complete'].indexOf(s)
}

function formatAgentLabel(name: string): string {
  const [type, ...rest] = name.split('_')
  const area = rest.join(' ')
  if (type === 'primary') return area
  if (type === 'comparison') return area
  if (type === 'regulatory') return 'Regulatory'
  return name
}

function formatAgentType(name: string): string {
  const type = name.split('_')[0]
  if (type === 'primary') return 'PRIMARY'
  if (type === 'comparison') return 'COMPARE'
  if (type === 'regulatory') return 'REGS'
  return type.toUpperCase()
}

function stageLabel(si: number, agentCount: number): string {
  if (si <= 1) return 'Deploying agents...'
  if (si === 2) return `${agentCount} agents complete`
  if (si === 3) return 'Synthesizing...'
  if (si === 4) return 'Streaming response...'
  return 'Complete'
}

// ── Sub-components ───────────────────────────────────────────────────────

function Spinner({ size = 10 }: { size?: number }) {
  return (
    <div
      className="border border-white/40 border-t-transparent rounded-full animate-spin"
      style={{ width: size, height: size }}
    />
  )
}

function NodeDot({ active, done, error }: { active: boolean; done: boolean; error?: boolean }) {
  if (error) return (
    <div className="w-2.5 h-2.5 rounded-full bg-red-400/60 flex items-center justify-center">
      <span className="text-[6px] text-[#06080d] font-bold leading-none">!</span>
    </div>
  )
  if (active) return <Spinner />
  if (done) return (
    <svg width={10} height={10} viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-emerald-400">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
    </svg>
  )
  return <div className="w-2.5 h-2.5 rounded-full border border-white/10" />
}

function ConnectorLine({ active, done }: { active: boolean; done: boolean }) {
  return (
    <div className="flex justify-center" style={{ width: 10 }}>
      <div
        className={`w-px h-full min-h-[12px] transition-colors duration-300 ${
          done ? 'bg-emerald-400/30' : active ? 'bg-white/20' : 'bg-white/[0.06]'
        }`}
      />
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────

export default function ProcessFlow({ stage, question, agentInfo, elapsedMs, logs }: Props) {
  if (stage === 'idle') return null

  // Auto-expand while active, collapse when complete
  const [userToggled, setUserToggled] = useState<boolean | null>(null)
  const [copied, setCopied] = useState(false)
  const isComplete = stage === 'complete'
  const expanded = userToggled !== null ? userToggled : !isComplete

  const si = stageIndex(stage)
  const requestDone = si >= 1
  const agentsDone = si >= 2
  const hasAgents = agentInfo && (agentInfo.agents_deployed > 0 || (agentInfo.agent_summaries && agentInfo.agent_summaries.length > 0))
  const synthActive = si === 2 || si === 3
  const synthDone = si >= 4
  const streamActive = si === 4
  const streamDone = si >= 5
  const complete = si >= 5

  // Build agent list only when we have real data
  const agents: AgentSummary[] = agentInfo?.agent_summaries || []
  const fallbackAgents = !agents.length && hasAgents
    ? [
        ...agentInfo!.neighborhoods.map((n, i) => ({
          name: i === 0 ? `primary_${n}` : `comparison_${n}`,
          data_points: 0,
        })),
        { name: 'regulatory_all', data_points: 0 },
      ]
    : []
  const agentList = agents.length ? agents : fallbackAgents
  const agentCount = agentInfo?.agents_deployed || agentList.length

  return (
    <div className="border border-white/[0.06] bg-white/[0.015] overflow-hidden">
      {/* Header — always visible, clickable to toggle */}
      <button
        onClick={() => setUserToggled(prev => prev === null ? !(!isComplete) : !prev)}
        className="w-full px-3 py-1.5 flex items-center justify-between cursor-pointer hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          {!complete ? <Spinner size={8} /> : (
            <svg width={8} height={8} viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-emerald-400">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
          <span className="text-[10px] font-mono text-white/40">
            {stageLabel(si, agentCount)}
          </span>
          {complete && agentInfo && agentInfo.data_points > 0 && (
            <span className="text-[9px] font-mono text-white/15">
              {agentInfo.data_points} pts
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {complete && elapsedMs !== undefined && (
            <span className="text-[9px] font-mono text-white/15">{(elapsedMs / 1000).toFixed(1)}s</span>
          )}
          {complete && logs && logs.length > 0 && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation()
                navigator.clipboard.writeText(logs.join('\n'))
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              }}
              onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.click() }}
              className="p-0.5 hover:bg-white/[0.06] rounded transition-colors"
              title="Copy logs"
            >
              {copied ? (
                <svg className="w-3 h-3 text-emerald-400/60" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-3 h-3 text-white/20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <rect x="9" y="9" width="13" height="13" rx="2" strokeWidth={2} />
                  <path strokeWidth={2} d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
              )}
            </span>
          )}
          <svg
            className={`w-3 h-3 text-white/20 transition-transform ${expanded ? 'rotate-180' : ''}`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded flow diagram */}
      {expanded && (
        <div className="px-3 py-2 border-t border-white/[0.04]">

          {/* ① Chat Request */}
          <div className="flex items-center gap-2">
            <NodeDot active={si === 0} done={requestDone} />
            <span className="text-[10px] font-mono text-white/40">Chat Request</span>
            {question && (
              <span className="text-[9px] font-mono text-white/15 truncate ml-1">"{question}"</span>
            )}
          </div>

          <div className="flex items-stretch gap-2 h-2.5">
            <ConnectorLine active={si >= 1} done={requestDone} />
          </div>

          {/* ② Agent Orchestrator */}
          <div className="flex items-center gap-2">
            <NodeDot active={si === 1} done={agentsDone} />
            <span className="text-[10px] font-mono text-white/40">Orchestrator</span>
            <span className="text-[9px] font-mono text-white/15">
              {si === 1 ? '.spawn() fan-out...' : agentsDone && hasAgents ? `${agentCount} agents` : agentsDone ? 'local fallback' : ''}
            </span>
          </div>

          {/* ③ Agent fan-out — only show if we have real agent data */}
          {agentList.length > 0 && (
            <>
              <div className="flex items-stretch gap-2 h-1.5">
                <ConnectorLine active={si >= 1} done={agentsDone} />
              </div>
              <div className="ml-1 border-l border-white/[0.05] pl-2 space-y-px">
                {agentList.map((agent, i) => (
                  <div key={i} className="flex items-center gap-1.5 py-px">
                    <NodeDot active={si === 1} done={agentsDone} error={agent.error} />
                    <span className="text-[8px] font-mono uppercase tracking-wider text-white/20 w-10 shrink-0">
                      {formatAgentType(agent.name)}
                    </span>
                    <span className="text-[10px] font-mono text-white/30 truncate">
                      {formatAgentLabel(agent.name)}
                    </span>
                    {agentsDone && !agent.error && agent.data_points > 0 && (
                      <span className="text-[9px] font-mono text-white/12 ml-auto shrink-0">
                        {agent.data_points} pts
                      </span>
                    )}
                    {agent.error && (
                      <span className="text-[9px] font-mono text-red-400/40 ml-auto shrink-0">err</span>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="flex items-stretch gap-2 h-2.5">
            <ConnectorLine active={synthActive || synthDone} done={synthDone} />
          </div>

          {/* ④ LLM Synthesis */}
          <div className="flex items-center gap-2">
            <NodeDot active={synthActive || streamActive} done={streamDone} />
            <span className="text-[10px] font-mono text-white/40">LLM Synthesis</span>
            <span className="text-[9px] font-mono text-white/15">
              {streamActive && <span className="text-white/20">streaming<span className="animate-pulse">...</span></span>}
              {synthActive && !streamActive && 'Qwen3-8B'}
              {streamDone && 'done'}
            </span>
          </div>

          <div className="flex items-stretch gap-2 h-2.5">
            <ConnectorLine active={streamDone} done={complete} />
          </div>

          {/* ⑤ Complete */}
          <div className="flex items-center gap-2">
            <NodeDot active={false} done={complete} />
            <span className={`text-[10px] font-mono ${complete ? 'text-emerald-400/50' : 'text-white/20'}`}>
              Delivered
            </span>
            {complete && agentInfo && agentInfo.data_points > 0 && (
              <span className="text-[9px] font-mono text-white/12">
                {agentInfo.data_points} pts · {agentInfo.neighborhoods.length} areas
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
