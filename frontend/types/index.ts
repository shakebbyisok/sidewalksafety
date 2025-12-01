
export interface User {
  id: string
  email: string
  company_name: string
  phone?: string
  is_active: boolean
  created_at: string
}

export interface Deal {
  id: string
  user_id: string
  business_name: string
  address: string
  city?: string
  state?: string
  zip?: string
  county?: string
  phone?: string
  email?: string
  website?: string
  category?: string
  latitude?: number
  longitude?: number
  places_id?: string
  apollo_id?: string
  status: DealStatus
  has_property_verified: boolean
  property_verification_method?: string
  property_type: string
  created_at: string
  updated_at?: string
}

export type DealStatus = 'pending' | 'evaluating' | 'evaluated' | 'archived'

export interface DealMapResponse {
  id: string
  business_name: string
  address: string
  latitude?: number
  longitude?: number
  status: DealStatus
  deal_score?: number
  estimated_job_value?: number
  damage_severity?: DamageSeverity
}

export type DamageSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface Evaluation {
  id: string
  deal_id: string
  deal_score?: number
  parking_lot_area_sqft?: number
  crack_density_percent?: number
  damage_severity?: DamageSeverity
  estimated_repair_cost?: number
  estimated_job_value?: number
  satellite_image_url?: string
  parking_lot_mask?: Record<string, any>
  crack_detections?: Array<Record<string, any>>
  evaluation_metadata?: Record<string, any>
  evaluated_at: string
}

export interface DealWithEvaluation extends Deal {
  evaluation?: Evaluation
}

export interface GeographicSearchRequest {
  area_type: 'zip' | 'county'
  value: string
  state?: string
  max_deals?: number
}

export interface GeographicSearchResponse {
  job_id: string
  status: string
  message: string
}

export interface BatchEvaluateRequest {
  deal_ids: string[]
}

export interface BatchEvaluateResponse {
  evaluated: number
  failed: number
  message: string
}

export interface ApiError {
  detail: string
}

export interface Token {
  access_token: string
  token_type: string
  user: User
}

export interface UserCreate {
  email: string
  password: string
  company_name: string
  phone?: string
}

export interface UserLogin {
  email: string
  password: string
}

