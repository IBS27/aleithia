import { type ReactNode } from 'react'
import type { NeighborhoodData, RiskScore, UserProfile, Document, SocialTrend } from '../types/index.ts'
import { type TrendData } from '../api.ts'
import { computeInsights, LICENSE_MAP } from '../insights.ts'
import MapView from './MapView.tsx'
import CommandPanel from './CommandPanel.tsx'
import DemographicsCard from './DemographicsCard.tsx'

interface Props {
  profile: UserProfile
  neighborhoodData: NeighborhoodData | null
  riskScore: RiskScore | null
  trends: TrendData | null
  socialTrends: SocialTrend[]
  socialLoading: boolean
  socialError: string | null
  onTabChange: (tab: string) => void
}

type Signal = {
  title: string
  detail: string
}

interface Competitor {
  name: string
  type: string
  isDirect: boolean
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

export default function OverviewTab({ profile, neighborhoodData, riskScore, trends, socialTrends, socialLoading, socialError, onTabChange }: Props) {
  const insights = neighborhoodData
    ? computeInsights(neighborhoodData, profile)
    : null

  const advantages = neighborhoodData ? extractAllAdvantages(neighborhoodData, profile) : []
  const risks = neighborhoodData ? extractAllRisks(neighborhoodData, profile) : []
  const competitors = neighborhoodData ? extractCompetitors(neighborhoodData, profile) : []
  const regulatory = neighborhoodData ? extractRegulatory(neighborhoodData) : null

  return (
    <div className="space-y-4">
      {trends?.congestion.anomalies && trends.congestion.anomalies.length > 0 && (
        <div className="border border-red-500/20 bg-red-500/[0.04] px-4 py-3 flex items-center gap-3">
          <span className="text-red-400 text-xs font-mono font-bold">ALERT</span>
          <span className="text-xs text-white/50">
            {trends.congestion.anomalies.length} traffic anomal{trends.congestion.anomalies.length === 1 ? 'y' : 'ies'} detected:
            {' '}{trends.congestion.anomalies.map(a => a.road).join(', ')}
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.8fr)_minmax(340px,0.95fr)] gap-4 items-start">
        <div className="space-y-4 min-w-0">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="h-[620px] min-h-0">
              <MapView activeNeighborhood={profile.neighborhood} />
            </div>

            <div className="h-[620px] min-h-0">
              {riskScore && neighborhoodData ? (
                <CommandPanel
                  data={neighborhoodData}
                  profile={profile}
                  riskScore={riskScore}
                  onTabChange={onTabChange}
                />
              ) : (
                <div className="h-full flex items-center justify-center border border-white/[0.06] bg-white/[0.01]">
                  <span className="text-[10px] font-mono text-white/20">Loading command panel</span>
                </div>
              )}
            </div>
          </div>

          {neighborhoodData && (
            <OverviewPreviewRow
              data={neighborhoodData}
              onTabChange={onTabChange}
            />
          )}

          {neighborhoodData?.metrics && (
            <DemographicsCard metrics={neighborhoodData.metrics} demographics={neighborhoodData.demographics} horizontal />
          )}
        </div>

        <section className="space-y-4 xl:sticky xl:top-4">
          {!neighborhoodData || !insights ? (
            <InsightTile label="Intelligence Brief" accent="text-cyan-300/70" dot="bg-cyan-400/60">
              <div className="text-xs text-white/40 font-mono">Select a neighborhood to generate intelligence brief.</div>
            </InsightTile>
          ) : (
            <>
              <InsightTile
                label="Advantages"
                count={advantages.length}
                accent="text-emerald-300/70"
                dot="bg-emerald-400/60"
              >
                <div className="space-y-1.5">
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
              </InsightTile>

              <InsightTile
                label="Risks"
                count={risks.length}
                accent="text-amber-300/70"
                dot="bg-amber-400/60"
              >
                <div className="space-y-1.5">
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
              </InsightTile>

              <InsightTile
                label="Social Trends"
                count={socialTrends.length}
                accent="text-cyan-300/70"
                dot="bg-cyan-400/60"
              >
                <div className="space-y-1.5">
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
              </InsightTile>

              <InsightTile
                label="Nearby Businesses"
                count={competitors.length}
                accent="text-blue-300/70"
                dot="bg-blue-400/60"
              >
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
              </InsightTile>

              {regulatory && (
                <InsightTile
                  label="Regulatory Checklist"
                  count={regulatory.total || undefined}
                  accent="text-violet-300/70"
                  dot="bg-violet-400/60"
                >
                  <div className="space-y-2">
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
                            <div key={idx} className="flex justify-between gap-3 text-[10px]">
                              <span className="text-white/55 truncate">{i.name}</span>
                              <span className={`shrink-0 font-mono ${i.result.toLowerCase().includes('pass') ? 'text-emerald-400/70' : i.result.toLowerCase().includes('fail') ? 'text-red-400/70' : 'text-white/40'}`}>
                                {i.result}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {regulatory.permitBreakdown.length > 0 && (
                      <div className="border border-white/[0.05] bg-white/[0.01] p-2.5">
                        <p className="text-[9px] font-mono uppercase tracking-wider text-white/40 mb-1.5">Permits by Type</p>
                        <div className="space-y-0.5">
                          {regulatory.permitBreakdown.map((p) => (
                            <div key={p.type} className="flex justify-between gap-3 text-[10px]">
                              <span className="text-white/55 truncate">{p.type}</span>
                              <span className="text-white/40 font-mono shrink-0">{p.count}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

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
                </InsightTile>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}

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

  competitors.sort((a, b) => {
    if (a.isDirect !== b.isDirect) return a.isDirect ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return competitors.slice(0, 8)
}

function extractRegulatory(data: NeighborhoodData): RegulatorySummary {
  const stats = data.inspection_stats
  const passRate = stats.total > 0 ? Math.round((stats.passed / stats.total) * 100) : 0

  const recentInspections: RegulatoryItem[] = data.inspections
    .slice(0, 5)
    .map(i => {
      const raw = i.metadata?.raw_record as Record<string, unknown> | undefined
      return {
        name: (raw?.dba_name as string) || i.title || 'Unknown',
        result: (raw?.results as string) || 'N/A',
      }
    })

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

interface PreviewRowProps {
  data: NeighborhoodData
  onTabChange: (tab: string) => void
}

function OverviewPreviewRow({ data, onTabChange }: PreviewRowProps) {
  const newsItems = [
    ...(data.news || []).map((item) => ({
      title: item.title,
      meta: item.source || 'news',
    })),
    ...(data.politics || []).map((item) => ({
      title: item.title,
      meta: (item.metadata?.matter_type as string) || 'policy',
    })),
    ...(data.federal_register || []).map((item) => ({
      title: item.title,
      meta: (item.metadata?.agency as string) || 'federal',
    })),
  ].slice(0, 3)
  const communityItems = [...(data.reddit || []), ...(data.tiktok || [])].slice(0, 3)
  const marketItems = [
    ...(data.reviews || []).map((review) => ({
      title: review.title,
      meta: review.metadata?.rating ? `${review.metadata.rating}/5 · ${review.metadata.review_count || 0} reviews` : 'review',
    })),
    ...(data.realestate || []).map((listing) => ({
      title: listing.title,
      meta: [
        listing.metadata?.listing_type as string | undefined,
        listing.metadata?.price as string | undefined,
      ].filter(Boolean).join(' · ') || 'listing',
    })),
  ].slice(0, 3)
  const hasAny = newsItems.length > 0 || communityItems.length > 0 || marketItems.length > 0
  if (!hasAny) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <PreviewPanel
        title="Local Intelligence"
        accent="text-blue-300/70"
        dot="bg-blue-400/70"
        count={(data.news?.length || 0) + (data.politics?.length || 0) + (data.federal_register?.length || 0)}
        onClick={() => onTabChange('intel')}
        items={newsItems}
        emptyMsg="No recent news signals"
      />
      <PreviewPanel
        title="Community Pulse"
        accent="text-green-300/70"
        dot="bg-green-400/70"
        count={(data.reddit?.length || 0) + (data.tiktok?.length || 0)}
        onClick={() => onTabChange('community')}
        items={communityItems.map(c => ({
          title: c.title,
          meta: (c.metadata?.subreddit as string) ? `r/${c.metadata?.subreddit}` : (c.metadata?.creator as string) ? `@${c.metadata?.creator}` : 'social',
        }))}
        emptyMsg="No community chatter"
      />
      <PreviewPanel
        title="Market Snapshot"
        accent="text-cyan-300/70"
        dot="bg-cyan-400/70"
        count={(data.reviews?.length || 0) + (data.realestate?.length || 0)}
        onClick={() => onTabChange('market')}
        items={marketItems}
        emptyMsg="No market data"
      />
    </div>
  )
}

interface PreviewPanelProps {
  title: string
  accent: string
  dot: string
  count: number
  onClick: () => void
  items: Array<{ title: string; meta: string }>
  emptyMsg: string
}

function PreviewPanel({ title, accent, dot, count, onClick, items, emptyMsg }: PreviewPanelProps) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col text-left border border-white/[0.06] bg-white/[0.01] hover:border-white/[0.12] hover:bg-white/[0.02] transition-all cursor-pointer group"
    >
      <div className="flex h-8 items-center justify-between px-4 border-b border-white/[0.04]">
        <div className="flex items-center gap-2">
          <span className={`w-1 h-1 rounded-full ${dot}`} />
          <span className={`text-[10px] font-mono uppercase tracking-wider leading-none ${accent}`}>{title}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-white/25 leading-none">{count}</span>
          <span className="text-[10px] text-white/25 leading-none group-hover:text-white/60 transition-colors">›</span>
        </div>
      </div>
      <div className="p-3 space-y-2 min-h-[130px]">
        {items.length > 0 ? items.map((item, i) => (
          <div key={i} className="text-[11px] leading-snug">
            <div className="text-white/75 line-clamp-2 group-hover:text-white/90 transition-colors">{item.title}</div>
            <div className="text-[9px] font-mono uppercase tracking-wider text-white/25 mt-0.5">{item.meta}</div>
          </div>
        )) : (
          <div className="text-[10px] font-mono text-white/20 flex items-center justify-center h-full">{emptyMsg}</div>
        )}
      </div>
    </button>
  )
}

function InsightTile({
  label,
  count,
  accent,
  dot,
  children,
}: {
  label: string
  count?: number
  accent: string
  dot?: string
  children: ReactNode
}) {
  return (
    <div className="border border-white/[0.06] bg-white/[0.01]">
      <div className="flex h-8 items-center justify-between px-4 border-b border-white/[0.04]">
        <div className="flex items-center gap-2 min-w-0">
          {dot && <span className={`w-1 h-1 rounded-full ${dot}`} />}
          <span className={`text-[10px] font-mono uppercase tracking-wider leading-none ${accent}`}>{label}</span>
        </div>
        {count !== undefined && count > 0 && (
          <span className="text-[10px] font-mono text-white/25 leading-none">{count}</span>
        )}
      </div>
      <div className="p-3">
        {children}
      </div>
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
