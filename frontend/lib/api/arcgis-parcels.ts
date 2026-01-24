/**
 * ArcGIS Regrid Parcel Tiles Integration
 * 
 * Uses the free, unlimited ArcGIS-hosted Regrid parcel layer
 * for discovery without rate limits.
 * 
 * Tile attributes available:
 * - Address (full formatted)
 * - Acreage (size in acres)
 * - APN (parcel number)
 * - Regrid ID (UUID)
 */

// ArcGIS Regrid Parcel Layer Configuration
export const ARCGIS_REGRID_CONFIG = {
  // The public tile layer hosted on ArcGIS Online
  itemId: 'a2050b09baff493aa4ad7848ba2fac00',
  
  // Vector tile service URL (we'll need to fetch the actual URL from the item)
  // Format: https://tiles.arcgis.com/tiles/{orgId}/arcgis/rest/services/{serviceName}/VectorTileServer
  
  // Tile URL template (populated after fetching service info)
  tileUrl: '',
  
  // Available zoom levels for parcels
  minZoom: 10,
  maxZoom: 18,
  
  // Attribute field names (confirmed from user testing)
  fields: {
    address: 'Address',      // or could be address (lowercase)
    acreage: 'Acreage',      // Size in acres
    apn: 'APN',              // Assessor's Parcel Number
    regridId: 'Regrid ID',   // UUID
  }
}

// Parcel data extracted from tiles
export interface ArcGISParcel {
  id: string              // APN or Regrid ID
  address: string
  acreage: number
  apn: string
  regridId: string
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
  centroid: { lat: number; lng: number }
  selected: boolean       // For user selection
}

// Size filter options
export interface SizeFilter {
  minAcres?: number
  maxAcres?: number
}

// Preset size ranges for quick selection
export const SIZE_PRESETS = [
  { label: 'Any size', min: undefined, max: undefined },
  { label: 'Small (< 1 acre)', min: 0, max: 1 },
  { label: 'Medium (1-5 acres)', min: 1, max: 5 },
  { label: 'Large (5-20 acres)', min: 5, max: 20 },
  { label: 'Very Large (20+ acres)', min: 20, max: undefined },
] as const

/**
 * Filter parcels by size
 */
export function filterParcelsBySize(
  parcels: ArcGISParcel[],
  filter: SizeFilter
): ArcGISParcel[] {
  return parcels.filter(parcel => {
    const acres = parcel.acreage
    if (filter.minAcres !== undefined && acres < filter.minAcres) return false
    if (filter.maxAcres !== undefined && acres > filter.maxAcres) return false
    return true
  })
}

/**
 * Check if a point is inside a polygon
 */
export function isPointInPolygon(
  point: { lat: number; lng: number },
  polygon: GeoJSON.Polygon | GeoJSON.MultiPolygon
): boolean {
  // Simple ray-casting algorithm for point-in-polygon
  const { lat, lng } = point
  
  const checkRing = (ring: number[][]): boolean => {
    let inside = false
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1]
      const xj = ring[j][0], yj = ring[j][1]
      
      if (((yi > lat) !== (yj > lat)) &&
          (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi)) {
        inside = !inside
      }
    }
    return inside
  }
  
  if (polygon.type === 'Polygon') {
    // Check outer ring, exclude holes
    const outerRing = polygon.coordinates[0]
    if (!checkRing(outerRing)) return false
    
    // Check holes (if point is in a hole, it's outside the polygon)
    for (let i = 1; i < polygon.coordinates.length; i++) {
      if (checkRing(polygon.coordinates[i])) return false
    }
    return true
  } else if (polygon.type === 'MultiPolygon') {
    // Check each polygon
    for (const poly of polygon.coordinates) {
      const outerRing = poly[0]
      if (checkRing(outerRing)) {
        // Check holes
        let inHole = false
        for (let i = 1; i < poly.length; i++) {
          if (checkRing(poly[i])) {
            inHole = true
            break
          }
        }
        if (!inHole) return true
      }
    }
    return false
  }
  
  return false
}

/**
 * Calculate centroid of a polygon
 */
export function calculateCentroid(
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
): { lat: number; lng: number } {
  let totalLat = 0
  let totalLng = 0
  let count = 0
  
  const processRing = (ring: number[][]) => {
    for (const coord of ring) {
      totalLng += coord[0]
      totalLat += coord[1]
      count++
    }
  }
  
  if (geometry.type === 'Polygon') {
    processRing(geometry.coordinates[0])
  } else if (geometry.type === 'MultiPolygon') {
    for (const poly of geometry.coordinates) {
      processRing(poly[0])
    }
  }
  
  return {
    lat: count > 0 ? totalLat / count : 0,
    lng: count > 0 ? totalLng / count : 0,
  }
}

/**
 * Filter parcels by polygon boundary
 */
