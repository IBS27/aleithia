import { jsPDF } from 'jspdf'
import type { NeighborhoodData, RiskScore, UserProfile } from '../types/index.ts'
import { computeInsights } from '../insights.ts'

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

const CATEGORY_TITLES: Record<string, string> = {
  regulatory: 'Regulatory environment',
  economic: 'Economic momentum',
  market: 'Market demand and competition',
  demographic: 'Demographic fit',
  safety: 'Safety and access',
  community: 'Community momentum',
}

// Extract granular, business-specific advantages from raw data
function extractGranularAdvantage(data: NeighborhoodData, profile: UserProfile): Signal | null {
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  // Service businesses: check for good population base
  if (isServiceBusiness && data.demographics) {
    const d = data.demographics
    if (d.total_population && d.total_population > 5000) {
      return {
        title: 'Strong resident base supports repeat customer potential',
        detail: `Neighborhood has ~${Math.round(d.total_population / 1000)}K residents, creating a stable foundation for walk-in and repeat service business.`,
      }
    }
  }

  // Check for recent real estate activity (indicates neighborhood momentum)
  const realestate = (data.realestate?.length || 0)
  if (realestate > 3) {
    return {
      title: 'Recent real estate activity signals neighborhood growth',
      detail: `${realestate} active real estate listings indicate ongoing residential or commercial interest in the area.`,
    }
  }

  // Food/beverage: check for social/news visibility
  if (isFoodBusiness) {
    const newsCount = (data.news?.length || 0)
    if (newsCount > 5) {
      return {
        title: 'Neighborhood has visible media presence',
        detail: `${newsCount} recent local news mentions indicate visitor traffic potential and community awareness.`,
      }
    }
  }

  // Check for diverse license ecosystem (indicates commercial vitality)
  const uniqueLicenseTypes = new Set(
    data.licenses.map(l => (l.metadata?.raw_record as Record<string, unknown>)?.license_description || '').filter(Boolean)
  )
  if (uniqueLicenseTypes.size > 15) {
    return {
      title: 'Diverse business ecosystem suggests commercial stability',
      detail: `${uniqueLicenseTypes.size} different business types operate in the neighborhood, indicating established commercial infrastructure.`,
    }
  }

  return null
}

// Extract granular, business-specific risks from raw data
function extractGranularRisk(data: NeighborhoodData, profile: UserProfile): Signal | null {
  const isServiceBusiness = ['Salon', 'Barbershop', 'Gym'].includes(profile.business_type)
  const isFoodBusiness = ['Restaurant', 'Coffee Shop', 'Bar', 'Cafe'].includes(profile.business_type)

  // Service businesses: check for low foot traffic
  if (isServiceBusiness && data.cctv) {
    const cameras = data.cctv.cameras || []
    const avgPeds = data.cctv.avg_pedestrians || 0
    
    if (cameras.length > 0 && avgPeds < 5) {
      return {
        title: 'Observed foot traffic too low for walk-in service business',
        detail: `Average pedestrian count ~${Math.round(avgPeds)}/observation across ${cameras.length} cameras; service businesses typically need 10+ for sustainable walk-in volume.`,
      }
    }
  }

  // Service businesses: check for income mismatch
  if (isServiceBusiness && data.demographics && data.demographics.median_household_income) {
    const income = data.demographics.median_household_income
    if (income < 30000) {
      return {
        title: 'Local income levels may limit premium service demand',
        detail: `Median household income ~$${Math.round(income / 1000)}K suggests predominantly price-sensitive customer base; premium services may struggle.`,
      }
    }
  }

  // Food businesses: check for stale/declining review activity
  if (isFoodBusiness && data.reviews && data.reviews.length > 0) {
    const recentReviews = data.reviews.filter(r => {
      const metadata = r.metadata as Record<string, unknown>
      const raw = metadata?.raw_record as Record<string, unknown>
      const reviewDate = raw?.review_date || raw?.date
      if (!reviewDate) return false
      const daysSince = (Date.now() - new Date(reviewDate as string).getTime()) / (1000 * 60 * 60 * 24)
      return daysSince < 90
    }).length

    const totalReviews = data.reviews.length
    const recentPct = (recentReviews / totalReviews) * 100
    
    if (recentPct < 25 && totalReviews > 5) {
      return {
        title: 'Review activity declining; weak market engagement signal',
        detail: `Only ${recentReviews} of ${totalReviews} reviews are recent (< 90 days); suggests weakening customer interest or market presence.`,
      }
    }
  }

  // Generic: check for extreme competitor density
  const competitors = data.licenses.length
  if (competitors > 30) {
    return {
      title: 'Very high competitor density may compress profit margins',
      detail: `${competitors} active business licenses suggest intense local competition; differentiation becomes critical for viability.`,
    }
  }

  // Check for very low inspection pass rate (food safety risk)
  if (isFoodBusiness && data.inspection_stats.total > 0) {
    const passRate = data.inspection_stats.passed / data.inspection_stats.total
    if (passRate < 0.6) {
      return {
        title: 'Area shows low food safety compliance baseline',
        detail: `Only ${Math.round(passRate * 100)}% of ${data.inspection_stats.total} inspections passed; suggests regulatory compliance challenges in the market.`,
      }
    }
  }

  return null
}

