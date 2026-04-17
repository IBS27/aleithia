import { useState, useEffect, useMemo } from 'react'
import type { NeighborhoodData, UserProfile, RiskScore, RiskProfile, CategoryScore, StreetscapeData } from '../types/index.ts'
import { computeInsights } from '../insights.ts'
import { api } from '../api.ts'

interface Props {
  data: NeighborhoodData
  profile: UserProfile
  riskScore: RiskScore
  onTabChange?: (tab: string) => void
}

const CATEGORY_TAB_MAP: Record<string, string> = {
  regulatory: 'regulatory',
  economic: 'regulatory',
  market: 'market',
  demographic: 'overview',
  safety: 'vision',
  community: 'community',
}

const PROFILES: { key: RiskProfile; label: string; desc: string }[] = [
  { key: 'conservative', label: 'Conservative', desc: 'Weighs regulatory compliance & safety highest' },
  { key: 'growth', label: 'Growth', desc: 'Weighs economic & market signals highest' },
  { key: 'budget', label: 'Budget', desc: 'Weighs affordability & community highest' },
]

function riskColor(score: number): string {
  if (score <= 3) return 'text-emerald-400'
  if (score <= 6) return 'text-amber-400'
  return 'text-red-400'
}

function riskTint(score: number): string {
  if (score <= 3) return 'from-emerald-500/[0.08] border-emerald-500/25'
  if (score <= 6) return 'from-amber-500/[0.08] border-amber-500/25'
  return 'from-red-500/[0.08] border-red-500/25'
}

function oppColor(score: number): string {
  if (score >= 65) return 'text-emerald-400'
  if (score >= 40) return 'text-amber-400'
  return 'text-red-400'
}

function oppTint(score: number): string {
  if (score >= 65) return 'from-emerald-500/[0.08] border-emerald-500/25'
  if (score >= 40) return 'from-amber-500/[0.08] border-amber-500/25'
  return 'from-red-500/[0.08] border-red-500/25'
}

function signalTint(signal: string): string {
  if (signal === 'positive') return 'bg-emerald-400/80'
  if (signal === 'neutral') return 'bg-amber-400/80'
  return 'bg-red-400/80'
}

function signalText(signal: string): string {
  if (signal === 'positive') return 'text-emerald-400/80'
  if (signal === 'neutral') return 'text-amber-400/80'
  return 'text-red-400/80'
}

function signalGlyph(signal: string): string {
  if (signal === 'positive') return '▲'
  if (signal === 'neutral') return '●'
  return '▼'
}

function CategoryBar({ cat, onViewAll }: { cat: CategoryScore; onViewAll?: () => void }) {
  return (
    <div className="group">
      <button
        type="button"
        onClick={onViewAll}
        disabled={!onViewAll}
        className="w-full flex items-center gap-2 py-1.5 px-0 disabled:cursor-default enabled:cursor-pointer enabled:hover:bg-white/[0.015] transition-colors text-left"
      >
        <span className={`text-[9px] font-mono ${signalText(cat.signal)} w-3 shrink-0`}>
          {signalGlyph(cat.signal)}
        </span>
        <span className="text-[11px] font-medium text-white/65 w-28 shrink-0 truncate">{cat.name}</span>
        <div className="flex-1 h-1 bg-white/[0.05] overflow-hidden">
          <div className={`h-full transition-all duration-500 ${signalTint(cat.signal)}`} style={{ width: `${cat.score}%` }} />
        </div>
        <span className="text-[10px] font-mono font-semibold text-white/60 w-8 text-right shrink-0">{cat.score}</span>
      </button>
    </div>
  )
}

