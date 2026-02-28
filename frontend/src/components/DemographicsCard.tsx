import type { NeighborhoodMetrics } from '../types/index.ts'

interface Props {
  metrics: NeighborhoodMetrics
}

export default function DemographicsCard({ metrics }: Props) {
  const items = [
    { label: 'Active Permits', value: metrics.active_permits || 0, fmt: (v: number) => v.toString() },
    { label: 'Crime (30d)', value: metrics.crime_incidents_30d || 0, fmt: (v: number) => v.toString() },
    { label: 'Avg Review', value: metrics.avg_review_rating || 0, fmt: (v: number) => v > 0 ? `${v.toFixed(1)}/5` : 'N/A' },
    { label: 'Reviews', value: metrics.review_count || 0, fmt: (v: number) => v.toString() },
  ]

  const scores = [
    { label: 'Regulatory Density', value: metrics.regulatory_density || 0, color: 'bg-red-500' },
    { label: 'Business Activity', value: metrics.business_activity || 0, color: 'bg-blue-500' },
    { label: 'Sentiment', value: metrics.sentiment || 0, color: 'bg-green-500' },
  ]

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">
        {metrics.neighborhood} Metrics
      </h3>

      {/* Key numbers */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        {items.map(item => (
          <div key={item.label} className="bg-gray-800/50 rounded-lg p-2.5">
            <div className="text-lg font-bold text-gray-100">{item.fmt(item.value)}</div>
            <div className="text-xs text-gray-500">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Score bars */}
      <div className="space-y-2.5">
        {scores.map(score => (
          <div key={score.label}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-gray-400">{score.label}</span>
              <span className="text-gray-500">{score.value.toFixed(1)}</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full ${score.color} transition-all`}
                style={{ width: `${Math.min(score.value, 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Risk score */}
      {metrics.risk_score > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-800 flex items-center justify-between">
          <span className="text-xs text-gray-400">Overall Risk Score</span>
          <span className={`text-lg font-bold ${
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
