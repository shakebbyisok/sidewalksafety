import { apiClient } from './client'
import {
  Deal,
  DealMapResponse,
  GeographicSearchRequest,
  GeographicSearchResponse,
} from '@/types'

export const dealsApi = {
  // Start a discovery job
  discover: async (request: GeographicSearchRequest): Promise<GeographicSearchResponse> => {
    const { data } = await apiClient.post<GeographicSearchResponse>('/discover', request)
    return data
  },

  // Legacy scrape endpoint (redirects to discover)
  scrape: async (request: GeographicSearchRequest): Promise<GeographicSearchResponse> => {
    const { data } = await apiClient.post<GeographicSearchResponse>('/discover', request)
    return data
  },

  // Get parking lots (deals)
  getDeals: async (status?: string): Promise<Deal[]> => {
    const params: Record<string, any> = {}
    if (status === 'pending') {
      params.is_evaluated = false
    } else if (status === 'evaluated') {
      params.is_evaluated = true
    }
    
    const { data } = await apiClient.get('/parking-lots', { params })
    
    // Transform parking lot response to Deal format for compatibility
    const results = data.results || []
    return results.map((lot: any) => ({
      id: lot.id,
      user_id: '',
      business_name: lot.business?.name || lot.operator_name || 'Unknown',
      address: lot.address || 'Unknown address',
      latitude: lot.centroid?.lat,
      longitude: lot.centroid?.lng,
      status: lot.is_evaluated ? 'evaluated' : 'pending',
      score: lot.condition_score,
      satellite_url: lot.satellite_image_url,
      created_at: lot.created_at,
      // Business association data
      business: lot.business ? {
        id: lot.business.id,
        name: lot.business.name,
        phone: lot.business.phone,
        email: lot.business.email,
        website: lot.business.website,
        address: lot.business.address,
        category: lot.business.category,
      } : undefined,
      has_business: !!lot.business,
      match_score: lot.match_score,
      distance_meters: lot.distance_meters,
      // Business-first discovery fields
      business_type_tier: lot.business_type_tier,
      discovery_mode: lot.discovery_mode,
      // Analysis data
      paved_area_sqft: lot.paved_area_sqft,
      crack_count: lot.crack_count,
      pothole_count: lot.pothole_count,
      property_boundary_source: lot.property_boundary_source,
      lead_quality: lot.lead_quality,
    }))
  },

  // Get single parking lot
  getDeal: async (id: string): Promise<Deal> => {
    const { data } = await apiClient.get(`/parking-lots/${id}`)
    return {
      id: data.id,
      user_id: '',
      business_name: data.business?.name || data.operator_name || 'Unknown',
      address: data.address || 'Unknown address',
      latitude: data.centroid?.lat,
      longitude: data.centroid?.lng,
      status: data.is_evaluated ? 'evaluated' : 'pending',
      score: data.condition_score,
      satellite_url: data.satellite_image_url,
      created_at: data.created_at,
    } as Deal
  },

  // Get parking lots for map
  getDealsForMap: async (params?: {
    min_lat?: number
    max_lat?: number
    min_lng?: number
    max_lng?: number
    status?: string
  }): Promise<DealMapResponse[]> => {
    const queryParams: Record<string, any> = {}
    
    if (params?.min_lat) queryParams.min_lat = params.min_lat
    if (params?.max_lat) queryParams.max_lat = params.max_lat
    if (params?.min_lng) queryParams.min_lng = params.min_lng
    if (params?.max_lng) queryParams.max_lng = params.max_lng
    
    const { data } = await apiClient.get('/parking-lots/map', { params: queryParams })
    
    // Transform GeoJSON to DealMapResponse format
    const features = data.features || []
    return features.map((feature: any) => ({
      id: feature.properties.id,
      business_name: feature.properties.business_name || feature.properties.operator_name || 'Parking Lot',
      address: feature.properties.address || '',
      latitude: feature.geometry.coordinates[1],
      longitude: feature.geometry.coordinates[0],
      status: feature.properties.is_evaluated ? 'evaluated' : 'pending',
      score: feature.properties.condition_score,
      condition_score: feature.properties.condition_score,
      satellite_url: feature.properties.satellite_image_url,
      business_type_tier: feature.properties.business_type_tier,
      has_business: feature.properties.has_business,
      // Analysis data
      paved_area_sqft: feature.properties.paved_area_sqft,
      crack_count: feature.properties.crack_count,
      pothole_count: feature.properties.pothole_count,
      property_boundary_source: feature.properties.property_boundary_source,
      lead_quality: feature.properties.lead_quality,
    }))
  },
}
