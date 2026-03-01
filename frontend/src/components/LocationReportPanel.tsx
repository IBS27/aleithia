import { jsPDF } from 'jspdf'
import type { NeighborhoodData, RiskScore, UserProfile, Document } from '../types/index.ts'
import { computeInsights, LICENSE_MAP } from '../insights.ts'

interface AgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
  agent_summaries: Array<{
    name: string
    data_points: number
    sources?: string[]
  }>
}

interface Props {
  profile: UserProfile
  neighborhoodData: NeighborhoodData | null
  riskScore: RiskScore | null
  loading: boolean
  agentInfo: AgentInfo | null
}

type Signal = {
  title: string
  detail: string
}

// ── Extraction helpers ──────────────────────────────────────────────

function extractAllAdvantages(data: NeighborhoodData, profile: UserProfile): Signal[] {
  const signals: Signal[] = []
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  if (isServiceBusiness && data.demographics) {
    const d = data.demographics
    if (d.total_population && d.total_population > 5000) {
      signals.push({
        title: 'Large resident base',
        detail: `~${Math.round(d.total_population / 1000)}K residents in the neighborhood.`,
      })
    }
  }

  const realestate = data.realestate?.length || 0
  if (realestate > 3) {
    signals.push({
      title: 'Active real estate market',
      detail: `${realestate} listings — area is attracting investment.`,
    })
  }

  if (isFoodBusiness) {
    const newsCount = data.news?.length || 0
    if (newsCount > 5) {
      signals.push({
        title: 'Local media coverage',
        detail: `${newsCount} recent news mentions in the area.`,
      })
    }
  }

  const uniqueLicenseTypes = new Set(
    data.licenses.map(l => (l.metadata?.raw_record as Record<string, unknown>)?.license_description || '').filter(Boolean)
  )
  if (uniqueLicenseTypes.size > 15) {
    signals.push({
      title: 'Diverse business mix',
      detail: `${uniqueLicenseTypes.size} different business types — established commercial corridor.`,
    })
  }

  if (data.transit && data.transit.stations_nearby >= 2) {
    signals.push({
      title: 'Strong transit access',
      detail: `${data.transit.stations_nearby} CTA stations (${data.transit.station_names.slice(0, 3).join(', ')}), ~${Math.round(data.transit.total_daily_riders / 1000)}K daily riders.`,
    })
  }

  const reviews = data.reviews || []
  const ratings = reviews.map(r => (r.metadata?.rating as number) || 0).filter(r => r > 0)
  if (ratings.length >= 3) {
    const avgRating = ratings.reduce((a, b) => a + b, 0) / ratings.length
    if (avgRating >= 4.0) {
      signals.push({
        title: 'High review ratings',
        detail: `${avgRating.toFixed(1)}/5 avg across ${ratings.length} businesses.`,
      })
    }
  }

  const insights = computeInsights(data, profile, 'conservative')
  for (const cat of insights.categories) {
    if (cat.score >= 65 && !signals.some(s => s.title.toLowerCase().includes(cat.name.toLowerCase()))) {
      signals.push({
        title: `${cat.name}: ${cat.score}/100`,
        detail: cat.claim,
      })
    }
  }

  return signals.slice(0, 5)
}

function extractAllRisks(data: NeighborhoodData, profile: UserProfile): Signal[] {
  const signals: Signal[] = []
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  if (isServiceBusiness && data.cctv) {
    const cameras = data.cctv.cameras || []
    const avgPeds = data.cctv.avg_pedestrians || 0
    if (cameras.length > 0 && avgPeds < 5) {
      signals.push({
        title: 'Low foot traffic',
        detail: `~${Math.round(avgPeds)} pedestrians/observation across ${cameras.length} cameras.`,
      })
    }
  }

  if (isServiceBusiness && data.demographics?.median_household_income) {
    const income = data.demographics.median_household_income
    if (income < 30000) {
      signals.push({
        title: 'Low-income area',
        detail: `Median household income ~$${Math.round(income / 1000)}K — limits premium service demand.`,
      })
    }
  }

  if (isFoodBusiness && data.reviews && data.reviews.length > 5) {
    const recentReviews = data.reviews.filter(r => {
      const metadata = r.metadata as Record<string, unknown>
      const raw = metadata?.raw_record as Record<string, unknown>
      const reviewDate = raw?.review_date || raw?.date
      if (!reviewDate) return false
      const daysSince = (Date.now() - new Date(reviewDate as string).getTime()) / (1000 * 60 * 60 * 24)
      return daysSince < 90
    }).length
    const recentPct = (recentReviews / data.reviews.length) * 100
    if (recentPct < 25) {
      signals.push({
        title: 'Declining review activity',
        detail: `Only ${recentReviews} of ${data.reviews.length} reviews from the last 90 days.`,
      })
    }
  }

  if (data.licenses.length > 30) {
    signals.push({
      title: 'Crowded market',
      detail: `${data.licenses.length} active business licenses in the area.`,
    })
  }

  if (isFoodBusiness && data.inspection_stats.total > 0) {
    const passRate = data.inspection_stats.passed / data.inspection_stats.total
    if (passRate < 0.6) {
      signals.push({
        title: 'Low inspection pass rate',
        detail: `${Math.round(passRate * 100)}% of ${data.inspection_stats.total} inspections passed.`,
      })
    }
  }

  if (!data.transit || data.transit.stations_nearby === 0) {
    signals.push({
      title: 'No nearby transit',
      detail: 'No CTA L-stations within range. Customers rely on driving or bus.',
    })
  }

  const fedCount = data.federal_register?.length || 0
  if (fedCount > 5) {
    signals.push({
      title: 'Federal regulatory pressure',
      detail: `${fedCount} recent SBA/FDA/OSHA/EPA regulations to review.`,
    })
  }

  const reviewCount = data.reviews?.length || 0
  if (reviewCount > 0 && reviewCount < 3) {
    signals.push({
      title: 'Sparse review data',
      detail: `Only ${reviewCount} review(s) — not enough for reliable market read.`,
    })
  }

  const insights = computeInsights(data, profile, 'conservative')
  for (const cat of insights.categories) {
    if (cat.score < 40 && !signals.some(s => s.title.toLowerCase().includes(cat.name.toLowerCase()))) {
      signals.push({
        title: `${cat.name}: ${cat.score}/100`,
        detail: cat.claim,
      })
    }
  }

  return signals.slice(0, 5)
}

