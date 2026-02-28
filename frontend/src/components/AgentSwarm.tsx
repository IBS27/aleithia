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

interface Props {
  agentInfo: AgentInfo | null
  isActive: boolean
  elapsedMs?: number
}

function formatAgentName(name: string): string {
  const [type, ...rest] = name.split('_')
  const area = rest.join(' ')
  if (type === 'primary') return `Primary: ${area}`
  if (type === 'comparison') return `Compare: ${area}`
  if (type === 'regulatory') return 'Regulatory Agent'
  return name
}

export default function AgentSwarm({ agentInfo, isActive, elapsedMs }: Props) {
  if (!isActive && !agentInfo) return null

  // Fallback: build agent names from neighborhoods if no summaries
  const fallbackNames = agentInfo?.neighborhoods.map((n, i) =>
    i === 0 ? `Primary: ${n}` : `Comparison: ${n}`
  ) || []
  fallbackNames.push('Regulatory Agent')

  return (
    <div className="border border-white/[0.06] bg-white/[0.01] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span className="text-xs font-medium text-white/60">
            {isActive ? 'Deploying intelligence agents...' : `${agentInfo?.agents_deployed || 0} agents complete`}
          </span>
        </div>
        {elapsedMs !== undefined && !isActive && (
          <span className="text-[10px] font-mono text-white/20">{(elapsedMs / 1000).toFixed(1)}s</span>
        )}
      </div>

      <div className="space-y-1.5">
        {agentInfo?.agent_summaries ? (
          agentInfo.agent_summaries.map((agent, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              {isActive ? (
                <div className="w-3 h-3 border border-white/30 border-t-transparent rounded-full animate-spin" />
              ) : agent.error ? (
                <div className="w-3 h-3 rounded-full bg-red-400/60 flex items-center justify-center">
                  <span className="text-[8px] text-[#06080d] font-bold">!</span>
                </div>
              ) : (
                <div className="w-3 h-3 rounded-full bg-emerald-400 flex items-center justify-center">
                  <svg className="w-2 h-2 text-[#06080d]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              )}
              <span className="text-white/35 font-mono text-[10px]">
                {formatAgentName(agent.name)}
              </span>
              {!isActive && !agent.error && (
                <span className="text-white/15 font-mono text-[10px]">
                  {agent.data_points} pts
                  {agent.sources && ` · ${agent.sources.join(', ')}`}
                  {agent.regulation_count ? ` · ${agent.regulation_count} regs` : ''}
                </span>
              )}
              {agent.error && <span className="text-red-400/50 text-[10px]">failed</span>}
            </div>
          ))
        ) : (
          fallbackNames.map((name, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              {isActive ? (
                <div className="w-3 h-3 border border-white/30 border-t-transparent rounded-full animate-spin" />
              ) : (
                <div className="w-3 h-3 rounded-full bg-emerald-400 flex items-center justify-center">
                  <svg className="w-2 h-2 text-[#06080d]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              )}
              <span className="text-white/35 font-mono text-[10px]">{name}</span>
            </div>
          ))
        )}
      </div>

      {agentInfo && (
        <div className="flex items-center gap-4 text-[10px] font-mono text-white/20 pt-1 border-t border-white/[0.06]">
          <span>{agentInfo.agents_deployed} agents</span>
          <span>{agentInfo.neighborhoods.length} neighborhoods</span>
          <span>{agentInfo.data_points} data points</span>
        </div>
      )}
    </div>
  )
}