export function filterParcelsByPolygon(
  parcels: ArcGISParcel[],
  boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon
): ArcGISParcel[] {
  return parcels.filter(parcel => 
    isPointInPolygon(parcel.centroid, boundary)
  )
}

/**
 * Parse parcel features from Google Maps queryRenderedFeatures
 * This is called when tiles are loaded and we need to extract data
 */
export function parseParcelFeatures(
  features: google.maps.Data.Feature[]
): ArcGISParcel[] {
  const parcels: ArcGISParcel[] = []
  const seenIds = new Set<string>()
  
  for (const feature of features) {
    // Extract properties
    const address = feature.getProperty('Address') || 
                   feature.getProperty('address') || 
                   'Unknown Address'
    
    const acreage = parseFloat(
      feature.getProperty('Acreage') || 
      feature.getProperty('acreage') || 
      feature.getProperty('ll_gisacre') ||
      '0'
    )
    
    const apn = feature.getProperty('APN') || 
               feature.getProperty('apn') || 
               feature.getProperty('parcelnumb') ||
               ''
    
    const regridId = feature.getProperty('Regrid ID') || 
                    feature.getProperty('ll_uuid') ||
                    ''
    
    // Use APN or Regrid ID as unique identifier
    const id = apn || regridId || `${address}-${acreage}`
    
    // Skip duplicates
    if (seenIds.has(id)) continue
    seenIds.add(id)
    
    // Extract geometry
    const geometry = feature.getGeometry()
    if (!geometry) continue
    
    // Convert to GeoJSON
    let geoJsonGeometry: GeoJSON.Polygon | GeoJSON.MultiPolygon | null = null
    
    geometry.forEachLatLng((latLng) => {
      // This is a simplified extraction - in practice we'd need to 
      // properly convert the google.maps.Data.Geometry to GeoJSON
    })
    
    // For now, create a simple point-based representation
    // The actual geometry will be rendered by Google Maps Data layer
    const centroid = { lat: 0, lng: 0 }
    let pointCount = 0
    
    if (geometry.getType() === 'Polygon') {
      const poly = geometry as google.maps.Data.Polygon
      const path = poly.getArray()[0] // outer ring
      if (path) {
        path.getArray().forEach(latLng => {
          centroid.lat += latLng.lat()
          centroid.lng += latLng.lng()
          pointCount++
        })
      }
    }
    
    if (pointCount > 0) {
      centroid.lat /= pointCount
      centroid.lng /= pointCount
    }
    
    parcels.push({
      id,
      address,
      acreage,
      apn,
      regridId,
      geometry: { type: 'Polygon', coordinates: [] }, // Placeholder
      centroid,
      selected: false,
    })
  }
  
  return parcels
}

/**
 * Get the ArcGIS Feature Service URL for direct queries
 * This allows server-side filtering by size
 */
export const ARCGIS_FEATURE_SERVICE = {
  // Regrid's public Feature Service endpoint (requires authentication for full access)
  // For the free tile layer, we use client-side filtering instead
  baseUrl: 'https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services',
  
  // Query endpoint format
  queryUrl: (layerId: string) => 
    `${ARCGIS_FEATURE_SERVICE.baseUrl}/${layerId}/FeatureServer/0/query`,
}

/**
 * Calculate bounding box from a polygon
 */
export function getBoundingBox(polygon: GeoJSON.Polygon | GeoJSON.MultiPolygon): {
  minLat: number
  maxLat: number
  minLng: number
  maxLng: number
} {
  let minLat = Infinity
  let maxLat = -Infinity
  let minLng = Infinity
  let maxLng = -Infinity
  
  const processRing = (ring: number[][]) => {
    for (const coord of ring) {
      minLng = Math.min(minLng, coord[0])
      maxLng = Math.max(maxLng, coord[0])
      minLat = Math.min(minLat, coord[1])
      maxLat = Math.max(maxLat, coord[1])
    }
  }
  
  if (polygon.type === 'Polygon') {
    processRing(polygon.coordinates[0])
  } else if (polygon.type === 'MultiPolygon') {
    for (const poly of polygon.coordinates) {
      processRing(poly[0])
    }
  }
  
  return { minLat, maxLat, minLng, maxLng }
}

/**
 * Calculate approximate area in square miles
 */
export function calculateAreaSqMiles(polygon: GeoJSON.Polygon | GeoJSON.MultiPolygon): number {
  const bbox = getBoundingBox(polygon)
  
  // Approximate using bounding box (rough estimate)
  const latDiff = bbox.maxLat - bbox.minLat
  const lngDiff = bbox.maxLng - bbox.minLng
  
  // Convert to miles (1 degree ≈ 69 miles for latitude, varies for longitude)
  const latMiles = latDiff * 69
  const lngMiles = lngDiff * 69 * Math.cos((bbox.minLat + bbox.maxLat) / 2 * Math.PI / 180)
  
  return latMiles * lngMiles
}
