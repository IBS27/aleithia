import { useEffect, useMemo, useState } from 'react'
import {
  getBusinessIntelligenceSnapshot,
  type BusinessRecommendation,
  type CommandActionCopy,
  type CommandAnalysisSnapshot,
  type CommandSynthesis,
  type ProductMetric,
} from '../business/index.ts'
import type { NeighborhoodData, UserProfile } from '../types/index.ts'
import { api } from '../api.ts'

const money = (cents: number) => `$${Math.round(cents / 100).toLocaleString()}`

const EFFORT_TONE: Record<BusinessRecommendation['effort'], string> = {
  low: 'text-emerald-300 border-emerald-400/25 bg-emerald-400/[0.06]',
  medium: 'text-amber-300 border-amber-400/25 bg-amber-400/[0.06]',
  high: 'text-red-300 border-red-400/25 bg-red-400/[0.06]',
}

const RISK_TONE: Record<CommandAnalysisSnapshot['risk']['level'], string> = {
  low: 'text-emerald-300',
  medium: 'text-amber-300',
  high: 'text-red-300',
}

interface Props {
  profile: UserProfile
  neighborhoodData: NeighborhoodData | null
}

export default function BusinessCommandPage({ profile, neighborhoodData }: Props) {
  const snapshot = useMemo(
    () => getBusinessIntelligenceSnapshot(profile.business_type, neighborhoodData, profile.neighborhood),
    [profile.business_type, profile.neighborhood, neighborhoodData],
  )
  const command = snapshot.command
  const commandSynthesisPayload = JSON.stringify(command)
  const [synthesis, setSynthesis] = useState<CommandSynthesis | null>(null)

  useEffect(() => {
    let cancelled = false
    const commandForSynthesis = JSON.parse(commandSynthesisPayload) as CommandAnalysisSnapshot
    queueMicrotask(() => {
      if (!cancelled) setSynthesis(null)
    })

    api.commandSynthesis(commandForSynthesis)
      .then((result) => {
        if (!cancelled) setSynthesis(result)
      })
      .catch(() => {
        if (!cancelled) setSynthesis(buildLocalSynthesis(commandForSynthesis))
      })

    return () => {
      cancelled = true
    }
  }, [commandSynthesisPayload])

  const orderedRecommendations = useMemo(
    () => mergeSynthesisWithActions(command.recommendations, synthesis),
    [command.recommendations, synthesis],
  )

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 border border-white/[0.06] bg-white/[0.01] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Command</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <h2 className="text-lg font-semibold text-white/90">{command.business.name}</h2>
            <span className="text-white/15">/</span>
            <span className="text-xs font-mono text-white/45">{command.context.neighborhood}</span>
            <span className="text-xs font-mono text-emerald-300/70">LIVE ANALYSIS</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 text-right">
          <HeaderMetric label="Data Coverage" value={`${command.coverage.percent}%`} />
          <HeaderMetric label="Sources" value={`${command.coverage.sourcesOnline}/${command.coverage.sourcesTotal}`} />
          <HeaderMetric label="Actions" value={String(command.recommendations.length)} />
        </div>
      </header>

      <KpiStrip command={command} />

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.25fr)_minmax(380px,0.75fr)] gap-4">
        <ActionQueue recommendations={orderedRecommendations} />
        <OperatorBrief command={command} synthesis={synthesis} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <RevenueForecast command={command} />
        <ProductPerformance products={command.metrics.productMetrics} />
        <MarketContext command={command} />
        <CompliancePanel command={command} />
        <SourceCoverage command={command} />
      </div>
    </div>
  )
}

function KpiStrip({ command }: { command: CommandAnalysisSnapshot }) {
  const revenueDelta = command.forecast.baselineWeekRevenueCents > 0
    ? Math.round((command.forecast.opportunityCentsPerWeek / command.forecast.baselineWeekRevenueCents) * 100)
    : 0

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
      <Kpi label="Today Revenue" value={money(command.metrics.todayRevenueCents)} sub={`${command.metrics.orderCount} orders · ${money(command.metrics.averageOrderValueCents)} AOV`} tone="text-white/85" />
      <Kpi label="Projected Week" value={money(command.forecast.baselineWeekRevenueCents)} sub={`${money(command.metrics.weekRevenueCents)} observed 7-day revenue`} tone="text-blue-300" />
      <Kpi label="Opportunity Unlocked" value={money(command.forecast.opportunityCentsPerWeek)} sub={`+${revenueDelta}% vs baseline`} tone="text-emerald-300" />
      <Kpi label="Risk Level" value={command.risk.label} sub={command.risk.detail} tone={RISK_TONE[command.risk.level]} />
      <Kpi label="Confidence" value={`${command.coverage.percent}%`} sub="Analyzed source coverage" tone="text-white/80" />
    </div>
  )
}

function HeaderMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[9px] font-mono uppercase tracking-wider text-white/25">{label}</div>
      <div className="mt-1 text-xs font-mono uppercase text-white/55">{value}</div>
    </div>
  )
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: string }) {
  return (
    <section className="border border-white/[0.06] bg-white/[0.01] px-4 py-3">
      <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">{label}</div>
      <div className={`mt-2 text-2xl font-mono font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-[10px] font-mono text-white/35 line-clamp-1">{sub}</div>
    </section>
  )
}

function ActionQueue({ recommendations }: { recommendations: BusinessRecommendation[] }) {
  return (
    <section className="border border-white/[0.06] bg-white/[0.01]">
      <PanelHeader label="Action Queue" meta={`${recommendations.length} prioritized`} />
      <div className="divide-y divide-white/[0.06]">
        {recommendations.map((item, index) => (
          <article key={item.id} className="grid grid-cols-[36px_minmax(0,1fr)] gap-3 px-4 py-3">
            <div className="flex h-8 w-8 items-center justify-center border border-[#2B95D6]/35 bg-[#2B95D6]/15 text-sm font-mono text-[#48AFF0]">
              {index + 1}
            </div>
            <div className="min-w-0">
              <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_132px_92px_104px] lg:items-center">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-medium text-white/85">{item.title}</h3>
                  <p className="mt-1 text-xs text-white/45 line-clamp-2">{item.detail}</p>
                </div>
                <MetricCell label="Impact" value={`+${money(item.impactCentsPerWeek)}/wk`} tone="text-emerald-300" />
                <MetricCell label="Confidence" value={`${Math.round(item.confidence * 100)}%`} tone="text-white/70" />
                <div className="flex lg:justify-end">
                  <span className={`border px-2 py-1 text-[9px] font-mono uppercase ${EFFORT_TONE[item.effort]}`}>{item.effort}</span>
                </div>
              </div>
              <p className="mt-2 text-[10px] font-mono text-white/35">{item.whyNow}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {item.sources.map(source => (
                  <span key={source} className="border border-white/[0.06] bg-white/[0.02] px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider text-white/35">
                    {source}
                  </span>
                ))}
                <span className="ml-auto border border-[#2B95D6]/30 bg-[#2B95D6]/10 px-2.5 py-1 text-[9px] font-mono uppercase tracking-wider text-[#48AFF0]">
                  {item.nextStepLabel}
                </span>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

function MetricCell({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div>
      <div className="text-[9px] font-mono uppercase tracking-wider text-white/25">{label}</div>
      <div className={`mt-0.5 text-xs font-mono ${tone}`}>{value}</div>
    </div>
  )
}

function OperatorBrief({ command, synthesis }: { command: CommandAnalysisSnapshot; synthesis: CommandSynthesis | null }) {
  const lines = synthesis?.brief_lines.length ? synthesis.brief_lines : buildLocalSynthesis(command).brief_lines

  return (
    <section className="border border-white/[0.06] bg-white/[0.01]">
      <PanelHeader label="AI Operator Brief" meta={synthesis?.fallback_used ? 'fallback' : 'gpt-5'} />
      <div className="space-y-3 px-4 py-4">
        {lines.slice(0, 4).map((line, index) => (
          <div key={line} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3 text-xs">
            <span className="flex h-5 w-5 items-center justify-center border border-[#2B95D6]/25 bg-[#2B95D6]/10 text-[10px] font-mono text-[#48AFF0]">
              {index + 1}
            </span>
            <span className="text-white/55">{line}</span>
          </div>
        ))}

        <div className="border-t border-white/[0.06] pt-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-white/35">7-day simulation</span>
            <span className="text-[10px] font-mono text-emerald-300">Recommended +{money(command.forecast.opportunityCentsPerWeek)}</span>
          </div>
          <MiniForecast points={command.forecast.points} />
          <div className="mt-3 grid grid-cols-3 gap-3 text-[10px] font-mono">
            <BriefStat label="Baseline" value={money(command.forecast.baselineWeekRevenueCents)} />
            <BriefStat label="Recommended" value={money(command.forecast.recommendedWeekRevenueCents)} />
            <BriefStat label="Gross Profit" value={money(command.forecast.grossProfitRecommendedCents)} />
          </div>
        </div>
      </div>
    </section>
  )
}

function MiniForecast({ points }: { points: CommandAnalysisSnapshot['forecast']['points'] }) {
  const max = Math.max(...points.flatMap(point => [point.baselineRevenueCents, point.recommendedRevenueCents]), 1)
  return (
    <div className="flex h-24 items-end gap-2 border border-white/[0.05] bg-white/[0.01] px-3 py-3">
      {points.map((point) => (
        <div key={point.label} className="flex h-full flex-1 items-end justify-center gap-0.5">
          <div className="w-2 bg-white/25" style={{ height: `${Math.max(8, (point.baselineRevenueCents / max) * 100)}%` }} />
          <div className="w-2 bg-emerald-400/80" style={{ height: `${Math.max(8, (point.recommendedRevenueCents / max) * 100)}%` }} />
        </div>
      ))}
    </div>
  )
}

function BriefStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="uppercase tracking-wider text-white/25">{label}</div>
      <div className="mt-1 text-white/60">{value}</div>
    </div>
  )
}

function RevenueForecast({ command }: { command: CommandAnalysisSnapshot }) {
  return (
    <section className="border border-white/[0.06] bg-white/[0.01] px-4 py-4 lg:col-span-1">
      <PanelTitle label="Revenue Forecast" meta="7 days" />
      <MiniForecast points={command.forecast.points} />
      <div className="mt-4 grid grid-cols-2 gap-3 text-[10px] font-mono">
        <BriefStat label="Baseline" value={money(command.forecast.baselineWeekRevenueCents)} />
        <BriefStat label="Recommended" value={money(command.forecast.recommendedWeekRevenueCents)} />
      </div>
    </section>
  )
}

function ProductPerformance({ products }: { products: ProductMetric[] }) {
  const maxRevenue = Math.max(...products.map(product => product.revenueCents), 1)

  return (
    <section className="border border-white/[0.06] bg-white/[0.01] px-4 py-4 lg:col-span-1">
      <PanelTitle label="Top Product Performance" meta="7 days" />
      <div className="mt-4 space-y-3">
        {products.slice(0, 5).map(product => (
          <div key={product.menuItemId}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate text-xs text-white/65">{product.name}</span>
              <span className="shrink-0 text-[10px] font-mono text-white/35">{money(product.revenueCents)} / {product.marginPct}%</span>
            </div>
            <div className="mt-1 h-1 bg-white/[0.05]">
              <div className="h-1 bg-[#2B95D6]" style={{ width: `${Math.max(8, (product.revenueCents / maxRevenue) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function MarketContext({ command }: { command: CommandAnalysisSnapshot }) {
  return (
    <section className="border border-white/[0.06] bg-white/[0.01] px-4 py-4 lg:col-span-1">
      <PanelTitle label="Market Context" meta={command.market.footTrafficLabel} />
      <div className="mt-4 text-3xl font-mono text-[#48AFF0]">{command.market.footTrafficScore}</div>
      <div className="mt-1 text-[10px] font-mono uppercase tracking-wider text-white/30">Foot traffic score</div>
      <div className="mt-4 space-y-2">
        {command.market.nearbyBusinesses.slice(0, 3).map(item => (
          <div key={item.name} className="flex justify-between gap-3 text-xs">
            <span className="truncate text-white/55">{item.name}</span>
            <span className={item.isDirect ? 'text-red-300/70' : 'text-white/30'}>{item.isDirect ? 'direct' : 'nearby'}</span>
          </div>
        ))}
        {command.market.nearbyBusinesses.length === 0 && (
          <p className="text-xs text-white/35">No competitor license records available.</p>
        )}
      </div>
    </section>
  )
}

function CompliancePanel({ command }: { command: CommandAnalysisSnapshot }) {
  return (
    <section className="border border-white/[0.06] bg-white/[0.01] px-4 py-4 lg:col-span-1">
      <PanelTitle label="Compliance Countdown" meta={command.compliance.windowLabel} />
      <div className={`mt-4 text-3xl font-mono ${command.compliance.daysUntilWindow === 0 ? 'text-red-300' : 'text-amber-300'}`}>
        {command.compliance.daysUntilWindow === 0 ? 'OPEN' : `${command.compliance.daysUntilWindow}D`}
      </div>
      <div className="mt-4 space-y-2">
        {command.compliance.risks.map((risk, index) => (
          <div key={risk.label} className="flex items-center justify-between gap-3 text-xs">
            <span className="text-white/55">{index + 1}. {risk.label}</span>
            <span className={`border px-1.5 py-0.5 text-[9px] font-mono uppercase ${EFFORT_TONE[risk.severity]}`}>{risk.severity}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function SourceCoverage({ command }: { command: CommandAnalysisSnapshot }) {
  return (
    <section className="border border-white/[0.06] bg-white/[0.01] px-4 py-4 lg:col-span-1">
      <PanelTitle label="Source Coverage" meta="online" />
      <div className="mt-4 text-3xl font-mono text-white/80">{command.coverage.percent}%</div>
      <div className="mt-2 h-1 bg-white/[0.06]">
        <div className="h-1 bg-emerald-400/80" style={{ width: `${command.coverage.percent}%` }} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-[10px] font-mono">
        <BriefStat label="Sources" value={`${command.coverage.sourcesOnline}/${command.coverage.sourcesTotal}`} />
        <BriefStat label="Risks" value={String(command.risk.unresolvedCount)} />
      </div>
    </section>
  )
}

function PanelHeader({ label, meta }: { label: string; meta: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
      <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/55">{label}</h3>
      <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">{meta}</span>
    </div>
  )
}

function PanelTitle({ label, meta }: { label: string; meta: string }) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/55">{label}</h3>
      <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">{meta}</span>
    </div>
  )
}

function mergeSynthesisWithActions(
  recommendations: BusinessRecommendation[],
  synthesis: CommandSynthesis | null,
): BusinessRecommendation[] {
  const copyById = new Map<string, CommandActionCopy>()
  synthesis?.action_copy.forEach(copy => copyById.set(copy.id, copy))

  const known = new Map(recommendations.map(item => [item.id, item]))
  const rankedIds = synthesis?.ranked_action_ids.filter(id => known.has(id)) ?? []
  const orderedIds = [...rankedIds, ...recommendations.map(item => item.id).filter(id => !rankedIds.includes(id))]

  return orderedIds
    .map(id => {
      const base = known.get(id)
      if (!base) return null
      const copy = copyById.get(id)
      return copy
        ? {
            ...base,
            title: copy.title || base.title,
            detail: copy.detail || base.detail,
            whyNow: copy.why_now || base.whyNow,
            nextStepLabel: copy.next_step_label || base.nextStepLabel,
          }
        : base
    })
    .filter((item): item is BusinessRecommendation => Boolean(item))
}

function buildLocalSynthesis(command: CommandAnalysisSnapshot): CommandSynthesis {
  const top = [...command.recommendations].sort((a, b) => b.impactCentsPerWeek - a.impactCentsPerWeek).slice(0, 4)
  return {
    brief_lines: [
      `${money(command.forecast.opportunityCentsPerWeek)} per week is available across the current action queue.`,
      `${command.market.footTrafficLabel} foot traffic and ${command.context.competitorPressure} competitor pressure shape the top priorities.`,
      `${command.risk.label} risk level means actions should protect execution quality while revenue tests run.`,
    ],
    ranked_action_ids: top.map(item => item.id),
    action_copy: top.map(item => ({
      id: item.id,
      title: item.title,
      detail: item.detail,
      why_now: item.whyNow,
      next_step_label: item.nextStepLabel,
    })),
    uncertainty_notes: [],
    fallback_used: true,
  }
}
