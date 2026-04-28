export type BusinessKind = 'coffee_shop' | 'restaurant'
export type Daypart = 'morning' | 'lunch' | 'afternoon' | 'dinner' | 'evening'
export type RecommendationEffort = 'low' | 'medium' | 'high'
export type RecommendationSource = 'pos' | 'menu' | 'hours' | 'inventory' | 'neighborhood'

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
  grossProfitCents: number
  averageOrderValueCents: number
  orderCount: number
  refundRatePct: number
  productMetrics: ProductMetric[]
  daypartRevenueCents: Record<Daypart, number>
  highMarginAttachRatePct: number
  stockoutRiskItems: string[]
}

export interface BusinessRecommendation {
  id: string
  title: string
  detail: string
  impactCentsPerWeek: number
  confidence: number
  effort: RecommendationEffort
  evidence: string[]
  sources: RecommendationSource[]
}

export interface BusinessIntelligenceSnapshot {
  mockBusiness: MockBusiness
  context: NeighborhoodBusinessContext
  metrics: BusinessMetrics
  recommendations: BusinessRecommendation[]
}
