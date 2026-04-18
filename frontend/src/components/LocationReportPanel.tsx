import { useState, useEffect } from 'react'
import type { NeighborhoodData, RiskScore, UserProfile, Document, SocialTrend } from '../types/index.ts'
import { computeInsights, LICENSE_MAP } from '../insights.ts'
import { api } from '../api.ts'

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

// ── Extraction helpers ──────────────────────────────────────────────

function extractAllAdvantages(data: NeighborhoodData, profile: UserProfile): Signal[] {
  const signals: Signal[] = []
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  if (isServiceBusiness && data.demographics) {
    const d = data.demographics
    if (d.total_population && d.total_population > 5000) {
      signals.push({
        title: 'Large resident base',
        detail: `~${Math.round(d.total_population / 1000)}K residents in the neighborhood.`,
      })
    }
  }

  const realestate = data.realestate?.length || 0
  if (realestate > 3) {
    signals.push({
      title: 'Active real estate market',
      detail: `${realestate} listings — area is attracting investment.`,
    })
  }

  if (isFoodBusiness) {
    const newsCount = data.news?.length || 0
    if (newsCount > 5) {
      signals.push({
        title: 'Local media coverage',
        detail: `${newsCount} recent news mentions in the area.`,
      })
    }
  }

  const uniqueLicenseTypes = new Set(
    data.licenses.map(l => (l.metadata?.raw_record as Record<string, unknown>)?.license_description || '').filter(Boolean)
  )
  if (uniqueLicenseTypes.size > 15) {
    signals.push({
      title: 'Diverse business mix',
      detail: `${uniqueLicenseTypes.size} different business types — established commercial corridor.`,
    })
  }

  if (data.transit && data.transit.stations_nearby >= 2) {
    signals.push({
      title: 'Strong transit access',
      detail: `${data.transit.stations_nearby} CTA stations (${data.transit.station_names.slice(0, 3).join(', ')}), ~${Math.round(data.transit.total_daily_riders / 1000)}K daily riders.`,
    })
  }

  const reviews = data.reviews || []
  const ratings = reviews.map(r => (r.metadata?.rating as number) || 0).filter(r => r > 0)
  if (ratings.length >= 3) {
    const avgRating = ratings.reduce((a, b) => a + b, 0) / ratings.length
    if (avgRating >= 4.0) {
      signals.push({
        title: 'High review ratings',
        detail: `${avgRating.toFixed(1)}/5 avg across ${ratings.length} businesses.`,
      })
    }
  }

  const insights = computeInsights(data, profile)
  for (const cat of insights.categories) {
    if (cat.score >= 65 && !signals.some(s => s.title.toLowerCase().includes(cat.name.toLowerCase()))) {
      signals.push({
        title: `${cat.name}: ${cat.score}/100`,
        detail: cat.claim,
      })
    }
  }

  return signals.slice(0, 5)
}

function extractAllRisks(data: NeighborhoodData, profile: UserProfile): Signal[] {
  const signals: Signal[] = []
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  if (isServiceBusiness && data.cctv) {
    const cameras = data.cctv.cameras || []
    const avgPeds = data.cctv.avg_pedestrians || 0
    if (cameras.length > 0 && avgPeds < 5) {
      signals.push({
        title: 'Low foot traffic',
        detail: `~${Math.round(avgPeds)} pedestrians/observation across ${cameras.length} cameras.`,
      })
    }
  }

  if (isServiceBusiness && data.demographics?.median_household_income) {
    const income = data.demographics.median_household_income
    if (income < 30000) {
      signals.push({
        title: 'Low-income area',
        detail: `Median household income ~$${Math.round(income / 1000)}K — limits premium service demand.`,
      })
    }
  }

  if (isFoodBusiness && data.reviews && data.reviews.length > 5) {
    const recentReviews = data.reviews.filter(r => {
      const metadata = r.metadata as Record<string, unknown>
      const raw = metadata?.raw_record as Record<string, unknown>
      const reviewDate = raw?.review_date || raw?.date
      if (!reviewDate) return false
      const daysSince = (Date.now() - new Date(reviewDate as string).getTime()) / (1000 * 60 * 60 * 24)
      return daysSince < 90
    }).length
    const recentPct = (recentReviews / data.reviews.length) * 100
    if (recentPct < 25) {
      signals.push({
        title: 'Declining review activity',
        detail: `Only ${recentReviews} of ${data.reviews.length} reviews from the last 90 days.`,
      })
    }
  }

  if (data.licenses.length > 30) {
    signals.push({
      title: 'Crowded market',
      detail: `${data.licenses.length} active business licenses in the area.`,
    })
  }

  if (isFoodBusiness && data.inspection_stats.total > 0) {
    const passRate = data.inspection_stats.passed / data.inspection_stats.total
    if (passRate < 0.6) {
      signals.push({
        title: 'Low inspection pass rate',
        detail: `${Math.round(passRate * 100)}% of ${data.inspection_stats.total} inspections passed.`,
      })
    }
  }

  if (!data.transit || data.transit.stations_nearby === 0) {
    signals.push({
      title: 'No nearby transit',
      detail: 'No CTA L-stations within range. Customers rely on driving or bus.',
    })
  }

  const fedCount = data.federal_register?.length || 0
  if (fedCount > 5) {
    signals.push({
      title: 'Federal regulatory pressure',
      detail: `${fedCount} recent SBA/FDA/OSHA/EPA regulations to review.`,
    })
  }

  const reviewCount = data.reviews?.length || 0
  if (reviewCount > 0 && reviewCount < 3) {
    signals.push({
      title: 'Sparse review data',
      detail: `Only ${reviewCount} review(s) — not enough for reliable market read.`,
    })
  }

  const insights = computeInsights(data, profile)
  for (const cat of insights.categories) {
    if (cat.score < 40 && !signals.some(s => s.title.toLowerCase().includes(cat.name.toLowerCase()))) {
      signals.push({
        title: `${cat.name}: ${cat.score}/100`,
        detail: cat.claim,
      })
    }
  }

  return signals.slice(0, 5)
}

