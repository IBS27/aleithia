import { useState, useEffect, useMemo } from 'react'
import type { NeighborhoodData, UserProfile, RiskProfile, CategoryScore, StreetscapeData } from '../types/index.ts'
import { computeInsights } from '../insights.ts'
import { api } from '../api.ts'

interface Props {
  data: NeighborhoodData
  profile: UserProfile
  onTabChange?: (tab: string) => void
}

const CATEGORY_TAB_MAP: Record<string, string> = {
  regulatory: 'inspections',
  economic: 'permits',
  market: 'market',
  demographic: 'overview',
  safety: 'vision',
  community: 'community',
}

const PROFILES: { key: RiskProfile; label: string }[] = [
  { key: 'conservative', label: 'Conservative' },
  { key: 'growth', label: 'Growth' },
  { key: 'budget', label: 'Budget' },
]

function signalColor(signal: string) {
  if (signal === 'positive') return 'text-green-400'
  if (signal === 'neutral') return 'text-yellow-400'
  return 'text-red-400'
}

function barColor(signal: string) {
  if (signal === 'positive') return 'bg-green-400/80'
  if (signal === 'neutral') return 'bg-yellow-400/80'
  return 'bg-red-400/80'
}

function signalIcon(signal: string) {
  if (signal === 'positive') return '\u2713'
  if (signal === 'neutral') return '\u2192'
  return '\u2717'
}

function ScoreBar({ score, signal }: { score: number; signal: string }) {
  return (
    <div className="flex items-center gap-3 flex-1">
      <div className="flex-1 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor(signal)}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-mono font-bold text-white/70 w-7 text-right">{score}</span>
    </div>
  )
}

