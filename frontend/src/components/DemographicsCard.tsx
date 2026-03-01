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
}

function fmt$(v: number): string {
  if (v >= 1000) return `$${Math.round(v / 1000)}K`
  return `$${v}`
}

export default function DemographicsCard({ metrics, demographics }: Props) {
  const hasDemographics = demographics && demographics.total_population && demographics.total_population > 0

  const items = [
    { label: 'Active Permits', value: metrics.active_permits || 0, fmt: (v: number) => v.toString() },
    { label: 'Crime 30d', value: metrics.crime_incidents_30d || 0, fmt: (v: number) => v.toString() },
    { label: 'Avg Review', value: metrics.avg_review_rating || 0, fmt: (v: number) => v > 0 ? `${v.toFixed(1)}/5` : 'N/A' },
    { label: 'Reviews', value: metrics.review_count || 0, fmt: (v: number) => v > 0 ? v.toString() : 'N/A' },
  ]

  const scores = [
    { label: 'Regulatory Density', value: metrics.regulatory_density || 0 },
    { label: 'Business Activity', value: metrics.business_activity || 0 },
    { label: 'Sentiment', value: metrics.sentiment || 0 },
  ]

  return (
    <div className="border border-white/[0.06] bg-white/[0.01] p-5">
      <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30 mb-4">
        {metrics.neighborhood} Metrics
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
              <div className="text-lg font-bold font-mono text-white">{fmt$(demographics!.median_household_income || 0)}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Median Income</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{fmt$(demographics!.median_gross_rent || 0)}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Median Rent</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.unemployment_rate || 0}%</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Unemployment</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.median_age || 0}</div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mt-0.5">Median Age</div>
            </div>
            <div className="bg-white/[0.02] border border-white/[0.04] p-3">
              <div className="text-lg font-bold font-mono text-white">{demographics!.renter_pct || 0}%</div>
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