function buildAdvantages(data: NeighborhoodData | null, profile: UserProfile): Signal[] {
  if (!data) return []

  // Try to extract a granular, data-driven advantage first
  const granularAdvantage = extractGranularAdvantage(data, profile)
  if (granularAdvantage) {
    return [granularAdvantage]
  }

  // Fall back to BIS-driven advantage
  const insights = computeInsights(data, profile, 'conservative')
  const positive = insights.categories
    .filter(cat => cat.signal !== 'negative')
    .sort((a, b) => b.score - a.score)

  if (positive.length > 0) {
    const strongest = positive[0]
    return [{
      title: CATEGORY_TITLES[strongest.id] ?? strongest.name,
      detail: `${strongest.claim} (Business Intelligence Score: ${strongest.score}/100).`,
    }]
  }

  return [{
    title: 'Limited favorable evidence',
    detail: 'Not enough scored categories show a strong upside signal yet; collect more ground-truth data before scaling.',
  }]
}

function buildRisks(data: NeighborhoodData | null, profile: UserProfile): Signal[] {
  if (!data) return []

  // Try to extract a granular, data-driven risk first
  const granularRisk = extractGranularRisk(data, profile)
  
  const insights = computeInsights(data, profile, 'conservative')
  
  // High-severity score-driven risks (actual negative/concerning scores)
  const scoreDrivenRisks = insights.categories
    .filter(cat => cat.signal === 'negative' || cat.score < 40)
    .sort((a, b) => a.score - b.score)

  // If we found a granular risk AND there are significant score-driven concerns, 
  // prioritize the score-driven one (real data > inference)
  if (scoreDrivenRisks.length > 0) {
    return [{
      title: CATEGORY_TITLES[scoreDrivenRisks[0].id] ?? scoreDrivenRisks[0].name,
      detail: `${scoreDrivenRisks[0].claim} (Business Intelligence Score: ${scoreDrivenRisks[0].score}/100).`,
    }]
  }

  // If no score-driven risks but granular risk found, use it
  if (granularRisk) {
    return [granularRisk]
  }

  // Fall back to neutral/monitoring signal
  const weakerSignals = insights.categories
    .filter(cat => cat.signal === 'neutral')
    .sort((a, b) => a.score - b.score)

  if (weakerSignals.length > 0) {
    return [{
      title: `${CATEGORY_TITLES[weakerSignals[0].id] ?? weakerSignals[0].name} requires validation`,
      detail: `${weakerSignals[0].claim} (Business Intelligence Score: ${weakerSignals[0].score}/100).`,
    }]
  }

  return [{
    title: 'No dominant risk detected',
    detail: 'No high-severity downside signal is currently dominant, but continue monitoring for data drift and execution risk.',
  }]
}

function safeNumber(value: number | undefined): string {
  return typeof value === 'number' ? `${value}` : 'N/A'
}

