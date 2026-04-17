import type { NeighborhoodMetrics } from '../types/index.ts'

interface Demographics {
  total_population?: number
  median_household_income?: number
  median_home_value?: number
  median_gross_rent?: number
  unemployment_rate?: number
  median_age?: number
  total_housing_units?: number
  renter_pct?: number
  bachelors_degree?: number
  masters_degree?: number
  tracts_counted?: number
}

interface Props {
  metrics: NeighborhoodMetrics
  demographics?: Demographics | null
  horizontal?: boolean
}

function fmt$(v: number): string {
  if (v >= 1000) return `$${Math.round(v / 1000)}K`
  return `$${v}`
}

export default function DemographicsCard({ metrics, demographics, horizontal }: Props) {
  const hasDemographics = demographics && demographics.total_population && demographics.total_population > 0

  const items = [
    { label: 'Active Permits', value: metrics.active_permits || 0, fmt: (v: number) => v.toString() },
    { label: 'Crimes (30 Days)', value: metrics.crime_incidents_30d || 0, fmt: (v: number) => v.toString() },
    { label: 'Avg Review', value: metrics.avg_review_rating || 0, fmt: (v: number) => v > 0 ? `${v.toFixed(1)}/5` : 'N/A' },
    { label: 'Reviews', value: metrics.review_count || 0, fmt: (v: number) => v > 0 ? v.toString() : 'N/A' },
  ]

  const scores = [
    { label: 'Regulatory Score', value: metrics.regulatory_density || 0 },
    { label: 'Business Activity', value: metrics.business_activity || 0 },
    { label: 'Overall Sentiment', value: metrics.sentiment || 0 },
  ]

  if (horizontal) {
    const hasDemo = demographics && demographics.total_population && demographics.total_population > 0

    // Primary decision-relevant values — ordered by the refactor brief:
    // population → income → rent → permits → reviews → transit/sentiment
    const primaryStats: { label: string; value: string; accent?: string }[] = []
    if (hasDemo) {
      primaryStats.push({ label: 'Pop', value: demographics!.total_population!.toLocaleString() })
      if (demographics!.median_household_income) {
        primaryStats.push({ label: 'Income', value: fmt$(demographics!.median_household_income) })
      }
      if (demographics!.median_gross_rent) {
        primaryStats.push({ label: 'Rent', value: fmt$(demographics!.median_gross_rent) })
      }
    }
    primaryStats.push({ label: 'Permits', value: (metrics.active_permits || 0).toString() })
    if (metrics.review_count) {
      primaryStats.push({ label: 'Reviews', value: metrics.review_count.toString() })
    }
    if (metrics.avg_review_rating) {
      primaryStats.push({
        label: 'Rating',
        value: `${metrics.avg_review_rating.toFixed(1)}★`,
        accent: metrics.avg_review_rating >= 4 ? 'text-emerald-400' : metrics.avg_review_rating >= 3 ? 'text-amber-400' : 'text-red-400',
      })
    }
    if (metrics.crime_incidents_30d !== undefined) {
      primaryStats.push({ label: 'Crime 30d', value: metrics.crime_incidents_30d.toString() })
    }

    // Secondary demographic values
    const secondaryStats = hasDemo ? [
      { label: 'Age', value: `${demographics!.median_age || 0}` },
      { label: 'Unemp', value: `${demographics!.unemployment_rate || 0}%` },
      { label: 'Renters', value: `${demographics!.renter_pct || 0}%` },
    ] : []

    return (
      <div className="border border-white/[0.06] bg-white/[0.01]">
        {/* Ribbon header */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.04]">
          <div className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-white/30" />
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-white/35">
              {metrics.neighborhood} Tactical Stats
            </span>
          </div>
          <div className="hidden md:flex items-center gap-4">
            {scores.map(score => {
              const colorClass = score.value >= 65 ? 'text-emerald-400' : score.value >= 40 ? 'text-amber-400' : 'text-red-400'
              const barClass = score.value >= 65 ? 'bg-emerald-400' : score.value >= 40 ? 'bg-amber-400' : 'bg-red-400'
              return (
                <div key={score.label} className="flex items-center gap-2">
                  <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">{score.label.replace(' Score', '').replace('Overall ', '')}</span>
                  <div className="w-14 bg-white/[0.05] h-1">
                    <div className={`h-1 ${barClass} transition-all`} style={{ width: `${Math.min(score.value, 100)}%` }} />
                  </div>
                  <span className={`text-[10px] font-mono font-semibold ${colorClass} w-7 text-right`}>{score.value.toFixed(0)}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Primary stats — decision-relevant first */}
        <div className="grid grid-cols-4 md:grid-cols-7 divide-x divide-white/[0.04]">
          {primaryStats.map(stat => (
            <div key={stat.label} className="px-3 py-2.5">
              <div className={`text-sm font-bold font-mono leading-tight ${stat.accent || 'text-white'}`}>{stat.value}</div>
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Secondary stats row - shown only if demographics present */}
        {secondaryStats.length > 0 && (
          <div className="border-t border-white/[0.04] px-4 py-1.5 flex items-center gap-5">
            <span className="text-[9px] font-mono uppercase tracking-wider text-white/20">Census</span>
            {secondaryStats.map(s => (
              <div key={s.label} className="flex items-center gap-1.5">
                <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">{s.label}</span>
                <span className="text-[10px] font-mono text-white/55">{s.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="border border-white/[0.06] bg-white/[0.01] p-5">
      <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30 mb-4">
        {metrics.neighborhood} Key Stats
      </h3>

      {/* Census Demographics */}
      {hasDemographics && (
        <div className="mb-5 pb-4 border-b border-white/[0.06]">
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mb-3">Census Data</div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.total_population!.toLocaleString()}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Population</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.median_household_income ? fmt$(demographics!.median_household_income) : '\u2014'}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Median Income</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.median_gross_rent ? fmt$(demographics!.median_gross_rent) : '\u2014'}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Median Rent</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.unemployment_rate ? `${demographics!.unemployment_rate}%` : '\u2014'}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Unemployment</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.median_age ? String(demographics!.median_age) : '\u2014'}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Median Age</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.renter_pct ? `${demographics!.renter_pct}%` : '\u2014'}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Renters</div>
            </div>
          </div>
        </div>
      )}

      {/* Activity metrics */}
      <div className="grid grid-cols-2 gap-2 mb-5">
        {items.map(item => (
          <div key={item.label} className="bg-white/[0.02] border border-white/[0.04] p-3">
            <div className="text-lg font-bold font-mono text-white">{item.fmt(item.value)}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        {scores.map(score => (
          <div key={score.label}>
            <div className="flex items-center justify-between text-[10px] font-mono mb-1">
              <span className="text-white/30 uppercase tracking-wider">{score.label}</span>
              <span className="text-white/20">{score.value.toFixed(1)}</span>
            </div>
            <div className="w-full bg-white/[0.04] h-1">
              <div
                className="h-1 bg-white/40 transition-all"
                style={{ width: `${Math.min(score.value, 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>

    </div>
  )
}