interface Competitor {
  name: string
  type: string
  isDirect: boolean
}

function extractCompetitors(data: NeighborhoodData, profile: UserProfile): Competitor[] {
  const keywords = LICENSE_MAP[profile.business_type] || []
  const seen = new Set<string>()
  const competitors: Competitor[] = []

  for (const l of data.licenses) {
    const raw = l.metadata?.raw_record as Record<string, unknown> | undefined
    const name = (raw?.doing_business_as_name as string) || ''
    const desc = (raw?.license_description as string) || ''
    if (!name || seen.has(name)) continue
    seen.add(name)

    const isDirect = keywords.length > 0
      ? keywords.some(kw => desc.toLowerCase().includes(kw))
      : false

    competitors.push({ name, type: desc, isDirect })
  }

  // Sort: direct competitors first, then alphabetical
  competitors.sort((a, b) => {
    if (a.isDirect !== b.isDirect) return a.isDirect ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return competitors.slice(0, 8)
}

interface RegulatoryItem {
  name: string
  result: string
}

interface RegulatorySummary {
  passRate: number
  total: number
  passed: number
  failed: number
  recentInspections: RegulatoryItem[]
  permitBreakdown: { type: string; count: number }[]
  federalAlerts: { title: string; agency: string }[]
}

function extractRegulatory(data: NeighborhoodData): RegulatorySummary {
  const stats = data.inspection_stats
  const passRate = stats.total > 0 ? Math.round((stats.passed / stats.total) * 100) : 0

  // Recent inspections
  const recentInspections: RegulatoryItem[] = data.inspections
    .slice(0, 5)
    .map(i => {
      const raw = i.metadata?.raw_record as Record<string, unknown> | undefined
      return {
        name: (raw?.dba_name as string) || i.title || 'Unknown',
        result: (raw?.results as string) || 'N/A',
      }
    })

  // Permit breakdown by type
  const permitTypes: Record<string, number> = {}
  for (const p of data.permits) {
    const raw = p.metadata?.raw_record as Record<string, unknown> | undefined
    const type = (raw?.permit_type as string) || 'Other'
    permitTypes[type] = (permitTypes[type] || 0) + 1
  }
  const permitBreakdown = Object.entries(permitTypes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([type, count]) => ({ type, count }))

  // Federal register alerts
  const federalAlerts: { title: string; agency: string }[] = (data.federal_register || [])
    .slice(0, 3)
    .map((d: Document) => ({
      title: d.title || 'Untitled regulation',
      agency: (d.metadata?.agency as string) || 'Federal',
    }))

  return {
    passRate,
    total: stats.total,
    passed: stats.passed,
    failed: stats.failed,
    recentInspections,
    permitBreakdown,
    federalAlerts,
  }
}

interface MetricItem {
  label: string
  value: string
}

function extractMetrics(data: NeighborhoodData): MetricItem[] {
  const stats = data.inspection_stats
  const reviews = data.reviews || []
  const ratings = reviews.map(r => (r.metadata?.rating as number) || 0).filter(r => r > 0)
  const avgRating = ratings.length > 0 ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1) : '—'

  return [
    {
      label: 'Inspection Pass Rate',
      value: stats.total > 0 ? `${Math.round((stats.passed / stats.total) * 100)}%` : '—',
    },
    {
      label: 'Avg Review Rating',
      value: avgRating !== '—' ? `${avgRating}/5` : '—',
    },
    {
      label: 'Active Permits',
      value: `${data.permit_count}`,
    },
    {
      label: 'Business Licenses',
      value: `${data.license_count}`,
    },
    {
      label: 'Transit Score',
      value: data.transit ? `${data.transit.transit_score}` : '—',
    },
    {
      label: 'Population',
      value: data.demographics?.total_population
        ? data.demographics.total_population.toLocaleString()
        : '—',
    },
    {
      label: 'Median Income',
      value: data.demographics?.median_household_income
        ? `$${Math.round(data.demographics.median_household_income / 1000)}K`
        : '—',
    },
    {
      label: 'Review Count',
      value: `${reviews.length}`,
    },
  ]
}

interface SourceCount {
  name: string
  count: number
}

function extractSources(data: NeighborhoodData): { sources: SourceCount[]; total: number } {
  const raw: [string, number][] = [
    ['News', data.news?.length || 0],
    ['Politics', data.politics?.length || 0],
    ['Reddit', data.reddit?.length || 0],
    ['Reviews', data.reviews?.length || 0],
    ['Real Estate', data.realestate?.length || 0],
    ['TikTok', data.tiktok?.length || 0],
    ['Traffic', data.traffic?.length || 0],
    ['Federal Register', data.federal_register?.length || 0],
    ['Inspections', data.inspections?.length || 0],
    ['Permits', data.permits?.length || 0],
    ['Licenses', data.licenses?.length || 0],
  ]

  const sources = raw
    .filter(([, count]) => count > 0)
    .map(([name, count]) => ({ name, count }))

  const total = sources.reduce((sum, s) => sum + s.count, 0)
  return { sources, total }
}

function buildExecutiveSummary(insights: ReturnType<typeof computeInsights>): string {
  const overall = insights.overall
  const cats = [...insights.categories].sort((a, b) => b.score - a.score)
  const strongest = cats[0]
  const weakest = cats[cats.length - 1]

  const verdict = overall >= 65 ? 'Favorable' : overall >= 40 ? 'Mixed signals' : 'Unfavorable'

  let summary = `${verdict} — ${overall}/100 across ${insights.coverageCount} categories.`

  if (strongest) {
    summary += ` Best signal: ${strongest.name} (${strongest.score})`
    if (weakest && weakest.score < 40) {
      summary += `; weakest: ${weakest.name} (${weakest.score}).`
    } else {
      summary += '; no major red flags.'
    }
  }

  return summary
}

// ── Score color helpers ─────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 65) return 'text-emerald-400'
  if (score >= 40) return 'text-amber-400'
  return 'text-red-400'
}