interface Competitor {
  name: string
  type: string
  isDirect: boolean
}

function extractCompetitors(data: NeighborhoodData, profile: UserProfile): Competitor[] {
  const keywords = LICENSE_MAP[profile.business_type] || []
  const seen = new Set<string>()
  const competitors: Competitor[] = []

  for (const l of data.licenses) {
    const raw = l.metadata?.raw_record as Record<string, unknown> | undefined
    const name = (raw?.doing_business_as_name as string) || ''
    const desc = (raw?.license_description as string) || ''
    if (!name || seen.has(name)) continue
    seen.add(name)

    const isDirect = keywords.length > 0
      ? keywords.some(kw => desc.toLowerCase().includes(kw))
      : false

    competitors.push({ name, type: desc, isDirect })
  }

  // Sort: direct competitors first, then alphabetical
  competitors.sort((a, b) => {
    if (a.isDirect !== b.isDirect) return a.isDirect ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return competitors.slice(0, 8)
}

interface RegulatoryItem {
  name: string
  result: string
}

interface RegulatorySummary {
  passRate: number
  total: number
  passed: number
  failed: number
  recentInspections: RegulatoryItem[]
  permitBreakdown: { type: string; count: number }[]
  federalAlerts: { title: string; agency: string }[]
}

function extractRegulatory(data: NeighborhoodData): RegulatorySummary {
  const stats = data.inspection_stats
  const passRate = stats.total > 0 ? Math.round((stats.passed / stats.total) * 100) : 0

  // Recent inspections
  const recentInspections: RegulatoryItem[] = data.inspections
    .slice(0, 5)
    .map(i => {
      const raw = i.metadata?.raw_record as Record<string, unknown> | undefined
      return {
        name: (raw?.dba_name as string) || i.title || 'Unknown',
        result: (raw?.results as string) || 'N/A',
      }
    })

  // Permit breakdown by type
  const permitTypes: Record<string, number> = {}
  for (const p of data.permits) {
    const raw = p.metadata?.raw_record as Record<string, unknown> | undefined
    const type = (raw?.permit_type as string) || 'Other'
    permitTypes[type] = (permitTypes[type] || 0) + 1
  }
  const permitBreakdown = Object.entries(permitTypes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([type, count]) => ({ type, count }))

  // Federal register alerts
  const federalAlerts: { title: string; agency: string }[] = (data.federal_register || [])
    .slice(0, 3)
    .map((d: Document) => ({
      title: d.title || 'Untitled regulation',
      agency: (d.metadata?.agency as string) || 'Federal',
    }))

  return {
    passRate,
    total: stats.total,
    passed: stats.passed,
    failed: stats.failed,
    recentInspections,
    permitBreakdown,
    federalAlerts,
  }
}

// ── Component ───────────────────────────────────────────────────────

export default function LocationReportPanel({ profile, neighborhoodData, loading, agentInfo: _agentInfo }: Props) {
  const [socialTrends, setSocialTrends] = useState<SocialTrend[]>([])
  const [socialLoading, setSocialLoading] = useState(false)
  const [socialError, setSocialError] = useState<string | null>(null)

  useEffect(() => {
    if (!profile.neighborhood) return
    let cancelled = false
    setSocialLoading(true)
    setSocialError(null)
    setSocialTrends([])
    api.socialTrends(profile.neighborhood, profile.business_type)
      .then((data) => {
        if (!cancelled) setSocialTrends(data.trends)
      })
      .catch((err) => {
        if (!cancelled) setSocialError(err.message || 'Failed to load social trends')
      })
      .finally(() => {
        if (!cancelled) setSocialLoading(false)
      })
    return () => { cancelled = true }
  }, [profile.neighborhood, profile.business_type])

  const insights = neighborhoodData
    ? computeInsights(neighborhoodData, profile)
    : null

  const advantages = neighborhoodData ? extractAllAdvantages(neighborhoodData, profile) : []
  const risks = neighborhoodData ? extractAllRisks(neighborhoodData, profile) : []
  const competitors = neighborhoodData ? extractCompetitors(neighborhoodData, profile) : []
  const regulatory = neighborhoodData ? extractRegulatory(neighborhoodData) : null

  return (
    <section className="h-full flex flex-col border border-white/[0.06] bg-white/[0.02]">
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-xs text-white/40 font-mono">Generating intelligence brief from live pipeline signals…</div>
        ) : !neighborhoodData || !insights ? (
          <div className="p-4 text-xs text-white/40 font-mono">Select a neighborhood to generate intelligence brief.</div>
        ) : (
          <>
            {/* 1. Advantages */}
            <ModuleHeader
              label="Advantages"
              count={advantages.length}
              accent="text-emerald-300/70"
              dot="bg-emerald-400/60"
            />
            <div className="px-4 pb-4 space-y-1.5">
              {advantages.length > 0 ? advantages.map((item) => (
                <BriefRow
                  key={item.title}
                  title={item.title}
                  detail={item.detail}
                  tone="positive"
                />
              )) : (
                <p className="text-[10px] font-mono text-white/25 italic">No clear advantages from available data.</p>
              )}
            </div>

            {/* 2. Risks */}
            <ModuleHeader
              label="Risks"
              count={risks.length}
              accent="text-amber-300/70"
              dot="bg-amber-400/60"
            />
            <div className="px-4 pb-4 space-y-1.5">
              {risks.length > 0 ? risks.map((item) => (
                <BriefRow
                  key={item.title}
                  title={item.title}
                  detail={item.detail}
                  tone="warning"
                />
              )) : (
                <p className="text-[10px] font-mono text-white/25 italic">No major risks identified.</p>
              )}
            </div>

            {/* 3. Social Media Trends */}
            <ModuleHeader
              label="Social Trends"
              accent="text-cyan-300/70"
              dot="bg-cyan-400/60"
            />
            <div className="px-4 pb-4 space-y-1.5">
              {socialLoading ? (
                <p className="text-[10px] font-mono text-cyan-300/50 animate-pulse">Analyzing social signals…</p>
              ) : socialError ? (
                <p className="text-[10px] font-mono text-red-400/70">{socialError}</p>
              ) : socialTrends.length > 0 ? socialTrends.map((trend) => (
                <BriefRow
                  key={trend.title}
                  title={trend.title}
                  detail={trend.detail}
                  tone="info"
                />
              )) : (
                <p className="text-[10px] font-mono text-white/25 italic">No social signals detected.</p>
              )}
            </div>

            {/* 4. Nearby Businesses — direct competitors (if any) are flagged inline */}
            <ModuleHeader
              label="Nearby Businesses"
              count={competitors.length}
              accent="text-blue-300/70"
              dot="bg-blue-400/60"
            />
            <div className="px-4 pb-4">
              {competitors.length > 0 ? (
                <div className="border border-white/[0.05] bg-white/[0.01] divide-y divide-white/[0.04]">
                  {competitors.map((c) => (
                    <div key={c.name} className="flex items-start gap-2 px-2.5 py-1.5 text-[11px]">
                      <span className={`mt-1 shrink-0 w-1 h-1 rounded-full ${c.isDirect ? 'bg-red-400' : 'bg-white/25'}`} />
                      <div className="flex-1 min-w-0 flex items-baseline gap-2">
                        <span className="text-white/80 truncate">{c.name}</span>
                        <span className="text-white/25 text-[10px] truncate">{c.type}</span>
                      </div>
                      {c.isDirect && <span className="text-red-400/80 text-[9px] font-mono uppercase tracking-wider shrink-0">Direct</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[10px] font-mono text-white/25 italic">No competitor data available.</p>
              )}
            </div>

            {/* 5. Regulatory Checklist */}
            {regulatory && (
              <>
                <ModuleHeader
                  label="Regulatory Checklist"
                  accent="text-violet-300/70"
                  dot="bg-violet-400/60"
                />
                <div className="px-4 pb-4 space-y-2">
                  {/* Inspection pass rate bar */}
                  <div className="border border-white/[0.05] bg-white/[0.01] p-2.5">
                    <div className="flex items-baseline justify-between mb-1.5">
                      <p className="text-[9px] font-mono uppercase tracking-wider text-white/40">Inspections</p>
                      {regulatory.total > 0 && (
                        <p className="text-[10px] font-mono text-white/50">
                          <span className={`font-bold ${regulatory.passRate >= 80 ? 'text-emerald-400/80' : regulatory.passRate >= 60 ? 'text-amber-400/80' : 'text-red-400/80'}`}>
                            {regulatory.passRate}%
                          </span>
                          <span className="text-white/30"> · {regulatory.passed}/{regulatory.total}</span>
                        </p>
                      )}
                    </div>
                    {regulatory.total > 0 && (
                      <div className="h-1 bg-white/[0.05] overflow-hidden rounded-full">
                        <div className={`h-1 ${regulatory.passRate >= 80 ? 'bg-emerald-400/60' : regulatory.passRate >= 60 ? 'bg-amber-400/60' : 'bg-red-400/60'}`} style={{ width: `${regulatory.passRate}%` }} />
                      </div>
                    )}
                    {regulatory.recentInspections.length > 0 && (
                      <div className="mt-2 space-y-0.5">
                        {regulatory.recentInspections.slice(0, 4).map((i, idx) => (
                          <div key={idx} className="flex justify-between text-[10px]">
                            <span className="text-white/55 truncate mr-2">{i.name}</span>
                            <span className={`shrink-0 font-mono ${i.result.toLowerCase().includes('pass') ? 'text-emerald-400/70' : i.result.toLowerCase().includes('fail') ? 'text-red-400/70' : 'text-white/40'}`}>
                              {i.result}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Permits by type */}
                  {regulatory.permitBreakdown.length > 0 && (
                    <div className="border border-white/[0.05] bg-white/[0.01] p-2.5">
                      <p className="text-[9px] font-mono uppercase tracking-wider text-white/40 mb-1.5">Permits by Type</p>
                      <div className="space-y-0.5">
                        {regulatory.permitBreakdown.map((p) => (
                          <div key={p.type} className="flex justify-between text-[10px]">
                            <span className="text-white/55 truncate">{p.type}</span>
                            <span className="text-white/40 font-mono">{p.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Federal alerts */}
                  {regulatory.federalAlerts.length > 0 && (
                    <div className="border border-red-500/15 bg-red-500/[0.03] p-2.5">
                      <p className="text-[9px] font-mono uppercase tracking-wider text-red-300/60 mb-1.5">Federal Regulation Alerts</p>
                      <div className="space-y-1">
                        {regulatory.federalAlerts.map((a, idx) => (
                          <div key={idx} className="text-[10px]">
                            <p className="text-white/70 line-clamp-2">{a.title}</p>
                            <p className="text-[9px] font-mono text-red-300/40 mt-0.5">{a.agency}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

          </>
        )}
      </div>
    </section>
  )
}

// ────────────────────────────────────────────────────────────────────
// Shared brief rail helpers
// ────────────────────────────────────────────────────────────────────

function ModuleHeader({ label, count, accent, dot }: { label: string; count?: number; accent: string; dot?: string }) {
  return (
    <div className="px-4 pt-4 pb-2 flex items-center gap-2">
      {dot && <span className={`w-1 h-1 rounded-full ${dot}`} />}
      <p className={`text-[9px] font-mono uppercase tracking-[0.2em] ${accent}`}>{label}</p>
      {count !== undefined && count > 0 && (
        <span className="text-[9px] font-mono text-white/25">({count})</span>
      )}
      <div className="flex-1 h-px bg-white/[0.05] ml-1" />
    </div>
  )
}

function BriefRow({ title, detail, tone }: { title: string; detail: string; tone: 'positive' | 'warning' | 'info' }) {
  const tones = {
    positive: { border: 'border-l-emerald-500/40', text: 'text-emerald-200/90', bg: 'bg-emerald-500/[0.025]' },
    warning: { border: 'border-l-amber-500/40', text: 'text-amber-200/90', bg: 'bg-amber-500/[0.025]' },
    info: { border: 'border-l-cyan-500/40', text: 'text-cyan-200/90', bg: 'bg-cyan-500/[0.025]' },
  }
  const t = tones[tone]
  return (
    <div className={`border-l-2 ${t.border} ${t.bg} px-2.5 py-1.5`}>
      <p className={`text-[11px] font-semibold ${t.text}`}>{title}</p>
      <p className="text-[10px] text-white/55 mt-0.5 leading-relaxed">{detail}</p>
    </div>
  )
}
