/**
 * Discovery API Client
 * 
 * Fetches real parcel geometries from Regrid's MVT vector tiles.
 * Tiles are free (unlimited), only record queries count against quota.
 */

import { apiClient } from './client'

// Types
export interface DiscoveryParcel {
  id: string
  address: string
  acreage: number
  apn: string
  regrid_id: string
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
  centroid: { lat: number; lng: number }
  owner?: string | null  // From Regrid tiles
  selected?: boolean  // Client-side selection state
}

export interface DiscoveryQueryRequest {
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
  min_acres?: number
  max_acres?: number
  limit?: number
}

export interface DiscoveryQueryResponse {
  success: boolean
  parcels: DiscoveryParcel[]
  total_count: number
  error?: string
}

export interface ProcessParcelsRequest {
  parcels: DiscoveryParcel[]
}

export interface ProcessParcelsResponse {
  success: boolean
  message: string
  job_id?: string
}

// API Client
export const discoveryApi = {
  /**
   * Query parcels within a given area with optional size filter.
   * Uses Regrid Tileserver MVT - real geometries, unlimited requests!
   */
  queryParcels: async (request: DiscoveryQueryRequest): Promise<DiscoveryQueryResponse> => {
    const { data } = await apiClient.post<DiscoveryQueryResponse>('/discover/parcels', {
      geometry: request.geometry,
      min_acres: request.min_acres,
      max_acres: request.max_acres,
      limit: request.limit || 500,
    })
    return data
  },

  /**
   * Process selected parcels for LLM enrichment to find contact information.
   */
  processParcels: async (request: ProcessParcelsRequest): Promise<ProcessParcelsResponse> => {
    const { data } = await apiClient.post<ProcessParcelsResponse>('/discover/process', {
      parcels: request.parcels,
    })
    return data
  },
}

export default discoveryApi
