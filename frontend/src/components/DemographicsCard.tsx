import { motion } from 'framer-motion'
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

function barGradient(value: number): string {
  if (value >= 70) return 'from-emerald-400/80 to-green-500/60'
  if (value >= 40) return 'from-amber-400/80 to-yellow-500/60'
  return 'from-red-400/80 to-rose-500/60'
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
    <div className="relative rounded-xl overflow-hidden p-[1px] bg-gradient-to-br from-neutral-700/60 via-neutral-800/40 to-neutral-900/60">
      {/* Halo */}
      <motion.div
        className="absolute w-14 h-14 rounded-full bg-blue-400/15 blur-2xl"
        animate={{
          top: ['12%', '75%', '75%', '12%', '12%'],
          left: ['80%', '80%', '15%', '15%', '80%'],
        }}
        transition={{ duration: 14, repeat: Infinity, ease: 'linear' }}
      />

      <div className="relative rounded-[11px] border border-white/[0.06] bg-gradient-to-br from-neutral-900/90 to-black/70 backdrop-blur-md p-5 overflow-hidden">
        {/* Rotating ray */}
        <motion.div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[160px] h-[30px] rounded-full bg-white/[0.03] blur-2xl pointer-events-none"
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 16, repeat: Infinity, ease: 'linear' }}
        />

        {/* Top accent line */}
        <motion.div
          className="absolute top-0 left-[10%] w-[80%] h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent"
          animate={{ opacity: [0.3, 0.6, 0.3] }}
          transition={{ duration: 6, repeat: Infinity }}
        />

        <h3 className="text-[10px] font-mono font-medium uppercase tracking-[0.15em] text-white/35 mb-4 relative z-10">
          {metrics.neighborhood} Metrics
        </h3>

        {/* Census Demographics */}
        {hasDemographics && (
          <div className="mb-5 pb-4 border-b border-white/[0.06] relative z-10">
            <div className="text-[10px] font-mono uppercase tracking-[0.12em] text-white/25 mb-3">Census Data</div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: demographics!.total_population!.toLocaleString(), label: 'Population' },
                { value: fmt$(demographics!.median_household_income || 0), label: 'Median Income' },
                { value: fmt$(demographics!.median_gross_rent || 0), label: 'Median Rent' },
                { value: `${demographics!.unemployment_rate || 0}%`, label: 'Unemployment' },
                { value: String(demographics!.median_age || 0), label: 'Median Age' },
                { value: `${demographics!.renter_pct || 0}%`, label: 'Renters' },
              ].map((item, i) => (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 hover:bg-white/[0.05] transition-colors"
                >
                  <div className="text-lg font-bold font-mono text-white/90">{item.value}</div>
                  <div className="text-[9px] font-mono uppercase tracking-[0.12em] text-white/25 mt-0.5">{item.label}</div>
                </motion.div>
              ))}
            </div>
          </div>
        )}

        {/* Activity metrics */}
        <div className="grid grid-cols-2 gap-2 mb-5 relative z-10">
          {items.map((item, i) => (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: (hasDemographics ? 6 : 0) * 0.05 + i * 0.05 }}
              className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 hover:bg-white/[0.05] transition-colors"
            >
              <div className="text-lg font-bold font-mono text-white/90">{item.fmt(item.value)}</div>
              <div className="text-[9px] font-mono uppercase tracking-[0.12em] text-white/25 mt-0.5">{item.label}</div>
            </motion.div>
          ))}
        </div>

        {/* Score bars */}
        <div className="space-y-4 relative z-10">
          {scores.map((score, i) => (
            <div key={score.label}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-mono text-white/35 uppercase tracking-[0.12em]">{score.label}</span>
                <motion.span
                  className="text-[11px] font-mono font-semibold text-white/50"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 + i * 0.1 }}
                >
                  {score.value.toFixed(1)}
                </motion.span>
              </div>
              <div className="relative w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full bg-gradient-to-r ${barGradient(score.value)}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(score.value, 100)}%` }}
                  transition={{ duration: 0.8, delay: 0.2 + i * 0.1, ease: 'easeOut' }}
                />
                <motion.div
                  className="absolute top-0 h-full w-6 bg-gradient-to-r from-transparent via-white/15 to-transparent rounded-full"
                  animate={{ left: ['-10%', `${Math.min(score.value, 100) + 5}%`] }}
                  transition={{ duration: 1.5, delay: 1 + i * 0.3, repeat: Infinity, repeatDelay: 4 }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Bottom line */}
        <motion.div
          className="absolute bottom-0 left-[10%] w-[80%] h-[1px] bg-gradient-to-r from-transparent via-white/15 to-transparent"
          animate={{ opacity: [0.4, 0.2, 0.4] }}
          transition={{ duration: 6, repeat: Infinity }}
        />
      </div>
    </div>
  )
}
