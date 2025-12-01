import { apiClient } from './client'
import {
  Deal,
  DealResponse,
  DealMapResponse,
  GeographicSearchRequest,
  GeographicSearchResponse,
} from '@/types'

export const dealsApi = {
  scrape: async (request: GeographicSearchRequest): Promise<GeographicSearchResponse> => {
    const { data } = await apiClient.post<GeographicSearchResponse>('/deals/scrape', request)
    return data
  },

  getDeals: async (status?: string): Promise<Deal[]> => {
    const params = status ? { status } : {}
    const { data } = await apiClient.get<Deal[]>('/deals', { params })
    return data
  },

  getDeal: async (id: string): Promise<Deal> => {
    const { data } = await apiClient.get<Deal>(`/deals/${id}`)
    return data
  },

  getDealsForMap: async (params?: {
    min_lat?: number
    max_lat?: number
    min_lng?: number
    max_lng?: number
    status?: string
  }): Promise<DealMapResponse[]> => {
    const { data } = await apiClient.get<DealMapResponse[]>('/deals/map', { params })
    return data
  },
}

