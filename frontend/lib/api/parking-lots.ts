import { apiClient } from './client'

export interface ParkingLotCoordinates {
  lat: number
  lng: number
}

export interface ParkingLotGeometry {
  type: 'Polygon'
  coordinates: number[][][]
}

export interface BusinessSummary {
  id: string
  name: string
  phone?: string
  email?: string
  website?: string
  address?: string
  category?: string
}

export interface PropertyAnalysisImages {
  wide_satellite?: string
  segmentation?: string
  property_boundary?: string
  condition_analysis?: string
}

export interface PropertyBoundaryInfo {
  source: string
  parcel_id?: string
  owner?: string
  apn?: string
  land_use?: string
  zoning?: string
  area_acres?: number
  year_built?: string
  polygon?: GeoJSONPolygon
}

export interface GeoJSONPolygon {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: number[][][] | number[][][][]
}

export interface GeoJSONFeature {
  type: 'Feature'
  geometry: GeoJSONPolygon
  properties?: Record<string, any>
}

export interface GeoJSONFeatureCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature[]
}

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
  asphalt_area_m2: number
  private_asphalt_area_m2?: number
  private_asphalt_area_sqft?: number
  private_asphalt_geojson?: GeoJSONFeature
  public_road_area_m2?: number
  asphalt_source?: string
  condition_score: number
  crack_count: number
  pothole_count: number
  status: string
  has_image?: boolean
}

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

export interface PropertyAnalysisSummary {
  id: string
  status: string
  analysis_type?: 'single' | 'tiled'
  detection_method?: 'grounded_sam' | 'legacy_cv'
  
  // NEW: Surface type breakdown from Grounded SAM
  surfaces?: SurfacesBreakdown
  surfaces_geojson?: { type: 'FeatureCollection', features: GeoJSONFeature[] }
  total_paved_area_m2?: number
  total_paved_area_sqft?: number
  
  // Metrics
  total_asphalt_area_m2?: number
  total_asphalt_area_sqft?: number
  private_asphalt_area_m2?: number
  private_asphalt_area_sqft?: number
  private_asphalt_geojson?: GeoJSONFeature
  public_road_area_m2?: number
  parking_area_sqft?: number
  road_area_sqft?: number
  // Condition
  weighted_condition_score?: number
  worst_tile_score?: number
  best_tile_score?: number
  total_crack_count: number
  total_pothole_count: number
  total_detection_count?: number
  damage_density?: number
  // Tiles
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
  // Images (legacy)
  images: PropertyAnalysisImages
  analyzed_at?: string
  // Property boundary
  property_boundary?: PropertyBoundaryInfo
  // Tiles array
  tiles?: AnalysisTile[]
}

export interface ParkingLotDetail {
  id: string
  centroid: ParkingLotCoordinates
  // Flat lat/lng for easier use
  latitude?: number
  longitude?: number
  geometry?: ParkingLotGeometry
  area_m2?: number
  area_sqft?: number
  operator_name?: string
  address?: string
  surface_type?: string
  condition_score?: number
  crack_density?: number
  pothole_score?: number
  line_fading_score?: number
  satellite_image_url?: string
  satellite_image_base64?: string
  is_evaluated: boolean
  data_sources: string[]
  degradation_areas?: Array<Record<string, any>>
  raw_metadata?: Record<string, any>
  evaluation_error?: string
  created_at: string
  evaluated_at?: string
  updated_at?: string
  business?: BusinessSummary
  match_score?: number
  distance_meters?: number
  lead_score?: number
  lead_quality?: 'high' | 'medium' | 'low'
  paved_percentage?: number
  building_percentage?: number
  landscaping_percentage?: number
  analysis_notes?: string
  analyzed_at?: string
  status?: string
  property_analysis?: PropertyAnalysisSummary
  contact?: ContactInfo
  // Enrichment flow for UI
  enrichment_steps?: string[]
  enrichment_detailed_steps?: EnrichmentStep[]
  enrichment_flow?: string
}

export interface EnrichmentStep {
  action: string
  description: string
  output?: string
  reasoning?: string
  status: 'success' | 'failed' | 'skipped'
  confidence?: number
  url?: string  // Resource URL (search URL, website, etc.)
  source?: string  // Source name (apartments.com, Google Places, etc.)
}

export interface ParkingLotBusiness {
  id: string
  name: string
  phone?: string
  email?: string
  website?: string
  address?: string
  category?: string
  match_score: number
  distance_meters: number
  is_primary: boolean
  location: ParkingLotCoordinates
}

export interface TileImageResponse {
  id: string
  tile_index: number
  image_base64?: string
  segmentation_image_base64?: string
  condition_image_base64?: string
}

export interface PropertyPreviewRequest {
  lat: number
  lng: number
  address?: string
  zoom?: number
}