function scoreBorderColor(score: number): string {
  if (score >= 65) return 'border-emerald-500/30'
  if (score >= 40) return 'border-amber-500/30'
  return 'border-red-500/30'
}

function scoreBgColor(score: number): string {
  if (score >= 65) return 'bg-emerald-500/[0.08]'
  if (score >= 40) return 'bg-amber-500/[0.08]'
  return 'bg-red-500/[0.08]'
}

// ── PDF Generation ──────────────────────────────────────────────────

function generatePdf(
  profile: UserProfile,
  insights: ReturnType<typeof computeInsights>,
  advantages: Signal[],
  risks: Signal[],
  competitors: Competitor[],
  regulatory: RegulatorySummary,
  metrics: MetricItem[],
  sourcesData: { sources: SourceCount[]; total: number },
  neighborhoodData: NeighborhoodData,
) {
  const doc = new jsPDF({ unit: 'pt', format: 'letter' })
  const marginX = 72 // 1 inch margins
  const topMargin = 72
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const contentWidth = pageWidth - marginX * 2
  let y = topMargin
  const dateLabel = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })

  // Generate reference number: ALT-{NEIGHBORHOOD_4CHARS}-{HASH}
  const nbrCode = profile.neighborhood.replace(/\s/g, '').substring(0, 4).toUpperCase()
  const hashSrc = `${profile.neighborhood}-${profile.business_type}-${Date.now()}`
  let hash = 0
  for (let i = 0; i < hashSrc.length; i++) hash = ((hash << 5) - hash + hashSrc.charCodeAt(i)) | 0
  const refNumber = `ALT-${nbrCode}-${Math.abs(hash).toString(16).substring(0, 6).toUpperCase()}`

  // ── Formatting helpers ──

  const addPageHeader = () => {
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(7)
    doc.setTextColor(180, 40, 40)
    doc.text('CONFIDENTIAL', marginX, 36)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7)
    doc.setTextColor(140, 140, 140)
    doc.text(refNumber, pageWidth - marginX, 36, { align: 'right' })
    doc.setDrawColor(180, 180, 180)
    doc.setLineWidth(0.5)
    doc.line(marginX, 42, pageWidth - marginX, 42)
    doc.setTextColor(0, 0, 0)
  }

  const addFooterFinal = (page: number, total: number) => {
    doc.setDrawColor(180, 180, 180)
    doc.setLineWidth(0.5)
    doc.line(marginX, pageHeight - 40, pageWidth - marginX, pageHeight - 40)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7)
    doc.setTextColor(140, 140, 140)
    doc.text('Confidential \u2014 Prepared by Alethia Intelligence Platform', marginX, pageHeight - 28)
    doc.text(`Page ${page} of ${total}`, pageWidth - marginX, pageHeight - 28, { align: 'right' })
    doc.setTextColor(0, 0, 0)
  }

  const newPage = () => {
    doc.addPage()
    y = topMargin
    addPageHeader()
  }

  const ensureSpace = (minHeight = 30) => {
    if (y + minHeight > pageHeight - 56) {
      newPage()
    }
  }

  const addSection = (num: number, title: string) => {
    ensureSpace(44)
    // Thick rule
    doc.setDrawColor(40, 40, 40)
    doc.setLineWidth(1.5)
    doc.line(marginX, y, marginX + contentWidth, y)
    y += 14
    // Section label
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8)
    doc.setTextColor(120, 120, 120)
    doc.text(`SECTION ${num}`, marginX, y)
    y += 16
    // Title
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(14)
    doc.setTextColor(40, 40, 40)
    doc.text(title, marginX, y)
    doc.setTextColor(0, 0, 0)
    y += 22
  }

  const addSubheading = (text: string) => {
    ensureSpace(22)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(10)
    doc.setTextColor(40, 40, 40)
    doc.text(text, marginX, y)
    doc.setTextColor(0, 0, 0)
    y += 14
  }

  const addParagraph = (text: string, size = 9.5) => {
    const lineHeight = size * 1.5
    const lines: string[] = doc.splitTextToSize(text, contentWidth)
    ensureSpace(lines.length * lineHeight + 6)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(size)
    doc.setTextColor(40, 40, 40)
    for (const line of lines) {
      doc.text(line, marginX, y)
      y += lineHeight
    }
    y += 6
    doc.setTextColor(0, 0, 0)
  }

  const addBullet = (text: string) => {
    // Split on first colon or em-dash to get label and detail
    const colonIdx = text.indexOf(': ')
    const label = colonIdx > 0 ? text.substring(0, colonIdx) : ''
    const detail = colonIdx > 0 ? text.substring(colonIdx + 2) : text
    const display = label ? `${label} \u2014 ${detail}` : text
    const wrapped: string[] = doc.splitTextToSize(display, contentWidth - 14)
    ensureSpace(wrapped.length * 13 + 4)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9.5)
    doc.setTextColor(40, 40, 40)
    doc.text('\u2022', marginX, y)
    doc.text(wrapped, marginX + 12, y)
    y += wrapped.length * 13 + 4
    doc.setTextColor(0, 0, 0)
  }

  const addMetricRow = (label: string, value: string) => {
    ensureSpace(16)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9.5)
    doc.setTextColor(40, 40, 40)
    doc.text(label, marginX + 12, y)
    doc.setFont('helvetica', 'bold')
    doc.text(value, marginX + contentWidth - 10, y, { align: 'right' })
    // Thin gray underline
    doc.setDrawColor(221, 221, 221)
    doc.setLineWidth(0.3)
    doc.line(marginX + 12, y + 4, marginX + contentWidth - 10, y + 4)
    doc.setTextColor(0, 0, 0)
    y += 16
  }

  const addTable = (headers: string[], rows: string[][], colWidths: number[]) => {
    const rowHeight = 18
    const headerHeight = 20
    const fontSize = 8.5
    const totalRows = rows.length + 1 // +1 for header
    const tableHeight = headerHeight + rows.length * rowHeight
    ensureSpace(Math.min(tableHeight, headerHeight + rowHeight * 3)) // at least header + 3 rows

    // Calculate x positions
    const colX: number[] = [marginX]
    for (let i = 1; i < colWidths.length; i++) {
      colX.push(colX[i - 1] + colWidths[i - 1])
    }
    const tableWidth = colWidths.reduce((a, b) => a + b, 0)

    // Header row
    doc.setFillColor(240, 240, 240)
    doc.rect(marginX, y, tableWidth, headerHeight, 'F')
    doc.setDrawColor(180, 180, 180)
    doc.setLineWidth(0.5)
    doc.rect(marginX, y, tableWidth, headerHeight, 'S')
    // Header cell borders
    for (let c = 1; c < colWidths.length; c++) {
      doc.line(colX[c], y, colX[c], y + headerHeight)
    }
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(fontSize)
    doc.setTextColor(40, 40, 40)
    for (let c = 0; c < headers.length; c++) {
      doc.text(headers[c], colX[c] + 6, y + 13)
    }
    y += headerHeight

    // Data rows
    for (let r = 0; r < rows.length; r++) {
      ensureSpace(rowHeight + 4)
      // Alternating row shading
      if (r % 2 === 1) {
        doc.setFillColor(248, 248, 248)
        doc.rect(marginX, y, tableWidth, rowHeight, 'F')
      }
      doc.setDrawColor(200, 200, 200)
      doc.setLineWidth(0.3)
      doc.rect(marginX, y, tableWidth, rowHeight, 'S')
      // Cell borders
      for (let c = 1; c < colWidths.length; c++) {
        doc.line(colX[c], y, colX[c], y + rowHeight)
      }
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(fontSize)
      doc.setTextColor(40, 40, 40)
      for (let c = 0; c < rows[r].length; c++) {
        const cellText = rows[r][c]
        const maxCellWidth = colWidths[c] - 12
        const truncated = doc.splitTextToSize(cellText, maxCellWidth)[0] || ''
        doc.text(truncated, colX[c] + 6, y + 12)
      }
      y += rowHeight
    }
    // Suppress unused totalRows warning
    void totalRows
    y += 8
    doc.setTextColor(0, 0, 0)
  }

  // ── Cover Page ──

  // CONFIDENTIAL marking
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(11)
  doc.setTextColor(180, 40, 40)
  doc.text('CONFIDENTIAL', pageWidth / 2, 72, { align: 'center' })
  doc.setTextColor(0, 0, 0)

  // Double rule (thick + thin)
  y = 88
  doc.setDrawColor(40, 40, 40)
  doc.setLineWidth(2)
  doc.line(marginX, y, pageWidth - marginX, y)
  doc.setLineWidth(0.5)
  doc.line(marginX, y + 5, pageWidth - marginX, y + 5)

  // Main title
  y = 180
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(22)
  doc.setTextColor(40, 40, 40)
  doc.text('Location Intelligence', pageWidth / 2, y, { align: 'center' })
  y += 28
  doc.text('Assessment Report', pageWidth / 2, y, { align: 'center' })

  // Short centered rule
  y += 24
  const ruleLen = 140
  doc.setDrawColor(160, 160, 160)
  doc.setLineWidth(0.5)
  doc.line(pageWidth / 2 - ruleLen / 2, y, pageWidth / 2 + ruleLen / 2, y)

  // Business type + neighborhood
  y += 28
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(12)
  doc.setTextColor(60, 60, 60)
  doc.text(`${profile.business_type} \u2014 ${profile.neighborhood}, Chicago, IL`, pageWidth / 2, y, { align: 'center' })

  // Large score
  y += 52
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(48)
  doc.setTextColor(40, 40, 40)
  doc.text(`${insights.overall}`, pageWidth / 2, y, { align: 'center' })
  y += 20
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(120, 120, 120)
  doc.text('BUSINESS INTELLIGENCE SCORE (0\u2013100)', pageWidth / 2, y, { align: 'center' })

  // Info grid: PREPARED BY / DATE / REFERENCE / RISK PROFILE
  y += 56
  const leftCol = marginX + 40
  const rightCol = pageWidth / 2 + 40
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(7.5)
  doc.setTextColor(140, 140, 140)
  doc.text('PREPARED BY', leftCol, y)
  doc.text('DATE', rightCol, y)
  y += 14
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.setTextColor(40, 40, 40)
  doc.text('Alethia Intelligence Platform', leftCol, y)
  doc.text(dateLabel, rightCol, y)
  y += 24
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(7.5)
  doc.setTextColor(140, 140, 140)
  doc.text('REFERENCE', leftCol, y)
  doc.text('RISK PROFILE', rightCol, y)
  y += 14
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.setTextColor(40, 40, 40)
  doc.text(refNumber, leftCol, y)
  doc.text(insights.profile.charAt(0).toUpperCase() + insights.profile.slice(1), rightCol, y)

  // Bottom double rule
  const bottomRuleY = pageHeight - 100
  doc.setDrawColor(40, 40, 40)
  doc.setLineWidth(0.5)
  doc.line(marginX, bottomRuleY, pageWidth - marginX, bottomRuleY)
  doc.setLineWidth(2)
  doc.line(marginX, bottomRuleY + 5, pageWidth - marginX, bottomRuleY + 5)

  // Proprietary notice
  doc.setFont('helvetica', 'italic')
  doc.setFontSize(7.5)
  doc.setTextColor(120, 120, 120)
  const noticeLines: string[] = doc.splitTextToSize(
    'This document contains proprietary analysis and is intended solely for the use of the addressee.',
    contentWidth - 40,
  )
  doc.text(noticeLines, pageWidth / 2, bottomRuleY + 20, { align: 'center' })
  doc.setTextColor(0, 0, 0)

  // ── Section 1: Executive Summary ──
  newPage()
  addSection(1, 'Executive Summary')

  const verdict = insights.overall >= 65 ? 'Favorable' : insights.overall >= 40 ? 'Mixed signals' : 'Unfavorable'
  const strongest = [...insights.categories].sort((a, b) => b.score - a.score)[0]
  const summaryText = `${verdict} for a ${profile.business_type} in ${profile.neighborhood}. Score: ${insights.overall}/100 (${insights.profile} profile, ${insights.coverageCount}/6 categories scored).${strongest ? ` Best signal: ${strongest.name} (${strongest.score}/100).` : ''}`
  addParagraph(summaryText)

  // Category Scores table
  if (insights.categories.length > 0) {
    y += 4
    addSubheading('Category Scores')
    const catHeaders = ['Category', 'Score', 'Assessment']
    const catRows = [...insights.categories]
      .sort((a, b) => b.score - a.score)
      .map(c => [c.name, `${c.score}/100`, c.claim])
    const catWidths = [contentWidth * 0.22, contentWidth * 0.15, contentWidth * 0.63]
    addTable(catHeaders, catRows, catWidths)
  }

  if (advantages.length > 0) {
    y += 4
    addSubheading('Key Advantages')
    advantages.slice(0, 3).forEach(s => addBullet(`${s.title}: ${s.detail}`))
  }
  if (risks.length > 0) {
    y += 4
    addSubheading('Key Risks')
    risks.slice(0, 3).forEach(s => addBullet(`${s.title}: ${s.detail}`))
  }

  // ── Section 2: Labor Market Analytics ──
  addSection(2, 'Labor Market Analytics')
  const demo = neighborhoodData.demographics
  if (demo) {
    addSubheading('Talent Supply')
    addMetricRow('Population within neighborhood', demo.total_population ? demo.total_population.toLocaleString() : 'N/A')
    addMetricRow('Median age', demo.median_age ? `${demo.median_age} years` : 'N/A')
    y += 6
    addSubheading('Wage Indicator')
    addMetricRow('Median household income', demo.median_household_income ? `$${Math.round(demo.median_household_income).toLocaleString()}` : 'N/A')
    addMetricRow('Unemployment rate', demo.unemployment_rate != null ? `${(demo.unemployment_rate * 100).toFixed(1)}%` : 'N/A')
    y += 6
    addSubheading('Education Profile')
    addMetricRow("Bachelor's degree holders", demo.bachelors_degree != null ? `${(demo.bachelors_degree * 100).toFixed(1)}%` : 'N/A')
    addMetricRow("Master's degree holders", demo.masters_degree != null ? `${(demo.masters_degree * 100).toFixed(1)}%` : 'N/A')
    y += 6
    addSubheading('Competition for Talent')
    addMetricRow('Active business licenses (labor competition proxy)', `${neighborhoodData.license_count}`)
  } else {
    addParagraph('Demographic data not available for this neighborhood.')
  }

  // ── Section 3: Competitive Landscape ──
  addSection(3, 'Competitive Landscape')
  const directCount = competitors.filter(c => c.isDirect).length
  addMetricRow('Total business licenses in area', `${neighborhoodData.license_count}`)
  addMetricRow('Direct competitors identified', `${directCount}`)
  const reviews = neighborhoodData.reviews || []
  const ratings = reviews.map(r => (r.metadata?.rating as number) || 0).filter(r => r > 0)
  const avgRating = ratings.length > 0 ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1) : 'N/A'
  addMetricRow('Average competitor review rating', avgRating !== 'N/A' ? `${avgRating}/5` : 'N/A')
  y += 6
  if (competitors.length > 0) {
    addSubheading('Notable Competitors')
    const compHeaders = ['Business Name', 'License Type', 'Competitor Type']
    const compRows = competitors.map(c => [c.name, c.type, c.isDirect ? 'DIRECT' : 'Indirect'])
    const compWidths = [contentWidth * 0.38, contentWidth * 0.38, contentWidth * 0.24]
    addTable(compHeaders, compRows, compWidths)
  } else {
    addParagraph('No competitor data available.')
  }

  // ── Section 4: Operational Cost Modeling ──
  addSection(4, 'Operational Cost Modeling')
  if (demo) {
    addSubheading('Real Estate Signal')
    addMetricRow('Median gross rent', demo.median_gross_rent ? `$${Math.round(demo.median_gross_rent).toLocaleString()}/mo` : 'N/A')
    addMetricRow('Median home value', demo.median_home_value ? `$${Math.round(demo.median_home_value).toLocaleString()}` : 'N/A')
    y += 6
  }
  addSubheading('Permit Investment')
  const totalFees = neighborhoodData.permits.reduce((sum, p) => {
    const raw = p.metadata?.raw_record as Record<string, unknown> | undefined
    const fee = parseFloat(String(raw?.building_fee_paid || '0')) || 0
    return sum + fee
  }, 0)
  addMetricRow('Total building fees paid (recent permits)', totalFees > 0 ? `$${Math.round(totalFees).toLocaleString()}` : 'N/A')
  addMetricRow('Active permits', `${neighborhoodData.permit_count}`)
  if (regulatory.permitBreakdown.length > 0) {
    y += 4
    addSubheading('Permits by Type')
    const permitHeaders = ['Permit Type', 'Count']
    const permitRows = regulatory.permitBreakdown.map(p => [p.type, `${p.count}`])
    const permitWidths = [contentWidth * 0.75, contentWidth * 0.25]
    addTable(permitHeaders, permitRows, permitWidths)
  }

  // ── Section 5: Risk Assessment ──
  addSection(5, 'Risk Assessment')
  if (risks.length > 0) {
    risks.slice(0, 5).forEach(s => addBullet(`${s.title}: ${s.detail}`))
  } else {
    addParagraph('No dominant risks detected at this time.')
  }
  y += 6
  addSubheading('Inspection Compliance')
  addMetricRow('Inspection pass rate', `${regulatory.passRate}%`)
  addMetricRow('Total inspections', `${regulatory.total}`)
  addMetricRow('Failed inspections', `${regulatory.failed}`)
  if (regulatory.recentInspections.length > 0) {
    y += 4
    addSubheading('Recent Inspection Results')
    const inspHeaders = ['Establishment', 'Result']
    const inspRows = regulatory.recentInspections.map(i => [i.name, i.result])
    const inspWidths = [contentWidth * 0.65, contentWidth * 0.35]
    addTable(inspHeaders, inspRows, inspWidths)
  }
  if (regulatory.federalAlerts.length > 0) {
    y += 4
    addSubheading('Federal Regulatory Alerts')
    regulatory.federalAlerts.forEach(a => addBullet(`${a.title} (${a.agency})`))
  }
  // Flag BIS categories < 40
  const weakCategories = insights.categories.filter(c => c.score < 40)
  if (weakCategories.length > 0) {
    y += 4
    addSubheading('Low-Scoring Categories (< 40/100)')
    weakCategories.forEach(c => addBullet(`${c.name}: ${c.score}/100 \u2014 ${c.claim}`))
  }

  // ── Section 6: Incentive & Regulatory Environment ──
  addSection(6, 'Incentive & Regulatory Environment')
  addMetricRow('Inspection pass rate', `${regulatory.passRate}% (${regulatory.passed} pass / ${regulatory.total} total)`)
  addMetricRow('Political/legislative activity', `${neighborhoodData.politics.length} items`)
  addMetricRow('Federal register activity', `${(neighborhoodData.federal_register || []).length} regulations`)
  addMetricRow('News mentions', `${neighborhoodData.news.length} articles`)
  addMetricRow('Community signals (Reddit/TikTok)', `${(neighborhoodData.reddit?.length || 0) + (neighborhoodData.tiktok?.length || 0)} posts`)

  // ── Section 7: Accessibility & Transit ──
  addSection(7, 'Accessibility & Transit')
  const transit = neighborhoodData.transit
  if (transit) {
    addMetricRow('Transit score', `${transit.transit_score}/100`)
    addMetricRow('CTA stations nearby', `${transit.stations_nearby}`)
    addMetricRow('Total daily riders (nearby stations)', `${transit.total_daily_riders.toLocaleString()}`)
    if (transit.station_names.length > 0) {
      addBullet(`Stations: ${transit.station_names.join(', ')}`)
    }
  } else {
    addParagraph('No CTA transit data available for this neighborhood.')
  }
  const cctvCams = neighborhoodData.cctv?.cameras || []
  if (cctvCams.length > 0) {
    y += 4
    addSubheading('Highway Traffic Density')
    const avgVeh = Math.round(cctvCams.reduce((s, c) => s + c.vehicles, 0) / cctvCams.length)
    addMetricRow('Nearby cameras', `${cctvCams.length}`)
    addMetricRow('Avg vehicles per camera', `${avgVeh}`)
    addMetricRow('Density', neighborhoodData.cctv?.density || 'N/A')
  }

  // ── Section 8: Key Metrics Summary ──
  addSection(8, 'Key Metrics Summary')
  const colWidth = contentWidth / 2
  const cellGap = 6
  const cellW = colWidth - cellGap / 2
  const cellH = 36
  for (let i = 0; i < metrics.length; i += 2) {
    ensureSpace(cellH + 6)
    // Left cell
    doc.setDrawColor(200, 200, 200)
    doc.setLineWidth(0.5)
    doc.rect(marginX, y, cellW, cellH, 'S')
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7)
    doc.setTextColor(120, 120, 120)
    doc.text(metrics[i].label.toUpperCase(), marginX + 8, y + 12)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(13)
    doc.setTextColor(40, 40, 40)
    doc.text(metrics[i].value, marginX + 8, y + 28)
    // Right cell
    if (i + 1 < metrics.length) {
      const rx = marginX + cellW + cellGap
      doc.setDrawColor(200, 200, 200)
      doc.rect(rx, y, cellW, cellH, 'S')
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(7)
      doc.setTextColor(120, 120, 120)
      doc.text(metrics[i + 1].label.toUpperCase(), rx + 8, y + 12)
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(13)
      doc.setTextColor(40, 40, 40)
      doc.text(metrics[i + 1].value, rx + 8, y + 28)
    }
    y += cellH + 6
  }
  doc.setTextColor(0, 0, 0)

  // ── Section 9: Data Sources & Methodology ──
  addSection(9, 'Data Sources & Methodology')
  // Sources as bordered table
  const srcHeaders = ['Source', 'Documents']
  const srcRows = sourcesData.sources.map(s => [s.name, `${s.count}`])
  srcRows.push(['TOTAL', `${sourcesData.total}`])
  const srcWidths = [contentWidth * 0.7, contentWidth * 0.3]
  addTable(srcHeaders, srcRows, srcWidths)

  y += 4
  addParagraph(
    'Business Intelligence Score (BIS) is computed by Alethia across 6 categories: Regulatory, Economic, Market, Demographic, Safety, and Community. ' +
    'Each category is scored 0\u2013100 based on sub-metrics derived from live pipeline data. The overall score is a weighted average using the selected risk profile. ' +
    `This report was generated using the "${insights.profile}" risk profile with ${insights.coverageCount} of 6 categories scored.`,
    8.5,
  )

  // ── Disclaimer ──
  ensureSpace(120)
  y += 8
  doc.setDrawColor(40, 40, 40)
  doc.setLineWidth(1.5)
  doc.line(marginX, y, marginX + contentWidth, y)
  y += 18
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(10)
  doc.setTextColor(40, 40, 40)
  doc.text('DISCLAIMER', marginX, y)
  y += 16

  const disclaimerText =
    'This report is provided for informational purposes only and does not constitute legal, financial, or investment advice. ' +
    'The data and analysis contained herein have been derived from publicly available sources believed to be reliable; however, ' +
    'Alethia Intelligence Platform makes no representations or warranties, express or implied, as to the accuracy, completeness, ' +
    'or timeliness of the information. Recipients of this report should conduct their own independent due diligence and seek ' +
    'professional counsel before making any business, investment, or legal decisions based on the information provided. ' +
    'This document is confidential and intended solely for the use of the addressee. Any unauthorized distribution, reproduction, ' +
    'or use of this report is strictly prohibited.'
  const disclaimerLines: string[] = doc.splitTextToSize(disclaimerText, contentWidth)
  const disclaimerLineHeight = 10.5
  ensureSpace(disclaimerLines.length * disclaimerLineHeight + 10)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(7.5)
  doc.setTextColor(100, 100, 100)
  for (const line of disclaimerLines) {
    doc.text(line, marginX, y)
    y += disclaimerLineHeight
  }
  doc.setTextColor(0, 0, 0)

  // ── Final pass: add headers + footers to all pages ──
  const totalPages = doc.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i)
    if (i > 1) {
      addPageHeader()
    }
    addFooterFinal(i, totalPages)
  }

  const fileName = `alethia-proposal-${profile.neighborhood.toLowerCase().replaceAll(' ', '-')}-${profile.business_type.toLowerCase().replaceAll(' ', '-')}.pdf`
  doc.save(fileName)
}

