/**
 * ProcessFlow — vertical trace diagram showing the pipeline stages
 * during a chat query. Visualizes: request → orchestrator → agents (fan-out)
 * → LLM synthesis → response complete.
 */

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

// ── Sub-components ───────────────────────────────────────────────────────

function Spinner({ size = 10 }: { size?: number }) {
  return (
    <div
      className="border border-white/40 border-t-transparent rounded-full animate-spin"
      style={{ width: size, height: size }}
    />
  )
}

function Check({ size = 10 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-emerald-400">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
    </svg>
  )
}

function ErrorDot() {
  return (
    <div className="w-2.5 h-2.5 rounded-full bg-red-400/60 flex items-center justify-center">
      <span className="text-[6px] text-[#06080d] font-bold leading-none">!</span>
    </div>
  )
}

function NodeDot({ active, done, error }: { active: boolean; done: boolean; error?: boolean }) {
  if (error) return <ErrorDot />
  if (active) return <Spinner />
  if (done) return <Check />
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

export default function ProcessFlow({ stage, question, agentInfo, elapsedMs }: Props) {
  if (stage === 'idle') return null

  const si = stageIndex(stage)

  // Stages
  const requestDone = si >= 1
  const agentsDone = si >= 2
  const synthActive = si === 2 || si === 3
  const synthDone = si >= 4
  const streamActive = si === 4
  const streamDone = si >= 5
  const complete = si >= 5

  // Build agent list (use summaries or fallback)
  const agents: AgentSummary[] = agentInfo?.agent_summaries || []
  const fallbackAgents = !agents.length && agentInfo
    ? [
        ...agentInfo.neighborhoods.map((n, i) => ({
          name: i === 0 ? `primary_${n}` : `comparison_${n}`,
          data_points: 0,
        })),
        { name: 'regulatory_all', data_points: 0 },
      ]
    : []
  const agentList = agents.length ? agents : fallbackAgents

  return (
    <div className="border border-white/[0.06] bg-white/[0.015] overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-3 h-3 text-white/30" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
            Process Trace
          </span>
        </div>
        {complete && elapsedMs !== undefined && (
          <span className="text-[10px] font-mono text-white/15">{(elapsedMs / 1000).toFixed(1)}s</span>
        )}
      </div>

      {/* Flow diagram */}
      <div className="px-3 py-2.5">

        {/* ① Chat Request */}
        <div className="flex items-start gap-2">
          <div className="flex flex-col items-center pt-0.5">
            <NodeDot active={si === 0} done={requestDone} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-mono text-white/50 font-medium">Chat Request</div>
            {question && (
              <div className="text-[9px] font-mono text-white/20 truncate mt-0.5">{question}</div>
            )}
          </div>
        </div>

        {/* Connector */}
        <div className="flex items-stretch gap-2 h-3">
          <ConnectorLine active={si >= 1} done={requestDone} />
        </div>

        {/* ② Agent Orchestrator */}
        <div className="flex items-start gap-2">
          <div className="flex flex-col items-center pt-0.5">
            <NodeDot active={si === 1} done={agentsDone} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-mono text-white/50 font-medium">Agent Orchestrator</div>
            <div className="text-[9px] font-mono text-white/15 mt-0.5">
              {si === 1 ? 'Fan-out via .spawn()...' : agentsDone ? `${agentInfo?.agents_deployed || agentList.length} agents deployed` : 'Waiting...'}
            </div>
          </div>
        </div>

        {/* Connector to fan-out */}
        <div className="flex items-stretch gap-2 h-2">
          <ConnectorLine active={si >= 1} done={agentsDone} />
        </div>

        {/* ③ Agent fan-out (branching) */}
        {agentList.length > 0 && (
          <div className="ml-1 border-l border-white/[0.06] pl-2 space-y-0.5">
            {agentList.map((agent, i) => (
              <div key={i} className="flex items-center gap-1.5 py-0.5">
                <NodeDot
                  active={si === 1}
                  done={agentsDone}
                  error={agent.error}
                />
                <span className="text-[8px] font-mono uppercase tracking-wider text-white/20 w-[46px] shrink-0">
                  {formatAgentType(agent.name)}
                </span>
                <span className="text-[10px] font-mono text-white/35 truncate">
                  {formatAgentLabel(agent.name)}
                </span>
                {agentsDone && !agent.error && (
                  <span className="text-[9px] font-mono text-white/15 ml-auto shrink-0 pl-1">
                    {agent.data_points > 0 && `${agent.data_points} pts`}
                    {agent.sources && agent.sources.length > 0 && ` · ${agent.sources.slice(0, 2).join(', ')}`}
                    {agent.regulation_count ? ` · ${agent.regulation_count} regs` : ''}
                  </span>
                )}
                {agent.error && (
                  <span className="text-[9px] font-mono text-red-400/50 ml-auto shrink-0">error</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Connector */}
        <div className="flex items-stretch gap-2 h-3">
          <ConnectorLine active={synthActive || synthDone} done={synthDone} />
        </div>

        {/* ④ LLM Synthesis */}
        <div className="flex items-start gap-2">
          <div className="flex flex-col items-center pt-0.5">
            <NodeDot active={synthActive || streamActive} done={streamDone} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-mono text-white/50 font-medium">LLM Synthesis</div>
            <div className="text-[9px] font-mono text-white/15 mt-0.5">
              {synthActive && !streamActive ? 'Connecting to Qwen3-8B...' : ''}
              {streamActive ? (
                <span className="text-white/25">
                  Streaming response
                  <span className="animate-pulse"> ...</span>
                </span>
              ) : ''}
              {streamDone ? 'Complete' : ''}
              {si < 2 ? 'Waiting for agents...' : ''}
            </div>
          </div>
        </div>

        {/* Connector */}
        <div className="flex items-stretch gap-2 h-3">
          <ConnectorLine active={streamDone} done={complete} />
        </div>

        {/* ⑤ Complete */}
        <div className="flex items-start gap-2">
          <div className="flex flex-col items-center pt-0.5">
            <NodeDot active={false} done={complete} />
          </div>
          <div className="flex-1 min-w-0">
            <div className={`text-[10px] font-mono font-medium ${complete ? 'text-emerald-400/60' : 'text-white/20'}`}>
              Response Delivered
            </div>
            {complete && agentInfo && (
              <div className="text-[9px] font-mono text-white/15 mt-0.5">
                {agentInfo.data_points} data points · {agentInfo.agents_deployed} agents · {agentInfo.neighborhoods.length} neighborhoods
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
