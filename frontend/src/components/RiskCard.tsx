import { useState } from 'react'
import type { RiskScore } from '../types/index.ts'

interface Props {
  score: RiskScore
  borderless?: boolean
}

const severityColors = {
  low: 'text-green-400/80 border-green-500/20',
  medium: 'text-yellow-400/80 border-yellow-500/20',
  high: 'text-red-400/80 border-red-500/20',
}

function scoreColor(score: number): string {
  if (score <= 3) return 'text-green-400'
  if (score <= 6) return 'text-yellow-400'
  return 'text-red-400'
}

function scoreBg(score: number): string {
  if (score <= 3) return 'bg-green-500'
  if (score <= 6) return 'bg-yellow-500'
  return 'bg-red-500'
}

export default function RiskCard({ score, borderless }: Props) {
  const [expanded, setExpanded] = useState(false)

  const glowStyle = score.overall_score <= 3 ? '0 0 12px rgba(41, 166, 52, 0.15)' : score.overall_score <= 6 ? '0 0 12px rgba(217, 158, 11, 0.15)' : '0 0 12px rgba(219, 55, 55, 0.15)'
  return (
    <div
      className={borderless ? 'overflow-hidden shrink-0' : 'border border-white/[0.06] bg-white/[0.01] overflow-hidden'}
      style={borderless ? undefined : { boxShadow: glowStyle }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full text-left hover:bg-white/[0.02] transition-colors cursor-pointer ${borderless ? 'px-5 py-3' : 'p-5'}`}
      >
        <div className={`flex items-center justify-between ${borderless ? 'mb-2' : 'mb-4'}`}>
          <div>
            <h3 className="text-sm font-semibold text-white">{score.neighborhood}</h3>
            <p className="text-[10px] font-mono uppercase tracking-wider text-white/25 mt-0.5">{score.business_type}</p>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-bold font-mono ${scoreColor(score.overall_score)}`}>
              {score.overall_score.toFixed(1)}
            </div>
            <div className="text-[10px] font-mono text-white/20">/10 RISK SCORE</div>
            <div className="text-[9px] font-mono text-white/15">Lower is better</div>
          </div>
        </div>

        <div className={`w-full bg-white/[0.06] h-1 ${borderless ? 'mb-2' : 'mb-4'}`}>
          <div
            className={`h-1 ${scoreBg(score.overall_score)} transition-all`}
            style={{ width: `${score.overall_score * 10}%` }}
          />
        </div>

        <p className="text-xs text-white/35 leading-relaxed">{score.summary}</p>

        <div className={`flex items-center text-[10px] font-mono text-white/20 ${borderless ? 'mt-2' : 'mt-4'}`}>
          <span>CONFIDENCE {(score.confidence * 100).toFixed(0)}%</span>
          <span className="mx-2 text-white/10">|</span>
          <span>{score.factors.length} RISK FACTORS</span>
          <span className="ml-auto uppercase">{expanded ? 'collapse' : 'expand'}</span>
        </div>
      </button>

      {borderless && !expanded && <div className="mx-5 border-b border-white/[0.06]" />}

      {expanded && (
        <div className="px-5 pb-5 space-y-3 border-t border-white/[0.06] pt-4">
          {score.factors.map((factor, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${severityColors[factor.severity]}`}>
                    {factor.severity}
                  </span>
                  <span className="text-[10px] font-mono text-white/15">{factor.source}</span>
                </div>
                <p className="text-xs text-white/60">{factor.label}</p>
                <p className="text-[10px] text-white/25 mt-0.5">{factor.description}</p>
              </div>
              <div className="text-right shrink-0">
                <div className="text-xs font-mono font-semibold text-white/50">{factor.pct}%</div>
                <div className="w-16 bg-white/[0.06] h-1 mt-1">
                  <div
                    className={`h-1 ${scoreBg(factor.pct / 10)}`}
                    style={{ width: `${factor.pct}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