// ── Component ───────────────────────────────────────────────────────

export default function LocationReportPanel({ profile, neighborhoodData, loading, agentInfo: _agentInfo }: Props) {
  const insights = neighborhoodData
    ? computeInsights(neighborhoodData, profile, 'conservative')
    : null

  const advantages = neighborhoodData ? extractAllAdvantages(neighborhoodData, profile) : []
  const risks = neighborhoodData ? extractAllRisks(neighborhoodData, profile) : []
  const competitors = neighborhoodData ? extractCompetitors(neighborhoodData, profile) : []
  const regulatory = neighborhoodData ? extractRegulatory(neighborhoodData) : null
  const metrics = neighborhoodData ? extractMetrics(neighborhoodData) : []
  const sourcesData = neighborhoodData ? extractSources(neighborhoodData) : { sources: [], total: 0 }

  const handleDownloadPdf = () => {
    if (loading || !insights || !neighborhoodData) return
    generatePdf(profile, insights, advantages, risks, competitors, regulatory!, metrics, sourcesData, neighborhoodData)
  }

  return (
    <section className="h-full flex flex-col border border-white/[0.06] bg-white/[0.02]">
      <div className="px-4 py-3 border-b border-white/[0.06] flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-white/35">Intelligence Brief</p>
          <h3 className="text-sm font-semibold text-white mt-1">{profile.business_type} • {profile.neighborhood}</h3>
        </div>
        <button
          type="button"
          onClick={handleDownloadPdf}
          disabled={loading}
          className="text-[10px] font-mono uppercase tracking-wider border border-white/20 px-2.5 py-1.5 text-white/75 hover:text-white hover:border-white/40 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors"
        >
          Download PDF
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading ? (
          <div className="text-xs text-white/40 font-mono">Generating intelligence brief from live pipeline signals…</div>
        ) : !neighborhoodData || !insights ? (
          <div className="text-xs text-white/40 font-mono">Select a neighborhood to generate intelligence brief.</div>
        ) : (
          <>
            {/* 1. Score Banner */}
            <div className={`border ${scoreBorderColor(insights.overall)} ${scoreBgColor(insights.overall)} p-4 text-center`}>
              <p className={`text-3xl font-bold ${scoreColor(insights.overall)}`}>{insights.overall}</p>
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/50 mt-1">
                Business Intelligence Score
              </p>
              <p className="text-[10px] text-white/40 mt-0.5">
                {insights.profile} profile • {insights.coverageCount} of 6 categories scored
              </p>
            </div>

            {/* 2. Verdict */}
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/35 mb-2">Verdict</p>
              <p className="text-[11px] text-white/70 leading-relaxed">
                {buildExecutiveSummary(insights)}
              </p>
            </div>

            {/* 3. Advantages */}
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-emerald-300/70 mb-2">
                Advantages {advantages.length > 0 && <span className="text-white/30">({advantages.length})</span>}
              </p>
              <div className="space-y-2">
                {advantages.length > 0 ? advantages.map((item) => (
                  <div key={item.title} className="border border-emerald-500/20 bg-emerald-500/[0.05] p-3">
                    <p className="text-xs font-semibold text-emerald-300">{item.title}</p>
                    <p className="text-[11px] text-white/65 mt-1 leading-relaxed">{item.detail}</p>
                  </div>
                )) : (
                  <p className="text-[11px] text-white/40">No clear advantages from available data.</p>
                )}
              </div>
            </div>

            {/* 4. Risks */}
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-amber-300/70 mb-2">
                Risks {risks.length > 0 && <span className="text-white/30">({risks.length})</span>}
              </p>
              <div className="space-y-2">
                {risks.length > 0 ? risks.map((item) => (
                  <div key={item.title} className="border border-amber-500/20 bg-amber-500/[0.05] p-3">
                    <p className="text-xs font-semibold text-amber-200">{item.title}</p>
                    <p className="text-[11px] text-white/65 mt-1 leading-relaxed">{item.detail}</p>
                  </div>
                )) : (
                  <p className="text-[11px] text-white/40">No major risks identified.</p>
                )}
              </div>
            </div>

            {/* 5. Competitive Landscape */}
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-blue-300/70 mb-2">
                Competitive Landscape {competitors.length > 0 && <span className="text-white/30">({competitors.length})</span>}
              </p>
              {competitors.length > 0 ? (
                <div className="space-y-1">
                  {competitors.map((c) => (
                    <div key={c.name} className="flex items-start gap-2 text-[11px]">
                      <span className={`mt-0.5 shrink-0 w-1.5 h-1.5 rounded-full ${c.isDirect ? 'bg-red-400' : 'bg-white/20'}`} />
                      <div>
                        <span className="text-white/80">{c.name}</span>
                        <span className="text-white/35 ml-1.5">{c.type}</span>
                        {c.isDirect && <span className="text-red-400/80 ml-1.5 text-[9px] font-mono uppercase">Direct</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-white/40 italic">No competitor data available.</p>
              )}
            </div>

            {/* 6. Regulatory Checklist */}
            {regulatory && (
              <div>
                <p className="text-[10px] font-mono uppercase tracking-wider text-violet-300/70 mb-2">Regulatory Checklist</p>
                <div className="space-y-3">
                  {/* Inspection pass rate */}
                  <div className="border border-white/[0.06] bg-white/[0.02] p-3">
                    <p className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1">Inspections</p>
                    <p className="text-sm font-semibold text-white/90">
                      {regulatory.passRate}% pass rate
                      <span className="text-[10px] text-white/40 font-normal ml-2">
                        ({regulatory.passed}/{regulatory.total} passed, {regulatory.failed} failed)
                      </span>
                    </p>
                    {regulatory.recentInspections.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {regulatory.recentInspections.map((i, idx) => (
                          <div key={idx} className="flex justify-between text-[10px]">
                            <span className="text-white/60 truncate mr-2">{i.name}</span>
                            <span className={`shrink-0 font-mono ${i.result.toLowerCase().includes('pass') ? 'text-emerald-400/70' : i.result.toLowerCase().includes('fail') ? 'text-red-400/70' : 'text-white/40'}`}>
                              {i.result}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Permits by type */}
                  {regulatory.permitBreakdown.length > 0 && (
                    <div className="border border-white/[0.06] bg-white/[0.02] p-3">
                      <p className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1">Permits by Type</p>
                      <div className="space-y-1">
                        {regulatory.permitBreakdown.map((p) => (
                          <div key={p.type} className="flex justify-between text-[10px]">
                            <span className="text-white/60">{p.type}</span>
                            <span className="text-white/40 font-mono">{p.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Federal alerts */}
                  {regulatory.federalAlerts.length > 0 && (
                    <div className="border border-red-500/10 bg-red-500/[0.03] p-3">
                      <p className="text-[10px] font-mono uppercase tracking-wider text-red-300/60 mb-1">Federal Regulation Alerts</p>
                      <div className="space-y-1.5">
                        {regulatory.federalAlerts.map((a, idx) => (
                          <div key={idx} className="text-[10px]">
                            <p className="text-white/70">{a.title}</p>
                            <p className="text-white/30">{a.agency}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 7. Key Metrics Grid */}
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/35 mb-2">Key Metrics</p>
              <div className="grid grid-cols-2 gap-2">
                {metrics.map((m) => (
                  <div key={m.label} className="border border-white/[0.06] bg-white/[0.02] p-2.5">
                    <p className="text-[10px] text-white/40 font-mono truncate">{m.label}</p>
                    <p className="text-sm font-semibold text-white/90 mt-0.5">{m.value}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* 8. Data Sources */}
            <div className="pt-3 border-t border-white/[0.06]">
              <p className="text-[10px] font-mono text-white/25">
                {sourcesData.total} documents analyzed across {sourcesData.sources.length} sources
              </p>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
