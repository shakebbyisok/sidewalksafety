
export interface User {
  id: string
  email: string
  company_name: string
  phone?: string
  is_active: boolean
  created_at: string
}

export interface BusinessInfo {
  id: string
  name: string
  phone?: string
  email?: string
  website?: string
  address?: string
  category?: string
}

export interface Deal {
  id: string
  user_id: string
  business_name?: string
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
  score?: number
  lead_score?: number
  satellite_url?: string
  has_property_verified?: boolean
  property_verification_method?: string
  property_type?: string
  created_at: string
  updated_at?: string
  // Regrid data
  regrid_owner?: string
  property_category?: string
  // Contact/enrichment data
  contact_company?: string
  contact_phone?: string
  contact_email?: string
  has_contact?: boolean
  enrichment_status?: 'success' | 'not_found' | 'error'
  // Discovery source
  discovery_source?: 'business_first' | 'regrid_first' | 'contact_first' | 'map_click'
  // Business association
  business?: BusinessInfo
  has_business: boolean
  match_score?: number
  distance_meters?: number
  // Analysis data
  paved_area_sqft?: number
  crack_count?: number
  pothole_count?: number
  property_boundary_source?: 'regrid' | 'estimated'
  lead_quality?: 'HIGH' | 'MEDIUM' | 'LOW'
  // Business-first discovery fields
  business_type_tier?: 'premium' | 'high' | 'standard'
  discovery_mode?: 'business_first' | 'parking_first' | 'contact_first'
}

export type DealStatus = 'pending' | 'evaluating' | 'evaluated' | 'archived'

export interface DealMapResponse {
  id: string
  business_name?: string
  display_name?: string
  address: string
  latitude?: number
  longitude?: number
  status: DealStatus
  score?: number
  deal_score?: number
  lead_score?: number
  estimated_job_value?: number
  damage_severity?: DamageSeverity
  satellite_url?: string
  condition_score?: number
  crack_density?: number
  // Business-first discovery fields
  business_type_tier?: 'premium' | 'high' | 'standard'
  business?: BusinessInfo
  has_business?: boolean
  // Regrid data
  regrid_owner?: string
  property_category?: string
  // Contact/enrichment data
  contact_company?: string
  contact_phone?: string
  contact_email?: string
  enrichment_status?: 'success' | 'not_found' | 'error'
  has_contact?: boolean
  // Analysis data
  paved_area_sqft?: number
  crack_count?: number
  pothole_count?: number
  property_boundary_source?: 'regrid' | 'estimated'
  lead_quality?: 'high' | 'medium' | 'low'
  discovery_source?: 'business_first' | 'regrid_first' | 'contact_first' | 'map_click'
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

// Single tile from tile-based analysis
export interface AnalysisTile {
  id: string
  tile_index: number
  center_lat: number
  center_lng: number
  zoom_level: number
  bounds: {
    min_lat: number
    max_lat: number
    min_lng: number
    max_lng: number
  }
  // Total asphalt from CV (includes public roads)
  asphalt_area_m2: number
  // Private asphalt (after filtering public roads via OSM)
  private_asphalt_area_m2?: number
  private_asphalt_area_sqft?: number
  private_asphalt_geojson?: GeoJSONFeature  // For map overlay
  // Public roads filtered out
  public_road_area_m2?: number
  asphalt_source?: string  // cv_only, cv_with_osm_filter, fallback
  // Condition
  condition_score: number
  crack_count: number
  pothole_count: number
  status: string
  has_image?: boolean  // Images are lazy-loaded via separate endpoint
  image_base64?: string  // Only populated when fetched individually
}

// Tile image response from /tiles/{id}/image endpoint
export interface TileImageResponse {
  id: string
  tile_index: number
  image_base64?: string
  segmentation_image_base64?: string
  condition_image_base64?: string
}

// Property Analysis Summary (embedded in parking lot/deal response)
export interface PropertyAnalysisSummary {
  id: string
  status: string
  analysis_type?: 'single' | 'tiled'
  detection_method?: 'grounded_sam' | 'legacy_cv'
  
  // ============ SURFACE TYPE BREAKDOWN (NEW - Grounded SAM) ============
  surfaces?: SurfacesBreakdown
  surfaces_geojson?: { type: 'FeatureCollection', features: GeoJSONFeature[] }
  total_paved_area_m2?: number
  total_paved_area_sqft?: number
  
