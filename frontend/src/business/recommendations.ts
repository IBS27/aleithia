import type { BusinessMetrics, BusinessRecommendation, MockBusiness, NeighborhoodBusinessContext } from './types.ts'

export function generateBusinessRecommendations(
  mockBusiness: MockBusiness,
  metrics: BusinessMetrics,
  context: NeighborhoodBusinessContext,
): BusinessRecommendation[] {
  const recommendations = [
    recommendHoursExtension(mockBusiness, metrics, context),
    recommendHighMarginPush(mockBusiness, metrics, context),
    recommendStockoutFix(mockBusiness, metrics),
    recommendComplianceWork(mockBusiness, context),
  ].filter((item): item is BusinessRecommendation => Boolean(item))

  return recommendations.sort((a, b) => b.impactCentsPerWeek - a.impactCentsPerWeek)
}

function recommendHoursExtension(
  mockBusiness: MockBusiness,
  metrics: BusinessMetrics,
  context: NeighborhoodBusinessContext,
): BusinessRecommendation | null {
  if (context.eveningDemandIndex < 75) return null
  const latestCloseMinute = Math.max(...mockBusiness.operatingHours.map(hours => hours.closeMinute))
  const eveningDemandMinute = 21 * 60
  if (latestCloseMinute >= eveningDemandMinute) return null

  const dinnerRevenue = metrics.daypartRevenueCents.dinner + metrics.daypartRevenueCents.evening
  const impact = Math.max(42_000, Math.round(dinnerRevenue * 0.22))

  return {
    id: `${mockBusiness.id}-extend-hours-${context.neighborhood}`,
    title: mockBusiness.business.kind === 'coffee_shop' ? 'Extend Friday hours' : 'Add late dinner window',
    detail: 'Capture demand that remains active after current operating hours.',
    impactCentsPerWeek: impact,
    confidence: 0.82,
    effort: 'low',
    evidence: [
      `Evening demand index is ${context.eveningDemandIndex}/100 in ${context.neighborhood}.`,
      `Current dinner/evening revenue is ${formatMoney(dinnerRevenue)} today.`,
      `Current close is ${formatTime(latestCloseMinute)}, before the modeled late demand window.`,
    ],
    sources: ['hours', 'pos', 'neighborhood'],
  }
}

function recommendHighMarginPush(
  mockBusiness: MockBusiness,
  metrics: BusinessMetrics,
  context: NeighborhoodBusinessContext,
): BusinessRecommendation | null {
  const highMarginProduct = metrics.productMetrics.find(item => item.marginPct >= 68)
  if (!highMarginProduct) return null
  const attachWeak = mockBusiness.business.kind === 'coffee_shop'
    ? metrics.highMarginAttachRatePct < 45
    : metrics.highMarginAttachRatePct < 55
  if (!attachWeak && context.competitorPressure !== 'high' && highMarginProduct.revenueCents < metrics.todayRevenueCents * 0.18) return null

  return {
    id: `${mockBusiness.id}-high-margin-push-${context.neighborhood}`,
    title: mockBusiness.business.kind === 'coffee_shop' ? 'Bundle high-margin pastry' : 'Promote high-margin add-on',
    detail: `Increase attachment for ${highMarginProduct.name}, which has stronger margin than the current mix.`,
    impactCentsPerWeek: Math.round(highMarginProduct.grossProfitCents * 0.18),
    confidence: 0.74,
    effort: 'low',
    evidence: [
      `${highMarginProduct.name} margin is ${highMarginProduct.marginPct}%.`,
      `High-margin attach rate is ${metrics.highMarginAttachRatePct}%.`,
      `${highMarginProduct.name} sold ${highMarginProduct.unitsSold} units in the current week.`,
      `Competitor pressure is ${context.competitorPressure} in ${context.neighborhood}.`,
    ],
    sources: ['pos', 'menu'],
  }
}

function recommendStockoutFix(
  mockBusiness: MockBusiness,
  metrics: BusinessMetrics,
): BusinessRecommendation | null {
  if (metrics.stockoutRiskItems.length === 0) return null
  return {
    id: `${mockBusiness.id}-stockout-risk`,
    title: 'Reduce stockout risk',
    detail: `Protect peak-period sales for ${metrics.stockoutRiskItems.join(', ')}.`,
    impactCentsPerWeek: Math.round(metrics.todayRevenueCents * 0.08),
    confidence: 0.78,
    effort: 'medium',
    evidence: [
      `${metrics.stockoutRiskItems.length} item family has low inventory or a same-day stockout signal.`,
      'Stockout risk overlaps with observed peak demand windows.',
    ],
    sources: ['inventory', 'pos'],
  }
}

function recommendComplianceWork(
  mockBusiness: MockBusiness,
  context: NeighborhoodBusinessContext,
): BusinessRecommendation | null {
  if (context.inspectionPressure !== 'high') return null
  return {
    id: `${mockBusiness.id}-compliance-work-${context.neighborhood}`,
    title: 'Close inspection checklist gaps',
    detail: 'Address high-friction compliance items before the next inspection window.',
    impactCentsPerWeek: 79_000,
    confidence: 0.9,
    effort: 'low',
    evidence: [
      `Inspection pressure is high in ${context.neighborhood}.`,
      'Refund and service issue patterns increase late-day operational risk.',
    ],
    sources: ['neighborhood', 'pos'],
  }
}

function formatMoney(cents: number): string {
  return `$${Math.round(cents / 100).toLocaleString()}`
}

function formatTime(minuteOfDay: number): string {
  const hour24 = Math.floor(minuteOfDay / 60)
  const hour12 = hour24 > 12 ? hour24 - 12 : hour24
  return `${hour12 || 12}:00 ${hour24 >= 12 ? 'PM' : 'AM'}`
}
