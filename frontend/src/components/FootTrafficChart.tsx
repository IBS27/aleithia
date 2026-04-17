import { useState, useEffect } from 'react'
import type { CCTVTimeseries } from '../types/index.ts'
import { api } from '../api.ts'

interface Props {
  neighborhood: string
  embedded?: boolean
}

function formatHour(h: number): string {
  if (h === 0) return '12a'
  if (h < 12) return `${h}a`
  if (h === 12) return '12p'
  return `${h - 12}p`
}

export default function FootTrafficChart({ neighborhood, embedded }: Props) {
  const [data, setData] = useState<CCTVTimeseries | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.cctvTimeseries(neighborhood)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [neighborhood])

  if (loading) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.02] p-4">
        <div className="text-[10px] font-mono text-white/20">Loading highway traffic timeseries...</div>
      </div>
    )
  }

  if (!data || data.hours.length === 0 || data.camera_count === 0) return null

  const values = data.hours.map((h) => h.avg_pedestrians + h.avg_vehicles)
  const mean = values.reduce((a, b) => a + b, 0) / values.length
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length
  const std = Math.sqrt(variance) || 1
  const threshold2sigma = mean + 2 * std

  const maxPed = Math.max(...data.hours.map((h) => h.avg_pedestrians), 1)
  const hasSamples = data.hours.some((h) => h.sample_count > 0)
  if (!hasSamples) return null

  const wrapClass = embedded ? 'p-4' : 'border border-white/[0.06] bg-white/[0.02] p-5'
  return (
    <div className={wrapClass}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">
          Highway Traffic — 24h Pattern
        </h3>
        <span className="text-[9px] font-mono text-white/20">
          {data.camera_count} camera{data.camera_count !== 1 ? 's' : ''} · Chicago time
        </span>
      </div>

      {/* Bar chart — 2σ anomaly highlighting in amber */}
      <div className="flex items-end gap-px h-24">
        {data.hours.map((bucket) => {
          const pct = maxPed > 0 ? (bucket.avg_pedestrians / maxPed) * 100 : 0
          const isPeak = bucket.hour === data.peak_hour && bucket.sample_count > 0
          const totalActivity = bucket.avg_pedestrians + bucket.avg_vehicles
          const isAnomaly = totalActivity > threshold2sigma
          const color = isAnomaly
            ? 'bg-amber-500/80 ring-1 ring-amber-400/50'
            : bucket.density === 'high'
              ? 'bg-green-500/70'
              : bucket.density === 'medium'
                ? 'bg-amber-500/70'
                : 'bg-white/10'

          return (
            <div
              key={bucket.hour}
              className="flex-1 flex flex-col items-center justify-end h-full group relative"
            >
              {/* Tooltip */}
              <div className="absolute bottom-full mb-1 hidden group-hover:block z-10 pointer-events-none">
                <div className={`bg-black/90 px-2 py-1 text-[9px] font-mono whitespace-nowrap border ${
                  isAnomaly ? 'border-amber-500/50 text-amber-200' : 'border-white/10 text-white/70'
                }`}>
                  {formatHour(bucket.hour)}: {bucket.avg_vehicles} veh, {bucket.avg_pedestrians} ped
                  {isAnomaly && ' · 2σ anomaly'}
                  {bucket.sample_count > 0 ? ` (${bucket.sample_count} samples)` : ''}
                </div>
              </div>
              <div
                className={`w-full rounded-t-sm transition-all ${color} ${isPeak ? 'ring-1 ring-white/40' : ''}`}
                style={{ height: `${Math.max(pct, 2)}%` }}
              />
            </div>
          )
        })}
      </div>

      {/* Hour labels — show every 3rd */}
      <div className="flex gap-px mt-1">
        {data.hours.map(bucket => (
          <div key={bucket.hour} className="flex-1 text-center">
            {bucket.hour % 3 === 0 && (
              <span className="text-[8px] font-mono text-white/15">{formatHour(bucket.hour)}</span>
            )}
          </div>
        ))}
      </div>

      {/* Peak summary */}
      {data.peak_pedestrians > 0 && (
        <div className="mt-3 pt-3 border-t border-white/[0.04] text-[10px] font-mono text-white/40">
          Peak: {formatHour(data.peak_hour)}–{formatHour((data.peak_hour + 2) % 24)} (avg {data.peak_pedestrians} detections/hr)
        </div>
      )}
    </div>
  )
}
