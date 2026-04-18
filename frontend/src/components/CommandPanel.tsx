import { useState, useEffect, useMemo } from 'react'
import type { NeighborhoodData, UserProfile, RiskScore, CategoryScore, StreetscapeData } from '../types/index.ts'
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

// Risk uses a /100 visual scale derived from the backend's /10 score.
// Thresholds are the original /10 cutoffs multiplied by 10.
function riskColor(score: number): string {
  if (score <= 30) return 'text-emerald-400'
  if (score <= 60) return 'text-amber-400'
  return 'text-red-400'
}

function riskTint(score: number): string {
  if (score <= 30) return 'from-emerald-500/[0.08] border-emerald-500/25'
  if (score <= 60) return 'from-amber-500/[0.08] border-amber-500/25'
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
  const [streetscape, setStreetscape] = useState<{ neighborhood: string; data: StreetscapeData | null } | null>(null)

  useEffect(() => {
    if (!profile.neighborhood) return

    let cancelled = false
    api.streetscape(profile.neighborhood)
      .then(d => {
        if (!cancelled) {
          setStreetscape({
            neighborhood: profile.neighborhood,
            data: d.counts ? d as StreetscapeData : null,
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStreetscape({
            neighborhood: profile.neighborhood,
            data: null,
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [profile.neighborhood])

  const streetscapeForProfile = streetscape?.neighborhood === profile.neighborhood ? streetscape.data : null

  const insights = useMemo(
    () => computeInsights(data, profile, 'balanced', streetscapeForProfile),
    [data, profile, streetscapeForProfile],
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
      </div>

      {/* Score cockpit: Risk + Opportunity + Confidence — all on /100 for easy comparison */}
      <div className="grid grid-cols-3 border-b border-white/[0.06]">
        {(() => {
          const riskDisplay = Math.round(riskScore.overall_score * 10)
          return (
            <div className={`border-r border-white/[0.06] p-4 bg-gradient-to-br ${riskTint(riskDisplay)}`}>
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/40">Risk</div>
              <div className="flex items-baseline gap-1 mt-1">
                <span className={`text-2xl font-bold font-mono ${riskColor(riskDisplay)}`}>
                  {riskDisplay}
                </span>
                <span className="text-[10px] font-mono text-white/25">/100</span>
              </div>
              <div className="mt-2 w-full h-0.5 bg-white/[0.06]">
                <div
                  className={`h-0.5 ${riskDisplay <= 30 ? 'bg-emerald-400' : riskDisplay <= 60 ? 'bg-amber-400' : 'bg-red-400'}`}
                  style={{ width: `${riskDisplay}%` }}
                />
              </div>
              <div className="text-[9px] font-mono text-white/30 mt-1.5">Lower is better</div>
            </div>
          )
        })()}

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
            <span className="text-[10px] font-mono text-white/25">/100</span>
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

      {/* Category bars */}
      <div className="px-5 py-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Signal Matrix</div>
          <div className="flex items-center gap-3 text-[9px] font-mono text-white/30">
            <span className="flex items-center gap-1"><span className="text-emerald-400/80">▲</span>improving</span>
            <span className="flex items-center gap-1"><span className="text-amber-400/80">●</span>stable</span>
            <span className="flex items-center gap-1"><span className="text-red-400/80">▼</span>declining</span>
          </div>
        </div>
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
    </div>
  )
}
