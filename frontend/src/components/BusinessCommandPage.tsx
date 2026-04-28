import { useMemo } from 'react'
import {
  getBusinessIntelligenceSnapshot,
  type BusinessIntelligenceSnapshot,
  type BusinessRecommendation,
  type Daypart,
  type ProductMetric,
} from '../business/index.ts'
import type { NeighborhoodData, UserProfile } from '../types/index.ts'

const money = (cents: number) => `$${Math.round(cents / 100).toLocaleString()}`

const DAYPART_LABELS: Record<Daypart, string> = {
  morning: 'Morning',
  lunch: 'Lunch',
  afternoon: 'Afternoon',
  dinner: 'Dinner',
  evening: 'Evening',
}

const EFFORT_TONE: Record<BusinessRecommendation['effort'], string> = {
  low: 'text-emerald-300 border-emerald-400/25 bg-emerald-400/[0.06]',
  medium: 'text-amber-300 border-amber-400/25 bg-amber-400/[0.06]',
  high: 'text-red-300 border-red-400/25 bg-red-400/[0.06]',
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

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 border border-white/[0.06] bg-white/[0.01] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Business Command</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <h2 className="text-lg font-semibold text-white/90">{snapshot.mockBusiness.business.name}</h2>
            <span className="text-white/15">/</span>
            <span className="text-xs font-mono text-white/45">{snapshot.context.neighborhood}</span>
            <span className="text-xs font-mono text-white/30">{snapshot.mockBusiness.business.kind.replace('_', ' ')}</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 text-right">
          <HeaderMetric label="Context" value={snapshot.context.neighborhood} />
          <HeaderMetric label="Confidence" value={`${Math.round(snapshot.context.confidence * 100)}%`} />
          <HeaderMetric label="Competition" value={snapshot.context.competitorPressure} />
        </div>
      </header>

      <KpiStrip snapshot={snapshot} />

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)] gap-4">
        <ActionQueue recommendations={snapshot.recommendations} />
        <OperatorBrief snapshot={snapshot} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <ProductPerformance products={snapshot.metrics.productMetrics} />
        </div>
        <DaypartPanel snapshot={snapshot} />
      </div>
    </div>
  )
}

function KpiStrip({ snapshot }: { snapshot: BusinessIntelligenceSnapshot }) {
  const { metrics, recommendations } = snapshot
  const opportunity = recommendations.reduce((sum, item) => sum + item.impactCentsPerWeek, 0)
  const confidence = recommendations.length > 0
    ? Math.round((recommendations.reduce((sum, item) => sum + item.confidence, 0) / recommendations.length) * 100)
    : 0

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
      <Kpi label="Today Revenue" value={money(metrics.todayRevenueCents)} sub={`${metrics.orderCount} orders`} tone="text-white/85" />
      <Kpi label="Projected Week" value={money(metrics.projectedWeekRevenueCents)} sub={`${money(metrics.averageOrderValueCents)} AOV`} tone="text-blue-300" />
      <Kpi label="Weekly Gross Profit" value={money(metrics.grossProfitCents)} sub={`${metrics.refundRatePct}% refund rate today`} tone="text-emerald-300" />
      <Kpi label="Opportunity" value={money(opportunity)} sub={`${recommendations.length} actions`} tone="text-emerald-300" />
      <Kpi label="Confidence" value={`${confidence}%`} sub="Mock POS coverage" tone="text-white/80" />
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
      <div className="mt-1 text-[10px] font-mono text-white/35">{sub}</div>
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-medium text-white/85">{item.title}</h3>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-emerald-300">+{money(item.impactCentsPerWeek)}/wk</span>
                  <span className={`border px-2 py-0.5 text-[9px] font-mono uppercase ${EFFORT_TONE[item.effort]}`}>{item.effort}</span>
                </div>
              </div>
              <p className="mt-1 text-xs text-white/45">{item.detail}</p>
              <div className="mt-3 grid gap-1.5">
                {item.evidence.map(evidence => (
                  <div key={evidence} className="flex gap-2 text-[10px] font-mono text-white/35">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-white/20" />
                    <span>{evidence}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {item.sources.map(source => (
                  <span key={source} className="border border-white/[0.06] bg-white/[0.02] px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider text-white/35">
                    {source}
                  </span>
                ))}
                <span className="border border-white/[0.06] bg-white/[0.02] px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider text-white/45">
                  {Math.round(item.confidence * 100)}% confidence
                </span>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

function OperatorBrief({ snapshot }: { snapshot: BusinessIntelligenceSnapshot }) {
  const topProduct = snapshot.metrics.productMetrics[0]
  const stockoutText = snapshot.metrics.stockoutRiskItems.length > 0
    ? `${snapshot.metrics.stockoutRiskItems.join(', ')} stockout risk needs attention.`
    : 'No stockout risk in the current mock POS snapshot.'

  return (
    <section className="border border-white/[0.06] bg-white/[0.01]">
      <PanelHeader label="Operator Brief" meta="mock POS" />
      <div className="space-y-3 px-4 py-4">
        <BriefLine label="Revenue" text={`${money(snapshot.metrics.todayRevenueCents)} today with ${snapshot.metrics.orderCount} orders.`} />
        <BriefLine label="Mix" text={topProduct ? `${topProduct.name} leads product revenue at ${money(topProduct.revenueCents)} this week.` : 'No product revenue available.'} />
        <BriefLine label="Inventory" text={stockoutText} />
        <BriefLine label="Market" text={`${snapshot.context.competitorPressure} competitor pressure with ${snapshot.context.eveningDemandIndex}/100 evening demand.`} />
        <BriefLine label="Risk" text={`Inspection pressure is ${snapshot.context.inspectionPressure}.`} />
      </div>
    </section>
  )
}

function BriefLine({ label, text }: { label: string; text: string }) {
  return (
    <div className="grid grid-cols-[76px_minmax(0,1fr)] gap-3 text-xs">
      <span className="font-mono uppercase tracking-wider text-white/30">{label}</span>
      <span className="text-white/55">{text}</span>
    </div>
  )
}

function ProductPerformance({ products }: { products: ProductMetric[] }) {
  const maxRevenue = Math.max(...products.map(product => product.revenueCents), 1)

  return (
    <section className="border border-white/[0.06] bg-white/[0.01]">
      <PanelHeader label="Product Performance" meta="7 days" />
      <div className="space-y-3 px-4 py-4">
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

function DaypartPanel({ snapshot }: { snapshot: BusinessIntelligenceSnapshot }) {
  const entries = Object.entries(snapshot.metrics.daypartRevenueCents) as Array<[Daypart, number]>
  const maxRevenue = Math.max(...entries.map(([, value]) => value), 1)

  return (
    <section className="border border-white/[0.06] bg-white/[0.01]">
      <PanelHeader label="Daypart Revenue" meta="today" />
      <div className="space-y-3 px-4 py-4">
        {entries.map(([daypart, value]) => (
          <div key={daypart}>
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-white/60">{DAYPART_LABELS[daypart]}</span>
              <span className="text-[10px] font-mono text-white/35">{money(value)}</span>
            </div>
            <div className="mt-1 h-1 bg-white/[0.05]">
              <div className="h-1 bg-emerald-400/80" style={{ width: `${Math.max(4, (value / maxRevenue) * 100)}%` }} />
            </div>
          </div>
        ))}
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