export default function CommandPanel({ data, profile, riskScore, onTabChange }: Props) {
  const [riskProfile, setRiskProfile] = useState<RiskProfile>('conservative')
  const [streetscape, setStreetscape] = useState<StreetscapeData | null>(null)

  useEffect(() => {
    if (!profile.neighborhood) return
    api.streetscape(profile.neighborhood)
      .then(d => setStreetscape(d.counts ? d as StreetscapeData : null))
      .catch(() => setStreetscape(null))
  }, [profile.neighborhood])

  const insights = useMemo(
    () => computeInsights(data, profile, riskProfile, streetscape),
    [data, profile, riskProfile, streetscape],
  )

  const positives = useMemo(() => {
    const items: Array<{ label: string; detail: string }> = []
    for (const cat of insights.categories) {
      if (cat.signal === 'positive') {
        items.push({ label: cat.name, detail: cat.claim })
      }
    }
    return items.slice(0, 3)
  }, [insights.categories])

  const concerns = useMemo(() => {
    const items: Array<{ label: string; detail: string }> = []
    for (const cat of insights.categories) {
      if (cat.signal === 'negative') {
        items.push({ label: cat.name, detail: cat.claim })
      }
    }
    return items.slice(0, 3)
  }, [insights.categories])

  const verdict = useMemo(() => {
    const opp = insights.overall
    const risk = riskScore.overall_score
    if (opp >= 60 && risk <= 4) return { tone: 'positive' as const, label: 'PROCEED', detail: 'Strong opportunity with low risk signals.' }
    if (opp >= 40 && risk <= 6) return { tone: 'neutral' as const, label: 'PROCEED WITH CAUTION', detail: 'Moderate signals — validate key assumptions before committing.' }
    if (risk > 7 || opp < 30) return { tone: 'negative' as const, label: 'HIGH RISK', detail: 'Significant risk indicators — reconsider or mitigate before entry.' }
    return { tone: 'neutral' as const, label: 'MIXED SIGNALS', detail: 'Balanced risk/opportunity profile — prioritize evidence review.' }
  }, [insights.overall, riskScore.overall_score])

  const verdictTint = verdict.tone === 'positive'
    ? 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-300'
    : verdict.tone === 'negative'
      ? 'border-red-500/30 bg-red-500/[0.06] text-red-300'
      : 'border-amber-500/30 bg-amber-500/[0.06] text-amber-300'

  return (
    <div className="flex flex-col h-full border border-white/[0.06] bg-white/[0.01]">
      {/* Header: Location + Profile Toggle */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Decision Cockpit</div>
          <div className="flex items-baseline gap-2 mt-0.5">
            <h3 className="text-sm font-semibold text-white truncate">{riskScore.neighborhood}</h3>
            <span className="text-white/15">·</span>
            <p className="text-[11px] text-white/50 truncate">{riskScore.business_type}</p>
          </div>
        </div>
        <div className="flex gap-0 border border-white/[0.08] overflow-hidden">
          {PROFILES.map(p => (
            <button
              key={p.key}
              type="button"
              title={p.desc}
              onClick={() => setRiskProfile(p.key)}
              className={`px-2.5 py-1 text-[9px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                riskProfile === p.key
                  ? 'bg-white/[0.08] text-white'
                  : 'text-white/30 hover:text-white/60'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Score cockpit: Risk + Opportunity + Confidence */}
      <div className="grid grid-cols-3 border-b border-white/[0.06]">
        <div className={`border-r border-white/[0.06] p-4 bg-gradient-to-br ${riskTint(riskScore.overall_score)}`}>
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/40">Risk</div>
          <div className="flex items-baseline gap-1 mt-1">
            <span className={`text-2xl font-bold font-mono ${riskColor(riskScore.overall_score)}`}>
              {riskScore.overall_score.toFixed(1)}
            </span>
            <span className="text-[10px] font-mono text-white/25">/10</span>
          </div>
          <div className="mt-2 w-full h-0.5 bg-white/[0.06]">
            <div
              className={`h-0.5 ${riskScore.overall_score <= 3 ? 'bg-emerald-400' : riskScore.overall_score <= 6 ? 'bg-amber-400' : 'bg-red-400'}`}
              style={{ width: `${riskScore.overall_score * 10}%` }}
            />
          </div>
          <div className="text-[9px] font-mono text-white/30 mt-1.5">Lower is better</div>
        </div>

        <div className={`border-r border-white/[0.06] p-4 bg-gradient-to-br ${oppTint(insights.overall)}`}>
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/40">Opportunity</div>
          <div className="flex items-baseline gap-1 mt-1">
            <span className={`text-2xl font-bold font-mono ${oppColor(insights.overall)}`}>
              {insights.overall}
            </span>
            <span className="text-[10px] font-mono text-white/25">/100</span>
          </div>
          <div className="mt-2 w-full h-0.5 bg-white/[0.06]">
            <div
              className={`h-0.5 ${insights.overall >= 65 ? 'bg-emerald-400' : insights.overall >= 40 ? 'bg-amber-400' : 'bg-red-400'}`}
              style={{ width: `${insights.overall}%` }}
            />
          </div>
          <div className="text-[9px] font-mono text-white/30 mt-1.5">{insights.coverageCount}/6 signals</div>
        </div>

        <div className="p-4">
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/40">Confidence</div>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-2xl font-bold font-mono text-white/80">
              {Math.round(riskScore.confidence * 100)}
            </span>
            <span className="text-[10px] font-mono text-white/25">%</span>
          </div>
          <div className="mt-2 w-full h-0.5 bg-white/[0.06]">
            <div
              className="h-0.5 bg-white/60"
              style={{ width: `${riskScore.confidence * 100}%` }}
            />
          </div>
          <div className="text-[9px] font-mono text-white/30 mt-1.5">Data coverage</div>
        </div>
      </div>

      {/* Verdict strip */}
      <div className={`px-5 py-2.5 border-b border-white/[0.06] flex items-center gap-3 ${verdictTint}`}>
        <span className="text-[9px] font-mono uppercase tracking-[0.2em] shrink-0">Verdict</span>
        <span className="text-[10px] font-mono font-bold tracking-wider shrink-0">{verdict.label}</span>
        <span className="text-[10px] text-white/55 truncate">— {verdict.detail}</span>
      </div>

      {/* Category bars */}
      <div className="px-5 py-3 border-b border-white/[0.06]">
        <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mb-2">Signal Matrix</div>
        <div className="space-y-0.5">
          {insights.categories.map(cat => (
            <CategoryBar
              key={cat.id}
              cat={cat}
              onViewAll={onTabChange && CATEGORY_TAB_MAP[cat.id] ? () => onTabChange(CATEGORY_TAB_MAP[cat.id]) : undefined}
            />
          ))}
        </div>
      </div>

      {/* Positives + Concerns two-column */}
      <div className="grid grid-cols-2 border-b border-white/[0.06] flex-1 min-h-0">
        <div className="p-4 border-r border-white/[0.06] overflow-y-auto">
          <div className="text-[9px] font-mono uppercase tracking-wider text-emerald-300/60 mb-2 flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-emerald-400" />
            Top Positives
          </div>
          {positives.length > 0 ? (
            <div className="space-y-2">
              {positives.map((p, i) => (
                <div key={i} className="border-l-2 border-emerald-500/40 pl-2.5 py-0.5">
                  <div className="text-[11px] font-semibold text-emerald-200/90">{p.label}</div>
                  <div className="text-[10px] text-white/50 leading-relaxed mt-0.5">{p.detail}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[10px] font-mono text-white/25">No strong positive signals.</div>
          )}
        </div>
        <div className="p-4 overflow-y-auto">
          <div className="text-[9px] font-mono uppercase tracking-wider text-red-300/60 mb-2 flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-red-400" />
            Top Concerns
          </div>
          {concerns.length > 0 ? (
            <div className="space-y-2">
              {concerns.map((c, i) => (
                <div key={i} className="border-l-2 border-red-500/40 pl-2.5 py-0.5">
                  <div className="text-[11px] font-semibold text-red-200/90">{c.label}</div>
                  <div className="text-[10px] text-white/50 leading-relaxed mt-0.5">{c.detail}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[10px] font-mono text-white/25">No major concerns identified.</div>
          )}
        </div>
      </div>

      {/* Quick-jump chips */}
      {onTabChange && (
        <div className="flex flex-wrap gap-1.5 px-5 py-3">
          <span className="text-[9px] font-mono uppercase tracking-wider text-white/30 self-center mr-1">Drill:</span>
          {[
            { key: 'regulatory', label: 'Regulatory', count: (data.inspections?.length ?? 0) + (data.permits?.length ?? 0) + (data.licenses?.length ?? 0) },
            { key: 'intel', label: 'News', count: (data.news?.length ?? 0) + (data.politics?.length ?? 0) },
            { key: 'community', label: 'Community', count: (data.reddit?.length ?? 0) + (data.tiktok?.length ?? 0) },
            { key: 'market', label: 'Market', count: (data.reviews?.length ?? 0) + (data.realestate?.length ?? 0) },
            { key: 'vision', label: 'Vision', count: data.cctv?.cameras.length ?? 0 },
          ].filter(chip => chip.count > 0).map(chip => (
            <button
              key={chip.key}
              onClick={() => onTabChange(chip.key)}
              className="flex items-center gap-1.5 px-2.5 py-1 border border-white/[0.08] hover:border-[#2B95D6]/40 hover:bg-[#2B95D6]/[0.05] text-[10px] font-mono uppercase tracking-wider text-white/55 hover:text-white/90 transition-colors cursor-pointer"
            >
              <span>{chip.label}</span>
              <span className="text-white/30 group-hover:text-[#2B95D6]">{chip.count}</span>
              <span className="text-white/20">›</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
