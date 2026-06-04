import type { NeighborhoodData } from '../types/index.ts'
import type {
  BusinessMetrics,
  CommandAnalysisSnapshot,
  CommandCompliance,
  CommandCoverage,
  CommandForecast,
  CommandMarketContext,
  CommandRisk,
  MockBusiness,
  NeighborhoodBusinessContext,
} from './types.ts'
import { generateBusinessRecommendations } from './recommendations.ts'

const LICENSE_KEYWORDS: Record<string, string[]> = {
  coffee_shop: ['coffee', 'cafe', 'retail food', 'bakery'],
  restaurant: ['restaurant', 'retail food', 'tavern'],
}

export function buildCommandAnalysisSnapshot(
  mockBusiness: MockBusiness,
  metrics: BusinessMetrics,
  context: NeighborhoodBusinessContext,
  neighborhoodData: NeighborhoodData | null,
): CommandAnalysisSnapshot {
  const recommendations = generateBusinessRecommendations(mockBusiness, metrics, context)
  const forecast = buildForecast(metrics, recommendations.reduce((sum, item) => sum + item.impactCentsPerWeek, 0))

  return {
    business: {
      ...mockBusiness.business,
      neighborhood: context.neighborhood,
    },
    context,
    metrics,
    forecast,
    recommendations,
    risk: buildRisk(context, neighborhoodData),
    compliance: buildCompliance(neighborhoodData, context),
    market: buildMarketContext(mockBusiness, context, neighborhoodData),
    coverage: buildCoverage(neighborhoodData, context, recommendations.length),
  }
}

function buildForecast(metrics: BusinessMetrics, opportunityCentsPerWeek: number): CommandForecast {
  const baselineWeekRevenueCents = metrics.projectedWeekRevenueCents
  const recommendedWeekRevenueCents = baselineWeekRevenueCents + opportunityCentsPerWeek
  const profitRatio = metrics.weekRevenueCents > 0
    ? metrics.grossProfitCents / metrics.weekRevenueCents
    : 0.42
  const dailyBaseline = Math.round(baselineWeekRevenueCents / 7)
  const dailyOpportunity = Math.round(opportunityCentsPerWeek / 7)

  return {
    baselineWeekRevenueCents,
    recommendedWeekRevenueCents,
    opportunityCentsPerWeek,
    grossProfitBaselineCents: Math.round(baselineWeekRevenueCents * profitRatio),
    grossProfitRecommendedCents: Math.round(recommendedWeekRevenueCents * profitRatio),
    points: Array.from({ length: 7 }, (_, index) => ({
      label: `Day ${index + 1}`,
      baselineRevenueCents: dailyBaseline,
      recommendedRevenueCents: dailyBaseline + dailyOpportunity,
    })),
  }
}

function buildRisk(context: NeighborhoodBusinessContext, data: NeighborhoodData | null): CommandRisk {
  const highCompliance = context.inspectionPressure === 'high'
  const highCompetition = context.competitorPressure === 'high'
  const lowDemand = context.eveningDemandIndex < 55
  const unresolvedCount = [highCompliance, highCompetition, lowDemand].filter(Boolean).length
  const level = unresolvedCount >= 2 ? 'high' : unresolvedCount === 1 ? 'medium' : 'low'

  return {
    level,
    label: level.toUpperCase(),
    detail: highCompliance
      ? 'Inspection pressure is elevated'
      : highCompetition
        ? 'Competitor pressure is elevated'
        : data?.inspection_stats.total
          ? 'No major inspection pressure'
          : 'Limited local risk data',
    unresolvedCount,
  }
}

function buildCompliance(data: NeighborhoodData | null, context: NeighborhoodBusinessContext): CommandCompliance {
  const failed = data?.inspection_stats.failed ?? 0
  const total = data?.inspection_stats.total ?? 0
  const risks = []

  if (context.inspectionPressure === 'high') {
    risks.push({ label: 'Inspection failure rate', severity: 'high' as const })
  }
  if (failed > 0) {
    risks.push({ label: `${failed} failed recent inspection${failed === 1 ? '' : 's'}`, severity: failed >= 3 ? 'high' as const : 'medium' as const })
  }
  if (total === 0) {
    risks.push({ label: 'No recent inspection sample', severity: 'medium' as const })
  }
  if (risks.length === 0) {
    risks.push({ label: 'Routine checklist review', severity: 'low' as const })
  }

  return {
    windowLabel: context.inspectionPressure === 'high' ? 'Open now' : 'Next 30 days',
    daysUntilWindow: context.inspectionPressure === 'high' ? 0 : 30,
    risks: risks.slice(0, 3),
  }
}

function buildMarketContext(
  mockBusiness: MockBusiness,
  context: NeighborhoodBusinessContext,
  data: NeighborhoodData | null,
): CommandMarketContext {
  const keywords = LICENSE_KEYWORDS[mockBusiness.business.kind] ?? []
  const seen = new Set<string>()
  const nearbyBusinesses = (data?.licenses ?? [])
    .map(license => {
      const raw = license.metadata?.raw_record as Record<string, unknown> | undefined
      const name = String(raw?.doing_business_as_name || raw?.legal_name || '').trim()
      const type = String(raw?.license_description || '').trim()
      if (!name || seen.has(name)) return null
      seen.add(name)
      const isDirect = keywords.some(keyword => type.toLowerCase().includes(keyword))
      return { name, type: type || 'Business license', isDirect }
    })
    .filter((item): item is { name: string; type: string; isDirect: boolean } => Boolean(item))
    .sort((a, b) => Number(b.isDirect) - Number(a.isDirect))
    .slice(0, 5)

  const footTrafficScore = Math.max(
    context.eveningDemandIndex,
    data?.transit?.transit_score ?? 0,
    data?.cctv?.density === 'high' ? 82 : data?.cctv?.density === 'medium' ? 66 : 0,
  )

  return {
    directCompetitors: nearbyBusinesses.filter(item => item.isDirect).length,
    nearbyBusinesses,
    footTrafficScore,
    footTrafficLabel: footTrafficScore >= 75 ? 'High' : footTrafficScore >= 55 ? 'Medium' : 'Low',
  }
}

function buildCoverage(
  data: NeighborhoodData | null,
  context: NeighborhoodBusinessContext,
  actionCount: number,
): CommandCoverage {
  const signals = [
    true,
    data?.license_count ? data.license_count > 0 : false,
    (data?.reviews?.length ?? 0) > 0,
    Boolean(data?.cctv?.density || data?.transit?.stations_nearby),
    (data?.inspection_stats.total ?? 0) > 0,
    (data?.reddit?.length ?? 0) + (data?.tiktok?.length ?? 0) > 0,
  ]
  const sourcesOnline = signals.filter(Boolean).length
  const sourcesTotal = signals.length

  return {
    percent: Math.round(((context.confidence * 4 + sourcesOnline) / (4 + sourcesTotal)) * 100),
    sourcesOnline,
    sourcesTotal,
    activeAlerts: actionCount,
  }
}