  // ============ LEGACY FIELDS (backwards compat) ============
  // Aggregated metrics (total from CV - includes public roads)
  total_asphalt_area_m2?: number
  total_asphalt_area_sqft?: number
  parking_area_sqft?: number
  road_area_sqft?: number
  // Private asphalt (after filtering public roads)
  private_asphalt_area_m2?: number
  private_asphalt_area_sqft?: number
  private_asphalt_geojson?: GeoJSONFeature  // Merged GeoJSON for map overlay
  public_road_area_m2?: number  // Roads filtered out
  
  // Condition
  weighted_condition_score?: number
  worst_tile_score?: number
  best_tile_score?: number
  total_crack_count: number
  total_pothole_count: number
  total_detection_count?: number
  damage_density?: number
  // Tile grid info
  total_tiles?: number
  analyzed_tiles?: number
  tiles_with_asphalt?: number
  tiles_with_damage?: number
  tile_zoom_level?: number
  tile_grid_rows?: number
  tile_grid_cols?: number
  // Lead quality
  lead_quality?: 'premium' | 'high' | 'standard' | 'low'
  hotspot_count?: number
  // Images (legacy or first tile)
  images: PropertyAnalysisImages
  analyzed_at?: string
  // Property boundary info
  property_boundary?: PropertyBoundaryInfo
  // Tiles (for tiled analysis)
  tiles?: AnalysisTile[]
}

export interface DealWithEvaluation extends Deal {
  evaluation?: Evaluation
  property_analysis?: PropertyAnalysisSummary
}

export type DiscoveryMode = 'business_first' | 'contact_first' | 'regrid_first'

export type PropertyCategory = 'multi_family' | 'retail' | 'office' | 'industrial' | 'institutional'

export interface GeographicSearchRequest {
  area_type: 'zip' | 'county'
  value: string
  state?: string
  max_results?: number
  business_type_ids?: string[]
  tiers?: ('premium' | 'high' | 'standard')[]
  scoring_prompt?: string
  // Discovery mode
  mode?: DiscoveryMode
  // Contact-first mode parameters
  city?: string
  job_titles?: string[]
  industries?: string[]
  // Regrid-first mode parameters
  property_categories?: PropertyCategory[]
  min_acres?: number
  max_acres?: number
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

// Property Analysis Types
export interface AsphaltArea {
  id: string
  area_type?: string
  area_m2?: number
  is_associated: boolean
  association_reason?: string
  distance_to_building_m?: number
  condition_score?: number
  crack_count?: number
  pothole_count?: number
  crack_density?: number
}

export interface PropertyAnalysisImages {
  wide_satellite?: string
  segmentation?: string
  property_boundary?: string
  condition_analysis?: string
}

// Property boundary info from Regrid
export interface PropertyBoundaryInfo {
  source: 'regrid' | 'osm' | 'estimated'
  parcel_id?: string
  owner?: string
  apn?: string  // Assessor Parcel Number
  land_use?: string
  zoning?: string
  // GeoJSON polygon (for map display)
  polygon?: GeoJSONPolygon
}

export interface GeoJSONPolygon {
  type: 'Polygon'
  coordinates: number[][][]
}

export interface GeoJSONFeature {
  type: 'Feature'
  geometry: GeoJSONPolygon
  properties?: Record<string, any>
}

// ============ SURFACE TYPE BREAKDOWN (Grounded SAM) ============
export interface SurfaceInfo {
  area_m2?: number
  area_sqft?: number
  geojson?: GeoJSONFeature | null
  color: string
  label: string
}

export interface SurfacesBreakdown {
  asphalt: SurfaceInfo
  concrete: SurfaceInfo
  buildings: SurfaceInfo
}

export interface PropertyAnalysis {
  id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  latitude?: number
  longitude?: number
  total_asphalt_area_m2?: number
  weighted_condition_score?: number
  total_crack_count?: number
  total_pothole_count?: number
  images: PropertyAnalysisImages
  asphalt_areas: AsphaltArea[]
  business_id?: string
  parking_lot_id?: string
  analyzed_at?: string
  created_at?: string
  error_message?: string
  // Regrid property boundary data
  property_boundary?: PropertyBoundaryInfo
}

export interface PropertyAnalysisRequest {
  latitude: number
  longitude: number
  business_id?: string
  parking_lot_id?: string
}

export interface PropertyAnalysisJobResponse {
  job_id: string
  analysis_id: string
  status: string
  message: string
}

export interface PropertyAnalysisListResponse {
  total: number
  limit: number
  offset: number
  results: PropertyAnalysis[]
}