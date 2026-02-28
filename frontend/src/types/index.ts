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
  crime_incidents_30d: number
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
  inspection_stats: {
    total: number
    failed: number
    passed: number
  }
  permit_count: number
  license_count: number
  cctv?: CCTVData
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
