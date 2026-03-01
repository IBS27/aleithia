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

  // Service businesses: good population base
  if (isServiceBusiness && data.demographics) {
    const d = data.demographics
    if (d.total_population && d.total_population > 5000) {
      signals.push({
        title: 'Strong resident base supports repeat customer potential',
        detail: `Neighborhood has ~${Math.round(d.total_population / 1000)}K residents, creating a stable foundation for walk-in and repeat service business.`,
      })
    }
  }

  // Real estate activity
  const realestate = data.realestate?.length || 0
  if (realestate > 3) {
    signals.push({
      title: 'Recent real estate activity signals neighborhood growth',
      detail: `${realestate} active real estate listings indicate ongoing residential or commercial interest in the area.`,
    })
  }

  // Food/beverage: media presence
  if (isFoodBusiness) {
    const newsCount = data.news?.length || 0
    if (newsCount > 5) {
      signals.push({
        title: 'Neighborhood has visible media presence',
        detail: `${newsCount} recent local news mentions indicate visitor traffic potential and community awareness.`,
      })
    }
  }

  // Diverse license ecosystem
  const uniqueLicenseTypes = new Set(
    data.licenses.map(l => (l.metadata?.raw_record as Record<string, unknown>)?.license_description || '').filter(Boolean)
  )
  if (uniqueLicenseTypes.size > 15) {
    signals.push({
      title: 'Diverse business ecosystem suggests commercial stability',
      detail: `${uniqueLicenseTypes.size} different business types operate in the neighborhood, indicating established commercial infrastructure.`,
    })
  }

  // Transit access
  if (data.transit && data.transit.stations_nearby >= 2) {
    signals.push({
      title: 'Strong transit access drives foot traffic',
      detail: `${data.transit.stations_nearby} CTA stations nearby (${data.transit.station_names.slice(0, 3).join(', ')}) with ~${Math.round(data.transit.total_daily_riders / 1000)}K daily riders.`,
    })
  }

  // Strong review ratings
  const reviews = data.reviews || []
  const ratings = reviews.map(r => (r.metadata?.rating as number) || 0).filter(r => r > 0)
  if (ratings.length >= 3) {
    const avgRating = ratings.reduce((a, b) => a + b, 0) / ratings.length
    if (avgRating >= 4.0) {
      signals.push({
        title: 'Area businesses enjoy strong customer satisfaction',
        detail: `Average rating ${avgRating.toFixed(1)}/5 across ${ratings.length} reviewed businesses suggests a positive consumer perception of the neighborhood.`,
      })
    }
  }

  // Category-driven positives
  const insights = computeInsights(data, profile, 'conservative')
  for (const cat of insights.categories) {
    if (cat.score >= 65 && !signals.some(s => s.title.toLowerCase().includes(cat.name.toLowerCase()))) {
      signals.push({
        title: `${cat.name}: ${cat.signalLabel}`,
        detail: `${cat.claim} (Score: ${cat.score}/100).`,
      })
    }
  }

  return signals.slice(0, 5)
}

