'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { 
  Search, X, Hexagon, Hash, Building2, 
  Loader2, ChevronDown, ChevronUp, SquareParking, Fuel, Store, 
  Utensils, Factory, Trees, Building, Home, Map, MousePointerClick, MousePointer, User,
  MapPin, Compass, CheckCircle2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { searchApi, SearchParcel, ViewportBounds, PropertyCategory } from '@/lib/api/search'
import { boundariesApi, BoundaryAtPointResponse } from '@/lib/api/boundaries'
import { parkingLotsApi, RegridLookupResponse } from '@/lib/api/parking-lots'

// Category icons mapping
const CATEGORY_ICONS: Record<string, React.ElementType> = {
  parking: SquareParking,
  gas_station: Fuel,
  retail: Store,
  restaurant: Utensils,
  industrial: Factory,
  vacant: Trees,
  office: Building2,
  multifamily: Home,
}

// Urban area info type
interface UrbanAreaInfo {
  id: string
  name: string
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
}

interface SearchPanelProps {
  viewport: ViewportBounds | null
  onSearchResults: (parcels: SearchParcel[]) => void
  onDrawPolygon: () => void
  onCancelDrawing?: () => void  // Cancel active drawing
  onClearSearch: () => void
  onBoundarySelect: (
    boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon | null, 
    name: string,
    type: 'zip' | 'county' | null
  ) => void
  onMapClickMode: (mode: 'zip' | 'county' | 'pin' | 'urban' | null) => void  // Enable click-to-select mode
  onClearClickedPoint?: () => void  // Clear the clicked point
  onPinParcelPolygon?: (polygon: GeoJSON.Polygon | GeoJSON.MultiPolygon | null) => void  // Update pin parcel polygon
  onClearDrawnPolygon?: () => void  // Clear the drawn polygon
  // Urban area selection
  onShowUrbanOverlay?: (show: boolean) => void  // Show urban areas with grey overlay on non-urban
  onUrbanAreaSelect?: (urbanArea: UrbanAreaInfo | null) => void  // When user selects an urban area
  selectedUrbanArea?: UrbanAreaInfo | null  // Currently selected urban area
  isDrawing: boolean
  drawnPolygon: GeoJSON.Polygon | null
  // These come from map clicks in ZIP/County/Pin/Urban mode
  clickedPoint: { lat: number, lng: number } | null
}

type SearchMode = 'idle' | 'draw' | 'zip' | 'county' | 'pin'
type Step = 'urban' | 'method' | 'area' | 'type'  // Added 'urban' as first step

