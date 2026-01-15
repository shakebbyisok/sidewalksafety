'use client'

import { useMemo, useCallback, useEffect, useState, useRef } from 'react'
import { APIProvider, Map, Marker, useMap, InfoWindow, useMapsLibrary } from '@vis.gl/react-google-maps'
import { MarkerClusterer, GridAlgorithm } from '@googlemaps/markerclusterer'
import { DealMapResponse, PropertyAnalysisSummary } from '@/types'
import { MapPin, ExternalLink, Satellite, Map as MapIcon, X, CheckCircle2, Clock, Target, Building2, Phone, Globe, AlertTriangle, Search, Loader2, Layers, User } from 'lucide-react'
import { StatusChip, IconChip } from '@/components/ui'
import { cn } from '@/lib/utils'
import { parkingLotsApi } from '@/lib/api/parking-lots'

// Surface colors for polygon overlays
const SURFACE_COLORS: Record<string, { fill: string; stroke: string; label: string }> = {
  asphalt: { fill: '#374151', stroke: '#1F2937', label: 'Paved' },
  concrete: { fill: '#9CA3AF', stroke: '#6B7280', label: 'Concrete' },
  building: { fill: '#DC2626', stroke: '#991B1B', label: 'Building' },
  property_boundary: { fill: '#3B82F6', stroke: '#1D4ED8', label: 'Property' },
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
        setPropertyData(data.property_analysis || null)
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
}: InteractiveMapProps) {
  const [mapType, setMapType] = useState<'roadmap' | 'hybrid'>('roadmap')
  const [searchLocation, setSearchLocation] = useState<{ lat: number; lng: number; name: string } | null>(null)
  const [showOverlay, setShowOverlay] = useState(true) // Show property boundaries by default
  
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
        {/* Top Controls: Search Bar + Map Type Toggle */}
        <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between gap-4">
          {/* Search Box */}
          <PlaceSearchBox onPlaceSelect={handlePlaceSelect} />
          
          <div className="flex items-center gap-2">
            {/* Show Overlay Toggle (only visible when deal is selected) */}
            {selectedDeal && (
              <div className="relative">
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
              </div>
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
  
  if (deal.status === 'evaluated' || deal.status === 'analyzed') {
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
            status={deal.status === 'evaluated' || deal.status === 'analyzed' ? 'success' : deal.status === 'evaluating' ? 'info' : 'warning'}
            icon={deal.status === 'evaluated' || deal.status === 'analyzed' ? CheckCircle2 : Clock}
          >
            {deal.status === 'evaluated' || deal.status === 'analyzed' ? 'Analyzed' : deal.status === 'evaluating' ? 'Evaluating' : 'Pending'}
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
