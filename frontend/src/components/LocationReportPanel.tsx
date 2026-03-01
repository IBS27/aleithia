import type { NeighborhoodData, RiskScore, UserProfile } from '../types/index.ts'

interface AgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
  agent_summaries: Array<{
    name: string
    data_points: number
    sources?: string[]
  }>
}

interface Props {
  profile: UserProfile
  neighborhoodData: NeighborhoodData | null
  riskScore: RiskScore | null
  loading: boolean
  agentInfo: AgentInfo | null
}

type Signal = {
  title: string
  detail: string
}

function buildAdvantages(data: NeighborhoodData | null): Signal[] {
  if (!data) return []

  const items: Signal[] = []
  const stats = data.inspection_stats
  const passRate = stats.total > 0 ? stats.passed / stats.total : null
  const avgRating = data.metrics?.avg_review_rating ?? 0

  if (passRate !== null && passRate >= 0.8 && stats.total >= 5) {
    items.push({
      title: 'Strong compliance baseline',
      detail: `${Math.round(passRate * 100)}% pass rate across ${stats.total} nearby food inspections can reduce early operational friction.`,
    })
  }

  if (avgRating >= 4.0 && (data.reviews?.length || 0) >= 5) {
    items.push({
      title: 'Healthy customer sentiment',
      detail: `Area businesses average ${avgRating.toFixed(1)}/5 across ${data.reviews?.length || 0} reviews, indicating active demand with positive sentiment.`,
    })
  }

  if (data.cctv && data.cctv.cameras.length > 0 && (data.cctv.density === 'high' || data.cctv.density === 'medium')) {
    items.push({
      title: 'Consistent street activity',
      detail: `${data.cctv.cameras.length} nearby cameras report ${data.cctv.density} foot traffic (avg ${data.cctv.avg_pedestrians} pedestrians), supporting walk-in potential.`,
    })
  }

  if (data.permit_count >= 8) {
    items.push({
      title: 'Growth and reinvestment signal',
      detail: `${data.permit_count} active permits suggest ongoing neighborhood investment and business momentum.`,
    })
  }

  if (items.length === 0) {
    items.push({
      title: 'Balanced baseline indicators',
      detail: 'Core public-data coverage is present, enabling a measured launch with targeted validation before expansion.',
    })
  }

  return items.slice(0, 2)
}

function buildRisks(data: NeighborhoodData | null): Signal[] {
  if (!data) return []

  const items: Signal[] = []
  const stats = data.inspection_stats
  const failRate = stats.total > 0 ? stats.failed / stats.total : null
  const avgRating = data.metrics?.avg_review_rating ?? 0
  const congestedCount = (data.traffic || []).filter(t => {
    const level = (t.metadata?.congestion_level as string | undefined)?.toLowerCase()
    return level === 'heavy' || level === 'blocked'
  }).length

  if (failRate !== null && failRate >= 0.25 && stats.total >= 4) {
    items.push({
      title: 'Elevated compliance risk',
      detail: `${stats.failed} failed inspections out of ${stats.total} records (${Math.round(failRate * 100)}%) may signal stricter enforcement or operational complexity.`,
    })
  }

  if (data.license_count >= 20) {
    items.push({
      title: 'High local competition',
      detail: `${data.license_count} active business licenses in the area indicate a crowded market and a higher differentiation burden.`,
    })
  }

  if (congestedCount >= 2) {
    items.push({
      title: 'Traffic friction',
      detail: `${congestedCount} nearby heavily congested zones can affect delivery reliability and customer convenience.`,
    })
  }

  if (avgRating > 0 && avgRating < 3.8) {
    items.push({
      title: 'Mixed consumer sentiment',
      detail: `Average local rating is ${avgRating.toFixed(1)}/5, suggesting quality expectations may be difficult to exceed consistently.`,
    })
  }

  if (items.length === 0) {
    items.push({
      title: 'No dominant red flag detected',
      detail: 'Current signals do not show an extreme downside driver, but category-specific diligence is still recommended.',
    })
  }

  return items.slice(0, 2)
}

