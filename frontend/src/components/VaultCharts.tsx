import {
  AreaChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Legend,
  ReferenceLine,
} from 'recharts'
import type { InspectionRecord } from '../types'
import type { NeighborhoodData } from '../types'
import type { Document } from '../types'

const CHART_COLORS = {
  pass: '#22c55e',
  fail: '#ef4444',
  passWithConditions: '#eab308',
  inspections: '#3b82f6',
  permits: '#8b5cf6',
  federal: '#f97316',
  news: '#06b6d4',
  politics: '#84cc16',
}

// Extract normalized violation key (first ~50 chars or common pattern)
function normalizeViolation(v: string): string {
  const s = v.trim()
  // Common Chicago food inspection format: "1. Item - Description" or "Item - Description"
  const m = s.match(/^(\d+\.\s*)?(.+?)(?:\s*-\s*|$)/)
  const key = (m ? m[2] || s : s).slice(0, 60)
  return key || '(no description)'
}

interface InspectionOutcomesChartProps {
  inspections: InspectionRecord[]
}

export function InspectionOutcomesChart({ inspections }: InspectionOutcomesChartProps) {
  if (inspections.length === 0) return null

  const byDate: Record<string, { date: string; Pass: number; Fail: number; 'Pass w/ Conditions': number }> = {}
  for (const insp of inspections) {
    const r = insp.metadata?.raw_record
    if (!r) continue
    const d = r.inspection_date?.slice(0, 10) ?? 'unknown'
    if (!byDate[d]) byDate[d] = { date: d, Pass: 0, Fail: 0, 'Pass w/ Conditions': 0 }
    const res = (r.results ?? 'Pass').trim()
    if (res === 'Pass') byDate[d].Pass++
    else if (res === 'Fail') byDate[d].Fail++
    else byDate[d]['Pass w/ Conditions']++
  }
  const data = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date))

  if (data.length === 0) return null

  return (
    <div className="border border-white/[0.06] bg-white/[0.02] p-5">
      <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30 mb-4">
        Inspection Outcomes Trend
      </h3>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
            <defs>
              <linearGradient id="passGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS.pass} stopOpacity={0.6} />
                <stop offset="100%" stopColor={CHART_COLORS.pass} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="failGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS.fail} stopOpacity={0.6} />
                <stop offset="100%" stopColor={CHART_COLORS.fail} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="passCondGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS.passWithConditions} stopOpacity={0.6} />
                <stop offset="100%" stopColor={CHART_COLORS.passWithConditions} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="date"
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }}
              tickFormatter={(v) => {
                const d = new Date(v)
                return `${d.getMonth() + 1}/${d.getDate()}`
              }}
            />
            <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} />
            <Tooltip
              contentStyle={{ background: '#0f1419', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4 }}
              labelStyle={{ color: 'rgba(255,255,255,0.8)' }}
              labelFormatter={(v) => new Date(v).toLocaleDateString()}
            />
            <Area type="monotone" dataKey="Pass" stackId="1" stroke={CHART_COLORS.pass} fill="url(#passGrad)" name="Pass" />
            <Area type="monotone" dataKey="Fail" stackId="1" stroke={CHART_COLORS.fail} fill="url(#failGrad)" name="Fail" />
            <Area type="monotone" dataKey="Pass w/ Conditions" stackId="1" stroke={CHART_COLORS.passWithConditions} fill="url(#passCondGrad)" name="Pass w/ Conditions" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

interface TopViolationsParetoProps {
  inspections: InspectionRecord[]
}

