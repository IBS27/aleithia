import type { NeighborhoodData } from '../types/index.ts'
import type { BusinessKind, NeighborhoodBusinessContext } from './types.ts'

export function computeNeighborhoodBusinessContext(
  data: NeighborhoodData | null,
  kind: BusinessKind,
  fallbackNeighborhood: string,
): NeighborhoodBusinessContext {
  if (!data) {
    return {
      neighborhood: fallbackNeighborhood,
      eveningDemandIndex: kind === 'restaurant' ? 60 : 55,
      inspectionPressure: 'medium',
      competitorPressure: 'medium',
      confidence: 0.35,
    }
  }

  const licensePressure = scoreLicensePressure(data.license_count, kind)
  const reviewSignal = scoreReviewSignal(data)
  const trafficSignal = scoreTrafficSignal(data, kind)
  const inspectionPressure = scoreInspectionPressure(data)
  const coverage = [
    data.license_count > 0,
    (data.reviews?.length ?? 0) > 0,
    Boolean(data.cctv?.density || data.transit?.stations_nearby),
    data.inspection_stats.total > 0,
  ].filter(Boolean).length

  return {
    neighborhood: data.neighborhood,
    eveningDemandIndex: Math.round((trafficSignal + reviewSignal) / 2),
    inspectionPressure,
    competitorPressure: licensePressure,
    confidence: Math.round((coverage / 4) * 100) / 100,
  }
}

function scoreLicensePressure(count: number, kind: BusinessKind): NeighborhoodBusinessContext['competitorPressure'] {
  const high = kind === 'restaurant' ? 18 : 12
  const medium = kind === 'restaurant' ? 8 : 5
  if (count >= high) return 'high'
  if (count >= medium) return 'medium'
  return 'low'
}

function scoreReviewSignal(data: NeighborhoodData): number {
  const ratings = (data.reviews ?? [])
    .map(review => Number(review.metadata?.rating ?? 0))
    .filter(rating => rating > 0)
  if (ratings.length === 0) return 55
  const avg = ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length
  return Math.max(35, Math.min(90, Math.round(avg * 18)))
}

function scoreTrafficSignal(data: NeighborhoodData, kind: BusinessKind): number {
  if (data.cctv?.density === 'high') return kind === 'restaurant' ? 82 : 78
  if (data.cctv?.density === 'medium') return 66
  if (data.transit && data.transit.stations_nearby >= 3) return kind === 'coffee_shop' ? 82 : 70
  if (data.transit && data.transit.stations_nearby > 0) return 64
  return 55
}

function scoreInspectionPressure(data: NeighborhoodData): NeighborhoodBusinessContext['inspectionPressure'] {
  const total = data.inspection_stats.total
  if (total === 0) return 'medium'
  const failRate = data.inspection_stats.failed / total
  if (failRate >= 0.25) return 'high'
  if (failRate >= 0.1) return 'medium'
  return 'low'
}