export default function LocationReportPanel({ profile, neighborhoodData, riskScore, loading, agentInfo: _agentInfo }: Props) {
  const advantages = buildAdvantages(neighborhoodData, profile)
  const risks = buildRisks(neighborhoodData, profile)
  const conservativeInsights = neighborhoodData
    ? computeInsights(neighborhoodData, profile, 'conservative')
    : null

  const handleDownloadPdf = () => {
    if (loading) return

    const doc = new jsPDF({ unit: 'pt', format: 'letter' })
    const marginX = 44
    const topMargin = 48
    const pageWidth = doc.internal.pageSize.getWidth()
    const pageHeight = doc.internal.pageSize.getHeight()
    const contentWidth = pageWidth - marginX * 2
    let y = topMargin

    const ensureSpace = (minHeight = 30) => {
      if (y + minHeight > pageHeight - 44) {
        doc.addPage()
        y = topMargin
      }
    }

    const addHeading = (text: string) => {
      ensureSpace(28)
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(14)
      doc.text(text, marginX, y)
      y += 18
    }

    const addParagraph = (text: string, size = 10) => {
      const lines = doc.splitTextToSize(text, contentWidth)
      ensureSpace(lines.length * (size + 3) + 6)
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(size)
      doc.text(lines, marginX, y)
      y += lines.length * (size + 3) + 6
    }

    const addBullet = (text: string) => {
      const wrapped = doc.splitTextToSize(text, contentWidth - 14)
      ensureSpace(wrapped.length * 13 + 4)
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(10)
      doc.text('•', marginX, y)
      doc.text(wrapped, marginX + 12, y)
      y += wrapped.length * 13 + 4
    }

    const dateLabel = new Date().toLocaleString()
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(18)
    doc.text('Alethia Report Summary', marginX, y)
    y += 22

    doc.setFont('helvetica', 'normal')
    doc.setFontSize(10)
    doc.text(`${profile.business_type} • ${profile.neighborhood}`, marginX, y)
    y += 14
    doc.text(`Generated: ${dateLabel}`, marginX, y)
    y += 16

    addHeading('Business Intelligence Score (Conservative Profile)')
    if (conservativeInsights) {
      addParagraph(`Overall score: ${conservativeInsights.overall}/100 across ${conservativeInsights.coverageCount} of 6 categories.`)
    } else {
      addParagraph('Business Intelligence Score is unavailable because neighborhood data has not loaded.')
    }

    addHeading('Top Advantages (BIS-Driven)')
    if (advantages.length > 0) {
      advantages.forEach((item) => addBullet(`${item.title}: ${item.detail}`))
    } else {
      addBullet('No strong upside concentration detected; proceed with controlled pilot testing.')
    }

    addHeading('Top Risks (BIS-Driven)')
    if (risks.length > 0) {
      risks.forEach((item) => addBullet(`${item.title}: ${item.detail}`))
    } else {
      addBullet('No single dominant risk detected; continue validation for category-specific constraints.')
    }

    addHeading('Category Breakdown')
    if (conservativeInsights && conservativeInsights.categories.length > 0) {
      const ranked = [...conservativeInsights.categories].sort((a, b) => b.score - a.score)
      ranked.forEach((cat) => {
        const label = CATEGORY_TITLES[cat.id] ?? cat.name
        addBullet(`${label}: ${cat.score}/100 (${cat.signalLabel}) — ${cat.claim}`)
      })
    } else {
      addBullet('No category-level Business Intelligence Scores are available for this location yet.')
    }

    addHeading('Data Snapshot')
    addBullet(`Food inspections: ${safeNumber(neighborhoodData?.inspection_stats.total)} total`)
    addBullet(`Building permits: ${safeNumber(neighborhoodData?.permit_count)}`)
    addBullet(`Business licenses: ${safeNumber(neighborhoodData?.license_count)}`)
    addBullet(`Intel items: ${(neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0)}`)
    addBullet(`Community signals: ${(neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0)}`)
    addBullet(`Market signals: ${(neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0)}`)
    addBullet(`CCTV cameras: ${safeNumber(neighborhoodData?.cctv?.cameras.length)}`)
    if (riskScore) {
      addBullet(`Risk score: ${riskScore.overall_score}/10 (confidence ${(riskScore.confidence * 100).toFixed(0)}%)`)
    }

    const fileName = `report-summary-${profile.neighborhood.toLowerCase().replaceAll(' ', '-')}-${profile.business_type.toLowerCase().replaceAll(' ', '-')}.pdf`
    doc.save(fileName)
  }

  return (
    <section className="h-full flex flex-col border border-white/[0.06] bg-white/[0.02]">
      <div className="px-4 py-3 border-b border-white/[0.06] flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-white/35">Report Summary</p>
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
          <div className="text-xs text-white/40 font-mono">Generating report from live pipeline signals…</div>
        ) : (
          <>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-emerald-300/70 mb-2">Advantages</p>
              <div className="space-y-2">
                {advantages.map((item) => (
                  <div key={item.title} className="border border-emerald-500/20 bg-emerald-500/[0.05] p-3">
                    <p className="text-xs font-semibold text-emerald-300">{item.title}</p>
                    <p className="text-[11px] text-white/65 mt-1 leading-relaxed">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-amber-300/70 mb-2">Risks</p>
              <div className="space-y-2">
                {risks.map((item) => (
                  <div key={item.title} className="border border-amber-500/20 bg-amber-500/[0.05] p-3">
                    <p className="text-xs font-semibold text-amber-200">{item.title}</p>
                    <p className="text-[11px] text-white/65 mt-1 leading-relaxed">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
