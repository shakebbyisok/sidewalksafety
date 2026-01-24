import { apiClient } from './client'

// ============================================================
// Types
// ============================================================

export interface BoundaryLayer {
  id: string
  name: string
  available: boolean
  size_mb: number
  loaded: boolean
}

export interface BoundarySearchResult {
  id: string
  name: string
  properties: Record<string, string>
}

export interface BoundaryFeature {
  type: 'Feature'
  properties: {
    id: string
    name: string
    display_name?: string
    [key: string]: string | undefined
  }
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
}

export interface BoundaryLayerResponse {
  type: 'FeatureCollection'
  features: BoundaryFeature[]
  total_in_layer?: number
  returned?: number
  truncated?: boolean
}

export interface ViewportBounds {
  minLng: number
  minLat: number
  maxLng: number
  maxLat: number
}

export interface BoundaryAtPointResponse {
  found: boolean
  layer: string
  lat: number
  lng: number
  boundary: {
    id: string
    name: string
    properties: Record<string, string>
    geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
  } | null
}

// ============================================================
// API Functions
// ============================================================

export const boundariesApi = {
  /**
   * Get list of available boundary layers
   */
  getLayers: async (): Promise<BoundaryLayer[]> => {
    const { data } = await apiClient.get<BoundaryLayer[]>('/boundaries/layers')
    return data
  },

  /**
   * Get a boundary layer as GeoJSON
   * For large layers (counties, zips, urban_areas), bounds are required
   */
  getLayer: async (
    layerId: string,
    bounds?: ViewportBounds,
    limit: number = 500
  ): Promise<BoundaryLayerResponse> => {
    const params: Record<string, string | number> = { limit }
    
    if (bounds) {
      params.min_lng = bounds.minLng
      params.min_lat = bounds.minLat
      params.max_lng = bounds.maxLng
      params.max_lat = bounds.maxLat
    }
    
    const { data } = await apiClient.get<BoundaryLayerResponse>(
      `/boundaries/layer/${layerId}`,
      { params }
    )
    return data
  },

  /**
   * Search boundaries by name within a layer
   */
  searchLayer: async (
    layerId: string,
    query: string,
    limit: number = 20
  ): Promise<{ results: BoundarySearchResult[], count: number }> => {
    const { data } = await apiClient.get<{ results: BoundarySearchResult[], count: number }>(
      `/boundaries/layer/${layerId}/search`,
      { params: { q: query, limit } }
    )
    return data
  },

  /**
   * Get a specific boundary by ID
   */
  getBoundary: async (layerId: string, boundaryId: string): Promise<BoundaryFeature> => {
    const { data } = await apiClient.get<BoundaryFeature>(
      `/boundaries/layer/${layerId}/${boundaryId}`
    )
    return data
  },

  /**
   * Preload a boundary layer into cache (faster subsequent loads)
   */
  preloadLayer: async (layerId: string): Promise<{ layer: string, loaded: boolean, feature_count: number }> => {
    const { data } = await apiClient.post<{ layer: string, loaded: boolean, feature_count: number }>(
      `/boundaries/layer/${layerId}/preload`
    )
    return data
  },

  /**
   * Clear boundary cache
   */
  clearCache: async (layerId?: string): Promise<{ cleared: string }> => {
    const { data } = await apiClient.delete<{ cleared: string }>('/boundaries/cache', {
      params: layerId ? { layer_id: layerId } : {},
    })
    return data
  },

  /**
   * Find boundary at a point (click-to-select)
   * @param lat Latitude
   * @param lng Longitude
   * @param layer 'zips' | 'counties' | 'states'
   */
  getBoundaryAtPoint: async (
    lat: number,
    lng: number,
    layer: 'zips' | 'counties' | 'states' = 'zips'
  ): Promise<BoundaryAtPointResponse> => {
    const { data } = await apiClient.get<BoundaryAtPointResponse>('/boundaries/point', {
      params: { lat, lng, layer }
    })
    return data
  },
}