export function SearchPanel({
  viewport,
  onSearchResults,
  onDrawPolygon,
  onCancelDrawing,
  onClearSearch,
  onBoundarySelect,
  onMapClickMode,
  onClearClickedPoint,
  onPinParcelPolygon,
  onClearDrawnPolygon,
  onShowUrbanOverlay,
  onUrbanAreaSelect,
  selectedUrbanArea,
  isDrawing,
  drawnPolygon,
  clickedPoint,
}: SearchPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [searchMode, setSearchMode] = useState<SearchMode>('idle')
  const [step, setStep] = useState<Step>('urban')  // Start with urban area selection
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [minAcres, setMinAcres] = useState<string>('')
  const [maxAcres, setMaxAcres] = useState<string>('')
  const [showFilters, setShowFilters] = useState(false)
  const [resultCount, setResultCount] = useState<number | null>(null)
  
  // Selected boundary (from click-to-select)
  const [selectedBoundary, setSelectedBoundary] = useState<{
    id: string
    name: string
    geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
    type: 'zip' | 'county'
  } | null>(null)
  
  const [isLoadingBoundary, setIsLoadingBoundary] = useState(false)
  
  // Pin mode parcel data
  const [pinParcelData, setPinParcelData] = useState<RegridLookupResponse | null>(null)
  const [isLoadingParcel, setIsLoadingParcel] = useState(false)

  // Fetch categories
  const { data: categories = [] } = useQuery({
    queryKey: ['search-categories'],
    queryFn: searchApi.getCategories,
    staleTime: Infinity,
  })

  // Search mutation
  const searchMutation = useMutation({
    mutationFn: searchApi.search,
    onSuccess: (data) => {
      if (!data.success && data.error) {
        alert(data.error)
        return
      }
      setResultCount(data.total_count)
      onSearchResults(data.parcels)
      if (data.total_count > 0) {
        setIsExpanded(false)
      }
    },
    onError: (error: any) => {
      console.error('Search error:', error)
      alert(error?.response?.data?.error || 'Search failed. Please try again.')
    },
  })

  // Handle method selection
  const handleMethodSelect = useCallback((mode: SearchMode) => {
    setSearchMode(mode)
    setIsExpanded(true)
    setSelectedCategory(null)
    setSelectedBoundary(null)
    setPinParcelData(null)
    onBoundarySelect(null, '', null)
    onPinParcelPolygon?.(null)
    onClearDrawnPolygon?.()
    
    if (mode === 'draw') {
      setStep('area')
      onMapClickMode(null)
    } else if (mode === 'zip' || mode === 'county') {
      setStep('area')
      onMapClickMode(mode)
    } else if (mode === 'pin') {
      // Pin mode - click on map to look up individual parcel
      setStep('method')  // Stay on method screen but show pin instructions
      onMapClickMode('pin')
    } else {
      setStep('method')
      onMapClickMode(null)
    }
  }, [onMapClickMode, onBoundarySelect, onPinParcelPolygon, onClearDrawnPolygon])

  // Handle click-to-select boundary lookup (ZIP/County)
  useEffect(() => {
    if (!clickedPoint) return
    if (searchMode !== 'zip' && searchMode !== 'county') return
    if (step !== 'area') return
    
    const fetchBoundary = async () => {
      setIsLoadingBoundary(true)
      try {
        const layer = searchMode === 'zip' ? 'zips' : 'counties'
        const result = await boundariesApi.getBoundaryAtPoint(
          clickedPoint.lat,
          clickedPoint.lng,
          layer
        )
        
        if (result.found && result.boundary) {
          setSelectedBoundary({
            id: result.boundary.id,
            name: result.boundary.name,
            geometry: result.boundary.geometry,
            type: searchMode,
          })
          onBoundarySelect(result.boundary.geometry, result.boundary.name, searchMode)
          setStep('type')
        } else {
          alert(`No ${searchMode === 'zip' ? 'ZIP code' : 'county'} found at this location`)
        }
      } catch (error) {
        console.error('Boundary lookup error:', error)
        alert('Failed to find boundary. Please try again.')
      } finally {
        setIsLoadingBoundary(false)
      }
    }
    
    fetchBoundary()
  }, [clickedPoint, searchMode, step, onBoundarySelect])

  // Handle Pin mode parcel lookup
  useEffect(() => {
    if (!clickedPoint) return
    if (searchMode !== 'pin') return
    
    const fetchParcel = async () => {
      setIsLoadingParcel(true)
      setPinParcelData(null)
      onPinParcelPolygon?.(null) // Clear polygon while loading
      try {
        const data = await parkingLotsApi.regridLookup(clickedPoint.lat, clickedPoint.lng)
        setPinParcelData(data)
        // Update polygon on map if available
        if (data.polygon_geojson) {
          onPinParcelPolygon?.(data.polygon_geojson)
        } else {
          onPinParcelPolygon?.(null)
        }
      } catch (error: any) {
        console.error('Parcel lookup error:', error)
        setPinParcelData({
          has_parcel: false,
          location: clickedPoint,
          error: error?.response?.data?.detail || 'Failed to lookup parcel',
        })
        onPinParcelPolygon?.(null)
      } finally {
        setIsLoadingParcel(false)
      }
    }
    
    fetchParcel()
  }, [clickedPoint, searchMode, onPinParcelPolygon])

  // Handle category selection and trigger search
  const handleCategorySelect = useCallback((categoryId: string) => {
    setSelectedCategory(categoryId)
  }, [])

  // Handle search execution
  const handleSearch = useCallback(() => {
    if (!selectedCategory) {
      alert('Please select a property type')
      return
    }

    const filters = {
      category_id: selectedCategory,
      min_acres: minAcres ? parseFloat(minAcres) : undefined,
      max_acres: maxAcres ? parseFloat(maxAcres) : undefined,
    }

    if (searchMode === 'draw' && drawnPolygon) {
      searchMutation.mutate({
        search_type: 'polygon',
        polygon_geojson: drawnPolygon,
        filters,
      })
    } else if ((searchMode === 'zip' || searchMode === 'county') && selectedBoundary) {
      // Use the boundary polygon for spatial search
      searchMutation.mutate({
        search_type: 'polygon',
        polygon_geojson: selectedBoundary.geometry,
        filters,
      })
    }
  }, [searchMode, drawnPolygon, selectedBoundary, selectedCategory, minAcres, maxAcres, searchMutation])

  // Auto-advance after drawing polygon
  useEffect(() => {
    if (drawnPolygon && searchMode === 'draw' && step === 'area') {
      setStep('type')
    }
  }, [drawnPolygon, searchMode, step])

  // ESC key to clear drawn polygon or cancel drawing
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && searchMode === 'draw') {
        if (isDrawing) {
          // Cancel active drawing
          onCancelDrawing?.()
        } else if (drawnPolygon) {
          // Clear completed polygon
          onClearDrawnPolygon?.()
          // If we're on type step, go back to area step
          if (step === 'type') {
            setStep('area')
            setSelectedCategory(null)
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [drawnPolygon, searchMode, step, isDrawing, onClearDrawnPolygon, onCancelDrawing])

  // Show/hide urban overlay based on panel expansion and step
  // Only show overlay when panel is expanded AND we're on the urban step
  // When user selects urban area and clicks Continue, overlay hides but area stays selected
  useEffect(() => {
    if (isExpanded && step === 'urban') {
      onShowUrbanOverlay?.(true)
      onMapClickMode('urban')
    } else if (step === 'method' || step === 'area' || step === 'type') {
      // After Continue is clicked, hide the overlay but keep selectedUrbanArea
      onShowUrbanOverlay?.(false)
      onMapClickMode(null)
    } else {
      onShowUrbanOverlay?.(false)
      if (step !== 'urban') {
        onMapClickMode(null)
      }
    }
  }, [isExpanded, step, onShowUrbanOverlay, onMapClickMode])

  // Clear search
  const handleClear = useCallback(() => {
    setSelectedCategory(null)
    setMinAcres('')
    setMaxAcres('')
    setResultCount(null)
    setSearchMode('idle')
    setStep('urban')  // Reset to urban step
    setSelectedBoundary(null)
    setPinParcelData(null)
    onBoundarySelect(null, '', null)
    onMapClickMode('urban')
    // Overlay visibility will be handled by useEffect based on isExpanded
    onUrbanAreaSelect?.(null)
    onPinParcelPolygon?.(null)
    onClearDrawnPolygon?.()
    onClearSearch()
  }, [onClearSearch, onBoundarySelect, onMapClickMode, onPinParcelPolygon, onClearDrawnPolygon, onUrbanAreaSelect])

  // Go back one step
  const handleBack = useCallback(() => {
    if (step === 'type') {
      setStep('area')
      setSelectedCategory(null)
      if (searchMode === 'draw') {
        // Keep the polygon but allow re-draw
      } else {
        // Clear the boundary and re-enable click mode for new selection
        setSelectedBoundary(null)
        onBoundarySelect(null, '', null)
        // Re-trigger click mode to clear the old clicked point and allow new selection
        onMapClickMode(searchMode as 'zip' | 'county')
      }
    } else if (step === 'area') {
      setStep('method')
      setSearchMode('idle')
      onMapClickMode(null)
      setSelectedBoundary(null)
      onBoundarySelect(null, '', null)
      onClearDrawnPolygon?.()
    } else if (step === 'method') {
      // Go back to urban area selection
      setStep('urban')
      setSearchMode('idle')
      onMapClickMode('urban')
      // Overlay visibility will be handled by useEffect based on isExpanded
    }
  }, [step, searchMode, onBoundarySelect, onMapClickMode, onClearDrawnPolygon])

  // Change - go back to method selection (reset everything)
  const handleChange = useCallback(() => {
    setStep('urban')  // Go back to urban selection
    setSearchMode('idle')
    setSelectedCategory(null)
    setSelectedBoundary(null)
    setPinParcelData(null)
    onBoundarySelect(null, '', null)
    onMapClickMode('urban')
    // Overlay visibility will be handled by useEffect based on isExpanded
    onPinParcelPolygon?.(null)
    onClearClickedPoint?.()
    onClearDrawnPolygon?.()
  }, [onBoundarySelect, onMapClickMode, onPinParcelPolygon, onClearClickedPoint, onClearDrawnPolygon])

  const isLoading = searchMutation.isPending || isLoadingBoundary || isLoadingParcel
  const selectedCategoryData = categories.find(c => c.id === selectedCategory)
  
  // Determine if search button should be enabled
  const canSearch = selectedCategory && (
    (searchMode === 'draw' && drawnPolygon) ||
    ((searchMode === 'zip' || searchMode === 'county') && selectedBoundary)
  )

  return (
    <div className="absolute top-4 right-4 z-20 w-72">
      <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-stone-200 overflow-hidden">
        {/* Header */}
        <div className="px-3 py-2.5 border-b border-stone-100 bg-stone-50/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Search className="h-3.5 w-3.5 text-stone-400" />
              <span className="text-xs font-semibold text-stone-700 uppercase tracking-wider">
                Find Properties
              </span>
            </div>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-1 hover:bg-stone-200/50 rounded transition-colors"
            >
              {isExpanded ? (
                <ChevronUp className="h-3.5 w-3.5 text-stone-400" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 text-stone-400" />
              )}
            </button>
          </div>
        </div>

        {/* Result Count */}
        {resultCount !== null && (
          <div className="px-3 py-2 bg-emerald-50 border-b border-emerald-100 flex items-center justify-between">
            <span className="text-xs text-emerald-700 font-medium">
              {resultCount} parcel{resultCount !== 1 ? 's' : ''} found
            </span>
            <button
              onClick={handleClear}
              className="text-xs text-emerald-600 hover:text-emerald-800 font-medium"
            >
              Clear
            </button>
          </div>
        )}

        {/* Content */}
        {isExpanded && (
          <div className="p-3">
            {/* Step 0: Select Urban Area (for data accuracy) */}
            {step === 'urban' && (
              <div className="space-y-3">
                {!selectedUrbanArea ? (
                  <>
                    <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
                      Select Urban Area
                    </p>
                    <div className="p-3 bg-stone-50 rounded-md border border-stone-200">
                      <div className="flex flex-col items-center gap-2 text-center">
                        <Compass className="h-8 w-8 text-indigo-500" />
                        <p className="text-xs font-medium text-stone-700">Click on an urban area</p>
                        <p className="text-[10px] text-stone-400">
                          Click on the map to select a metro area
                        </p>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="space-y-3">
                    {/* Selected urban area */}
                    <div className="p-2.5 bg-indigo-50 rounded-md border border-indigo-200">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-indigo-800 truncate">
                            {selectedUrbanArea.name}
                          </p>
                          <p className="text-[10px] text-indigo-600">
                            Metro Area Selected
                          </p>
                        </div>
                        <button
                          onClick={() => {
                            onUrbanAreaSelect?.(null)
                            // Overlay visibility will be handled by useEffect based on isExpanded
                          }}
                          className="p-1 hover:bg-indigo-100 rounded transition-colors"
                          title="Change urban area"
                        >
                          <X className="h-3 w-3 text-indigo-500" />
                        </button>
                      </div>
                    </div>
                    
                    {/* Continue button */}
                    <button
                      onClick={() => {
                        setStep('method')
                        // Overlay visibility will be handled by useEffect based on isExpanded
                      }}
                      className="w-full py-2.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
                    >
                      Continue
                      <span className="text-indigo-300">→</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Step 1: Select Method */}
            {step === 'method' && (
              <div className="space-y-2">
                {/* Show selected urban area if any */}
                {selectedUrbanArea && (
                  <div className="mb-3 p-2 bg-indigo-50/50 rounded-md border border-indigo-100 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 text-indigo-500" />
                      <span className="text-xs text-indigo-700 truncate">{selectedUrbanArea.name}</span>
                    </div>
                    <button
                      onClick={() => {
                        onMapClickMode('urban')
                        setStep('urban')
                        // Overlay visibility will be handled by useEffect based on isExpanded
                      }}
                      className="text-[10px] text-indigo-500 hover:text-indigo-700"
                    >
                      Change
                    </button>
                  </div>
                )}
                
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
                    Choose Search Method
                  </p>
                  <button
                    onClick={handleBack}
                    className="text-[10px] text-stone-400 hover:text-stone-600"
                  >
                    ← Back
                  </button>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  <MethodButton
                    icon={Hexagon}
                    label="Draw"
                    description="Draw area"
                    active={searchMode === 'draw'}
                    onClick={() => handleMethodSelect('draw')}
                  />
                  <MethodButton
                    icon={Hash}
                    label="ZIP"
                    description="Click map"
                    active={searchMode === 'zip'}
                    onClick={() => handleMethodSelect('zip')}
                  />
                  <MethodButton
                    icon={Map}
                    label="County"
                    description="Click map"
                    active={searchMode === 'county'}
                    onClick={() => handleMethodSelect('county')}
                  />
                  <MethodButton
                    icon={MousePointer}
                    label="Pin"
                    description="One parcel"
                    active={searchMode === 'pin'}
                    onClick={() => handleMethodSelect('pin')}
                  />
                </div>
                
                {/* Pin Mode Active */}
                {searchMode === 'pin' && (
                  <div className="mt-3 space-y-2">
                    {!pinParcelData && !isLoadingParcel && (
                      <div className="p-3 bg-stone-50 rounded-md border border-stone-200">
                        <div className="flex flex-col items-center gap-2 text-center">
                          <MousePointerClick className="h-6 w-6 text-emerald-600" />
                          <p className="text-xs font-medium text-stone-700">Click on the map</p>
                          <p className="text-[10px] text-stone-400">
                            to view details for any parcel
                          </p>
                        </div>
                      </div>
                    )}
                    
                    {isLoadingParcel && (
                      <div className="p-3 bg-stone-50 rounded-md border border-stone-200">
                        <div className="flex flex-col items-center gap-2">
                          <Loader2 className="h-6 w-6 text-stone-400 animate-spin" />
                          <p className="text-xs text-stone-500">Looking up parcel...</p>
                        </div>
                      </div>
                    )}
                    
                    {pinParcelData && (
                      <div className="p-3 bg-white rounded-md border border-stone-200 space-y-2">
                        {pinParcelData.has_parcel && pinParcelData.parcel ? (
                          <>
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-semibold text-stone-700">Parcel Details</h4>
                              <button
                                onClick={() => {
                                  setPinParcelData(null)
                                  onPinParcelPolygon?.(null)
                                  onClearClickedPoint?.()
                                }}
                                className="text-[10px] text-stone-400 hover:text-stone-600"
                              >
                                Clear
                              </button>
                            </div>
                            
                            <div className="space-y-1.5">
                              {pinParcelData.parcel.address && (
                                <div>
                                  <p className="text-xs font-medium text-stone-800 truncate">
                                    {pinParcelData.parcel.address}
                                  </p>
                                </div>
                              )}
                              
                              {pinParcelData.parcel.owner && (
                                <div className="flex items-center gap-1.5 text-xs text-stone-600">
                                  <User className="h-3 w-3" />
                                  <span className="truncate">{pinParcelData.parcel.owner}</span>
                                </div>
                              )}
                              
                              <div className="grid grid-cols-2 gap-2 pt-1">
                                {pinParcelData.parcel.area_acres && (
                                  <div className="bg-stone-50 rounded px-2 py-1">
                                    <div className="text-[10px] text-stone-400 uppercase">Area</div>
                                    <div className="text-xs font-medium text-stone-700">
                                      {pinParcelData.parcel.area_acres.toFixed(2)} ac
                                    </div>
                                  </div>
                                )}
                                
                                {pinParcelData.parcel.land_use && (
                                  <div className="bg-stone-50 rounded px-2 py-1">
                                    <div className="text-[10px] text-stone-400 uppercase">Use</div>
                                    <div className="text-xs font-medium text-stone-700 truncate">
                                      {pinParcelData.parcel.land_use}
                                    </div>
                                  </div>
                                )}
                              </div>
                              
                              {pinParcelData.parcel.apn && (
                                <div className="text-[10px] text-stone-400">
                                  APN: {pinParcelData.parcel.apn}
                                </div>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="text-center py-2">
                            <p className="text-xs text-amber-600">
                              {pinParcelData.error || 'No parcel found at this location'}
                            </p>
                            <button
                              onClick={() => {
                                setPinParcelData(null)
                                onPinParcelPolygon?.(null)
                                onClearClickedPoint?.()
                              }}
                              className="mt-2 text-[10px] text-stone-400 hover:text-stone-600"
                            >
                              Try another location
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Step 2: Define Area */}
            {step === 'area' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
                    {searchMode === 'draw' ? 'Draw Area' : searchMode === 'zip' ? 'Select ZIP Code' : 'Select County'}
                  </p>
                  <button
                    onClick={handleBack}
                    className="text-[10px] text-stone-400 hover:text-stone-600"
                  >
                    ← Back
                  </button>
                </div>

                {searchMode === 'draw' && (
                  <div className="space-y-2">
                    {!drawnPolygon ? (
                      <>
                        <button
                          onClick={onDrawPolygon}
                          disabled={isDrawing}
                          className={cn(
                            "w-full py-3 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors",
                            isDrawing
                              ? "bg-emerald-600 text-white cursor-not-allowed"
                              : "bg-emerald-600 text-white hover:bg-emerald-700"
                          )}
                        >
                          <Hexagon className="h-4 w-4" />
                          {isDrawing ? 'Drawing... Click to finish' : 'Start Drawing'}
                        </button>
                        {isDrawing && (
                          <div className="p-2 bg-emerald-50 border border-emerald-200 rounded-md space-y-1">
                            <p className="text-xs text-emerald-700 text-center">
                              Click on the map to add points. Double-click or click the first point to finish.
                            </p>
                            <p className="text-[9px] text-emerald-500 text-center">
                              Press ESC to cancel
                            </p>
                          </div>
                        )}
                        {!isDrawing && (
                          <p className="text-[10px] text-stone-400 text-center">
                            Click "Start Drawing" then click points on the map to create your search area
                          </p>
                        )}
                        <p className="text-[10px] text-amber-600 text-center">
                          Max area: 350 sq miles
                        </p>
                      </>
                    ) : (
                      <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md space-y-2">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 bg-emerald-600 rounded-full animate-pulse" />
                          <p className="text-xs font-medium text-emerald-700 flex-1">
                            Polygon drawn successfully!
                          </p>
                          <button
                            onClick={() => {
                              onClearDrawnPolygon?.()
                              if (step === 'type') {
                                setStep('area')
                                setSelectedCategory(null)
                              }
                            }}
                            className="p-1 hover:bg-emerald-100 rounded transition-colors"
                            title="Clear polygon (ESC)"
                          >
                            <X className="h-3 w-3 text-emerald-600" />
                          </button>
                        </div>
                        <p className="text-[10px] text-emerald-600">
                          Select a property type below to search within this area
                        </p>
                        <p className="text-[9px] text-emerald-500 text-center">
                          Press ESC to clear
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {(searchMode === 'zip' || searchMode === 'county') && (
                  <div className="text-center py-4">
                    {isLoadingBoundary ? (
                      <div className="flex flex-col items-center gap-2">
                        <Loader2 className="h-8 w-8 text-stone-400 animate-spin" />
                        <p className="text-xs text-stone-500">Finding boundary...</p>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-2">
                        <MousePointerClick className="h-8 w-8 text-stone-400" />
                        <p className="text-sm text-stone-600 font-medium">
                          Click on the map
                        </p>
                        <p className="text-xs text-stone-400">
                          to select a {searchMode === 'zip' ? 'ZIP code' : 'county'}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Step 3: Select Property Type & Search */}
            {step === 'type' && (
              <div className="space-y-3">
                {/* Selected Area Summary */}
                <div className="flex items-center justify-between p-2 bg-stone-50 rounded-md border border-stone-200">
                  <div className="flex items-center gap-2">
                    {searchMode === 'draw' && <Hexagon className="h-4 w-4 text-stone-500" />}
                    {searchMode === 'zip' && <Hash className="h-4 w-4 text-stone-500" />}
                    {searchMode === 'county' && <Map className="h-4 w-4 text-stone-500" />}
                    <div>
                      <p className="text-xs font-medium text-stone-700">
                        {searchMode === 'draw' && 'Drawn Area'}
                        {searchMode === 'zip' && `ZIP: ${selectedBoundary?.name || ''}`}
                        {searchMode === 'county' && `${selectedBoundary?.name || ''}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {searchMode === 'draw' && drawnPolygon && (
                      <button
                        onClick={() => {
                          onClearDrawnPolygon?.()
                          setStep('area')
                          setSelectedCategory(null)
                        }}
                        className="p-1 hover:bg-stone-200 rounded transition-colors"
                        title="Clear polygon (ESC)"
                      >
                        <X className="h-3 w-3 text-stone-500" />
                      </button>
                    )}
                    <button
                      onClick={handleChange}
                      className="text-[10px] text-stone-400 hover:text-stone-600"
                    >
                      Change
                    </button>
                  </div>
                </div>

                {/* Property Type Selection */}
                <div>
                  <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider mb-2">
                    Select Property Type
                  </p>
                  <div className="grid grid-cols-4 gap-1.5">
                    {categories.map((cat) => (
                      <CategoryButton
                        key={cat.id}
                        category={cat}
                        selected={selectedCategory === cat.id}
                        onClick={() => handleCategorySelect(cat.id)}
                      />
                    ))}
                  </div>
                </div>

                {/* Size Filters */}
                {selectedCategory && (
                  <div className="pt-2 border-t border-stone-100">
                    <button
                      onClick={() => setShowFilters(!showFilters)}
                      className="flex items-center gap-1.5 text-[10px] font-medium text-stone-500 hover:text-stone-700"
                    >
                      Size Filter (optional)
                      {showFilters ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </button>
                    
                    {showFilters && (
                      <div className="flex items-center gap-2 mt-2">
                        <input
                          type="number"
                          value={minAcres}
                          onChange={(e) => setMinAcres(e.target.value)}
                          placeholder="Min"
                          className="w-16 px-2 py-1.5 bg-stone-50 border border-stone-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-stone-400"
                        />
                        <span className="text-[10px] text-stone-400">to</span>
                        <input
                          type="number"
                          value={maxAcres}
                          onChange={(e) => setMaxAcres(e.target.value)}
                          placeholder="Max"
                          className="w-16 px-2 py-1.5 bg-stone-50 border border-stone-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-stone-400"
                        />
                        <span className="text-[10px] text-stone-400">acres</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Search Button */}
                <button
                  onClick={handleSearch}
                  disabled={!canSearch || isLoading}
                  className={cn(
                    "w-full py-2.5 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors",
                    canSearch && !isLoading
                      ? "bg-emerald-600 text-white hover:bg-emerald-700"
                      : "bg-stone-200 text-stone-400 cursor-not-allowed"
                  )}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Search className="h-4 w-4" />
                      Search {selectedCategoryData?.label || 'Properties'}
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Method button component
function MethodButton({
  icon: Icon,
  label,
  description,
  active,
  onClick,
}: {
  icon: React.ElementType
  label: string
  description: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-col items-center gap-1 p-3 rounded-lg transition-all border",
        active
          ? "bg-stone-800 text-white border-stone-800"
          : "bg-white text-stone-600 border-stone-200 hover:bg-stone-50 hover:border-stone-300"
      )}
    >
      <Icon className="h-5 w-5" />
      <span className="text-xs font-medium">{label}</span>
      <span className={cn(
        "text-[9px]",
        active ? "text-stone-300" : "text-stone-400"
      )}>
        {description}
      </span>
    </button>
  )
}

// Category button component
function CategoryButton({
  category,
  selected,
  onClick,
}: {
  category: PropertyCategory
  selected: boolean
  onClick: () => void
}) {
  const Icon = CATEGORY_ICONS[category.id] || Building2

  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-col items-center gap-0.5 p-2 rounded-md transition-all border",
        selected
          ? "bg-stone-800 text-white border-stone-800"
          : "bg-white text-stone-600 border-stone-200 hover:bg-stone-50"
      )}
      title={category.description}
    >
      <Icon className="h-4 w-4" />
      <span className="text-[9px] font-medium truncate w-full text-center">
        {category.label.split(' ')[0]}
      </span>
    </button>
  )
}

export default SearchPanel