export interface RegridLookupResponse {
  has_parcel: boolean
  location: { lat: number; lng: number }
  parcel?: {
    parcel_id?: string
    address?: string
    owner?: string
    land_use?: string
    zoning?: string
    year_built?: string
    area_acres?: number
    area_sqm?: number
    apn?: string
  } | null
  polygon_geojson?: GeoJSONPolygon | null
  error?: string
}

export interface PropertyPreviewResponse {
  success: boolean
  saved: boolean
  property_id: string
  is_new: boolean
  location: { lat: number; lng: number }
  image_base64: string
  image_size: { width: number; height: number }
  area_sqm: number
  area_sqft: number
  polygon?: GeoJSONPolygon
  regrid?: {
    parcel_id?: string
    apn?: string
    address?: string
    owner?: string
    land_use?: string
    zoning?: string
    year_built?: string
    area_acres?: number
    area_sqm?: number
  } | null
  boundary_source?: string
}

export interface AnalyzePropertyRequest {
  scoring_prompt_id?: string  // ID of saved prompt
  custom_prompt?: string      // Or custom prompt text
}

export interface AnalyzePropertyResponse {
  success: boolean
  property_id: string
  lead_score: number
  lead_quality: string
  confidence: number
  reasoning: string
  observations?: {
    paved_area_pct?: number
    building_pct?: number
    landscaping_pct?: number
    condition?: string
    visible_issues?: string[]
  } | null
  usage?: {
    tokens?: number
    cost?: number
  } | null
}

export interface ContactInfo {
  name?: string
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  title?: string
  linkedin_url?: string
  company?: string
  company_website?: string
  enriched_at?: string
  source?: string
  status?: string
}

// Enrichment process flow for UI display
export interface EnrichmentInfo {
  steps?: string[]           // ["Searched apartments.com", "Found Gables", "Got phone"]
  flow?: string              // "Searched apartments.com → Found Gables → Got phone"
}

export interface EnrichPropertyResponse {
  success: boolean
  property_id: string
  already_enriched?: boolean
  property_type?: string
  contact?: {
    name?: string
    first_name?: string
    last_name?: string
    email?: string
    phone?: string
    title?: string
    linkedin_url?: string
    company?: string
    company_website?: string
  }
  // Enrichment process flow for UI
  enrichment_steps?: string[]
  enrichment_detailed_steps?: EnrichmentStep[]
  enrichment_flow?: string
  confidence?: number
  tokens_used?: number
  enriched_at?: string
  error?: string
}

export const parkingLotsApi = {
  getParkingLot: async (id: string): Promise<ParkingLotDetail> => {
    const { data } = await apiClient.get<ParkingLotDetail>(`/parking-lots/${id}`)
    return data
  },

  getParkingLotBusinesses: async (id: string): Promise<ParkingLotBusiness[]> => {
    const { data } = await apiClient.get<ParkingLotBusiness[]>(`/parking-lots/${id}/businesses`)
    return data
  },

  getTileImage: async (tileId: string): Promise<TileImageResponse> => {
    const { data } = await apiClient.get<TileImageResponse>(`/parking-lots/tiles/${tileId}/image`)
    return data
  },

  // Fast Regrid lookup - NO satellite imagery (~1 second)
  regridLookup: async (lat: number, lng: number): Promise<RegridLookupResponse> => {
    const { data } = await apiClient.get<RegridLookupResponse>(`/parking-lots/regrid-lookup`, {
      params: { lat, lng },
      timeout: 10000, // 10 seconds max
    })
    return data
  },

  // Full capture: Regrid + satellite imagery + save to DB
  // Uses longer timeout since large properties can take 60+ seconds to process
  captureProperty: async (request: PropertyPreviewRequest): Promise<PropertyPreviewResponse> => {
    const { data } = await apiClient.post<PropertyPreviewResponse>(`/parking-lots/preview`, request, {
      timeout: 180000, // 3 minutes for very large properties
    })
    return data
  },

  // Analyze property with VLM
  analyzeProperty: async (propertyId: string, request: AnalyzePropertyRequest): Promise<AnalyzePropertyResponse> => {
    const { data } = await apiClient.post<AnalyzePropertyResponse>(`/parking-lots/${propertyId}/analyze`, request, {
      timeout: 60000, // 1 minute for VLM analysis
    })
    return data
  },

  // Enrich property with decision maker contact data via Apollo
  enrichProperty: async (propertyId: string): Promise<EnrichPropertyResponse> => {
    const { data } = await apiClient.post<EnrichPropertyResponse>(`/parking-lots/${propertyId}/enrich`, {}, {
      timeout: 30000, // 30 seconds for enrichment
    })
    return data
  },
}




