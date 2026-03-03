import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { RiskScore } from '../types/index.ts'

interface Props {
  score: RiskScore
}

const severityColors = {
  low: 'text-green-400/80 border-green-500/30 bg-green-500/[0.06]',
  medium: 'text-yellow-400/80 border-yellow-500/30 bg-yellow-500/[0.06]',
  high: 'text-red-400/80 border-red-500/30 bg-red-500/[0.06]',
}

function scoreColor(score: number) {
  if (score <= 3) return { text: 'from-green-300 via-green-400 to-emerald-300', glow: 'rgba(74, 222, 128, 0.25)', halo: 'bg-green-400/20', bar: 'from-green-500 to-emerald-400', ring: 'border-green-500/30' }
  if (score <= 6) return { text: 'from-amber-200 via-yellow-400 to-orange-300', glow: 'rgba(250, 204, 21, 0.25)', halo: 'bg-yellow-400/20', bar: 'from-yellow-500 to-amber-400', ring: 'border-yellow-500/30' }
  return { text: 'from-red-300 via-red-400 to-rose-300', glow: 'rgba(248, 113, 113, 0.25)', halo: 'bg-red-400/20', bar: 'from-red-500 to-rose-400', ring: 'border-red-500/30' }
}

function severityBarColor(severity: 'low' | 'medium' | 'high') {
  if (severity === 'low') return 'from-green-500/80 to-emerald-400/60'
  if (severity === 'medium') return 'from-yellow-500/80 to-amber-400/60'
  return 'from-red-500/80 to-rose-400/60'
}

export default function RiskCard({ score }: Props) {
  const [expanded, setExpanded] = useState(false)
  const colors = scoreColor(score.overall_score)

  return (
    <div className="relative rounded-xl overflow-hidden p-[1px] bg-gradient-to-br from-neutral-700/60 via-neutral-800/40 to-neutral-900/60">
      {/* Animated halo */}
      <motion.div
        className={`absolute w-16 h-16 rounded-full ${colors.halo} blur-2xl`}
        animate={{
          top: ['8%', '8%', '70%', '70%', '8%'],
          left: ['10%', '85%', '85%', '10%', '10%'],
        }}
        transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
      />

      {/* Inner card */}
      <div className="relative rounded-[11px] border border-white/[0.06] bg-gradient-to-br from-neutral-900/90 to-black/70 backdrop-blur-md overflow-hidden">
        {/* Rotating ray */}
        <motion.div
          className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[180px] h-[40px] rounded-full bg-white/[0.04] blur-2xl pointer-events-none"
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 14, repeat: Infinity, ease: 'linear' }}
        />

        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full p-6 text-left cursor-pointer relative z-10"
        >
          {/* Header row */}
          <div className="flex items-start justify-between mb-5">
            <div>
              <h3 className="text-base font-semibold text-white/90 tracking-tight">{score.neighborhood}</h3>
              <p className="text-[10px] font-mono uppercase tracking-[0.15em] text-white/30 mt-1">{score.business_type}</p>
            </div>

            {/* Score display */}
            <div className="text-right">
              <motion.div
                className={`text-4xl font-extrabold font-mono bg-gradient-to-r ${colors.text} bg-clip-text text-transparent`}
                animate={{
                  filter: [
                    `drop-shadow(0 0 8px ${colors.glow})`,
                    `drop-shadow(0 0 2px ${colors.glow.replace('0.25', '0.1')})`,
                    `drop-shadow(0 0 8px ${colors.glow})`,
                  ],
                }}
                transition={{ duration: 3, repeat: Infinity }}
              >
                {score.overall_score.toFixed(1)}
              </motion.div>
              <div className="text-[10px] font-mono text-white/25 mt-0.5 tracking-wider">/10 RISK</div>
            </div>
          </div>

          {/* Risk bar */}
          <div className="relative w-full h-1.5 bg-white/[0.06] rounded-full overflow-hidden mb-4">
            <motion.div
              className={`h-full rounded-full bg-gradient-to-r ${colors.bar}`}
              initial={{ width: 0 }}
              animate={{ width: `${score.overall_score * 10}%` }}
              transition={{ duration: 1, ease: 'easeOut' }}
            />
            <motion.div
              className="absolute top-0 h-full w-8 bg-gradient-to-r from-transparent via-white/20 to-transparent rounded-full"
              animate={{ left: ['-10%', `${score.overall_score * 10 + 5}%`] }}
              transition={{ duration: 2, repeat: Infinity, repeatDelay: 3 }}
            />
          </div>

          {/* Summary */}
          <p className="text-[11px] text-white/40 leading-relaxed">{score.summary}</p>

          {/* Meta row */}
          <div className="flex items-center mt-4 gap-4">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
              <span className="text-[10px] font-mono text-white/25">CONF {(score.confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
              <span className="text-[10px] font-mono text-white/25">{score.factors.length} FACTORS</span>
            </div>
            <span className="ml-auto text-[10px] font-mono text-white/20 uppercase tracking-wider">
              {expanded ? '− collapse' : '+ expand'}
            </span>
          </div>
        </button>

        {/* Animated top line */}
        <motion.div
          className="absolute top-0 left-[10%] w-[80%] h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent"
          animate={{ opacity: [0.3, 0.7, 0.3] }}
          transition={{ duration: 5, repeat: Infinity }}
        />

        {/* Expanded factors */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="overflow-hidden"
            >
              <div className="px-6 pb-6 space-y-3 border-t border-white/[0.06] pt-5 relative z-10">
                {score.factors.map((factor, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.06 }}
                    className="flex items-start gap-3 group"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-[9px] font-mono uppercase px-2 py-0.5 rounded border ${severityColors[factor.severity]}`}>
                          {factor.severity}
                        </span>
                        <span className="text-[9px] font-mono text-white/15">{factor.source}</span>
                      </div>
                      <p className="text-xs text-white/55 group-hover:text-white/70 transition-colors">{factor.label}</p>
                      <p className="text-[10px] text-white/20 mt-0.5 leading-relaxed">{factor.description}</p>
                    </div>
                    <div className="text-right shrink-0 pt-0.5">
                      <div className="text-xs font-mono font-semibold text-white/40">{factor.pct}%</div>
                      <div className="w-16 h-1.5 bg-white/[0.06] rounded-full mt-1 overflow-hidden">
                        <motion.div
                          className={`h-full rounded-full bg-gradient-to-r ${severityBarColor(factor.severity)}`}
                          initial={{ width: 0 }}
                          animate={{ width: `${factor.pct}%` }}
                          transition={{ duration: 0.6, delay: i * 0.06 }}
                        />
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Bottom line */}
        <motion.div
          className="absolute bottom-0 left-[10%] w-[80%] h-[1px] bg-gradient-to-r from-transparent via-white/15 to-transparent"
          animate={{ opacity: [0.5, 0.2, 0.5] }}
          transition={{ duration: 5, repeat: Infinity }}
        />
      </div>
    </div>
  )
}
