import { useState, useEffect } from 'react'
import { jsPDF } from 'jspdf'
import type { NeighborhoodData, RiskScore, UserProfile, StreetscapeData } from '../types/index.ts'
import { api } from '../api.ts'

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

function buildAdvantages(data: NeighborhoodData | null, streetscape?: StreetscapeData | null): Signal[] {
  if (!data) return []

  const items: Signal[] = []
  const stats = data.inspection_stats
  const passRate = stats.total > 0 ? stats.passed / stats.total : null
  const avgRating = data.metrics?.avg_review_rating ?? 0

  if (passRate !== null && passRate >= 0.8 && stats.total >= 5) {
    items.push({
      title: 'Strong compliance baseline',
      detail: `${Math.round(passRate * 100)}% pass rate across ${stats.total} nearby food inspections can reduce early operational friction.`,
    })
  }

  if (avgRating >= 4.0 && (data.reviews?.length || 0) >= 5) {
    items.push({
      title: 'Healthy customer sentiment',
      detail: `Area businesses average ${avgRating.toFixed(1)}/5 across ${data.reviews?.length || 0} reviews, indicating active demand with positive sentiment.`,
    })
  }

  if (data.cctv && data.cctv.cameras.length > 0 && (data.cctv.density === 'high' || data.cctv.density === 'medium')) {
    const peakNote = data.cctv.peak_hour != null
      ? `, peaking around ${data.cctv.peak_hour}:00`
      : ''
    items.push({
      title: 'Highway accessibility',
      detail: `${data.cctv.cameras.length} IDOT highway cameras report ${data.cctv.density} vehicle flow (~${Math.round(data.cctv.avg_vehicles)} avg vehicles${peakNote}), indicating strong transport corridor access.`,
    })
  }

  if (streetscape?.indicators?.vacancy_signal === 'moderate') {
    items.push({
      title: 'Available commercial space',
      detail: `Moderate vacancy detected (${streetscape.counts.for_lease_sign} for-lease signs) indicates room for new entrants without overcrowding.`,
    })
  }

  if (data.permit_count >= 8) {
    items.push({
      title: 'Growth and reinvestment signal',
      detail: `${data.permit_count} active permits suggest ongoing neighborhood investment and business momentum.`,
    })
  }

  if (items.length === 0) {
    items.push({
      title: 'Balanced baseline indicators',
      detail: 'Core public-data coverage is present, enabling a measured launch with targeted validation before expansion.',
    })
  }

  return items.slice(0, 3)
}

function buildRisks(data: NeighborhoodData | null, profile: UserProfile, streetscape?: StreetscapeData | null): Signal[] {
  if (!data) return []

  const items: Signal[] = []
  const stats = data.inspection_stats
  const failRate = stats.total > 0 ? stats.failed / stats.total : null
  const avgRating = data.metrics?.avg_review_rating ?? 0
  const congestedCount = (data.traffic || []).filter(t => {
    const level = (t.metadata?.congestion_level as string | undefined)?.toLowerCase()
    return level === 'heavy' || level === 'blocked'
  }).length

  if (failRate !== null && failRate >= 0.25 && stats.total >= 4) {
    items.push({
      title: 'Elevated compliance risk',
      detail: `${stats.failed} failed inspections out of ${stats.total} records (${Math.round(failRate * 100)}%) may signal stricter enforcement or operational complexity.`,
    })
  }

  if (data.license_count >= 20) {
    items.push({
      title: 'High local competition',
      detail: `${data.license_count} active business licenses in the area indicate a crowded market and a higher differentiation burden.`,
    })
  }

  if (congestedCount >= 2) {
    items.push({
      title: 'Traffic friction',
      detail: `${congestedCount} nearby heavily congested zones can affect delivery reliability and customer convenience.`,
    })
  }

  const isRestaurant = ['Restaurant', 'Coffee Shop', 'Bar'].includes(profile.business_type)
  if (streetscape?.indicators?.dining_saturation === 'high' && isRestaurant) {
    items.push({
      title: 'Saturated dining market',
      detail: `${streetscape.counts.restaurant_signage + streetscape.counts.outdoor_dining} dining indicators detected — high density may limit differentiation for food/beverage businesses.`,
    })
  }

  if (avgRating > 0 && avgRating < 3.8) {
    items.push({
      title: 'Mixed consumer sentiment',
      detail: `Average local rating is ${avgRating.toFixed(1)}/5, suggesting quality expectations may be difficult to exceed consistently.`,
    })
  }

  if (items.length === 0) {
    items.push({
      title: 'No dominant red flag detected',
      detail: 'Current signals do not show an extreme downside driver, but category-specific diligence is still recommended.',
    })
  }

  return items.slice(0, 3)
}

function buildSummary(profile: UserProfile, data: NeighborhoodData | null, riskScore: RiskScore | null): string {
  if (!data) {
    return `Preparing a location report for ${profile.business_type} in ${profile.neighborhood}.`
  }

  const totalSignals =
    data.inspection_stats.total +
    data.permit_count +
    data.license_count +
    (data.news.length || 0) +
    (data.politics.length || 0) +
    (data.reviews?.length || 0) +
    (data.traffic?.length || 0)

  const posture = riskScore
    ? riskScore.overall_score <= 4
      ? 'favorable'
      : riskScore.overall_score <= 7
        ? 'mixed'
        : 'higher-risk'
    : 'mixed'

  return `${profile.neighborhood} looks ${posture} for a ${profile.business_type.toLowerCase()} launch based on ${totalSignals} local signals. Prioritize quick validation on the highlighted risks while leveraging the strongest demand/compliance advantages.`
}

function safeNumber(value: number | undefined): string {
  return typeof value === 'number' ? `${value}` : 'N/A'
}

