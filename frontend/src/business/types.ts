export type BusinessKind = 'coffee_shop' | 'restaurant'
export type Daypart = 'morning' | 'lunch' | 'afternoon' | 'dinner' | 'evening'
export type RecommendationEffort = 'low' | 'medium' | 'high'
export type RecommendationSource = 'pos' | 'menu' | 'hours' | 'inventory' | 'neighborhood' | 'market' | 'compliance' | 'traffic'

export interface Business {
  id: string
  name: string
  kind: BusinessKind
  neighborhood: string
  address: string
  currency: 'USD'
}

export interface MenuItem {
  id: string
  name: string
  category: string
  priceCents: number
  unitCostCents: number
  kind: BusinessKind | 'shared'
}

export interface Order {
  id: string
  openedAt: string
  totalCents: number
  refundCents: number
}

export interface OrderItem {
  id: string
  orderId: string
  menuItemId: string
  quantity: number
  grossCents: number
}

export interface OperatingHours {
  dayOfWeek: number
  openMinute: number
  closeMinute: number
}

export interface InventorySignal {
  menuItemId: string
  date: string
  stockoutHour: number | null
  unitsRemaining: number
}

export interface NeighborhoodBusinessContext {
  neighborhood: string
  eveningDemandIndex: number
  inspectionPressure: 'low' | 'medium' | 'high'
  competitorPressure: 'low' | 'medium' | 'high'
  confidence: number
}

export interface MockBusiness {
  id: string
  label: string
  business: Business
  menuItems: MenuItem[]
  orders: Order[]
  orderItems: OrderItem[]
  operatingHours: OperatingHours[]
  inventorySignals: InventorySignal[]
}

export interface ProductMetric {
  menuItemId: string
  name: string
  category: string
  revenueCents: number
  grossProfitCents: number
  unitsSold: number
  marginPct: number
}

export interface BusinessMetrics {
  businessId: string
  todayRevenueCents: number
  projectedWeekRevenueCents: number
  weekRevenueCents: number
  grossProfitCents: number
  averageOrderValueCents: number
  orderCount: number
  refundRatePct: number
  dailyRevenueCents: Array<{ date: string; revenueCents: number }>
  productMetrics: ProductMetric[]
  daypartRevenueCents: Record<Daypart, number>
  highMarginAttachRatePct: number
  stockoutRiskItems: string[]
}

export interface BusinessRecommendation {
  id: string
  title: string
  detail: string
  whyNow: string
  nextStepLabel: string
  impactCentsPerWeek: number
  confidence: number
  effort: RecommendationEffort
  evidence: string[]
  sources: RecommendationSource[]
}

export interface ForecastPoint {
  label: string
  baselineRevenueCents: number
  recommendedRevenueCents: number
}

export interface CommandForecast {
  baselineWeekRevenueCents: number
  recommendedWeekRevenueCents: number
  opportunityCentsPerWeek: number
  grossProfitBaselineCents: number
  grossProfitRecommendedCents: number
  points: ForecastPoint[]
}

export interface CommandRisk {
  level: 'low' | 'medium' | 'high'
  label: string
  detail: string
  unresolvedCount: number
}

export interface ComplianceRisk {
  label: string
  severity: RecommendationEffort
}

export interface CommandCompliance {
  windowLabel: string
  daysUntilWindow: number
  risks: ComplianceRisk[]
}

export interface CommandMarketContext {
  directCompetitors: number
  nearbyBusinesses: Array<{ name: string; type: string; isDirect: boolean }>
  footTrafficLabel: string
  footTrafficScore: number
}

export interface CommandCoverage {
  percent: number
  sourcesOnline: number
  sourcesTotal: number
  activeAlerts: number
}

export interface CommandAnalysisSnapshot {
  business: Business
  context: NeighborhoodBusinessContext
  metrics: BusinessMetrics
  forecast: CommandForecast
  recommendations: BusinessRecommendation[]
  risk: CommandRisk
  compliance: CommandCompliance
  market: CommandMarketContext
  coverage: CommandCoverage
}

export interface CommandActionCopy {
  id: string
  title: string
  detail: string
  why_now: string
  next_step_label: string
}

export interface CommandSynthesis {
  brief_lines: string[]
  ranked_action_ids: string[]
  action_copy: CommandActionCopy[]
  uncertainty_notes: string[]
  fallback_used?: boolean
}

export interface BusinessIntelligenceSnapshot {
  mockBusiness: MockBusiness
  context: NeighborhoodBusinessContext
  metrics: BusinessMetrics
  recommendations: BusinessRecommendation[]
  command: CommandAnalysisSnapshot
}