function CategoryRow({ cat, expanded, onToggle, evidence, onViewAll }: {
  cat: CategoryScore
  expanded: boolean
  onToggle: () => void
  evidence: Array<{ label: string; detail: string }>
  onViewAll?: () => void
}) {
  return (
    <div className="border-b border-white/[0.04] last:border-0">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 border rounded ${signalColor(cat.signal)} border-current/20`}>
          {signalIcon(cat.signal)} {cat.signalLabel}
        </span>
        <span className="text-xs font-medium text-white/60 w-24">{cat.name}</span>
        <ScoreBar score={cat.score} signal={cat.signal} />
      </button>

      {expanded && (
        <div className="px-4 pb-3 space-y-2">
          <p className="text-sm text-white/50 leading-relaxed">{cat.claim}</p>

          {cat.subMetrics.length > 0 && (
            <div className="space-y-1">
              {cat.subMetrics.map(sub => (
                <div key={sub.name} className="flex items-center gap-2 text-[11px]">
                  <span className="text-white/25 w-32 shrink-0">{sub.name}</span>
                  <div className="flex-1 h-1 bg-white/[0.04] rounded-full overflow-hidden">
                    <div className="h-full bg-white/20 rounded-full" style={{ width: `${sub.value}%` }} />
                  </div>
                  <span className="text-white/20 font-mono text-[10px] shrink-0">{Math.round(sub.value)}</span>
                </div>
              ))}
            </div>
          )}

          <div className="text-[10px] font-mono text-white/15">
            {cat.sources.join(' + ')} &middot; {cat.dataPoints} data point{cat.dataPoints !== 1 ? 's' : ''}
          </div>

          {evidence.length > 0 && (
            <div className="mt-2 pt-2 border-t border-white/[0.04] space-y-1.5">
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mb-1">
                Source Documents
              </div>
              {evidence.slice(0, 5).map((ev, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="text-white/10">&#9679;</span>
                  <span className="text-white/40 flex-1 truncate">{ev.label}</span>
                  <span className="text-white/15 font-mono text-[10px] shrink-0">{ev.detail}</span>
                </div>
              ))}
              {onViewAll && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onViewAll() }}
                  className="text-[10px] font-mono text-white/30 hover:text-white/60 transition-colors cursor-pointer mt-1"
                >
                  View all &rarr;
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function InsightsCard({ data, profile, onTabChange }: Props) {
  const [riskProfile, setRiskProfile] = useState<RiskProfile>('conservative')
  const [expandedId, setExpandedId] = useState<string | null>(null)
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

  const evidenceMap = useMemo(() => {
    const map: Record<string, Array<{ label: string; detail: string }>> = {}

    map.regulatory = (data.inspections || []).slice(0, 5).map(i => ({
      label: (i.metadata?.raw_record as Record<string, string>)?.dba_name || i.title,
      detail: (i.metadata?.raw_record as Record<string, string>)?.results || 'Inspected',
    }))

    map.economic = [
      ...(data.permits || []).slice(0, 3).map(p => ({
        label: `${(p.metadata?.raw_record as Record<string, string>)?.work_type || 'Permit'} — ${(p.metadata?.raw_record as Record<string, string>)?.street_name || ''}`,
        detail: (p.metadata?.raw_record as Record<string, string>)?.permit_status || 'Active',
      })),
      ...(data.licenses || []).slice(0, 2).map(l => ({
        label: (l.metadata?.raw_record as Record<string, string>)?.doing_business_as_name || l.title,
        detail: (l.metadata?.raw_record as Record<string, string>)?.license_description || 'License',
      })),
    ]

    map.market = (data.reviews || []).slice(0, 5).map(r => ({
      label: (r.metadata?.business_name as string) || r.title,
      detail: r.metadata?.rating ? `${r.metadata.rating}/5` : '',
    }))

    map.demographic = data.demographics ? [{
      label: 'Census / ACS Data',
      detail: `${data.demographics.total_population?.toLocaleString() || '—'} residents`,
    }] : []

    map.safety = [
      ...(data.cctv?.cameras || []).slice(0, 3).map(c => ({
        label: `Camera ${c.camera_id}`,
        detail: `${c.pedestrians} peds, ${c.vehicles} vehicles`,
      })),
      ...(data.traffic || []).slice(0, 2).map(t => ({
        label: t.title || 'Traffic segment',
        detail: (t.metadata?.congestion_level as string) || '',
      })),
    ]

    map.community = [
      ...(data.news || []).slice(0, 3).map(n => ({
        label: n.title,
        detail: n.source,
      })),
      ...(data.reddit || []).slice(0, 2).map(r => ({
        label: r.title,
        detail: 'reddit',
      })),
    ]

    return map
  }, [data])

  if (insights.coverageCount === 0) return null

  return (
    <div className="border border-white/[0.06] bg-white/[0.02]">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <div className="text-[10px] font-mono uppercase tracking-wider text-white/30">
          Business Intelligence Score
        </div>
        <div className="flex gap-0 border border-white/[0.08] rounded overflow-hidden">
          {PROFILES.map(p => (
            <button
              key={p.key}
              type="button"
              onClick={() => setRiskProfile(p.key)}
              className={`px-3 py-1 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                riskProfile === p.key
                  ? 'bg-white/[0.06] text-white border-white/[0.1]'
                  : 'text-white/30 hover:text-white/50'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Overall score */}
      <div className="px-5 pb-4">
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/30">
            Overall Opportunity
          </span>
          <div className="flex-1 h-2 bg-white/[0.06] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${barColor(insights.overall >= 65 ? 'positive' : insights.overall >= 40 ? 'neutral' : 'negative')}`}
              style={{ width: `${insights.overall}%` }}
            />
          </div>
          <span className="text-lg font-mono font-bold text-white">
            {insights.overall}
            <span className="text-white/20 text-sm"> / 100</span>
          </span>
        </div>
        <div className="text-[10px] font-mono text-white/20 mt-1">
          {insights.coverageCount} of 6 categories scored
        </div>
      </div>

      {/* Categories */}
      <div className="border-t border-white/[0.06]">
        {insights.categories.map(cat => (
          <CategoryRow
            key={cat.id}
            cat={cat}
            expanded={expandedId === cat.id}
            onToggle={() => setExpandedId(expandedId === cat.id ? null : cat.id)}
            evidence={evidenceMap[cat.id] || []}
            onViewAll={onTabChange && CATEGORY_TAB_MAP[cat.id] ? () => onTabChange(CATEGORY_TAB_MAP[cat.id]) : undefined}
          />
        ))}
      </div>
    </div>
  )
}