function buildSummary(profile: UserProfile, data: NeighborhoodData | null, riskScore: RiskScore | null): string {
  if (!data) {
    return `Preparing a location report for ${profile.business_type} in ${profile.neighborhood}.`
  }

  const totalSignals =
    data.inspection_stats.total +
    data.permit_count +
    data.license_count +
    (data.news.length || 0) +
    (data.politics.length || 0) +
    (data.reviews?.length || 0) +
    (data.traffic?.length || 0)

  const posture = riskScore
    ? riskScore.overall_score <= 4
      ? 'favorable'
      : riskScore.overall_score <= 7
        ? 'mixed'
        : 'higher-risk'
    : 'mixed'

  return `${profile.neighborhood} looks ${posture} for a ${profile.business_type.toLowerCase()} launch based on ${totalSignals} local signals. Prioritize quick validation on the highlighted risks while leveraging the strongest demand/compliance advantages.`
}

export default function LocationReportPanel({ profile, neighborhoodData, riskScore, loading, agentInfo }: Props) {
  const advantages = buildAdvantages(neighborhoodData)
  const risks = buildRisks(neighborhoodData)
  const summary = buildSummary(profile, neighborhoodData, riskScore)

  return (
    <section className="h-full flex flex-col border border-white/[0.06] bg-white/[0.02]">
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <p className="text-[10px] font-mono uppercase tracking-wider text-white/35">Location Report</p>
        <h3 className="text-sm font-semibold text-white mt-1">{profile.business_type} • {profile.neighborhood}</h3>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading ? (
          <div className="text-xs text-white/40 font-mono">Generating report from live pipeline signals…</div>
        ) : (
          <>
            {agentInfo && (
              <div className="border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
                <p className="text-[10px] font-mono uppercase tracking-wider text-cyan-200/75 mb-2">Agent Intelligence</p>
                <div className="grid grid-cols-3 gap-2 mb-3">
                  <div>
                    <p className="text-[10px] font-mono text-white/35 uppercase">Agents</p>
                    <p className="text-sm font-semibold text-white">{agentInfo.agents_deployed}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-mono text-white/35 uppercase">Neighborhoods</p>
                    <p className="text-sm font-semibold text-white">{agentInfo.neighborhoods.length}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-mono text-white/35 uppercase">Data points</p>
                    <p className="text-sm font-semibold text-white">{agentInfo.data_points}</p>
                  </div>
                </div>

                {agentInfo.agent_summaries.length > 0 && (
                  <div className="space-y-1.5">
                    {agentInfo.agent_summaries.slice(0, 4).map((agent) => (
                      <div key={agent.name} className="flex items-center justify-between text-[11px] border border-white/10 px-2 py-1.5">
                        <span className="text-white/70 capitalize">{agent.name}</span>
                        <span className="font-mono text-white/85">{agent.data_points}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-emerald-300/70 mb-2">Advantages</p>
              <div className="space-y-2">
                {advantages.map((item) => (
                  <div key={item.title} className="border border-emerald-500/20 bg-emerald-500/[0.05] p-3">
                    <p className="text-xs font-semibold text-emerald-300">{item.title}</p>
                    <p className="text-[11px] text-white/65 mt-1 leading-relaxed">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-amber-300/70 mb-2">Risks</p>
              <div className="space-y-2">
                {risks.map((item) => (
                  <div key={item.title} className="border border-amber-500/20 bg-amber-500/[0.05] p-3">
                    <p className="text-xs font-semibold text-amber-200">{item.title}</p>
                    <p className="text-[11px] text-white/65 mt-1 leading-relaxed">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-white/[0.08] bg-black/20 p-3">
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/35 mb-2">Brief summary</p>
              <p className="text-[11px] text-white/75 leading-relaxed">{summary}</p>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
