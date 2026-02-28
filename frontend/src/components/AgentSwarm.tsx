interface AgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
}

interface Props {
  agentInfo: AgentInfo | null
  isActive: boolean
  elapsedMs?: number
}

export default function AgentSwarm({ agentInfo, isActive, elapsedMs }: Props) {
  if (!isActive && !agentInfo) return null

  const agentNames = agentInfo?.neighborhoods.map((n, i) =>
    i === 0 ? `Primary: ${n}` : `Comparison: ${n}`
  ) || []
  agentNames.push('Regulatory Agent')

  return (
    <div className="bg-gray-900/50 rounded-xl border border-gray-800 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span className="text-sm font-medium text-gray-200">
            {isActive ? 'Deploying intelligence agents...' : `${agentInfo?.agents_deployed || 0} agents complete`}
          </span>
        </div>
        {elapsedMs !== undefined && !isActive && (
          <span className="text-xs text-gray-500">{(elapsedMs / 1000).toFixed(1)}s</span>
        )}
      </div>

      <div className="space-y-1.5">
        {agentNames.map((name, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            {isActive ? (
              <div className="w-3 h-3 border border-indigo-400 border-t-transparent rounded-full animate-spin" />
            ) : (
              <div className="w-3 h-3 rounded-full bg-green-500 flex items-center justify-center">
                <svg className="w-2 h-2 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              </div>
            )}
            <span className="text-gray-400">{name}</span>
          </div>
        ))}
      </div>

      {agentInfo && (
        <div className="flex items-center gap-4 text-[10px] text-gray-500 pt-1 border-t border-gray-800">
          <span>{agentInfo.agents_deployed} agents</span>
          <span>{agentInfo.neighborhoods.length} neighborhoods</span>
          <span>{agentInfo.data_points} data points</span>
        </div>
      )}
    </div>
  )
}
