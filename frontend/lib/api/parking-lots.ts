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
  geojson?: GeoJSONFeature | GeoJSONFeatureCollection | null
  color?: string
  label?: string
}

export interface SurfacesBreakdown {
  asphalt?: SurfaceInfo
  concrete?: SurfaceInfo
  buildings?: SurfaceInfo
}

export interface PropertyAnalysisSummary {
  id: string
  status: string
  analysis_type?: string
  detection_method?: string
  
  // NEW: Surface type breakdown from Grounded SAM
  surfaces?: SurfacesBreakdown
  surfaces_geojson?: GeoJSONFeatureCollection | null
  total_paved_area_m2?: number
  total_paved_area_sqft?: number
  
  // Metrics
  total_asphalt_area_m2?: number
  total_asphalt_area_sqft?: number
  private_asphalt_area_m2?: number
  private_asphalt_area_sqft?: number
  private_asphalt_geojson?: GeoJSONFeature | GeoJSONFeatureCollection | null
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
  lead_quality?: string
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
  property_analysis?: PropertyAnalysisSummary
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
}


