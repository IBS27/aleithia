import type { NeighborhoodData } from '../types/index.ts'
import { computeNeighborhoodBusinessContext } from './context.ts'
import { computeBusinessMetrics } from './metrics.ts'
import { buildCommandAnalysisSnapshot } from './analysis.ts'
import { getMockBusiness, toBusinessKind } from './mockBusinesses.ts'
import type { BusinessIntelligenceSnapshot } from './types.ts'

export { computeNeighborhoodBusinessContext } from './context.ts'
export { getMockBusiness, toBusinessKind } from './mockBusinesses.ts'
export { computeBusinessMetrics } from './metrics.ts'
export { generateBusinessRecommendations } from './recommendations.ts'
export { buildCommandAnalysisSnapshot } from './analysis.ts'

export function getBusinessIntelligenceSnapshot(
  businessType: string,
  neighborhoodData: NeighborhoodData | null,
  fallbackNeighborhood: string,
): BusinessIntelligenceSnapshot {
  const kind = toBusinessKind(businessType)
  const mockBusiness = getMockBusiness(kind)
  const context = computeNeighborhoodBusinessContext(neighborhoodData, kind, fallbackNeighborhood)
  const metrics = computeBusinessMetrics(mockBusiness)
  const command = buildCommandAnalysisSnapshot(mockBusiness, metrics, context, neighborhoodData)
  return { mockBusiness, context, metrics, recommendations: command.recommendations, command }
}

export type {
  Business,
  BusinessIntelligenceSnapshot,
  BusinessKind,
  BusinessMetrics,
  BusinessRecommendation,
  CommandActionCopy,
  CommandAnalysisSnapshot,
  CommandCompliance,
  CommandCoverage,
  CommandForecast,
  CommandMarketContext,
  CommandRisk,
  CommandSynthesis,
  Daypart,
  InventorySignal,
  MenuItem,
  MockBusiness,
  NeighborhoodBusinessContext,
  OperatingHours,
  Order,
  OrderItem,
  ProductMetric,
  RecommendationEffort,
  RecommendationSource,
} from './types.ts'
