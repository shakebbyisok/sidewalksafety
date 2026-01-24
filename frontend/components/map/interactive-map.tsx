'use client'

import { useMemo, useCallback, useEffect, useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { APIProvider, Map, Marker, useMap, InfoWindow, useMapsLibrary } from '@vis.gl/react-google-maps'
import { MarkerClusterer, GridAlgorithm } from '@googlemaps/markerclusterer'
import { DealMapResponse, PropertyAnalysisSummary } from '@/types'
import { MapPin, ExternalLink, Satellite, Map as MapIcon, X, CheckCircle2, Clock, Target, Building2, Phone, Globe, AlertTriangle, Search, Loader2, Layers, User, Pentagon } from 'lucide-react'
import { StatusChip, IconChip } from '@/components/ui'
import { cn } from '@/lib/utils'
import { parkingLotsApi } from '@/lib/api/parking-lots'
import { SearchParcel } from '@/lib/api/search'
import { BoundaryLayerResponse, BoundaryFeature, boundariesApi } from '@/lib/api/boundaries'

// Boundary layer colors
const BOUNDARY_LAYER_COLORS: Record<string, { stroke: string; fill: string }> = {
  states: { stroke: '#6366f1', fill: 'rgba(99, 102, 241, 0.08)' },
  counties: { stroke: '#f59e0b', fill: 'rgba(245, 158, 11, 0.08)' },
  zips: { stroke: '#10b981', fill: 'rgba(16, 185, 129, 0.05)' },
  urban_areas: { stroke: '#ef4444', fill: 'rgba(239, 68, 68, 0.08)' },
}

// Surface colors for polygon overlays
const SURFACE_COLORS: Record<string, { fill: string; stroke: string; label: string }> = {
  asphalt: { fill: '#374151', stroke: '#1F2937', label: 'Paved' },
  concrete: { fill: '#9CA3AF', stroke: '#6B7280', label: 'Concrete' },
  building: { fill: '#DC2626', stroke: '#991B1B', label: 'Building' },
  property_boundary: { fill: '#3B82F6', stroke: '#1D4ED8', label: 'Property' },
}

// Urban area info type for search guidance
interface UrbanAreaInfo {
  id: string
  name: string
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
}

interface InteractiveMapProps {
  deals: DealMapResponse[]
  selectedDeal: DealMapResponse | null
  onDealSelect: (deal: DealMapResponse | null) => void
  onViewDetails: (dealId: string) => void
  onBoundsChange?: (bounds: { minLat: number; maxLat: number; minLng: number; maxLng: number }) => void
  onMapClick?: (lat: number, lng: number) => void
  clickedLocation?: { lat: number; lng: number } | null
  previewPolygon?: any // GeoJSON polygon to preview on map
  // Search features
  searchResults?: SearchParcel[]
  isDrawingPolygon?: boolean
  onPolygonDrawn?: (polygon: GeoJSON.Polygon) => void
  // County boundary display
  countyBoundary?: { boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon | null; name: string }
  // Boundary layer display (states, counties, zips, urban areas from KML)
  boundaryLayer?: { data: BoundaryLayerResponse | null; layerId: string | null }
  // Click-to-select mode for ZIP/County/Pin/Urban search
  mapClickMode?: 'zip' | 'county' | 'pin' | 'urban' | null
  // Pin parcel polygon to display
  pinParcelPolygon?: GeoJSON.Polygon | GeoJSON.MultiPolygon | null
  // Drawn polygon for search (from drawing tool)
  drawnPolygon?: GeoJSON.Polygon | null
  // Urban area overlay for search guidance
  showUrbanOverlay?: boolean
  selectedUrbanArea?: UrbanAreaInfo | null
  onUrbanAreaSelect?: (urbanArea: UrbanAreaInfo | null) => void
}

// Clean, modern map style with subtle colors
const mapStyles: google.maps.MapTypeStyle[] = [
  // Base landscape - warm cream/beige
  {
    featureType: 'landscape',
    elementType: 'geometry.fill',
    stylers: [{ color: '#f5f3ef' }],
  },
  {
    featureType: 'landscape.man_made',
    elementType: 'geometry.fill',
    stylers: [{ color: '#f0ede8' }],
  },
  // Water - soft blue
  {
    featureType: 'water',
    elementType: 'geometry.fill',
    stylers: [{ color: '#d4e4ed' }],
  },
  {
    featureType: 'water',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#7da0b8' }],
  },
  // Parks and green areas - muted sage
  {
    featureType: 'poi.park',
    elementType: 'geometry.fill',
    stylers: [{ color: '#dce8dc' }],
  },
  {
    featureType: 'poi.park',
    elementType: 'labels',
    stylers: [{ visibility: 'off' }],
  },
  // Hide other POIs
  {
    featureType: 'poi',
    elementType: 'labels',
    stylers: [{ visibility: 'off' }],
  },
  {
    featureType: 'poi.business',
    stylers: [{ visibility: 'off' }],
  },
  // Roads - clean hierarchy
  {
    featureType: 'road.highway',
    elementType: 'geometry.fill',
    stylers: [{ color: '#ffffff' }],
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#e0ddd8' }, { weight: 1 }],
  },
  {
    featureType: 'road.highway',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#6b6b6b' }],
  },
  {
    featureType: 'road.arterial',
    elementType: 'geometry.fill',
    stylers: [{ color: '#ffffff' }],
  },
  {
    featureType: 'road.arterial',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#e8e5e0' }, { weight: 0.5 }],
  },
  {
    featureType: 'road.arterial',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#8a8a8a' }],
  },
  {
    featureType: 'road.local',
    elementType: 'geometry.fill',
    stylers: [{ color: '#fafafa' }],
  },
  {
    featureType: 'road.local',
    elementType: 'labels',
    stylers: [{ visibility: 'simplified' }],
  },
  {
    featureType: 'road.local',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#b0b0b0' }],
  },
  // Transit - hide
  {
    featureType: 'transit',
    stylers: [{ visibility: 'off' }],
  },
  // Administrative boundaries
  {
    featureType: 'administrative',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#c8c5c0' }, { weight: 0.8 }],
  },
  {
    featureType: 'administrative.locality',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#555555' }],
  },
  {
    featureType: 'administrative.neighborhood',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#999999' }],
  },
  // Buildings - subtle
  {
    featureType: 'landscape.man_made',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#e5e2dd' }, { weight: 0.5 }],
  },
]

function MapController({
  onBoundsChange,
  onMapClick,
}: {
  onBoundsChange?: (bounds: { minLat: number; maxLat: number; minLng: number; maxLng: number }) => void
  onMapClick?: (lat: number, lng: number) => void
}) {
  const map = useMap()

  useEffect(() => {
    if (!map) return

    const handleIdle = () => {
      const bounds = map.getBounds()
      if (bounds && onBoundsChange) {
        const ne = bounds.getNorthEast()
        const sw = bounds.getSouthWest()
        onBoundsChange({
          minLat: sw.lat(),
          maxLat: ne.lat(),
          minLng: sw.lng(),
          maxLng: ne.lng(),
        })
      }
    }

    const handleClick = (e: google.maps.MapMouseEvent) => {
      if (e.latLng && onMapClick) {
        onMapClick(e.latLng.lat(), e.latLng.lng())
      }
    }

    map.addListener('idle', handleIdle)
    map.addListener('click', handleClick)
    handleIdle()

    return () => {
      google.maps.event.clearListeners(map, 'idle')
      google.maps.event.clearListeners(map, 'click')
    }
  }, [map, onBoundsChange, onMapClick])

  return null
}

function CenterMapController({
  selectedDeal,
}: {
  selectedDeal: DealMapResponse | null
}) {
  const map = useMap()

  useEffect(() => {
    if (!map || !selectedDeal || !selectedDeal.latitude || !selectedDeal.longitude) return

    // Center the map on the selected parking lot with smooth pan
    const currentZoom = map.getZoom() || 13
    const targetZoom = currentZoom < 15 ? 15 : currentZoom // Zoom in if too far out
    
    map.panTo({
      lat: selectedDeal.latitude,
      lng: selectedDeal.longitude,
    })
    
    // Adjust zoom if needed (smooth zoom)
    if (currentZoom < 15) {
      map.setZoom(15)
    }
  }, [map, selectedDeal])

  return null
}

function MapTypeController({
  mapType,
  onMapTypeChange,
}: {
  mapType: 'roadmap' | 'hybrid'
  onMapTypeChange: (type: 'roadmap' | 'hybrid') => void
}) {
  const map = useMap()

  useEffect(() => {
    if (!map) return
    map.setMapTypeId(mapType)
  }, [map, mapType])

  return null
}

// Search box component using Google Places Autocomplete
function PlaceSearchBox({ onPlaceSelect }: { onPlaceSelect: (lat: number, lng: number, name: string) => void }) {
  const [inputValue, setInputValue] = useState('')
  const [predictions, setPredictions] = useState<google.maps.places.AutocompletePrediction[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  
  const placesLib = useMapsLibrary('places')
  const autocompleteServiceRef = useRef<google.maps.places.AutocompleteService | null>(null)
  const placesServiceRef = useRef<google.maps.places.PlacesService | null>(null)
  const map = useMap()
  
  useEffect(() => {
    if (!placesLib) return
    autocompleteServiceRef.current = new placesLib.AutocompleteService()
    if (map) {
      placesServiceRef.current = new placesLib.PlacesService(map)
    }
  }, [placesLib, map])
  
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          inputRef.current && !inputRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  
  const handleInputChange = async (value: string) => {
    setInputValue(value)
    
    if (!value.trim() || !autocompleteServiceRef.current) {
      setPredictions([])
      setShowDropdown(false)
      return
    }
    
    setIsLoading(true)
    try {
      const response = await autocompleteServiceRef.current.getPlacePredictions({
        input: value,
        types: ['geocode', 'establishment'],
      })
      setPredictions(response?.predictions || [])
      setShowDropdown(true)
    } catch (error) {
      console.error('Autocomplete error:', error)
      setPredictions([])
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleSelectPlace = async (prediction: google.maps.places.AutocompletePrediction) => {
    if (!placesServiceRef.current) return
    
    setIsLoading(true)
    setInputValue(prediction.description)
    setShowDropdown(false)
    
    try {
      placesServiceRef.current.getDetails(
        { placeId: prediction.place_id, fields: ['geometry', 'name'] },
        (place, status) => {
          if (status === google.maps.places.PlacesServiceStatus.OK && place?.geometry?.location) {
            const lat = place.geometry.location.lat()
            const lng = place.geometry.location.lng()
            onPlaceSelect(lat, lng, place.name || prediction.description)
          }
          setIsLoading(false)
        }
      )
    } catch (error) {
      console.error('Place details error:', error)
      setIsLoading(false)
    }
  }
  
  return (
    <div className="relative w-72">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={() => predictions.length > 0 && setShowDropdown(true)}
          placeholder="Search for a city or address..."
          className="w-full pl-10 pr-10 py-2.5 bg-white rounded-lg shadow-lg border border-slate-200 
                     text-sm text-slate-700 placeholder:text-slate-400
                     focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent
                     transition-all"
        />
        {isLoading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 animate-spin" />
        )}
        {inputValue && !isLoading && (
          <button
            onClick={() => { setInputValue(''); setPredictions([]); setShowDropdown(false) }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      
      {showDropdown && predictions.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute top-full left-0 right-0 mt-1 bg-white rounded-lg shadow-xl border border-slate-200 overflow-hidden z-50"
        >
          {predictions.map((prediction) => (
            <button
              key={prediction.place_id}
              onClick={() => handleSelectPlace(prediction)}
              className="w-full px-4 py-3 text-left hover:bg-slate-50 border-b border-slate-100 last:border-b-0 transition-colors"
            >
              <div className="text-sm font-medium text-slate-700 truncate">
                {prediction.structured_formatting.main_text}
              </div>
              <div className="text-xs text-slate-500 truncate">
                {prediction.structured_formatting.secondary_text}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Controller that pans the map to a searched location
function SearchLocationController({
  searchLocation,
}: {
  searchLocation: { lat: number; lng: number; name: string } | null
}) {
  const map = useMap()
  
  useEffect(() => {
    if (!map || !searchLocation) return
    
    map.panTo({ lat: searchLocation.lat, lng: searchLocation.lng })
    map.setZoom(14) // Good zoom for city/area view
  }, [map, searchLocation])
  
  return null
}

// Property overlay component - renders GeoJSON polygons for selected property
function PropertyOverlay({
  dealId,
  visible,
}: {
  dealId: string | null
  visible: boolean
}) {
  const map = useMap()
  const polygonsRef = useRef<google.maps.Polygon[]>([])
  const [propertyData, setPropertyData] = useState<PropertyAnalysisSummary | null>(null)
  
  // Fetch property data when deal changes
  useEffect(() => {
    if (!dealId) {
      setPropertyData(null)
      return
    }
    
    const fetchData = async () => {
      try {
        const data = await parkingLotsApi.getParkingLot(dealId)
        setPropertyData((data.property_analysis ?? null) as PropertyAnalysisSummary | null)
      } catch (error) {
        console.error('Failed to fetch property data:', error)
        setPropertyData(null)
      }
    }
    
    fetchData()
  }, [dealId])
  
  // Draw polygons when data or visibility changes
  useEffect(() => {
    if (!map) return
    
    // Clear existing polygons
    polygonsRef.current.forEach(p => p.setMap(null))
    polygonsRef.current = []
    
    if (!visible || !propertyData) return
    
    // Helper to convert GeoJSON coordinates to Google Maps LatLng
    const coordsToLatLng = (coords: number[][]): google.maps.LatLngLiteral[] => {
      return coords.map(coord => ({
        lat: coord[1],
        lng: coord[0]
      }))
    }
    
    // Helper to draw a polygon
    const drawPolygon = (
      geometry: any,
      color: { fill: string; stroke: string },
      fillOpacity: number = 0.4
    ) => {
      if (!geometry?.coordinates) return
      
      const createPoly = (paths: google.maps.LatLngLiteral[]) => {
        const polygon = new google.maps.Polygon({
          paths,
          strokeColor: color.stroke,
          strokeOpacity: 0.9,
          strokeWeight: 2,
          fillColor: color.fill,
          fillOpacity,
          map,
          zIndex: fillOpacity < 0.2 ? 1 : 2, // Property boundary behind surfaces
        })
        polygonsRef.current.push(polygon)
      }
      
      if (geometry.type === 'Polygon') {
        createPoly(coordsToLatLng(geometry.coordinates[0]))
      } else if (geometry.type === 'MultiPolygon') {
        geometry.coordinates.forEach((polyCoords: number[][][]) => {
          createPoly(coordsToLatLng(polyCoords[0]))
        })
      }
    }
    
    // Draw property boundary (light fill)
    if (propertyData.property_boundary?.polygon) {
      drawPolygon(
        propertyData.property_boundary.polygon,
        SURFACE_COLORS.property_boundary,
        0.1
      )
    }
    
    // Draw surfaces from surfaces_geojson
    if (propertyData.surfaces_geojson?.features) {
      propertyData.surfaces_geojson.features.forEach((feature: any) => {
        const surfaceType = feature.properties?.surface_type || 'asphalt'
        const colors = SURFACE_COLORS[surfaceType] || SURFACE_COLORS.asphalt
        const customColor = feature.properties?.color
        
        drawPolygon(
          feature.geometry,
          customColor ? { fill: customColor, stroke: customColor } : colors,
          surfaceType === 'building' ? 0.3 : 0.5
        )
      })
    } else if (propertyData.surfaces) {
      // Fallback to individual surfaces
      if (propertyData.surfaces.asphalt?.geojson) {
        const geo = propertyData.surfaces.asphalt.geojson as any
        drawPolygon(geo.geometry || geo, SURFACE_COLORS.asphalt)
      }
      if (propertyData.surfaces.concrete?.geojson) {
        const geo = propertyData.surfaces.concrete.geojson as any
        drawPolygon(geo.geometry || geo, SURFACE_COLORS.concrete)
      }
      if (propertyData.surfaces.buildings?.geojson) {
        const geo = propertyData.surfaces.buildings.geojson as any
        drawPolygon(geo.geometry || geo, SURFACE_COLORS.building, 0.3)
      }
    }
    
    return () => {
      polygonsRef.current.forEach(p => p.setMap(null))
      polygonsRef.current = []
    }
  }, [map, propertyData, visible])
  
  return null
}

// Component to display drawn polygon with improved styling
function DrawnPolygonLayer({ polygon }: { polygon: GeoJSON.Polygon | GeoJSON.MultiPolygon }) {
  const map = useMap()
  const polygonRef = useRef<google.maps.Polygon | null>(null)

  useEffect(() => {
    if (!map || !polygon) {
      if (polygonRef.current) {
        polygonRef.current.setMap(null)
        polygonRef.current = null
      }
      return
    }

    // Parse GeoJSON coordinates
    let coords: google.maps.LatLngLiteral[] = []
    try {
      if (polygon.type === 'Polygon' && polygon.coordinates) {
        coords = polygon.coordinates[0].map((coord: number[]) => ({
          lat: coord[1],
          lng: coord[0],
        }))
      } else if (polygon.type === 'MultiPolygon' && polygon.coordinates) {
        coords = polygon.coordinates[0][0].map((coord: number[]) => ({
          lat: coord[1],
          lng: coord[0],
        }))
      }
    } catch (e) {
      console.error('Failed to parse drawn polygon:', e)
      return
    }

    if (coords.length === 0) return

    // Create or update polygon with improved styling
    if (polygonRef.current) {
      polygonRef.current.setPath(coords)
    } else {
      polygonRef.current = new google.maps.Polygon({
        paths: coords,
        strokeColor: '#059669', // Emerald green
        strokeOpacity: 1,
        strokeWeight: 3,
        fillColor: '#10b981', // Lighter green
        fillOpacity: 0.2,
        map: map,
        zIndex: 1001, // Above other polygons
        editable: false,
        clickable: false,
      })
    }

    return () => {
      if (polygonRef.current) {
        polygonRef.current.setMap(null)
        polygonRef.current = null
      }
    }
  }, [map, polygon])

  return null
}

// Component to draw preview polygon on map
function PreviewPolygonLayer({ polygon }: { polygon: any }) {
  const map = useMap()
  const polygonRef = useRef<google.maps.Polygon | null>(null)

  useEffect(() => {
    if (!map || !polygon) {
      // Clean up existing polygon
      if (polygonRef.current) {
        polygonRef.current.setMap(null)
        polygonRef.current = null
      }
      return
    }

    // Parse GeoJSON coordinates
    let coords: google.maps.LatLngLiteral[] = []
    try {
      if (polygon.type === 'Polygon' && polygon.coordinates) {
        coords = polygon.coordinates[0].map((coord: number[]) => ({
          lat: coord[1],
          lng: coord[0],
        }))
      } else if (polygon.type === 'MultiPolygon' && polygon.coordinates) {
        // Take first polygon of multi-polygon
        coords = polygon.coordinates[0][0].map((coord: number[]) => ({
          lat: coord[1],
          lng: coord[0],
        }))
      }
    } catch (e) {
      console.error('Failed to parse polygon:', e)
      return
    }

    if (coords.length === 0) return

    // Create or update polygon
    if (polygonRef.current) {
      polygonRef.current.setPath(coords)
    } else {
      polygonRef.current = new google.maps.Polygon({
        paths: coords,
        strokeColor: '#3B82F6',
        strokeOpacity: 1,
        strokeWeight: 3,
        fillColor: '#3B82F6',
        fillOpacity: 0.15,
        map: map,
        zIndex: 1000,
      })
    }

    // Fit bounds to polygon
    const bounds = new google.maps.LatLngBounds()
    coords.forEach(coord => bounds.extend(coord))
    map.fitBounds(bounds, { top: 50, right: 350, bottom: 50, left: 50 })

    return () => {
      if (polygonRef.current) {
        polygonRef.current.setMap(null)
        polygonRef.current = null
      }
    }
  }, [map, polygon])
  
  return null
}

export function InteractiveMap({
  deals,
  selectedDeal,
  onDealSelect,
  onViewDetails,
  onBoundsChange,
  onMapClick,
  clickedLocation,
  previewPolygon,
  searchResults = [],
  isDrawingPolygon = false,
  onPolygonDrawn,
  countyBoundary,
  boundaryLayer,
  mapClickMode,
  pinParcelPolygon,
  drawnPolygon,
  showUrbanOverlay = false,
  selectedUrbanArea,
  onUrbanAreaSelect,
}: InteractiveMapProps) {
  const [mapType, setMapType] = useState<'roadmap' | 'hybrid'>('roadmap')
  const [searchLocation, setSearchLocation] = useState<{ lat: number; lng: number; name: string } | null>(null)
  const [showOverlay, setShowOverlay] = useState(true) // Show property boundaries by default
  const [selectedSearchResult, setSelectedSearchResult] = useState<SearchParcel | null>(null)
  
  // Preload urban areas data in background (silent, cached)
  // This ensures instant rendering when overlay is shown
  useQuery({
    queryKey: ['boundaries', 'urban_areas', 'preload'],
    queryFn: () => boundariesApi.getLayer('urban_areas', undefined, 1000),
    staleTime: Infinity, // Cache forever
    gcTime: Infinity, // Keep in cache forever
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })
  
  const handlePlaceSelect = useCallback((lat: number, lng: number, name: string) => {
    setSearchLocation({ lat, lng, name })
  }, [])
  
  const dealsWithLocation = useMemo(
    () => deals.filter((deal) => deal.latitude && deal.longitude),
    [deals]
  )

  const defaultCenter = useMemo(() => {
    if (dealsWithLocation.length === 0) {
      return { lat: 37.7749, lng: -122.4194 }
    }

    const lats = dealsWithLocation.map((d) => d.latitude!).filter(Boolean)
    const lngs = dealsWithLocation.map((d) => d.longitude!).filter(Boolean)

    return {
      lat: lats.reduce((a, b) => a + b, 0) / lats.length,
      lng: lngs.reduce((a, b) => a + b, 0) / lngs.length,
    }
  }, [dealsWithLocation])

  const handleMarkerClick = useCallback((deal: DealMapResponse) => {
    onDealSelect(deal)
  }, [onDealSelect])

  const toggleMapType = useCallback(() => {
    setMapType((prev) => (prev === 'roadmap' ? 'hybrid' : 'roadmap'))
  }, [])

  if (!process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY) {
    return (
      <div className="flex items-center justify-center h-full bg-slate-50">
        <div className="text-center">
          <MapPin className="h-12 w-12 text-slate-300 mx-auto mb-3" />
          <p className="text-sm text-slate-500">
            Google Maps API key not configured
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full cursor-crosshair">
      <APIProvider apiKey={process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY} libraries={['places']}>
        {/* Top Controls: Search Bar */}
        <div className="absolute top-4 left-4 z-10">
          {/* Search Box */}
          <PlaceSearchBox onPlaceSelect={handlePlaceSelect} />
        </div>

        {/* Bottom Right Controls: Map Type Toggle + Segments Toggle */}
        <div className="absolute bottom-4 right-4 z-10 flex items-center gap-2">
          {/* Show Overlay Toggle (only visible when deal is selected) */}
          {selectedDeal && (
            <button
              onClick={() => setShowOverlay(prev => !prev)}
              className={cn(
                "flex items-center gap-2 px-3 py-2.5 rounded-lg shadow-lg hover:shadow-xl transition-all border",
                showOverlay 
                  ? "bg-blue-500 text-white border-blue-600 hover:bg-blue-600" 
                  : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
              )}
              title={showOverlay ? 'Hide Property Boundaries' : 'Show Property Boundaries'}
            >
              <Layers className="h-4 w-4" />
              <span className="text-sm font-medium">Segments</span>
            </button>
          )}
          
          {/* Map Type Toggle Button */}
          <button
            onClick={toggleMapType}
            className="flex items-center gap-2 px-3 py-2.5 bg-white rounded-lg shadow-lg hover:shadow-xl transition-all hover:scale-105 border border-slate-200"
            title={mapType === 'roadmap' ? 'Switch to Satellite' : 'Switch to Map'}
          >
            {mapType === 'roadmap' ? (
              <>
                <Satellite className="h-4 w-4 text-slate-700" />
                <span className="text-sm font-medium text-slate-700">Satellite</span>
              </>
            ) : (
              <>
                <MapIcon className="h-4 w-4 text-slate-700" />
                <span className="text-sm font-medium text-slate-700">Map</span>
              </>
            )}
          </button>
        </div>
        <Map
          defaultCenter={defaultCenter}
          defaultZoom={dealsWithLocation.length > 0 ? 13 : 10}
          minZoom={3}
          gestureHandling="greedy"
          disableDefaultUI={true}
          zoomControl={false}
          mapTypeControl={false}
          fullscreenControl={false}
          streetViewControl={false}
          clickableIcons={false}
          styles={mapType === 'roadmap' ? mapStyles : undefined}
          className="w-full h-full"
        >
          <MapController onBoundsChange={onBoundsChange} onMapClick={onMapClick} />
          <MapTypeController mapType={mapType} onMapTypeChange={setMapType} />
          <CenterMapController selectedDeal={selectedDeal} />
          <SearchLocationController searchLocation={searchLocation} />
          
          {/* Property boundary and segment overlays */}
          <PropertyOverlay 
            dealId={selectedDeal?.id || null}
            visible={showOverlay}
          />
          
          {/* Preview polygon for clicked location */}
          {previewPolygon && <PreviewPolygonLayer polygon={previewPolygon} />}
          
          {/* Drawn polygon for search - better styling */}
          {drawnPolygon && <DrawnPolygonLayer polygon={drawnPolygon} />}
          
          {/* Pin parcel polygon */}
          {pinParcelPolygon && <PreviewPolygonLayer polygon={pinParcelPolygon} />}

          <MarkerClustererComponent
            deals={dealsWithLocation}
            selectedDeal={selectedDeal}
            onDealSelect={onDealSelect}
          />

          {/* Selected location marker */}
          {clickedLocation && (
            <Marker
              position={clickedLocation}
              icon={{
                url: `data:image/svg+xml,${encodeURIComponent(`
                  <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
                    <circle cx="24" cy="24" r="20" fill="none" stroke="#f97316" stroke-width="3" opacity="0.3">
                      <animate attributeName="r" from="12" to="22" dur="1.5s" repeatCount="indefinite"/>
                      <animate attributeName="opacity" from="0.6" to="0" dur="1.5s" repeatCount="indefinite"/>
                    </circle>
                    <circle cx="24" cy="24" r="12" fill="#f97316" stroke="white" stroke-width="3"/>
                    <circle cx="24" cy="24" r="4" fill="white"/>
                  </svg>
                `)}`,
                scaledSize: new google.maps.Size(48, 48),
                anchor: new google.maps.Point(24, 24),
              }}
            />
          )}


          {/* Parking lot info window */}
          {selectedDeal && selectedDeal.latitude && selectedDeal.longitude && (
            <InfoWindow
              position={{ lat: selectedDeal.latitude, lng: selectedDeal.longitude }}
              onCloseClick={() => onDealSelect(null)}
              pixelOffset={[0, -30]}
              headerDisabled
            >
              <div className="-m-3">
                <ParkingLotPopup 
                  deal={selectedDeal} 
                  onViewDetails={() => onViewDetails(selectedDeal.id)}
                  onClose={() => onDealSelect(null)}
                />
              </div>
            </InfoWindow>
          )}

          {/* Search Results Markers */}
          <SearchResultsLayer
            results={searchResults}
            selectedResult={selectedSearchResult}
            onResultSelect={setSelectedSearchResult}
          />

          {/* County Boundary Layer */}
          {countyBoundary?.boundary && (
            <CountyBoundaryLayer
              boundary={countyBoundary.boundary}
              name={countyBoundary.name}
            />
          )}

          {/* KML Boundary Layer (states, counties, zips, urban areas) */}
          <KMLBoundaryLayerWrapper boundaryLayer={boundaryLayer} />

          {/* Urban Areas Overlay for Search Guidance */}
          {showUrbanOverlay && (
            <UrbanAreasOverlay
              selectedUrbanArea={selectedUrbanArea}
              onUrbanAreaSelect={onUrbanAreaSelect}
            />
          )}

          {/* Selected Urban Area Highlight (when area is selected and overlay is hidden) */}
          {selectedUrbanArea && !showUrbanOverlay && (
            <SelectedUrbanAreaLayer
              urbanArea={selectedUrbanArea}
            />
          )}

          {/* Polygon Drawing Controller */}
          {onPolygonDrawn && (
            <PolygonDrawingController 
              isEnabled={isDrawingPolygon} 
              onPolygonComplete={onPolygonDrawn} 
            />
          )}

          {/* Search result info window */}
        </Map>
        
        {/* Segment Legend - shows when overlay is visible and deal is selected */}
        {selectedDeal && showOverlay && (
          <div className="absolute bottom-4 left-4 bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-slate-200 px-3 py-2">
            <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Detected Segments</div>
            <div className="flex items-center gap-3 text-xs">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm border-2" style={{ borderColor: '#1D4ED8', backgroundColor: 'rgba(59, 130, 246, 0.2)' }} />
                <span className="text-slate-600">Property</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#374151' }} />
                <span className="text-slate-600">Paved</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#9CA3AF' }} />
                <span className="text-slate-600">Concrete</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#DC2626' }} />
                <span className="text-slate-600">Building</span>
              </div>
            </div>
          </div>
        )}
      </APIProvider>
    </div>
  )
}

function MarkerClustererComponent({
  deals,
  selectedDeal,
  onDealSelect,
}: {
  deals: DealMapResponse[]
  selectedDeal: DealMapResponse | null
  onDealSelect: (deal: DealMapResponse | null) => void
}) {
  const map = useMap()
  const clustererRef = useRef<MarkerClusterer | null>(null)
  const markersRef = useRef<google.maps.Marker[]>([])
  // Use refs to avoid recreating markers when callbacks/selection changes
  const onDealSelectRef = useRef(onDealSelect)
  const dealsRef = useRef(deals)
  
  // Keep refs up to date
  useEffect(() => {
    onDealSelectRef.current = onDealSelect
  }, [onDealSelect])
  
  useEffect(() => {
    dealsRef.current = deals
  }, [deals])

  // Create markers only when map or deals change (not on selection change)
  useEffect(() => {
    if (!map || deals.length === 0) return

    // Clean up existing clusterer
    if (clustererRef.current) {
      clustererRef.current.clearMarkers()
      clustererRef.current = null
    }

    // Create markers for each deal with initial animation
    const markers: google.maps.Marker[] = deals.map((deal, index) => {
      const marker = new google.maps.Marker({
        position: { lat: deal.latitude!, lng: deal.longitude! },
        icon: getMarkerIcon(deal, false, true), // Initial state with animation
        map: null, // Don't add to map directly, clusterer will handle it
        optimized: false, // Required for SVG animations to work
      })

      // Add click handler using ref to avoid stale closure
      marker.addListener('click', () => {
        onDealSelectRef.current(dealsRef.current[index] || deal)
      })

      return marker
    })

    markersRef.current = markers

    // Create custom cluster renderer - iOS-style circles with smooth animations
    const customRenderer = {
      render: (cluster: any) => {
        const count = cluster.count
        const position = cluster.position

        // Size based on count - circles
        const size = count < 10 ? 36 : count < 50 ? 42 : count < 100 ? 48 : 54
        const fontSize = count < 10 ? 13 : count < 50 ? 14 : count < 100 ? 15 : 16
        const borderWidth = 2.5
        
        // Slate/gray color for clusters to differentiate from score pins
        const bgColor = '#475569' // slate-600
        const textColor = '#ffffff'

        // Create cluster marker with circle styling and pop-in animation
        const clusterMarker = new google.maps.Marker({
          position,
          icon: {
            url: `data:image/svg+xml,${encodeURIComponent(`
              <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
                <defs>
                  <style>
                    @keyframes clusterPop {
                      0% { transform: scale(0.6); opacity: 0; }
                      60% { transform: scale(1.08); }
                      100% { transform: scale(1); opacity: 1; }
                    }
                    .cluster-group { 
                      animation: clusterPop 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
                      transform-origin: center center;
                    }
                  </style>
                  <!-- iOS-style shadow -->
                  <filter id="cluster-shadow" x="-30%" y="-30%" width="160%" height="160%">
                    <feDropShadow dx="0" dy="1" stdDeviation="2.5" flood-color="#000000" flood-opacity="0.3"/>
                  </filter>
                </defs>
                <g class="cluster-group">
                  <!-- Circle background -->
                  <circle 
                    cx="${size / 2}" 
                    cy="${size / 2}" 
                    r="${size / 2 - borderWidth}"
                    fill="${bgColor}"
                    stroke="white"
                    stroke-width="${borderWidth}"
                    filter="url(#cluster-shadow)"
                  />
                  <!-- Count text - SF Pro style -->
                  <text 
                    x="${size / 2}" 
                    y="${size / 2}" 
                    font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', system-ui, sans-serif" 
                    font-size="${fontSize}" 
                    font-weight="600" 
                    fill="${textColor}" 
                    text-anchor="middle" 
                    dominant-baseline="central"
                    letter-spacing="-0.02em"
                  >${count}</text>
                </g>
              </svg>
            `)}`,
            scaledSize: new google.maps.Size(size, size),
            anchor: new google.maps.Point(size / 2, size / 2),
          },
          zIndex: Number(google.maps.Marker.MAX_ZINDEX) + count,
        })

        // Smooth zoom on click
        clusterMarker.addListener('click', () => {
          const bounds = new google.maps.LatLngBounds()
          cluster.markers.forEach((m: any) => {
            const pos = m.getPosition?.() || m.position
            if (pos) {
              if (pos instanceof google.maps.LatLng) {
                bounds.extend(pos)
              } else if (pos.lat && pos.lng) {
                bounds.extend(new google.maps.LatLng(pos.lat, pos.lng))
              }
            }
          })
          map.fitBounds(bounds, { top: 60, right: 60, bottom: 60, left: 60 })
        })

        return clusterMarker
      },
    }

    // Create clusterer with custom renderer
    const clusterer = new MarkerClusterer({
      map,
      markers,
      algorithm: new GridAlgorithm({ gridSize: 60 }),
      renderer: customRenderer,
    })

    clustererRef.current = clusterer

    // Cleanup
    return () => {
      if (clustererRef.current) {
        try {
          // Check if map is still valid before clearing markers
          if (map && map.getDiv()) {
            clustererRef.current.clearMarkers()
          }
        } catch (error) {
          // Map might be destroyed, just clean up markers individually
          console.warn('Error clearing clusterer markers:', error)
        }
        clustererRef.current = null
      }
      markers.forEach((marker) => {
        try {
          google.maps.event.clearInstanceListeners(marker)
          marker.setMap(null)
        } catch (error) {
          // Marker might already be cleaned up
        }
      })
    }
  }, [map, deals]) // Only recreate when map or deals change

  // Re-animate markers on zoom change (when clusters split/merge)
  useEffect(() => {
    if (!map) return
    
    let zoomTimeout: NodeJS.Timeout
    const handleZoomChange = () => {
      // Debounce to avoid multiple triggers
      clearTimeout(zoomTimeout)
      zoomTimeout = setTimeout(() => {
        // Re-apply icons with animation after zoom settles
        markersRef.current.forEach((marker, index) => {
          const deal = dealsRef.current[index]
          if (deal && marker.getMap()) {
            marker.setIcon(getMarkerIcon(deal, false, true))
          }
        })
      }, 100)
    }
    
    const zoomListener = map.addListener('zoom_changed', handleZoomChange)
    
    return () => {
      clearTimeout(zoomTimeout)
      google.maps.event.removeListener(zoomListener)
    }
  }, [map])

  // Update marker icons when selection changes (without recreating markers)
  useEffect(() => {
    if (!map || markersRef.current.length === 0) return

    markersRef.current.forEach((marker, index) => {
      const deal = deals[index]
      if (deal) {
        marker.setIcon(getMarkerIcon(deal, selectedDeal?.id === deal.id, false))
      }
    })
  }, [selectedDeal?.id, deals]) // Only update icons on selection change

  return null
}

function getMarkerIcon(deal: DealMapResponse, isSelected: boolean, animate: boolean = false) {
  const score = deal.lead_score ?? deal.score
  const hasScore = score !== null && score !== undefined
  
  // Color based on score: high score = green (good condition), low score = red (needs work)
  let bgColor = '#6366f1' // indigo for pending/unknown
  let textColor = '#ffffff'
  
  if (deal.status === 'evaluated') {
    if (hasScore) {
      if (score >= 80) bgColor = '#10b981' // emerald (excellent condition)
      else if (score >= 60) bgColor = '#22c55e' // green (good)
      else if (score >= 40) bgColor = '#f59e0b' // amber (fair)
      else bgColor = '#ef4444' // red (needs attention)
    } else {
      bgColor = '#6366f1' // indigo if no score
    }
  } else if (deal.status === 'evaluating') {
    bgColor = '#3b82f6' // blue
  }

  const scale = isSelected ? 1.15 : 1
  const width = 38 * scale
  const boxHeight = 26 * scale
  const arrowHeight = 8 * scale
  const totalHeight = boxHeight + arrowHeight
  const borderRadius = 6 * scale
  const borderWidth = 2
  const fontSize = hasScore ? 13 * scale : 10 * scale
  const displayText = hasScore ? Math.round(score) : '•••'
  
  // Animation styles for smooth appearance
  const animationStyle = animate ? `
    <style>
      @keyframes popIn {
        0% { transform: scale(0.5); opacity: 0; }
        70% { transform: scale(1.1); }
        100% { transform: scale(1); opacity: 1; }
      }
      .marker-group { 
        animation: popIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        transform-origin: center bottom;
      }
    </style>
  ` : ''

  // Location pin style: rounded box with arrow pointing down
  return {
    url: `data:image/svg+xml,${encodeURIComponent(`
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${totalHeight}" viewBox="0 0 ${width} ${totalHeight}">
        <defs>
          ${animationStyle}
          <!-- iOS-style shadow -->
          <filter id="pin-shadow" x="-30%" y="-20%" width="160%" height="160%">
            <feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-color="#000000" flood-opacity="0.3"/>
          </filter>
        </defs>
        <g class="marker-group">
          <!-- Pin shape: rounded rect + triangle arrow -->
          <path 
            d="M${borderRadius + borderWidth/2},${borderWidth/2} 
               H${width - borderRadius - borderWidth/2} 
               Q${width - borderWidth/2},${borderWidth/2} ${width - borderWidth/2},${borderRadius + borderWidth/2}
               V${boxHeight - borderRadius - borderWidth/2}
               Q${width - borderWidth/2},${boxHeight - borderWidth/2} ${width - borderRadius - borderWidth/2},${boxHeight - borderWidth/2}
               H${width/2 + arrowHeight/1.5}
               L${width/2},${totalHeight - borderWidth}
               L${width/2 - arrowHeight/1.5},${boxHeight - borderWidth/2}
               H${borderRadius + borderWidth/2}
               Q${borderWidth/2},${boxHeight - borderWidth/2} ${borderWidth/2},${boxHeight - borderRadius - borderWidth/2}
               V${borderRadius + borderWidth/2}
               Q${borderWidth/2},${borderWidth/2} ${borderRadius + borderWidth/2},${borderWidth/2}
               Z"
            fill="${bgColor}"
            stroke="white"
            stroke-width="${borderWidth}"
            stroke-linejoin="round"
            filter="url(#pin-shadow)"
          />
          <!-- Score text - SF Pro style -->
          <text 
            x="${width / 2}" 
            y="${boxHeight / 2}" 
            font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', system-ui, sans-serif" 
            font-size="${fontSize}" 
            font-weight="600" 
            fill="${textColor}" 
            text-anchor="middle" 
            dominant-baseline="central"
            letter-spacing="-0.02em"
          >${displayText}</text>
        </g>
      </svg>
    `)}`,
    scaledSize: new google.maps.Size(width, totalHeight),
    anchor: new google.maps.Point(width / 2, totalHeight), // Anchor at arrow tip
  }
}

function ParkingLotPopup({ 
  deal, 
  onViewDetails,
  onClose 
}: { 
  deal: DealMapResponse
  onViewDetails: () => void
  onClose: () => void
}) {
  const [satelliteImage, setSatelliteImage] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(true)

  // Reset and lazy load the satellite image when deal changes
  useEffect(() => {
    // Reset state immediately when deal changes
    setSatelliteImage(null)
    setImageLoading(true)
    
    const fetchImage = async () => {
      try {
        const data = await parkingLotsApi.getParkingLot(deal.id)
        const wideSatellite = data.property_analysis?.images?.wide_satellite
        if (wideSatellite) {
          // Convert base64 to data URL if needed
          const imageUrl = wideSatellite.startsWith('data:') 
            ? wideSatellite 
            : `data:image/jpeg;base64,${wideSatellite}`
          setSatelliteImage(imageUrl)
        }
      } catch (error) {
        console.error('Failed to load satellite image:', error)
      } finally {
        setImageLoading(false)
      }
    }
    fetchImage()
  }, [deal.id])

  const getScoreColor = (score: number | null | undefined) => {
    if (score === null || score === undefined) {
      return { bg: 'bg-muted', text: 'text-muted-foreground' }
    }
    // High score = green (good condition), low score = red (needs work)
    if (score >= 80) return { bg: 'bg-emerald-100 dark:bg-emerald-950', text: 'text-emerald-700 dark:text-emerald-400' }
    if (score >= 60) return { bg: 'bg-green-100 dark:bg-green-950', text: 'text-green-700 dark:text-green-400' }
    if (score >= 40) return { bg: 'bg-amber-100 dark:bg-amber-950', text: 'text-amber-700 dark:text-amber-400' }
    // Low score (needs attention)
    return { bg: 'bg-red-100 dark:bg-red-950', text: 'text-red-700 dark:text-red-400' }
  }

  const hasBusiness = deal.has_business || deal.business
  const hasContact = deal.has_contact || deal.contact_email || deal.contact_phone
  const isLead = deal.score !== null && deal.score !== undefined && deal.score < 50
  const leadScore = deal.lead_score ?? deal.score
  const scoreStyle = getScoreColor(leadScore)

  // Display name priority: business > contact company > address
  const displayName = deal.display_name || deal.business?.name || deal.business_name || deal.contact_company || deal.address || 'Property'
  const showAddress = deal.address && displayName !== deal.address

  // Format property category for display
  const formatCategory = (cat?: string) => {
    if (!cat) return null
    return cat.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  }

  return (
    <div className="w-72 bg-card border border-border rounded-lg shadow-xl overflow-hidden">
      {/* Close Button - positioned over image */}
      <button
        onClick={onClose}
        className="absolute top-1.5 right-1.5 z-10 h-6 w-6 flex items-center justify-center rounded-md bg-black/40 backdrop-blur-sm hover:bg-black/60 transition-colors"
      >
        <X className="h-3.5 w-3.5 text-white" />
      </button>

      {/* Satellite Image */}
      <div className="relative h-36 bg-gradient-to-br from-slate-800 to-slate-900 overflow-hidden">
        {satelliteImage ? (
          <img 
            src={satelliteImage} 
            alt="Satellite view"
            className="w-full h-full object-cover"
          />
        ) : imageLoading ? (
          <div className="w-full h-full flex items-center justify-center">
            <div className="animate-pulse flex flex-col items-center">
              <Satellite className="h-8 w-8 text-white/40 mb-1" />
              <p className="text-[10px] text-white/50">Loading...</p>
            </div>
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center">
              <Satellite className="h-8 w-8 text-white/40 mx-auto mb-1" />
              <p className="text-[10px] text-white/50 uppercase tracking-wider">No image</p>
            </div>
          </div>
        )}
        {/* Score badge overlay */}
        {leadScore !== null && leadScore !== undefined && (
          <div className={cn(
            'absolute top-2 left-2 px-2 py-1 rounded text-xs font-bold shadow-lg',
            scoreStyle.bg, scoreStyle.text
          )}>
            {Math.round(leadScore)}/100
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        {/* Title & Address */}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground truncate mb-0.5">
            {displayName}
          </h3>
          {showAddress && (
            <div className="flex items-start gap-1 text-xs text-muted-foreground">
              <MapPin className="h-3 w-3 flex-shrink-0 mt-0.5" />
              <span className="line-clamp-2">{deal.address}</span>
            </div>
          )}
        </div>

        {/* Tags */}
        <div className="flex items-center gap-1 flex-wrap">
          {/* Status */}
          <StatusChip 
            status={deal.status === 'evaluated' ? 'success' : deal.status === 'evaluating' ? 'info' : 'warning'}
            icon={deal.status === 'evaluated' ? CheckCircle2 : Clock}
          >
            {deal.status === 'evaluated' ? 'Analyzed' : deal.status === 'evaluating' ? 'Evaluating' : 'Pending'}
          </StatusChip>

          {/* Lead indicator */}
          {isLead && (
            <StatusChip status="success" icon={Target}>Lead</StatusChip>
          )}

          {/* Property category (for Regrid-first) */}
          {deal.property_category && !hasBusiness && (
            <StatusChip status="neutral" icon={Building2}>
              {formatCategory(deal.property_category)}
            </StatusChip>
          )}

          {/* Business info */}
          {hasBusiness && (
            <>
              <StatusChip status="neutral" icon={Building2}>
                {deal.business?.category || 'Business'}
              </StatusChip>
              {deal.business?.phone && <IconChip icon={Phone} tooltip="Has phone" />}
              {deal.business?.website && <IconChip icon={Globe} tooltip="Has website" />}
            </>
          )}

          {/* Contact info (for enriched Regrid properties) */}
          {hasContact && !hasBusiness && (
            <>
              {deal.contact_phone && <IconChip icon={Phone} tooltip="Has phone" />}
              {deal.contact_email && <IconChip icon={Globe} tooltip="Has email" />}
            </>
          )}
        </div>

        {/* Action Button */}
        <button
          onClick={onViewDetails}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-foreground bg-muted hover:bg-muted/80 border border-border rounded-md transition-colors"
        >
          View Details
          <ExternalLink className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

// County Boundary Layer - displays selected county boundary
function CountyBoundaryLayer({
  boundary,
  name,
}: {
  boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon
  name: string
}) {
  const map = useMap()
  const polygonsRef = useRef<google.maps.Polygon[]>([])

  useEffect(() => {
    if (!map || !boundary) return

    // Clear existing polygons
    polygonsRef.current.forEach(p => p.setMap(null))
    polygonsRef.current = []

    // Parse coordinates based on geometry type
    let allPaths: google.maps.LatLngLiteral[][] = []

    if (boundary.type === 'Polygon') {
      // Single polygon - all rings
      allPaths = boundary.coordinates.map(ring =>
        ring.map(coord => ({ lat: coord[1], lng: coord[0] }))
      )
    } else if (boundary.type === 'MultiPolygon') {
      // Multiple polygons
      boundary.coordinates.forEach(polygon => {
        polygon.forEach(ring => {
          allPaths.push(ring.map(coord => ({ lat: coord[1], lng: coord[0] })))
        })
      })
    }

    // Create polygon
    if (allPaths.length > 0) {
      const polygon = new google.maps.Polygon({
        paths: allPaths,
        strokeColor: '#6366f1',  // Indigo
        strokeOpacity: 1,
        strokeWeight: 3,
        fillColor: '#6366f1',
        fillOpacity: 0.05,
        map,
        zIndex: 10,
      })

      polygonsRef.current.push(polygon)

      // Fit bounds to county
      const bounds = new google.maps.LatLngBounds()
      allPaths.forEach(path => {
        path.forEach(coord => bounds.extend(coord))
      })
      map.fitBounds(bounds, { top: 100, right: 50, bottom: 50, left: 350 })
    }

    return () => {
      polygonsRef.current.forEach(p => p.setMap(null))
    }
  }, [map, boundary])

  return null
}

// Urban Areas Overlay Component - for search guidance
function UrbanAreasOverlay({
  selectedUrbanArea,
  onUrbanAreaSelect,
}: {
  selectedUrbanArea?: UrbanAreaInfo | null
  onUrbanAreaSelect?: (urbanArea: UrbanAreaInfo | null) => void
}) {
  const map = useMap()
  const dataLayerRef = useRef<google.maps.Data | null>(null)
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null)
  const overlayRef = useRef<google.maps.Rectangle | null>(null)
  
  // Use React Query to fetch urban areas (uses cache if preloaded)
  // This will be instant if data was preloaded in InteractiveMap
  const { data: urbanAreas, isLoading } = useQuery({
    queryKey: ['boundaries', 'urban_areas', 'preload'],
    queryFn: () => boundariesApi.getLayer('urban_areas', undefined, 1000),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })
  
  // Render urban areas on map
  useEffect(() => {
    if (!map || isLoading || !urbanAreas || urbanAreas.features.length === 0) return
    
    console.log(`[UrbanOverlay] Rendering ${urbanAreas.features.length} urban areas`)
    
    // Create semi-transparent overlay for non-urban areas (greying effect)
    if (!overlayRef.current) {
      overlayRef.current = new google.maps.Rectangle({
        map,
        bounds: {
          north: 85,
          south: -85,
          west: -180,
          east: 180,
        },
        strokeWeight: 0,
        fillColor: '#1f2937',  // Dark grey
        fillOpacity: 0.35,
        clickable: false,
        zIndex: 5,
      })
    }
    
    // Clear existing data layer if it exists (shouldn't happen, but safety check)
    if (dataLayerRef.current) {
      dataLayerRef.current.setMap(null)
      dataLayerRef.current = null
    }
    
    // Create info window without close button
    if (!infoWindowRef.current) {
      infoWindowRef.current = new google.maps.InfoWindow({
        disableAutoPan: false,
      })
      // Hide the close button using CSS after InfoWindow is created
      // We'll inject CSS to hide the close button for this specific InfoWindow
    }
    
    // Create data layer for urban areas
    const dataLayer = new google.maps.Data({ map })
    dataLayerRef.current = dataLayer
    
    // Style: highlighted urban areas that "punch through" the grey overlay
    dataLayer.setStyle((feature) => {
      const featureId = feature.getProperty('id')
      const isSelected = selectedUrbanArea?.id === featureId
      
      return {
        strokeColor: isSelected ? '#6366f1' : '#f97316',  // Indigo when selected, orange otherwise
        strokeOpacity: 1,
        strokeWeight: isSelected ? 3 : 2,
        fillColor: isSelected ? '#6366f1' : '#fef3c7',  // Light amber fill
        fillOpacity: isSelected ? 0.3 : 0.9,  // High opacity to show through grey
        zIndex: isSelected ? 15 : 10,
      }
    })
    
    // Add click listener
    dataLayer.addListener('click', (event: google.maps.Data.MouseEvent) => {
      const feature = event.feature
      const name = feature.getProperty('name') as string
      const id = feature.getProperty('id') as string
      
      if (onUrbanAreaSelect) {
        // Get the geometry from the feature
        const geom = feature.getGeometry()
        let geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon | null = null
        
        if (geom) {
          const type = geom.getType()
          if (type === 'Polygon') {
            const poly = geom as google.maps.Data.Polygon
            const coords: number[][][] = []
            poly.getArray().forEach(ring => {
              const ringCoords: number[][] = []
              ring.getArray().forEach(pt => {
                ringCoords.push([pt.lng(), pt.lat()])
              })
              coords.push(ringCoords)
            })
            geometry = { type: 'Polygon', coordinates: coords }
          } else if (type === 'MultiPolygon') {
            const multiPoly = geom as google.maps.Data.MultiPolygon
            const coords: number[][][][] = []
            multiPoly.getArray().forEach(poly => {
              const polyCoords: number[][][] = []
              poly.getArray().forEach(ring => {
                const ringCoords: number[][] = []
                ring.getArray().forEach(pt => {
                  ringCoords.push([pt.lng(), pt.lat()])
                })
                polyCoords.push(ringCoords)
              })
              coords.push(polyCoords)
            })
            geometry = { type: 'MultiPolygon', coordinates: coords }
          }
        }
        
        if (geometry) {
          onUrbanAreaSelect({
            id,
            name,
            geometry,
          })
          
          // Zoom to the selected area
          const bounds = new google.maps.LatLngBounds()
          if (geom) {
            geom.forEachLatLng(pt => bounds.extend(pt))
          }
          map.fitBounds(bounds, { top: 100, right: 50, bottom: 50, left: 350 })
        }
      }
    })
    
    // Hover effect
    dataLayer.addListener('mouseover', (event: google.maps.Data.MouseEvent) => {
      const name = event.feature.getProperty('name')
      if (infoWindowRef.current && event.latLng) {
        infoWindowRef.current.setContent(`
          <div style="padding: 8px;">
            <div style="font-weight: 600; font-size: 13px;">${name}</div>
            <div style="font-size: 11px; color: #666; margin-top: 2px;">Click to select metro area</div>
          </div>
        `)
        infoWindowRef.current.setPosition(event.latLng)
        infoWindowRef.current.open(map)
        
        // Hide the close button after InfoWindow opens
        setTimeout(() => {
          const infoWindowElement = document.querySelector('.gm-style-iw-d')?.parentElement
          if (infoWindowElement) {
            const closeButton = infoWindowElement.querySelector('button[aria-label*="Close"], button[title*="Close"], .gm-ui-hover-effect')
            if (closeButton) {
              ;(closeButton as HTMLElement).style.display = 'none'
            }
          }
        }, 10)
      }
      
      dataLayer.overrideStyle(event.feature, {
        strokeWeight: 3,
        fillOpacity: 0.95,
      })
    })
    
    dataLayer.addListener('mouseout', (event: google.maps.Data.MouseEvent) => {
      if (infoWindowRef.current) {
        infoWindowRef.current.close()
      }
      dataLayer.revertStyle(event.feature)
    })
    
    // Add GeoJSON data
    try {
      dataLayer.addGeoJson({
        type: 'FeatureCollection',
        features: urbanAreas.features.map(f => ({
          type: 'Feature' as const,
          properties: f.properties,
          geometry: f.geometry,
        })),
      })
      console.log(`[UrbanOverlay] Rendered ${urbanAreas.features.length} urban areas`)
    } catch (error) {
      console.error('[UrbanOverlay] Error adding GeoJSON:', error)
    }
    
    // Cleanup function - only runs on unmount or when urbanAreas changes
    return () => {
      if (dataLayerRef.current) {
        dataLayerRef.current.setMap(null)
        dataLayerRef.current = null
      }
    }
  }, [map, urbanAreas, selectedUrbanArea?.id, onUrbanAreaSelect])
  
  // Cleanup on unmount (when showUrbanOverlay becomes false or component unmounts)
  useEffect(() => {
    return () => {
      if (dataLayerRef.current) {
        dataLayerRef.current.setMap(null)
        dataLayerRef.current = null
      }
      if (overlayRef.current) {
        overlayRef.current.setMap(null)
        overlayRef.current = null
      }
      if (infoWindowRef.current) {
        infoWindowRef.current.close()
        infoWindowRef.current = null
      }
    }
  }, [])
  
  return null
}

// Selected Urban Area Layer - shows selected area highlighted with grey overlay outside
function SelectedUrbanAreaLayer({
  urbanArea,
}: {
  urbanArea: UrbanAreaInfo
  onZoomToArea?: (geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon) => void
}) {
  const map = useMap()
  const polygonsRef = useRef<google.maps.Polygon[]>([])
  const overlayRef = useRef<google.maps.Rectangle | null>(null)
  const hasZoomedRef = useRef(false)
  
  useEffect(() => {
    if (!map) {
      console.log('[SelectedUrbanArea] No map available')
      return
    }
    
    console.log('[SelectedUrbanArea] Rendering area:', urbanArea.name)
    
    // Zoom to urban area bounds (only once)
    if (!hasZoomedRef.current) {
      const bounds = new google.maps.LatLngBounds()
      
      if (urbanArea.geometry.type === 'Polygon') {
        urbanArea.geometry.coordinates.forEach(ring => {
          ring.forEach(([lng, lat]) => {
            bounds.extend({ lat, lng })
          })
        })
      } else if (urbanArea.geometry.type === 'MultiPolygon') {
        urbanArea.geometry.coordinates.forEach(polygon => {
          polygon.forEach(ring => {
            ring.forEach(([lng, lat]) => {
              bounds.extend({ lat, lng })
            })
          })
        })
      }
      
      map.fitBounds(bounds, { top: 50, right: 320, bottom: 50, left: 50 })
      hasZoomedRef.current = true
      console.log('[SelectedUrbanArea] Zoomed to bounds')
    }
    
    // No grey overlay - just show the selected area border
    // Clear any existing overlay
    if (overlayRef.current) {
      overlayRef.current.setMap(null)
      overlayRef.current = null
    }
    
    // Clear existing polygons
    polygonsRef.current.forEach(p => p.setMap(null))
    polygonsRef.current = []
    
    // Create polygon(s) for selected urban area
    const createPolygon = (coordinates: number[][][]): google.maps.Polygon => {
      // First ring is exterior, rest are holes
      const exteriorPath = coordinates[0].map(([lng, lat]) => new google.maps.LatLng(lat, lng))
      const holes = coordinates.slice(1).map(ring => 
        ring.map(([lng, lat]) => new google.maps.LatLng(lat, lng))
      )
      
      return new google.maps.Polygon({
        map,
        paths: [exteriorPath, ...holes],
        strokeColor: '#f97316',  // Orange border
        strokeOpacity: 1,
        strokeWeight: 2,
        fillColor: '#f97316',  // Orange fill
        fillOpacity: 0.08,  // Very subtle - can see everything through it
        clickable: false,
        zIndex: 10,
      })
    }
    
    if (urbanArea.geometry.type === 'Polygon') {
      const polygon = createPolygon(urbanArea.geometry.coordinates)
      polygonsRef.current.push(polygon)
      console.log('[SelectedUrbanArea] Created polygon')
    } else if (urbanArea.geometry.type === 'MultiPolygon') {
      urbanArea.geometry.coordinates.forEach((polygonCoords, i) => {
        const polygon = createPolygon(polygonCoords)
        polygonsRef.current.push(polygon)
      })
      console.log('[SelectedUrbanArea] Created', urbanArea.geometry.coordinates.length, 'polygons')
    }
    
    // No cleanup in this effect - we want the polygon to persist
  }, [map, urbanArea])
  
  // Cleanup only on unmount
  useEffect(() => {
    return () => {
      console.log('[SelectedUrbanArea] Unmounting, cleaning up')
      polygonsRef.current.forEach(p => p.setMap(null))
      polygonsRef.current = []
      if (overlayRef.current) {
        overlayRef.current.setMap(null)
        overlayRef.current = null
      }
      hasZoomedRef.current = false
    }
  }, [])
  
  return null
}

// Global storage for boundary layer - uses Google Maps Data layer for efficiency
const kmlDataStorage = {
  dataLayer: null as google.maps.Data | null,
  infoWindow: null as google.maps.InfoWindow | null,
  currentLayerId: '',
  featureCount: 0,
  
  clear(map?: google.maps.Map) {
    if (this.dataLayer) {
      this.dataLayer.setMap(null)
      this.dataLayer = null
    }
    this.currentLayerId = ''
    this.featureCount = 0
  }
}

// KML Boundary Layer - uses Data layer for efficient rendering of large datasets
function KMLBoundaryLayerWrapper({
  boundaryLayer,
}: {
  boundaryLayer?: { data: BoundaryLayerResponse | null; layerId: string | null }
}) {
  const map = useMap()
  
  // Extract values to use as stable dependencies
  const layerId = boundaryLayer?.layerId ?? null
  const data = boundaryLayer?.data ?? null
  const featureCount = data?.features?.length ?? 0
  
  useEffect(() => {
    // If no data or no layer, clear existing
    if (!data || !layerId || !map || featureCount === 0) {
      if (kmlDataStorage.currentLayerId !== '') {
        kmlDataStorage.clear(map)
      }
      return
    }
    
    // Skip if same layer already rendered with same feature count
    if (kmlDataStorage.currentLayerId === layerId && 
        kmlDataStorage.featureCount === featureCount) {
      return
    }
    
    // Clear old data layer
    kmlDataStorage.clear(map)
    kmlDataStorage.currentLayerId = layerId
    kmlDataStorage.featureCount = featureCount
    
    // Get colors for this layer type
    const colors = BOUNDARY_LAYER_COLORS[layerId] || BOUNDARY_LAYER_COLORS.states

    // Create info window
    if (!kmlDataStorage.infoWindow) {
      kmlDataStorage.infoWindow = new google.maps.InfoWindow()
    }

    console.log(`[KML] Loading ${featureCount} features for ${layerId} using Data layer...`)
    const startTime = performance.now()

    // Create new Data layer
    const dataLayer = new google.maps.Data({ map })
    kmlDataStorage.dataLayer = dataLayer
    
    // Style the features
    dataLayer.setStyle({
      strokeColor: colors.stroke,
      strokeOpacity: 0.8,
      strokeWeight: 1,
      fillColor: colors.stroke,
      fillOpacity: 0.05,
    })
    
    // Add GeoJSON data
    try {
      dataLayer.addGeoJson({
        type: 'FeatureCollection',
        features: data.features
      })
    } catch (e) {
      console.error('[KML] Error adding GeoJSON:', e)
      return
    }
    
    // Hover effect
    dataLayer.addListener('mouseover', (event: google.maps.Data.MouseEvent) => {
      dataLayer.overrideStyle(event.feature, {
        strokeWeight: 2,
        fillOpacity: 0.15,
      })
    })
    
    dataLayer.addListener('mouseout', (event: google.maps.Data.MouseEvent) => {
      dataLayer.revertStyle(event.feature)
    })
    
    // Click to show info
    dataLayer.addListener('click', (event: google.maps.Data.MouseEvent) => {
      const name = event.feature.getProperty('name') || event.feature.getProperty('display_name') || 'Unknown'
      const id = event.feature.getProperty('id') || ''
      
      if (kmlDataStorage.infoWindow && event.latLng) {
        kmlDataStorage.infoWindow.setContent(`
          <div style="padding: 8px; font-family: system-ui, sans-serif;">
            <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">
              ${name}
            </div>
            <div style="font-size: 12px; color: #666;">
              ${id ? `ID: ${id}` : ''}
            </div>
          </div>
        `)
        kmlDataStorage.infoWindow.setPosition(event.latLng)
        kmlDataStorage.infoWindow.open(map)
      }
    })

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
    console.log(`[KML] Loaded ${featureCount} features in ${elapsed}s`)
  }, [map, layerId, featureCount])

  return null
}

// Search Results Layer - renders polygons for search results (no markers)
function SearchResultsLayer({
  results,
  selectedResult,
  onResultSelect,
}: {
  results: SearchParcel[]
  selectedResult: SearchParcel | null
  onResultSelect: (result: SearchParcel | null) => void
}) {
  const map = useMap()
  const polygonsRef = useRef<google.maps.Polygon[]>([])
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null)
  const lastResultsHashRef = useRef<string>('')

  useEffect(() => {
    if (!map) return

    // Create hash of parcel IDs to detect if results actually changed
    const resultsHash = results.map(r => r.parcel_id).sort().join(',')
    
    // Skip update if results haven't actually changed
    if (resultsHash === lastResultsHashRef.current && polygonsRef.current.length > 0) {
      return
    }
    lastResultsHashRef.current = resultsHash

    // Clear existing polygons and info window
    polygonsRef.current.forEach(p => p.setMap(null))
    polygonsRef.current = []
    if (infoWindowRef.current) {
      infoWindowRef.current.close()
    }

    if (results.length === 0) return

    // Create info window for showing details
    if (!infoWindowRef.current) {
      infoWindowRef.current = new google.maps.InfoWindow()
    }

    // Create polygons for each search result (no markers)
    results.forEach((result) => {
      if (result.polygon_geojson) {
        try {
          // Handle both Polygon and MultiPolygon geometries
          const geomType = result.polygon_geojson.type
          
          // Collect all polygon paths (each polygon may have multiple rings for holes)
          let allPolygonPaths: google.maps.LatLngLiteral[][] = []
          
          if (geomType === 'Polygon') {
            // Polygon: coordinates is array of rings [exterior, hole1, hole2, ...]
            // All rings go into ONE Google Maps Polygon (it handles holes automatically)
            const paths = result.polygon_geojson.coordinates.map((ring: number[][]) =>
              ring.map((coord: number[]) => ({ lat: coord[1], lng: coord[0] }))
            )
            allPolygonPaths = [paths]  // Single polygon with all its rings
          } else if (geomType === 'MultiPolygon') {
            // MultiPolygon: array of Polygon structures
            // Each polygon becomes a separate Google Maps Polygon
            allPolygonPaths = result.polygon_geojson.coordinates.map((poly: number[][][]) =>
              poly.map((ring: number[][]) =>
                ring.map((coord: number[]) => ({ lat: coord[1], lng: coord[0] }))
              )
            )
          } else {
            // Fallback: treat as simple polygon
            const ring = result.polygon_geojson.coordinates[0]
            if (ring) {
              const coords = ring.map((coord: number[]) => ({ lat: coord[1], lng: coord[0] }))
              allPolygonPaths = [[coords]]
            }
          }
          
          // Create Google Maps Polygon for each polygon structure
          allPolygonPaths.forEach((paths) => {
            const polygon = new google.maps.Polygon({
              paths: paths,  // paths can be array of arrays for polygon with holes
              strokeColor: '#047857',  // Dark emerald outline
              strokeOpacity: 1,
              strokeWeight: 2,
              fillColor: '#34d399',    // Light emerald fill
              fillOpacity: 0.08,       // Very subtle fill
              map,
              zIndex: 50,
            })

            // Show info window on click with Regrid details
            polygon.addListener('click', (e: google.maps.MapMouseEvent) => {
            const content = `
              <div style="font-family: system-ui; max-width: 300px; padding: 8px;">
                <h3 style="margin: 0 0 8px 0; font-size: 14px; font-weight: 600; color: #1f2937;">
                  ${result.address || 'Unknown Address'}
                </h3>
                <div style="font-size: 12px; color: #6b7280; line-height: 1.6;">
                  ${result.owner ? `<div><strong>Owner:</strong> ${result.owner}</div>` : ''}
                  ${result.area_acres ? `<div><strong>Size:</strong> ${result.area_acres.toFixed(2)} acres</div>` : ''}
                  ${result.land_use ? `<div><strong>Land Use:</strong> ${result.land_use}</div>` : ''}
                  ${result.zoning ? `<div><strong>Zoning:</strong> ${result.zoning}</div>` : ''}
                  ${result.year_built ? `<div><strong>Year Built:</strong> ${result.year_built}</div>` : ''}
                  ${result.lbcs_activity ? `<div><strong>LBCS Code:</strong> ${result.lbcs_activity}</div>` : ''}
                  ${result.lbcs_activity_desc ? `<div><strong>LBCS Desc:</strong> ${result.lbcs_activity_desc}</div>` : ''}
                  <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #e5e7eb;">
                    <strong>Parcel ID:</strong> ${result.parcel_id}
                  </div>
                </div>
              </div>
            `
            
            if (infoWindowRef.current) {
              infoWindowRef.current.setContent(content)
              infoWindowRef.current.setPosition(e.latLng)
              infoWindowRef.current.open(map)
            }
            
            onResultSelect(result)
          })

          // Highlight on hover
          polygon.addListener('mouseover', () => {
            polygon.setOptions({ 
              fillOpacity: 0.25, 
              strokeWeight: 3,
              strokeColor: '#059669'
            })
          })
          polygon.addListener('mouseout', () => {
            polygon.setOptions({ 
              fillOpacity: 0.08, 
              strokeWeight: 2,
              strokeColor: '#047857'
            })
          })

            polygonsRef.current.push(polygon)
          })  // End rings.forEach
        } catch (e) {
          console.error('Failed to draw polygon:', e)
        }
      }
    })

    // Fit bounds to show all results
    if (results.length > 0) {
      const bounds = new google.maps.LatLngBounds()
      results.forEach(r => {
        if (r.polygon_geojson) {
          r.polygon_geojson.coordinates[0].forEach((coord: number[]) => {
            bounds.extend({ lat: coord[1], lng: coord[0] })
          })
        } else {
          bounds.extend({ lat: r.lat, lng: r.lng })
        }
      })
      map.fitBounds(bounds, { top: 100, right: 50, bottom: 50, left: 350 })
    }

    return () => {
      polygonsRef.current.forEach(p => {
        google.maps.event.clearInstanceListeners(p)
        p.setMap(null)
      })
    }
  }, [map, results, onResultSelect])

  return null
}

// Polygon Drawing Controller
function PolygonDrawingController({
  isEnabled,
  onPolygonComplete,
}: {
  isEnabled: boolean
  onPolygonComplete: (polygon: GeoJSON.Polygon) => void
}) {
  const map = useMap()
  const drawingManagerRef = useRef<google.maps.drawing.DrawingManager | null>(null)
  const polygonCompleteListenerRef = useRef<google.maps.MapsEventListener | null>(null)

  // Initialize drawing manager once
  useEffect(() => {
    if (!map || drawingManagerRef.current) return

    const loadDrawingManager = async () => {
      // @ts-ignore - google.maps.drawing may not be typed
      if (!google.maps.drawing) {
        await google.maps.importLibrary('drawing')
      }

      const drawingManager = new google.maps.drawing.DrawingManager({
        drawingMode: null, // Start disabled
        drawingControl: false,
        polygonOptions: {
          strokeColor: '#059669', // Emerald green
          strokeOpacity: 1,
          strokeWeight: 3,
          fillColor: '#10b981', // Lighter green
          fillOpacity: 0.15,
          editable: true, // Allow editing after drawing
          draggable: false,
          clickable: true,
        },
      })

      drawingManager.setMap(map)
      drawingManagerRef.current = drawingManager

      // Listen for polygon completion
      polygonCompleteListenerRef.current = google.maps.event.addListener(
        drawingManager,
        'polygoncomplete',
        (polygon: google.maps.Polygon) => {
          // Convert to GeoJSON
          const path = polygon.getPath()
          const coordinates: number[][] = []
          
          for (let i = 0; i < path.getLength(); i++) {
            const point = path.getAt(i)
            coordinates.push([point.lng(), point.lat()])
          }
          // Close the polygon
          if (coordinates.length > 0 && coordinates[0][0] !== coordinates[coordinates.length - 1][0] || 
              coordinates[0][1] !== coordinates[coordinates.length - 1][1]) {
            coordinates.push([coordinates[0][0], coordinates[0][1]])
          }

          const geoJson: GeoJSON.Polygon = {
            type: 'Polygon',
            coordinates: [coordinates],
          }

          // Remove the DrawingManager's polygon - we use DrawnPolygonLayer instead
          polygon.setMap(null)
          
          // Disable drawing mode
          drawingManager.setDrawingMode(null)

          onPolygonComplete(geoJson)
        }
      )
    }

    loadDrawingManager()

    return () => {
      // Clean up listener
      if (polygonCompleteListenerRef.current) {
        google.maps.event.removeListener(polygonCompleteListenerRef.current)
        polygonCompleteListenerRef.current = null
      }
      // Clean up drawing manager
      if (drawingManagerRef.current) {
        drawingManagerRef.current.setMap(null)
        drawingManagerRef.current = null
      }
    }
  }, [map, onPolygonComplete])

  // Toggle drawing mode based on isEnabled prop
  useEffect(() => {
    if (!drawingManagerRef.current) return

    if (isEnabled) {
      // Enable polygon drawing mode
      drawingManagerRef.current.setDrawingMode(google.maps.drawing.OverlayType.POLYGON)
    } else {
      // Disable drawing mode (but keep manager alive)
      drawingManagerRef.current.setDrawingMode(null)
    }
  }, [isEnabled])

  return null
}

// Search Result Popup
function SearchResultPopup({
  parcel,
  onClose,
}: {
  parcel: SearchParcel
  onClose: () => void
}) {
  const formatAcres = (acres: number | null) => {
    if (!acres) return null
    return acres < 1 ? `${(acres * 43560).toFixed(0)} sqft` : `${acres.toFixed(2)} acres`
  }

  return (
    <div className="w-64 bg-card border border-border rounded-lg shadow-xl overflow-hidden">
      {/* Close Button */}
      <button
        onClick={onClose}
        className="absolute top-1.5 right-1.5 z-10 h-6 w-6 flex items-center justify-center rounded-md bg-black/40 backdrop-blur-sm hover:bg-black/60 transition-colors"
      >
        <X className="h-3.5 w-3.5 text-white" />
      </button>

      {/* Header */}
      <div className="bg-emerald-500 px-3 py-2">
        <div className="flex items-center gap-2 text-white">
          <MapPin className="h-4 w-4" />
          <span className="text-sm font-medium">Search Result</span>
        </div>
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        {/* Address */}
        <div>
          <p className="text-sm font-medium text-foreground line-clamp-2">
            {parcel.address || 'Unknown Address'}
          </p>
          {parcel.brand_name && (
            <p className="text-xs text-muted-foreground">{parcel.brand_name}</p>
          )}
        </div>

        {/* Details */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          {parcel.owner && (
            <div>
              <span className="text-muted-foreground">Owner:</span>
              <p className="font-medium text-foreground truncate">{parcel.owner}</p>
            </div>
          )}
          {parcel.area_acres && (
            <div>
              <span className="text-muted-foreground">Size:</span>
              <p className="font-medium text-foreground">{formatAcres(parcel.area_acres)}</p>
            </div>
          )}
          {parcel.land_use && (
            <div>
              <span className="text-muted-foreground">Land Use:</span>
              <p className="font-medium text-foreground truncate">{parcel.land_use}</p>
            </div>
          )}
          {parcel.zoning && (
            <div>
              <span className="text-muted-foreground">Zoning:</span>
              <p className="font-medium text-foreground">{parcel.zoning}</p>
            </div>
          )}
        </div>

        {/* Parcel ID */}
        <div className="text-[10px] text-muted-foreground pt-1 border-t border-border">
          ID: {parcel.parcel_id}
        </div>
      </div>
    </div>
  )
}
