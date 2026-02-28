import type { NeighborhoodMetrics } from '../types/index.ts'

interface Props {
  metrics: NeighborhoodMetrics
}

export default function DemographicsCard({ metrics }: Props) {
  const items = [
    { label: 'Active Permits', value: metrics.active_permits || 0, fmt: (v: number) => v.toString() },
    { label: 'Crime 30d', value: metrics.crime_incidents_30d || 0, fmt: (v: number) => v.toString() },
    { label: 'Avg Review', value: metrics.avg_review_rating || 0, fmt: (v: number) => v > 0 ? `${v.toFixed(1)}/5` : 'N/A' },
    { label: 'Reviews', value: metrics.review_count || 0, fmt: (v: number) => v.toString() },
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

      {metrics.risk_score > 0 && (
        <div className="mt-5 pt-4 border-t border-white/[0.06] flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/20">Overall Risk</span>
          <span className={`text-lg font-bold font-mono ${
            metrics.risk_score <= 3 ? 'text-green-400' :
            metrics.risk_score <= 6 ? 'text-yellow-400' :
            'text-red-400'
          }`}>
            {metrics.risk_score.toFixed(1)}/10
          </span>
        </div>
      )}
    </div>
  )
}
