'use client'

/**
 * PropertyAnalysisMap - Interactive map displaying property analysis results
 * 
 * UPDATED: Now displays surface types from Grounded SAM detection
 * 
 * Displays:
 * - Property boundary (from Regrid) - Blue dashed outline
 * - Asphalt surfaces (dark pavement) - Dark gray fill
 * - Concrete surfaces (light pavement) - Light gray fill
 * - Buildings detected - Red outline
 * - Damage detections (cracks/potholes) - Red/orange markers
 * 
 * This is the core visualization for our smart analysis pipeline.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { Loader2, Layers, ZoomIn, ZoomOut, MapPin, Grid3X3, Eye, EyeOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { SurfacesBreakdown, GeoJSONFeature as TypedGeoJSONFeature } from '@/types'

// Types for GeoJSON structures
interface GeoJSONPolygon {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: number[][][] | number[][][][]
}

interface GeoJSONFeature {
  type: 'Feature'
  geometry: GeoJSONPolygon
  properties?: Record<string, any>
}

interface GeoJSONFeatureCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature[]
}

interface DamageMarker {
  lat: number
  lng: number
  type: 'crack' | 'pothole'
  severity: 'minor' | 'moderate' | 'severe'
  confidence?: number
}

// Surface layer configuration
interface SurfaceLayerConfig {
  key: string
  label: string
  color: string
  fillOpacity: number
  strokeOpacity: number
}

const SURFACE_LAYERS: SurfaceLayerConfig[] = [
  { key: 'asphalt', label: 'Paved', color: '#374151', fillOpacity: 0.5, strokeOpacity: 0.9 },
  { key: 'concrete', label: 'Concrete', color: '#9CA3AF', fillOpacity: 0.5, strokeOpacity: 0.9 },
  { key: 'buildings', label: 'Buildings', color: '#DC2626', fillOpacity: 0.1, strokeOpacity: 0.8 },
]

interface PropertyAnalysisMapProps {
  // Center point
  latitude: number
  longitude: number
  
  // Property boundary from Regrid (GeoJSON polygon)
  propertyBoundary?: GeoJSONPolygon | GeoJSONFeature
  
  // NEW: Surface breakdown from Grounded SAM
  surfaces?: SurfacesBreakdown
  
  // All surfaces as GeoJSON (for display)
  surfacesGeoJSON?: GeoJSONFeatureCollection
  
  // LEGACY: Private asphalt areas detected (backwards compat)
  asphaltAreas?: GeoJSONFeatureCollection | GeoJSONFeature
  
  // Damage detections with geo-coordinates
  damageMarkers?: DamageMarker[]
  
  // Damage GeoJSON (alternative format from backend)
  damageGeoJSON?: GeoJSONFeatureCollection
  
  // Optional: Public roads that were filtered (for reference)
  publicRoads?: GeoJSONFeatureCollection
  
  // UI options
  className?: string
  height?: string
  showLegend?: boolean
  showControls?: boolean
  initialZoom?: number
  
  // Callbacks
  onMarkerClick?: (marker: DamageMarker) => void
}

// Google Maps types (we'll use window.google)
declare global {
  interface Window {
    google: any
    initPropertyMap: () => void
  }
}

export function PropertyAnalysisMap({
  latitude,
  longitude,
  propertyBoundary,
  surfaces,
  surfacesGeoJSON,
  asphaltAreas,
  damageMarkers,
  damageGeoJSON,
  publicRoads,
  className,
  height = '500px',
  showLegend = true,
  showControls = true,
  initialZoom = 18,
  onMarkerClick,
}: PropertyAnalysisMapProps) {
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [mapError, setMapError] = useState<string | null>(null)
  const [activeLayer, setActiveLayer] = useState({
    boundary: true,
    asphalt: true,
    concrete: true,
    buildings: false,
    damage: true,
    roads: false,
  })
  
  // Store references to map overlays for toggling
  const overlaysRef = useRef<{
    boundary: any[]
    asphalt: any[]
    concrete: any[]
    buildings: any[]
    damage: any[]
    roads: any[]
  }>({
    boundary: [],
    asphalt: [],
    concrete: [],
    buildings: [],
    damage: [],
    roads: [],
  })

  // Load Google Maps script
  const loadGoogleMaps = useCallback(() => {
    return new Promise<void>((resolve, reject) => {
      if (window.google && window.google.maps) {
        resolve()
        return
      }

      // Check if script is already being loaded
      const existingScript = document.getElementById('google-maps-script')
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve())
        return
      }

      const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY
      if (!apiKey) {
        reject(new Error('Google Maps API key not configured'))
        return
      }

      const script = document.createElement('script')
      script.id = 'google-maps-script'
      script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=geometry`
      script.async = true
      script.defer = true
      
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Failed to load Google Maps'))
      
      document.head.appendChild(script)
    })
  }, [])

  // Initialize map
  const initializeMap = useCallback(async () => {
    if (!mapRef.current) return
    
    try {
      await loadGoogleMaps()
      
      const map = new window.google.maps.Map(mapRef.current, {
        center: { lat: latitude, lng: longitude },
        zoom: initialZoom,
        mapTypeId: 'satellite',
        tilt: 0,
        disableDefaultUI: false,
        zoomControl: false,
        streetViewControl: false,
        mapTypeControl: false,
        fullscreenControl: false,
        gestureHandling: 'greedy',
        styles: [
          {
            featureType: 'all',
            elementType: 'labels',
            stylers: [{ visibility: 'on' }]
          }
        ]
      })
      
      mapInstanceRef.current = map
      
      // Draw overlays
      drawPropertyBoundary(map)
      drawSurfaceAreas(map) // NEW: Uses surfaces or falls back to asphaltAreas
      drawDamageMarkers(map)
      drawPublicRoads(map)
      
      // Fit bounds to show all content
      fitMapToBounds(map)
      
      setIsLoading(false)
    } catch (error) {
      console.error('Failed to initialize map:', error)
      setMapError(error instanceof Error ? error.message : 'Failed to load map')
      setIsLoading(false)
    }
  }, [latitude, longitude, initialZoom, loadGoogleMaps])

  // Convert GeoJSON coordinates to Google Maps LatLng
  const coordsToLatLng = (coords: number[][]): any[] => {
    return coords.map(coord => ({
      lat: coord[1],
      lng: coord[0]
    }))
  }

  // Draw property boundary
  const drawPropertyBoundary = (map: any) => {
    if (!propertyBoundary) return
    
    const geometry = (propertyBoundary as GeoJSONFeature).geometry || propertyBoundary as GeoJSONPolygon
    if (!geometry || !geometry.coordinates) return
    
    const polygons: any[] = []
    
    if (geometry.type === 'Polygon') {
      const paths = coordsToLatLng(geometry.coordinates[0] as number[][])
      const polygon = new window.google.maps.Polygon({
        paths,
        strokeColor: '#3B82F6', // Blue
        strokeOpacity: 1,
        strokeWeight: 3,
        fillColor: '#3B82F6',
        fillOpacity: 0.05,
        map: activeLayer.boundary ? map : null,
      })
      polygons.push(polygon)
    } else if (geometry.type === 'MultiPolygon') {
      const multiCoords = geometry.coordinates as number[][][][]
      multiCoords.forEach((polyCoords: number[][][]) => {
        const paths = coordsToLatLng(polyCoords[0])
        const polygon = new window.google.maps.Polygon({
          paths,
          strokeColor: '#3B82F6',
          strokeOpacity: 1,
          strokeWeight: 3,
          fillColor: '#3B82F6',
          fillOpacity: 0.05,
          map: activeLayer.boundary ? map : null,
        })
        polygons.push(polygon)
      })
    }
    
    overlaysRef.current.boundary = polygons
  }

  // Draw surface areas (NEW: Uses Grounded SAM surfaces or falls back to legacy)
  const drawSurfaceAreas = (map: any) => {
    let hasDrawnSurfaces = false
    
    // NEW: If we have surfaces from Grounded SAM with geojson, use those
    if (surfaces) {
      // Draw asphalt
      if (surfaces.asphalt?.geojson) {
        // Handle both single Feature and FeatureCollection
        const geojson = surfaces.asphalt.geojson as any
        if (geojson.type === 'FeatureCollection' && geojson.features) {
          geojson.features.forEach((feature: GeoJSONFeature) => {
            const polygons = drawSurfacePolygon(map, feature, 'asphalt', surfaces.asphalt?.color || '#374151', undefined, 'Paved')
            overlaysRef.current.asphalt.push(...polygons)
          })
        } else {
          const polygons = drawSurfacePolygon(map, geojson as GeoJSONFeature, 'asphalt', surfaces.asphalt.color || '#374151', surfaces.asphalt.area_sqft, 'Paved Surface')
          overlaysRef.current.asphalt = polygons
        }
        hasDrawnSurfaces = true
      }
      
      // Draw concrete
      if (surfaces.concrete?.geojson) {
        const polygons = drawSurfacePolygon(
          map, 
          surfaces.concrete.geojson as unknown as GeoJSONFeature, 
          'concrete',
          surfaces.concrete.color || '#9CA3AF',
          surfaces.concrete.area_sqft,
          'Concrete'
        )
        overlaysRef.current.concrete = polygons
        hasDrawnSurfaces = true
      }
      
      // Draw buildings
      if (surfaces.buildings?.geojson) {
        const polygons = drawSurfacePolygon(
          map, 
          surfaces.buildings.geojson as unknown as GeoJSONFeature, 
          'buildings',
          surfaces.buildings.color || '#DC2626',
          undefined,
          'Building'
        )
        overlaysRef.current.buildings = polygons
        hasDrawnSurfaces = true
      }
      
      // If we drew surfaces from the structured data, we're done
      if (hasDrawnSurfaces) return
    }
    
    // FALLBACK: If we have surfacesGeoJSON (FeatureCollection), parse it
    if (surfacesGeoJSON?.features) {
      surfacesGeoJSON.features.forEach((feature: GeoJSONFeature) => {
        const surfaceType = feature.properties?.surface_type || feature.properties?.type || 'asphalt'
        const layerKey = surfaceType === 'concrete' ? 'concrete' : 
                         surfaceType === 'building' ? 'buildings' : 'asphalt'
        const config = SURFACE_LAYERS.find(l => l.key === layerKey) || SURFACE_LAYERS[0]
        
        const polygons = drawSurfacePolygon(
          map,
          feature,
          layerKey as 'asphalt' | 'concrete' | 'buildings',
          feature.properties?.color || config.color,
          feature.properties?.area_sqft,
          config.label
        )
        
        overlaysRef.current[layerKey as keyof typeof overlaysRef.current].push(...polygons)
      })
      return
    }
    
    // LEGACY: Fall back to old asphaltAreas format
    if (!asphaltAreas) return
    
    const features = (asphaltAreas as GeoJSONFeatureCollection).features || 
                     [(asphaltAreas as GeoJSONFeature)]
    
    features.forEach((feature: GeoJSONFeature) => {
      const polygons = drawSurfacePolygon(
        map,
        feature,
        'asphalt',
        '#374151',
        feature.properties?.area_sqft,
        'Private Pavement'
      )
      overlaysRef.current.asphalt.push(...polygons)
    })
  }
  
  // Helper: Draw a single surface polygon with proper styling
  const drawSurfacePolygon = (
    map: any,
    feature: GeoJSONFeature,
    layerKey: 'asphalt' | 'concrete' | 'buildings',
    color: string,
    areaSqft?: number,
    label?: string
  ): any[] => {
    const geometry = feature.geometry
    if (!geometry || !geometry.coordinates) return []
    
    const config = SURFACE_LAYERS.find(l => l.key === layerKey) || SURFACE_LAYERS[0]
    const polygons: any[] = []
    
    const createPolygon = (paths: any[]) => {
      const polygon = new window.google.maps.Polygon({
        paths,
        strokeColor: color,
        strokeOpacity: config.strokeOpacity,
        strokeWeight: 2,
        fillColor: color,
        fillOpacity: config.fillOpacity,
        map: activeLayer[layerKey as keyof typeof activeLayer] ? map : null,
      })
      
      // Info window
      if (areaSqft || label) {
        const infoWindow = new window.google.maps.InfoWindow({
          content: `<div style="padding: 10px; font-family: system-ui;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
              <div style="width: 12px; height: 12px; background: ${color}; border-radius: 2px;"></div>
              <strong style="font-size: 14px;">${label || config.label}</strong>
            </div>
            ${areaSqft ? `<div style="color: #666; font-size: 13px;">${Math.round(areaSqft).toLocaleString()} sq ft</div>` : ''}
          </div>`
        })
        
        polygon.addListener('click', (e: any) => {
          infoWindow.setPosition(e.latLng)
          infoWindow.open(map)
        })
      }
      
      return polygon
    }
    
    if (geometry.type === 'Polygon') {
      const paths = coordsToLatLng(geometry.coordinates[0] as number[][])
      polygons.push(createPolygon(paths))
    } else if (geometry.type === 'MultiPolygon') {
      const multiCoords = geometry.coordinates as number[][][][]
      multiCoords.forEach((polyCoords: number[][][]) => {
        const paths = coordsToLatLng(polyCoords[0])
        polygons.push(createPolygon(paths))
      })
    }
    
    return polygons
  }

  // Draw damage markers
  const drawDamageMarkers = (map: any) => {
    const markers: any[] = []
    
    // From direct markers prop
    if (damageMarkers) {
      damageMarkers.forEach((marker, idx) => {
        const mapMarker = createDamageMarker(map, marker, idx)
        if (mapMarker) markers.push(mapMarker)
      })
    }
    
    // From GeoJSON
    if (damageGeoJSON?.features) {
      damageGeoJSON.features.forEach((feature, idx) => {
        if (feature.geometry.type !== 'Point') return
        
        const [lng, lat] = feature.geometry.coordinates as unknown as number[]
        const marker: DamageMarker = {
          lat,
          lng,
          type: feature.properties?.type || 'crack',
          severity: feature.properties?.severity || 'minor',
          confidence: feature.properties?.confidence,
        }
        
        const mapMarker = createDamageMarker(map, marker, idx + (damageMarkers?.length || 0))
        if (mapMarker) markers.push(mapMarker)
      })
    }
    
    overlaysRef.current.damage = markers
  }

  // Create a single damage marker
  const createDamageMarker = (map: any, marker: DamageMarker, idx: number) => {
    const color = marker.type === 'pothole' ? '#EF4444' : '#F97316' // Red for pothole, orange for crack
    const size = marker.severity === 'severe' ? 16 : marker.severity === 'moderate' ? 12 : 8
    
    const mapMarker = new window.google.maps.Marker({
      position: { lat: marker.lat, lng: marker.lng },
      map: activeLayer.damage ? map : null,
      icon: {
        path: window.google.maps.SymbolPath.CIRCLE,
        fillColor: color,
        fillOpacity: 0.9,
        strokeColor: '#FFFFFF',
        strokeWeight: 2,
        scale: size,
      },
      title: `${marker.type} (${marker.severity})`,
    })
    
    // Info window
    const infoWindow = new window.google.maps.InfoWindow({
      content: `<div style="padding: 8px; font-family: system-ui;">
        <strong>${marker.type === 'pothole' ? '🕳️ Pothole' : '⚡ Crack'}</strong><br/>
        Severity: ${marker.severity}<br/>
        ${marker.confidence ? `Confidence: ${Math.round(marker.confidence * 100)}%` : ''}
      </div>`
    })
    
    mapMarker.addListener('click', () => {
      infoWindow.open(map, mapMarker)
      onMarkerClick?.(marker)
    })
    
    return mapMarker
  }

  // Draw public roads (reference layer)
  const drawPublicRoads = (map: any) => {
    if (!publicRoads?.features) return
    
    const polygons: any[] = []
    
    publicRoads.features.forEach((feature: GeoJSONFeature) => {
      const geometry = feature.geometry
      if (!geometry || !geometry.coordinates) return
      
      if (geometry.type === 'Polygon') {
        const paths = coordsToLatLng(geometry.coordinates[0] as number[][])
        const polygon = new window.google.maps.Polygon({
          paths,
          strokeColor: '#6B7280', // Gray
          strokeOpacity: 0.5,
          strokeWeight: 1,
          fillColor: '#6B7280',
          fillOpacity: 0.2,
          map: activeLayer.roads ? map : null,
        })
        polygons.push(polygon)
      }
    })
    
    overlaysRef.current.roads = polygons
  }

  // Fit map to show all content
  const fitMapToBounds = (map: any) => {
    const bounds = new window.google.maps.LatLngBounds()
    let hasContent = false
    
    // Add property boundary to bounds
    overlaysRef.current.boundary.forEach((polygon: any) => {
      polygon.getPath().forEach((point: any) => {
        bounds.extend(point)
        hasContent = true
      })
    })
    
    // Add asphalt areas
    overlaysRef.current.asphalt.forEach((polygon: any) => {
      polygon.getPath().forEach((point: any) => {
        bounds.extend(point)
        hasContent = true
      })
    })
    
    // Add damage markers
    overlaysRef.current.damage.forEach((marker: any) => {
      bounds.extend(marker.getPosition())
      hasContent = true
    })
    
    if (hasContent) {
      map.fitBounds(bounds, { padding: 50 })
    }
  }

  // Toggle layer visibility
  const toggleLayer = (layer: keyof typeof activeLayer) => {
    const newState = !activeLayer[layer]
    setActiveLayer(prev => ({ ...prev, [layer]: newState }))
    
    const overlays = overlaysRef.current[layer]
    overlays.forEach((overlay: any) => {
      overlay.setMap(newState ? mapInstanceRef.current : null)
    })
  }

  // Zoom controls
  const handleZoom = (direction: 'in' | 'out') => {
    const map = mapInstanceRef.current
    if (!map) return
    
    const currentZoom = map.getZoom()
    map.setZoom(direction === 'in' ? currentZoom + 1 : currentZoom - 1)
  }

  // Initialize map on mount
  useEffect(() => {
    initializeMap()
    
    return () => {
      // Cleanup overlays
      Object.values(overlaysRef.current).flat().forEach((overlay: any) => {
        if (overlay.setMap) overlay.setMap(null)
      })
    }
  }, [initializeMap])

  // Re-draw when data changes
  useEffect(() => {
    if (mapInstanceRef.current) {
      // Clear existing overlays
      Object.values(overlaysRef.current).flat().forEach((overlay: any) => {
        if (overlay.setMap) overlay.setMap(null)
      })
      overlaysRef.current = { boundary: [], asphalt: [], concrete: [], buildings: [], damage: [], roads: [] }
      
      // Redraw
      drawPropertyBoundary(mapInstanceRef.current)
      drawSurfaceAreas(mapInstanceRef.current)
      drawDamageMarkers(mapInstanceRef.current)
      drawPublicRoads(mapInstanceRef.current)
      fitMapToBounds(mapInstanceRef.current)
    }
  }, [propertyBoundary, surfaces, surfacesGeoJSON, asphaltAreas, damageMarkers, damageGeoJSON, publicRoads])

  if (mapError) {
    return (
      <div 
        className={cn("flex items-center justify-center bg-muted rounded-lg", className)}
        style={{ height }}
      >
        <div className="text-center text-muted-foreground">
          <MapPin className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>Failed to load map</p>
          <p className="text-sm">{mapError}</p>
        </div>
      </div>
    )
  }

  return (
    <div className={cn("relative rounded-lg overflow-hidden", className)} style={{ height }}>
      {/* Map container */}
      <div ref={mapRef} className="w-full h-full" />
      
      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}
      
      {/* Controls */}
      {showControls && !isLoading && (
        <div className="absolute top-3 right-3 flex flex-col gap-2">
          {/* Zoom controls */}
          <div className="flex flex-col bg-background rounded-lg shadow-md border">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => handleZoom('in')}
            >
              <ZoomIn className="h-4 w-4" />
            </Button>
            <div className="border-t" />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => handleZoom('out')}
            >
              <ZoomOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
      
      {/* Layer toggles */}
      {showControls && !isLoading && (
        <div className="absolute top-3 left-3 bg-background/95 backdrop-blur rounded-lg shadow-md border p-2.5">
          <div className="flex items-center gap-1.5 mb-2 pb-2 border-b">
            <Layers className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold">Layers</span>
          </div>
          <div className="space-y-1">
            <LayerToggle
              label="Property Boundary"
              color="#3B82F6"
              active={activeLayer.boundary}
              onClick={() => toggleLayer('boundary')}
            />
            <div className="pt-1 mt-1 border-t">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Surfaces</span>
            </div>
            <LayerToggle
              label="Paved"
              color="#374151"
              active={activeLayer.asphalt}
              onClick={() => toggleLayer('asphalt')}
              subtitle={surfaces?.asphalt?.area_sqft ? `${Math.round(surfaces.asphalt.area_sqft).toLocaleString()} sqft` : undefined}
            />
            <LayerToggle
              label="Concrete"
              color="#9CA3AF"
              active={activeLayer.concrete}
              onClick={() => toggleLayer('concrete')}
              subtitle={surfaces?.concrete?.area_sqft ? `${Math.round(surfaces.concrete.area_sqft).toLocaleString()} sqft` : undefined}
            />
            <LayerToggle
              label="Buildings"
              color="#DC2626"
              active={activeLayer.buildings}
              onClick={() => toggleLayer('buildings')}
            />
            <div className="pt-1 mt-1 border-t">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Analysis</span>
            </div>
            <LayerToggle
              label="Damage"
              color="#EF4444"
              active={activeLayer.damage}
              onClick={() => toggleLayer('damage')}
            />
            {publicRoads && (
              <LayerToggle
                label="Public Roads"
                color="#6B7280"
                active={activeLayer.roads}
                onClick={() => toggleLayer('roads')}
              />
            )}
          </div>
        </div>
      )}
      
      {/* Legend */}
      {showLegend && !isLoading && (
        <div className="absolute bottom-3 left-3 bg-background/95 backdrop-blur rounded-lg shadow-md border p-2.5 text-xs">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 border-2 border-blue-500 bg-blue-500/10 rounded-sm" />
              <span className="font-medium">Property</span>
            </div>
            <div className="h-4 border-l border-muted" />
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#374151' }} />
              <span>Paved</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#9CA3AF' }} />
              <span>Concrete</span>
            </div>
            <div className="h-4 border-l border-muted" />
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 bg-orange-500 rounded-full" />
              <span>Crack</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 bg-red-500 rounded-full" />
              <span>Pothole</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Layer toggle button
function LayerToggle({
  label,
  color,
  active,
  onClick,
  subtitle,
}: {
  label: string
  color: string
  active: boolean
  onClick: () => void
  subtitle?: string
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 w-full px-2 py-1.5 rounded text-xs transition-colors",
        active ? "bg-muted" : "hover:bg-muted/50 opacity-50"
      )}
    >
      <div 
        className="w-3 h-3 rounded-sm border flex-shrink-0"
        style={{ 
          backgroundColor: active ? color : 'transparent',
          borderColor: color,
        }}
      />
      <div className="flex flex-col items-start">
        <span className="font-medium">{label}</span>
        {subtitle && (
          <span className="text-[10px] text-muted-foreground">{subtitle}</span>
        )}
      </div>
      <div className="ml-auto">
        {active ? (
          <Eye className="h-3 w-3 text-muted-foreground" />
        ) : (
          <EyeOff className="h-3 w-3 text-muted-foreground/50" />
        )}
      </div>
    </button>
  )
}

export default PropertyAnalysisMap

