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
      business_name: lot.business?.name || lot.operator_name,
      address: lot.address || 'Unknown address',
      latitude: lot.centroid?.lat,
      longitude: lot.centroid?.lng,
      status: lot.status || (lot.is_evaluated ? 'evaluated' : 'pending'),
      score: lot.lead_score || lot.condition_score,
      lead_score: lot.lead_score,
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
      discovery_source: lot.discovery_source,
      // Regrid data
      regrid_owner: lot.regrid_owner,
      property_category: lot.property_category,
      // Contact/enrichment data
      contact_company: lot.contact?.company,
      contact_phone: lot.contact?.phone,
      contact_email: lot.contact?.email,
      has_contact: !!(lot.contact?.email || lot.contact?.phone || lot.contact?.company),
      enrichment_status: lot.contact?.status,
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
    return features.map((feature: any) => {
      const props = feature.properties
      return {
        id: props.id,
        business_name: props.business_name,
        display_name: props.display_name,
        address: props.address || '',
        latitude: feature.geometry.coordinates[1],
        longitude: feature.geometry.coordinates[0],
        status: props.status || (props.is_evaluated ? 'evaluated' : 'pending'),
        score: props.lead_score || props.condition_score,
        lead_score: props.lead_score,
        condition_score: props.condition_score,
        satellite_url: props.satellite_image_url,
        business_type_tier: props.business_type_tier,
        has_business: props.has_business,
        // Regrid data
        regrid_owner: props.regrid_owner,
        property_category: props.property_category,
        // Contact/enrichment data
        contact_company: props.contact_company,
        contact_phone: props.contact_phone,
        contact_email: props.contact_email,
        has_contact: props.has_contact,
        enrichment_status: props.enrichment_status,
        // Discovery source
        discovery_source: props.discovery_source,
        // Analysis data
        paved_area_sqft: props.paved_area_sqft,
        crack_count: props.crack_count,
        pothole_count: props.pothole_count,
        property_boundary_source: props.property_boundary_source,
        lead_quality: props.lead_quality,
      }
    })
  },
}