function extractAllRisks(data: NeighborhoodData, profile: UserProfile): Signal[] {
  const signals: Signal[] = []
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  // Low foot traffic for service businesses
  if (isServiceBusiness && data.cctv) {
    const cameras = data.cctv.cameras || []
    const avgPeds = data.cctv.avg_pedestrians || 0
    if (cameras.length > 0 && avgPeds < 5) {
      signals.push({
        title: 'Observed foot traffic too low for walk-in service business',
        detail: `Average pedestrian count ~${Math.round(avgPeds)}/observation across ${cameras.length} cameras; service businesses typically need 10+ for sustainable walk-in volume.`,
      })
    }
  }

  // Income mismatch for service businesses
  if (isServiceBusiness && data.demographics?.median_household_income) {
    const income = data.demographics.median_household_income
    if (income < 30000) {
      signals.push({
        title: 'Local income levels may limit premium service demand',
        detail: `Median household income ~$${Math.round(income / 1000)}K suggests predominantly price-sensitive customer base; premium services may struggle.`,
      })
    }
  }

  // Declining review activity for food businesses
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
        title: 'Review activity declining; weak market engagement signal',
        detail: `Only ${recentReviews} of ${data.reviews.length} reviews are recent (< 90 days); suggests weakening customer interest.`,
      })
    }
  }

  // High competitor density
  if (data.licenses.length > 30) {
    signals.push({
      title: 'Very high competitor density may compress profit margins',
      detail: `${data.licenses.length} active business licenses suggest intense local competition; differentiation becomes critical.`,
    })
  }

  // Low food safety compliance
  if (isFoodBusiness && data.inspection_stats.total > 0) {
    const passRate = data.inspection_stats.passed / data.inspection_stats.total
    if (passRate < 0.6) {
      signals.push({
        title: 'Area shows low food safety compliance baseline',
        detail: `Only ${Math.round(passRate * 100)}% of ${data.inspection_stats.total} inspections passed; suggests regulatory compliance challenges.`,
      })
    }
  }

  // No transit access
  if (!data.transit || data.transit.stations_nearby === 0) {
    signals.push({
      title: 'No nearby CTA stations limits walk-in potential',
      detail: 'No CTA L-stations found within range; customers will rely primarily on driving or bus transit.',
    })
  }

  // Federal regulatory pressure
  const fedCount = data.federal_register?.length || 0
  if (fedCount > 5) {
    signals.push({
      title: 'Elevated federal regulatory activity',
      detail: `${fedCount} recent federal regulations may affect business operations; review SBA/FDA/OSHA/EPA alerts.`,
    })
  }

  // Limited review data
  const reviewCount = data.reviews?.length || 0
  if (reviewCount > 0 && reviewCount < 3) {
    signals.push({
      title: 'Limited review data reduces market confidence',
      detail: `Only ${reviewCount} review(s) available; insufficient for reliable market demand assessment.`,
    })
  }

  // Category-driven negatives
  const insights = computeInsights(data, profile, 'conservative')
  for (const cat of insights.categories) {
    if (cat.score < 40 && !signals.some(s => s.title.toLowerCase().includes(cat.name.toLowerCase()))) {
      signals.push({
        title: `${cat.name}: ${cat.signalLabel}`,
        detail: `${cat.claim} (Score: ${cat.score}/100).`,
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

  let sentence1: string
  if (overall >= 65) {
    sentence1 = `This location scores ${overall}/100 overall, indicating a favorable environment for business establishment.`
  } else if (overall >= 40) {
    sentence1 = `This location scores ${overall}/100 overall, suggesting moderate viability with areas that warrant further investigation.`
  } else {
    sentence1 = `This location scores ${overall}/100 overall, flagging significant challenges that require careful risk assessment.`
  }

  let sentence2 = ''
  if (strongest) {
    sentence2 = ` The strongest signal is ${strongest.name} (${strongest.score}/100): ${strongest.claim.split('—')[0].trim()}.`
  }

  let sentence3 = ''
  if (weakest && weakest.score < 40) {
    sentence3 = ` The primary concern is ${weakest.name} (${weakest.score}/100), which may need mitigation.`
  } else if (cats.length > 1) {
    sentence3 = ' All scored categories are at moderate or favorable levels.'
  }

  return sentence1 + sentence2 + sentence3
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
  const marginX = 50
  const topMargin = 60
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const contentWidth = pageWidth - marginX * 2
  let y = topMargin
  const dateLabel = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  const footerText = `Confidential — Prepared by Alethia | ${profile.neighborhood} | ${dateLabel}`

  const addFooter = () => {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7)
    doc.setTextColor(140, 140, 140)
    doc.text(footerText, pageWidth / 2, pageHeight - 24, { align: 'center' })
    doc.setTextColor(0, 0, 0)
  }

  const newPage = () => {
    doc.addPage()
    y = topMargin
    addFooter()
  }

  const ensureSpace = (minHeight = 30) => {
    if (y + minHeight > pageHeight - 50) {
      newPage()
    }
  }

  const addSectionNumber = (num: number, text: string) => {
    ensureSpace(32)
    // Thin divider line
    doc.setDrawColor(200, 200, 200)
    doc.setLineWidth(0.5)
    doc.line(marginX, y - 8, marginX + contentWidth, y - 8)
    y += 2
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(13)
    doc.text(`${num}. ${text}`, marginX, y)
    y += 20
  }

  const addSubheading = (text: string) => {
    ensureSpace(22)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(10)
    doc.text(text, marginX, y)
    y += 14
  }

  const addParagraph = (text: string, size = 9.5) => {
    const lines = doc.splitTextToSize(text, contentWidth)
    ensureSpace(lines.length * (size + 3) + 6)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(size)
    doc.text(lines, marginX, y)
    y += lines.length * (size + 3) + 6
  }

  const addBullet = (text: string) => {
    const wrapped = doc.splitTextToSize(text, contentWidth - 14)
    ensureSpace(wrapped.length * 12 + 4)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9.5)
    doc.text('\u2022', marginX, y)
    doc.text(wrapped, marginX + 12, y)
    y += wrapped.length * 12 + 4
  }

  const addMetricRow = (label: string, value: string) => {
    ensureSpace(14)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9.5)
    doc.text(label, marginX + 12, y)
    doc.setFont('helvetica', 'bold')
    doc.text(value, marginX + contentWidth - 10, y, { align: 'right' })
    y += 14
  }

  // ── Title Page ──
  y = pageHeight * 0.3
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(24)
  doc.text('Strategic Location Analysis', pageWidth / 2, y, { align: 'center' })
  y += 36
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(14)
  doc.text(`${profile.business_type} Opportunity — ${profile.neighborhood}, Chicago`, pageWidth / 2, y, { align: 'center' })
  y += 28
  doc.setFontSize(10)
  doc.setTextColor(100, 100, 100)
  doc.text(`Prepared by Alethia Intelligence Platform`, pageWidth / 2, y, { align: 'center' })
  y += 16
  doc.text(dateLabel, pageWidth / 2, y, { align: 'center' })
  doc.setTextColor(0, 0, 0)

  // Score badge on title page
  y += 40
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(36)
  doc.text(`${insights.overall}`, pageWidth / 2, y, { align: 'center' })
  y += 16
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.setTextColor(100, 100, 100)
  doc.text('Business Intelligence Score (0–100)', pageWidth / 2, y, { align: 'center' })
  doc.setTextColor(0, 0, 0)
  addFooter()

  // ── Section 1: Executive Summary ──
  newPage()
  addSectionNumber(1, 'Executive Summary')

  const recommendation = insights.overall >= 65 ? 'We recommend' : insights.overall >= 40 ? 'We conditionally recommend' : 'We caution against'
  const strongest = [...insights.categories].sort((a, b) => b.score - a.score)[0]
  const summaryText = `${recommendation} ${profile.neighborhood} for a ${profile.business_type} operation. Overall Business Intelligence Score: ${insights.overall}/100 (${insights.profile} profile, ${insights.coverageCount} of 6 categories scored). ${strongest ? `The strongest signal is ${strongest.name} (${strongest.score}/100).` : ''}`
  addParagraph(summaryText)

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
  addSectionNumber(2, 'Labor Market Analytics')
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
  addSectionNumber(3, 'Competitive Landscape')
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
    competitors.forEach(c => {
      const tag = c.isDirect ? ' [DIRECT]' : ''
      addBullet(`${c.name} — ${c.type}${tag}`)
    })
  } else {
    addParagraph('No competitor data available.')
  }

  // ── Section 4: Operational Cost Modeling ──
  addSectionNumber(4, 'Operational Cost Modeling')
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
    regulatory.permitBreakdown.forEach(p => addMetricRow(p.type, `${p.count}`))
  }

  // ── Section 5: Risk Assessment ──
  addSectionNumber(5, 'Risk Assessment')
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
    regulatory.recentInspections.forEach(i => addMetricRow(i.name, i.result))
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
    weakCategories.forEach(c => addBullet(`${c.name}: ${c.score}/100 — ${c.claim}`))
  }

  // ── Section 6: Incentive & Regulatory Environment ──
  addSectionNumber(6, 'Incentive & Regulatory Environment')
  addMetricRow('Inspection pass rate', `${regulatory.passRate}% (${regulatory.passed} pass / ${regulatory.total} total)`)
  addMetricRow('Political/legislative activity', `${neighborhoodData.politics.length} items`)
  addMetricRow('Federal register activity', `${(neighborhoodData.federal_register || []).length} regulations`)
  addMetricRow('News mentions', `${neighborhoodData.news.length} articles`)
  addMetricRow('Community signals (Reddit/TikTok)', `${(neighborhoodData.reddit?.length || 0) + (neighborhoodData.tiktok?.length || 0)} posts`)

  // ── Section 7: Accessibility & Transit ──
  addSectionNumber(7, 'Accessibility & Transit')
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
  addSectionNumber(8, 'Key Metrics Summary')
  // 2x4 table
  const colWidth = contentWidth / 2
  for (let i = 0; i < metrics.length; i += 2) {
    ensureSpace(28)
    // Left cell
    doc.setDrawColor(220, 220, 220)
    doc.setLineWidth(0.5)
    doc.rect(marginX, y - 10, colWidth - 4, 26)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8)
    doc.setTextColor(120, 120, 120)
    doc.text(metrics[i].label, marginX + 6, y - 1)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(11)
    doc.setTextColor(0, 0, 0)
    doc.text(metrics[i].value, marginX + 6, y + 12)
    // Right cell
    if (i + 1 < metrics.length) {
      doc.rect(marginX + colWidth + 4, y - 10, colWidth - 4, 26)
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(8)
      doc.setTextColor(120, 120, 120)
      doc.text(metrics[i + 1].label, marginX + colWidth + 10, y - 1)
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(11)
      doc.setTextColor(0, 0, 0)
      doc.text(metrics[i + 1].value, marginX + colWidth + 10, y + 12)
    }
    y += 32
  }

  // ── Section 9: Data Sources & Methodology ──
  addSectionNumber(9, 'Data Sources & Methodology')
  sourcesData.sources.forEach(s => addMetricRow(s.name, `${s.count} documents`))
  y += 4
  doc.setDrawColor(200, 200, 200)
  doc.setLineWidth(0.5)
  doc.line(marginX, y - 4, marginX + contentWidth, y - 4)
  addMetricRow('Total documents analyzed', `${sourcesData.total}`)
  y += 8
  addParagraph(
    'Business Intelligence Score (BIS) is computed by Alethia across 6 categories: Regulatory, Economic, Market, Demographic, Safety, and Community. ' +
    'Each category is scored 0–100 based on sub-metrics derived from live pipeline data. The overall score is a weighted average using the selected risk profile. ' +
    `This report was generated using the "${insights.profile}" risk profile with ${insights.coverageCount} of 6 categories scored.`,
    8.5,
  )

  // Add footer to all pages
  const totalPages = doc.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i)
    addFooter()
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

            {/* 2. Executive Summary */}
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/35 mb-2">Executive Summary</p>
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
                  <p className="text-[11px] text-white/40 italic">No strong advantages detected.</p>
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
                  <p className="text-[11px] text-white/40 italic">No dominant risks detected.</p>
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
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/35 mb-2">Data Sources</p>
              <div className="space-y-1">
                {sourcesData.sources.map((s) => (
                  <div key={s.name} className="flex justify-between text-[10px]">
                    <span className="text-white/60">{s.name}</span>
                    <span className="text-white/40 font-mono">{s.count}</span>
                  </div>
                ))}
                <div className="flex justify-between text-[10px] border-t border-white/[0.06] pt-1 mt-1">
                  <span className="text-white/70 font-semibold">Total</span>
                  <span className="text-white/50 font-mono font-semibold">{sourcesData.total}</span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