export function TopViolationsPareto({ inspections }: TopViolationsParetoProps) {
  const violationCounts: Record<string, number> = {}
  for (const insp of inspections) {
    const r = insp.metadata?.raw_record
    const violations = ((r?.violations as string) ?? '').split('|').filter(Boolean)
    for (const v of violations) {
      const key = normalizeViolation(v)
      violationCounts[key] = (violationCounts[key] ?? 0) + 1
    }
  }
  const sorted = Object.entries(violationCounts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
  const total = sorted.reduce((s, x) => s + x.count, 0)
  let cum = 0
  const data = sorted.map((x) => {
    cum += x.count
    return {
      ...x,
      nameShort: x.name.length > 35 ? x.name.slice(0, 32) + '...' : x.name,
      cumPct: total > 0 ? Math.round((cum / total) * 100) : 0,
    }
  })

  if (data.length === 0) return null

  return (
    <div className="border border-white/[0.06] bg-white/[0.02] p-5">
      <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30 mb-4">
        Top Violations (Pareto)
      </h3>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 32, left: 4, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="nameShort"
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 8 }}
              angle={-45}
              textAnchor="end"
              height={50}
            />
            <YAxis yAxisId="left" orientation="left" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fill: 'rgba(147,197,253,0.7)', fontSize: 9 }} domain={[0, 100]} />
            <Tooltip
              contentStyle={{ background: '#0f1419', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4 }}
              formatter={(val, _name, props) => {
                const p = (props as { payload?: { name: string; count: number; cumPct: number } })?.payload
                if (!p) return String(val ?? '')
                return `${p.name}: ${p.count} · cumulative ${p.cumPct}%`
              }}
            />
            <Bar yAxisId="left" dataKey="count" fill={CHART_COLORS.fail} radius={[2, 2, 0, 0]} name="Count" />
            <Line yAxisId="right" type="monotone" dataKey="cumPct" stroke="#93c5fd" strokeWidth={2} dot={{ r: 3 }} name="Cumulative %" />
            <ReferenceLine yAxisId="right" y={80} stroke="rgba(147,197,253,0.4)" strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function docDate(d: Document): string | null {
  const ts = d.timestamp ?? (d.metadata as Record<string, unknown>)?.raw_record
  if (typeof ts === 'string') return ts.slice(0, 10)
  const r = (d.metadata as Record<string, unknown>)?.raw_record as Record<string, unknown> | undefined
  if (r?.inspection_date) return String(r.inspection_date).slice(0, 10)
  if (r?.issue_date) return String(r.issue_date).slice(0, 10)
  return null
}

interface AlertHoursStackedAreaProps {
  data: NeighborhoodData
}

const SOURCE_LABELS: Record<string, string> = {
  inspections: 'Inspections',
  permits: 'Permits',
  federal: 'Federal Alerts',
  news: 'News',
  politics: 'Legislation',
  other: 'Other',
}

export function AlertHoursStackedArea({ data }: AlertHoursStackedAreaProps) {
  const byDate: Record<string, Record<string, number | string>> = {}

  const addDoc = (doc: Document, sourceKey: string) => {
    const d = docDate(doc)
    if (!d) return
    if (!byDate[d]) {
      byDate[d] = { date: d, inspections: 0, permits: 0, federal: 0, news: 0, politics: 0, other: 0 }
    }
    const k = (['inspections', 'permits', 'federal', 'news', 'politics'] as const).includes(sourceKey as never) ? sourceKey : 'other'
    byDate[d][k] = (Number(byDate[d][k]) || 0) + 1
  }

  ;(data.inspections ?? []).forEach((d) => addDoc(d, 'inspections'))
  ;(data.permits ?? []).forEach((d) => addDoc(d, 'permits'))
  ;(data.federal_register ?? []).forEach((d) => addDoc(d, 'federal'))
  ;(data.news ?? []).forEach((d) => addDoc(d, 'news'))
  ;(data.politics ?? []).forEach((d) => addDoc(d, 'politics'))

  const dataArr = Object.values(byDate).sort((a, b) => String(a.date).localeCompare(String(b.date)))
  const hasData = dataArr.some((row) => Object.keys(row).some((k) => k !== 'date' && (row[k] as number) > 0))

  if (!hasData || dataArr.length === 0) return null

  const sources = ['inspections', 'permits', 'federal', 'news', 'politics'] as const
  const colors = [CHART_COLORS.inspections, CHART_COLORS.permits, CHART_COLORS.federal, CHART_COLORS.news, CHART_COLORS.politics]

  return (
    <div className="border border-white/[0.06] bg-white/[0.02] p-5">
      <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30 mb-4">
        Document Volume by Source (Stacked)
      </h3>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={dataArr} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
            <defs>
              {sources.map((src, i) => (
                <linearGradient key={src} id={`grad-${src}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors[i]} stopOpacity={0.6} />
                  <stop offset="100%" stopColor={colors[i]} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="date"
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }}
              tickFormatter={(v) => {
                const d = new Date(v)
                return `${d.getMonth() + 1}/${d.getDate()}`
              }}
            />
            <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} />
            <Tooltip
              contentStyle={{ background: '#0f1419', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4 }}
              labelFormatter={(v) => new Date(v).toLocaleDateString()}
            />
            <Legend wrapperStyle={{ fontSize: 9 }} formatter={(v) => SOURCE_LABELS[String(v)] ?? String(v)} />
            {sources.map((src, i) => (
              <Area
                key={src}
                type="monotone"
                dataKey={src}
                stackId="1"
                stroke={colors[i]}
                fill={`url(#grad-${src})`}
                name={src}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
