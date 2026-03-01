import { useState, useEffect } from 'react'
import type { StreetscapeData, VisionAssessData } from '../types/index.ts'
import { api } from '../api.ts'

interface Props {
  neighborhood: string
}

const INDICATOR_COLORS: Record<string, string> = {
  low: 'border-green-500/30 text-green-400/80 bg-green-500/[0.06]',
  moderate: 'border-amber-500/30 text-amber-400/80 bg-amber-500/[0.06]',
  high: 'border-red-500/30 text-red-400/80 bg-red-500/[0.06]',
  active: 'border-blue-500/30 text-blue-400/80 bg-blue-500/[0.06]',
  stable: 'border-white/10 text-white/40 bg-white/[0.03]',
}

export default function StreetscapeCard({ neighborhood }: Props) {
  const [data, setData] = useState<StreetscapeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [assess, setAssess] = useState<VisionAssessData | null>(null)
  const [assessLoading, setAssessLoading] = useState(false)
  const [assessError, setAssessError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setAssess(null)
    setAssessError(null)
    api.streetscape(neighborhood)
      .then(d => setData(d.counts ? d as StreetscapeData : null))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [neighborhood])

  if (loading) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.02] p-4">
        <div className="text-[10px] font-mono text-white/20">Loading streetscape data...</div>
      </div>
    )
  }

  if (!data) return null

  const { counts, indicators } = data

  const countGrid = [
    { label: 'Open storefronts', value: counts.storefront_open, color: 'text-green-400/70' },
    { label: 'Closed storefronts', value: counts.storefront_closed, color: 'text-red-400/70' },
    { label: 'For-lease signs', value: counts.for_lease_sign, color: 'text-amber-400/70' },
    { label: 'Restaurant signage', value: counts.restaurant_signage, color: 'text-blue-400/70' },
    { label: 'Outdoor dining', value: counts.outdoor_dining, color: 'text-cyan-400/70' },
    { label: 'Construction', value: counts.construction, color: 'text-purple-400/70' },
  ]

  return (
    <div className="border border-white/[0.06] bg-white/[0.02] p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">
          Streetscape Intelligence
        </h3>
        <span className="text-[9px] font-mono text-white/20">
          {data.analysis_count} frame{data.analysis_count !== 1 ? 's' : ''} analyzed
        </span>
      </div>

      {/* Indicator badges */}
      <div className="flex gap-2 mb-4">
        <span className={`text-[10px] font-mono px-2 py-1 border ${INDICATOR_COLORS[indicators.vacancy_signal]}`}>
          Vacancy: {indicators.vacancy_signal}
        </span>
        <span className={`text-[10px] font-mono px-2 py-1 border ${INDICATOR_COLORS[indicators.dining_saturation]}`}>
          Dining: {indicators.dining_saturation}
        </span>
        <span className={`text-[10px] font-mono px-2 py-1 border ${INDICATOR_COLORS[indicators.growth_signal]}`}>
          Growth: {indicators.growth_signal}
        </span>
      </div>

      {/* Count grid */}
      <div className="grid grid-cols-3 gap-3">
        {countGrid.map(item => (
          <div key={item.label}>
            <div className={`text-lg font-bold font-mono ${item.color}`}>{item.value}</div>
            <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* AI Assessment */}
      {!assess && (
        <button
          onClick={() => {
            setAssessLoading(true)
            setAssessError(null)
            api.visionAssess(neighborhood)
              .then(d => setAssess(d))
              .catch(e => setAssessError(e instanceof Error ? e.message : 'Assessment failed'))
              .finally(() => setAssessLoading(false))
          }}
          disabled={assessLoading}
          className="mt-4 w-full text-[10px] font-mono uppercase tracking-wider border border-white/10 px-3 py-2 text-white/40 hover:text-white/70 hover:border-white/25 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors"
        >
          {assessLoading ? 'Analyzing...' : 'Get AI Assessment'}
        </button>
      )}
      {assessError && (
        <p className="mt-2 text-[10px] text-red-400/70 font-mono">{assessError}</p>
      )}
      {assess && (
        <div className="mt-4 space-y-3 border-t border-white/[0.06] pt-4">
          <div className="flex items-center justify-between">
            <h4 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">AI Assessment</h4>
            <span className="text-[9px] font-mono text-white/15">{assess.frame_count} frames • {assess.model}</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="border border-white/[0.06] bg-white/[0.02] p-2.5">
              <p className="text-[9px] font-mono uppercase tracking-wider text-white/30 mb-1">Storefront Viability</p>
              <p className="text-sm font-bold text-white/80">{assess.assessment.storefront_viability.score}/10</p>
              <p className="text-[10px] text-white/40 mt-0.5">{assess.assessment.storefront_viability.condition}</p>
            </div>
            <div className="border border-white/[0.06] bg-white/[0.02] p-2.5">
              <p className="text-[9px] font-mono uppercase tracking-wider text-white/30 mb-1">Pedestrian Activity</p>
              <p className="text-sm font-bold text-white/80 capitalize">{assess.assessment.pedestrian_activity.level}</p>
              <p className="text-[10px] text-white/40 mt-0.5">{assess.assessment.pedestrian_activity.demographics}</p>
            </div>
          </div>
          <div className="border border-white/[0.06] bg-white/[0.02] p-2.5">
            <p className="text-[9px] font-mono uppercase tracking-wider text-white/30 mb-1">Infrastructure</p>
            <div className="space-y-1 text-[10px] text-white/50">
              <p>Transit: {assess.assessment.infrastructure.transit_access}</p>
              <p>Parking: {assess.assessment.infrastructure.parking}</p>
            </div>
          </div>
          <div className="border border-emerald-500/10 bg-emerald-500/[0.03] p-2.5">
            <p className="text-[9px] font-mono uppercase tracking-wider text-emerald-300/50 mb-1">Recommendation</p>
            <p className="text-[10px] text-white/60 leading-relaxed">{assess.assessment.overall_recommendation}</p>
          </div>
        </div>
      )}
    </div>
  )
}
