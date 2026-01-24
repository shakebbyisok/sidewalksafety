import { apiClient } from './client'

// ============================================================
// Types
// ============================================================

export interface PointLocation {
  lat: number
  lng: number
}

export interface ViewportBounds {
  minLat: number
  maxLat: number
  minLng: number
  maxLng: number
}

export interface SearchFilters {
  category_id?: string
  min_acres?: number
  max_acres?: number
}

export type SearchType = 'pin' | 'polygon' | 'zip' | 'nlp' | 'category' | 'brand'

export interface SearchRequest {
  search_type: SearchType
  point?: PointLocation
  polygon_geojson?: GeoJSON.Polygon
  zip_code?: string
  viewport?: ViewportBounds
  state_code?: string
  query?: string  // For NLP
  brand_name?: string  // For brand search
  filters?: SearchFilters
  preview_only?: boolean
  limit?: number
  offset?: number
}

export interface SearchParcel {
  parcel_id: string
  address: string | null
  owner: string | null
  lat: number
  lng: number
  area_acres: number | null
  area_sqft: number | null
  land_use: string | null
  zoning: string | null
  year_built: number | null
  polygon_geojson: GeoJSON.Polygon | null
  lbcs_activity: number | null
  lbcs_activity_desc: string | null
  brand_name: string | null
  place_id: string | null
}

export interface SearchResponse {
  success: boolean
  search_type: string
  total_count: number
  parcels: SearchParcel[]
  preview_only: boolean
  error: string | null
  search_session_id: string | null
}

export interface NLPParseRequest {
  query: string
  viewport?: ViewportBounds
}

export interface NLPParseResponse {
  success: boolean
  original_query: string
  parsed: {
    search_type: string
    category_id?: string
    brand_name?: string
    zip_code?: string
    state_code?: string
    min_acres?: number
    max_acres?: number
  }
  suggested_search_type: string
  requires_additional_input: boolean
  message: string | null
}

export interface PropertyCategory {
  id: string
  label: string
  description: string
  icon: string
}

export interface CategoriesResponse {
  categories: PropertyCategory[]
}

export interface County {
  fips: string
  name: string
  state: string
  full_name: string
}

export interface CountySearchResponse {
  counties: County[]
}

export interface CountyBoundaryResponse {
  fips: string
  name: string
  state: string
  boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon | null
}

// ============================================================
// API Functions
// ============================================================

export const searchApi = {
  /**
   * Execute a search
   */
  search: async (request: SearchRequest): Promise<SearchResponse> => {
    const { data } = await apiClient.post<SearchResponse>('/search/search', request, {
      timeout: 60000, // 1 minute for large searches
    })
    return data
  },

  /**
   * Parse a natural language query without executing
   */
  parseNLP: async (request: NLPParseRequest): Promise<NLPParseResponse> => {
    const { data } = await apiClient.post<NLPParseResponse>('/search/search/parse-nlp', request)
    return data
  },

  /**
   * Get available property categories
   */
  getCategories: async (): Promise<PropertyCategory[]> => {
    const { data } = await apiClient.get<CategoriesResponse>('/search/search/categories')
    return data.categories
  },

  /**
   * Get search suggestions for partial query
   */
  getSuggestions: async (query: string): Promise<string[]> => {
    const { data } = await apiClient.get<{ suggestions: string[] }>('/search/search/suggestions', {
      params: { query },
    })
    return data.suggestions
  },

  /**
   * Quick search by category in viewport
   */
  searchByCategory: async (
    categoryId: string,
    viewport: ViewportBounds,
    filters?: Partial<SearchFilters>
  ): Promise<SearchResponse> => {
    return searchApi.search({
      search_type: 'category',
      viewport,
      filters: {
        category_id: categoryId,
        ...filters,
      },
    })
  },

  /**
   * Search for a brand in viewport
   */
  searchBrand: async (
    brandName: string,
    viewport: ViewportBounds
  ): Promise<SearchResponse> => {
    return searchApi.search({
      search_type: 'brand',
      brand_name: brandName,
      viewport,
    })
  },

  /**
   * Search within a drawn polygon
   */
  searchPolygon: async (
    polygon: GeoJSON.Polygon,
    filters?: SearchFilters
  ): Promise<SearchResponse> => {
    return searchApi.search({
      search_type: 'polygon',
      polygon_geojson: polygon,
      filters,
    })
  },

  /**
   * Search by ZIP code with filters
   */
  searchByZip: async (
    zipCode: string,
    filters: SearchFilters
  ): Promise<SearchResponse> => {
    return searchApi.search({
      search_type: 'zip',
      zip_code: zipCode,
      filters,
    })
  },

  /**
   * Natural language search
   */
  searchNLP: async (
    query: string,
    viewport?: ViewportBounds
  ): Promise<SearchResponse> => {
    return searchApi.search({
      search_type: 'nlp',
      query,
      viewport,
    })
  },

  /**
   * Search counties by name (autocomplete)
   */
  searchCounties: async (query: string, limit: number = 20): Promise<County[]> => {
    const { data } = await apiClient.get<CountySearchResponse>('/search/search/counties', {
      params: { query, limit },
    })
    return data.counties
  },

  /**
   * Get county boundary GeoJSON
   */
  getCountyBoundary: async (fips: string): Promise<CountyBoundaryResponse> => {
    const { data } = await apiClient.get<CountyBoundaryResponse>(`/search/search/counties/${fips}/boundary`)
    return data
  },
}
