export interface RiskFactor {
  label: string
  pct: number
  source: string
  severity: 'low' | 'medium' | 'high'
  description: string
}

export interface RiskScore {
  neighborhood: string
  business_type: string
  overall_score: number
  confidence: number
  factors: RiskFactor[]
  summary: string
}

export interface NeighborhoodMetrics {
  neighborhood: string
  regulatory_density: number
  business_activity: number
  sentiment: number
  risk_score: number
  active_permits: number
  news_mentions: number
  avg_review_rating: number
  review_count?: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export interface UserProfile {
  business_type: string
  neighborhood: string
}

// Raw data types from API
export interface Document {
  id: string
  source: string
  title: string
  content: string
  url: string
  timestamp: string
  metadata: Record<string, unknown>
  geo: {
    lat?: string
    lng?: string
    neighborhood?: string
    ward?: string
    community_area?: string
  }
}

export interface InspectionRecord extends Document {
  metadata: {
    dataset: 'food_inspections'
    raw_record: {
      inspection_id: string
      dba_name: string
      aka_name: string
      facility_type: string
      risk: string
      address: string
      city: string
      state: string
      zip: string
      inspection_date: string
      inspection_type: string
      results: string
      violations: string
    }
  }
}

export interface PermitRecord extends Document {
  metadata: {
    dataset: 'building_permits'
    raw_record: {
      id: string
      permit_: string
      permit_status: string
      permit_type: string
      work_type: string
      work_description: string
      street_number: string
      street_direction: string
      street_name: string
      building_fee_paid: string
      issue_date: string
    }
  }
}

export interface LicenseRecord extends Document {
  metadata: {
    dataset: 'business_licenses'
    raw_record: {
      legal_name: string
      doing_business_as_name: string
      address: string
      license_description: string
      ward: string
      community_area: string
    }
  }
}

export interface Demographics {
  total_population?: number
  median_household_income?: number
  median_home_value?: number
  median_gross_rent?: number
  unemployment_rate?: number
  median_age?: number
  total_housing_units?: number
  renter_pct?: number
  bachelors_degree?: number
  masters_degree?: number
  tracts_counted?: number
}

export interface CCTVCamera {
  camera_id: string
  lat: number
  lng: number
  distance_km: number
  pedestrians: number
  vehicles: number
  bicycles: number
  density_level: 'low' | 'medium' | 'high' | 'unknown'
  timestamp: string
}

export interface CCTVData {
  cameras: CCTVCamera[]
  avg_pedestrians: number
  avg_vehicles: number
  density: string
  peak_hour?: number
  peak_pedestrians?: number
}

export interface CCTVHourBucket {
  hour: number
  avg_pedestrians: number
  avg_vehicles: number
  density: string
  sample_count: number
}

export interface CCTVTimeseries {
  hours: CCTVHourBucket[]
  peak_hour: number
  peak_pedestrians: number
  camera_count: number
}

export interface StreetscapeCounts {
  storefront_open: number
  storefront_closed: number
  for_lease_sign: number
  construction: number
  restaurant_signage: number
  outdoor_dining: number
  person: number
  vehicle: number
}

export interface StreetscapeIndicators {
  vacancy_signal: 'low' | 'moderate' | 'high'
  dining_saturation: 'low' | 'moderate' | 'high'
  growth_signal: 'active' | 'stable'
}

export interface StreetscapeData {
  counts: StreetscapeCounts
  indicators: StreetscapeIndicators
  analysis_count: number
}

export interface VisionAssessment {
  storefront_viability: { score: number; available_spaces: string; condition: string }
  competitor_presence: { restaurants: string; retail: string; notable_businesses: string[] }
  pedestrian_activity: { level: 'high' | 'medium' | 'low'; demographics: string; peak_indicators: string }
  infrastructure: { transit_access: string; parking: string; road_condition: string }
  overall_recommendation: string
}

export interface VisionAssessData {
  assessment: VisionAssessment
  frame_count: number
  neighborhood: string
  model: string
}

export interface ParkingLot {
  center_lat: number
  center_lng: number
  area_sqm: number
  estimated_capacity: number
  vehicles_detected: number
  occupancy_rate: number
}

export interface ParkingData {
  neighborhood: string
  parking_lots: ParkingLot[]
  total_capacity: number
  total_vehicles: number
  overall_occupancy: number
  coverage_area_sqm: number
  timestamp: string
}

export interface NeighborhoodData {
  neighborhood: string
  metrics: NeighborhoodMetrics
  demographics?: Demographics
  inspections: InspectionRecord[]
  permits: PermitRecord[]
  licenses: LicenseRecord[]
  news: Document[]
  politics: Document[]
  reddit?: Document[]
  reviews?: Document[]
  realestate?: Document[]
  tiktok?: Document[]
  traffic?: Document[]
  federal_register?: Document[]
  inspection_stats: {
    total: number
    failed: number
    passed: number
  }
  permit_count: number
  license_count: number
  cctv?: CCTVData
  transit?: TransitData
  parking?: ParkingData
}

export interface TransitData {
  stations_nearby: number
  total_daily_riders: number
  transit_score: number
  station_names: string[]
}

export interface GeoFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: NeighborhoodMetrics
}

export interface GeoJSON {
  type: 'FeatureCollection'
  features: GeoFeature[]
}

export interface DataSources {
  [key: string]: { count: number; active: boolean }
}

export type InsightSignal = 'positive' | 'neutral' | 'negative'
export type RiskProfile = 'conservative' | 'growth' | 'budget'

export interface SubMetric {
  name: string
  value: number
  raw: string
}

export interface CategoryScore {
  id: string
  name: string
  score: number
  subMetrics: SubMetric[]
  claim: string
  signal: InsightSignal
  signalLabel: string
  sources: string[]
  dataPoints: number
}

export interface SocialTrend {
  title: string
  detail: string
}

export interface SocialTrendsData {
  trends: SocialTrend[]
  source_counts: { reddit: number; tiktok: number }
}

export interface InsightsResult {
  categories: CategoryScore[]
  overall: number
  profile: RiskProfile
  coverageCount: number
  computedAt: string
}