export default function LocationReportPanel({ profile, neighborhoodData, riskScore, loading, agentInfo }: Props) {
  const [streetscape, setStreetscape] = useState<StreetscapeData | null>(null)

  useEffect(() => {
    if (!profile.neighborhood) return
    api.streetscape(profile.neighborhood)
      .then(d => setStreetscape(d.counts ? d as StreetscapeData : null))
      .catch(() => setStreetscape(null))
  }, [profile.neighborhood])

  const advantages = buildAdvantages(neighborhoodData, streetscape)
  const risks = buildRisks(neighborhoodData, profile, streetscape)
  const summary = buildSummary(profile, neighborhoodData, riskScore)

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
    const rating = neighborhoodData?.metrics?.avg_review_rating
    const stats = neighborhoodData?.inspection_stats
    const passRate = stats && stats.total > 0 ? Math.round((stats.passed / stats.total) * 100) : null
    const failRate = stats && stats.total > 0 ? Math.round((stats.failed / stats.total) * 100) : null
    const congestedCount = (neighborhoodData?.traffic || []).filter((t) => {
      const level = (t.metadata?.congestion_level as string | undefined)?.toLowerCase()
      return level === 'heavy' || level === 'blocked'
    }).length

    const detailedAdvantages = [
      passRate !== null && stats
        ? `Regulatory baseline: ${stats.passed} of ${stats.total} inspections passed (${passRate}%), which may support smoother launch operations.`
        : null,
      typeof rating === 'number' && rating > 0
        ? `Demand signal: local review sentiment averages ${rating.toFixed(1)}/5 across ${neighborhoodData?.reviews?.length || 0} records.`
        : null,
      neighborhoodData?.cctv?.cameras.length
        ? `Highway access: ${neighborhoodData.cctv.cameras.length} IDOT cameras report ${neighborhoodData.cctv.density} vehicle flow with ~${Math.round(neighborhoodData.cctv.avg_vehicles)} average vehicles.`
        : null,
      neighborhoodData && neighborhoodData.permit_count > 0
        ? `Investment velocity: ${neighborhoodData.permit_count} active permits suggest current reinvestment in the area.`
        : null,
    ].filter((v): v is string => Boolean(v))

    const detailedRisks = [
      failRate !== null && stats
        ? `Compliance exposure: ${stats.failed} failed inspections out of ${stats.total} (${failRate}%) may indicate tighter enforcement expectations.`
        : null,
      neighborhoodData && neighborhoodData.license_count > 0
        ? `Competitive pressure: ${neighborhoodData.license_count} active licenses increase the need for differentiation and pricing discipline.`
        : null,
      congestedCount > 0
        ? `Mobility friction: ${congestedCount} congested traffic zones may affect logistics, delivery times, and customer access.`
        : null,
      typeof rating === 'number' && rating > 0 && rating < 3.8
        ? `Consumer expectation risk: average rating at ${rating.toFixed(1)}/5 can imply stricter quality benchmarks for new entrants.`
        : null,
    ].filter((v): v is string => Boolean(v))

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

    addHeading('Executive Summary')
    addParagraph(summary)

    addHeading('Agent Intelligence')
    if (agentInfo) {
      addParagraph(`Agents deployed: ${agentInfo.agents_deployed} | Neighborhoods analyzed: ${agentInfo.neighborhoods.length} | Data points: ${agentInfo.data_points}`)
      if (agentInfo.agent_summaries.length > 0) {
        addParagraph('Top contributing agents:')
        agentInfo.agent_summaries.slice(0, 8).forEach((agent) => {
          addBullet(`${agent.name}: ${agent.data_points} points${agent.sources?.length ? ` (${agent.sources.join(', ')})` : ''}`)
        })
      }
    } else {
      addParagraph('Agent summary unavailable for this run. Pipeline metrics are shown from loaded neighborhood signals.')
    }

    addHeading('Detailed Advantages')
    if (detailedAdvantages.length > 0) {
      detailedAdvantages.forEach(addBullet)
    } else {
      addBullet('No strong upside concentration detected; proceed with controlled pilot testing.')
    }

    addHeading('Detailed Risks')
    if (detailedRisks.length > 0) {
      detailedRisks.forEach(addBullet)
    } else {
      addBullet('No single dominant risk detected; continue validation for category-specific constraints.')
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
            {agentInfo && (
              <div className="border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
                <p className="text-[10px] font-mono uppercase tracking-wider text-cyan-200/75 mb-2">Agent Intelligence</p>
                <div className="grid grid-cols-3 gap-2 mb-3">
                  <div>
                    <p className="text-[10px] font-mono text-white/35 uppercase">Agents</p>
                    <p className="text-sm font-semibold text-white">{agentInfo.agents_deployed}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-mono text-white/35 uppercase">Neighborhoods</p>
                    <p className="text-sm font-semibold text-white">{agentInfo.neighborhoods.length}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-mono text-white/35 uppercase">Data points</p>
                    <p className="text-sm font-semibold text-white">{agentInfo.data_points}</p>
                  </div>
                </div>

                {agentInfo.agent_summaries.length > 0 && (
                  <div className="space-y-1.5">
                    {agentInfo.agent_summaries.slice(0, 4).map((agent) => (
                      <div key={agent.name} className="flex items-center justify-between text-[11px] border border-white/10 px-2 py-1.5">
                        <span className="text-white/70 capitalize">{agent.name}</span>
                        <span className="font-mono text-white/85">{agent.data_points}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

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

            <div className="border border-white/[0.08] bg-black/20 p-3">
              <p className="text-[10px] font-mono uppercase tracking-wider text-white/35 mb-2">Brief summary</p>
              <p className="text-[11px] text-white/75 leading-relaxed">{summary}</p>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
