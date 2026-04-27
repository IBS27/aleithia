import { computeBusinessMetrics } from './metrics.ts'
import { generateBusinessRecommendations } from './recommendations.ts'
import { getBusinessScenario } from './scenarios.ts'
import type { BusinessIntelligenceSnapshot } from './types.ts'

export { MOCK_POS_SCENARIO_IDS, getBusinessScenario, listBusinessScenarios } from './scenarios.ts'
export { computeBusinessMetrics } from './metrics.ts'
export { generateBusinessRecommendations } from './recommendations.ts'

export function getBusinessIntelligenceSnapshot(scenarioId?: string): BusinessIntelligenceSnapshot {
  const scenario = getBusinessScenario(scenarioId)
  const metrics = computeBusinessMetrics(scenario)
  const recommendations = generateBusinessRecommendations(scenario, metrics)
  return { scenario, metrics, recommendations }
}

export type {
  Business,
  BusinessIntelligenceSnapshot,
  BusinessKind,
  BusinessMetrics,
  BusinessRecommendation,
  BusinessScenario,
  Daypart,
  InventorySignal,
  MenuItem,
  NeighborhoodBusinessContext,
  OperatingHours,
  Order,
  OrderItem,
  ProductMetric,
  RecommendationEffort,
  RecommendationSource,
} from './types.ts'
