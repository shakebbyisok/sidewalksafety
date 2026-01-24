'use client'

import { useState, useCallback, useEffect, useMemo } from 'react'
import { 
  Search, X, Hexagon, Hash, Map, Loader2, ChevronDown, ChevronUp, 
  MapPin, Compass, CheckCircle2, Filter, Square, SquareCheck, 
  ArrowRight, Ruler, ListFilter, MousePointerClick
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ArcGISParcel, SizeFilter, SIZE_PRESETS, filterParcelsBySize } from '@/lib/api/arcgis-parcels'

// Urban area info type
interface UrbanAreaInfo {
  id: string
  name: string
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
}

interface DiscoveryPanelProps {
  // Area selection
  onDrawPolygon: () => void
  onCancelDrawing?: () => void
  onClearDrawnPolygon?: () => void
  onMapClickMode: (mode: 'zip' | 'county' | 'urban' | null) => void
  onBoundarySelect: (
    boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon | null, 
    name: string,
    type: 'zip' | 'county' | null
  ) => void
  
  // Drawing state
  isDrawing: boolean
  drawnPolygon: GeoJSON.Polygon | null
  
  // Boundary selection from map click
  clickedPoint: { lat: number; lng: number } | null
  selectedBoundary: {
    id: string
    name: string
    geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
    type: 'zip' | 'county'
  } | null
  isLoadingBoundary: boolean
  
  // Urban area selection
  onShowUrbanOverlay?: (show: boolean) => void
  onUrbanAreaSelect?: (urbanArea: UrbanAreaInfo | null) => void
  selectedUrbanArea?: UrbanAreaInfo | null
  
  // Parcels from map tiles
  loadedParcels: ArcGISParcel[]
  isLoadingParcels: boolean
  onRequestParcels: (boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon) => void
  
  // Selection
  selectedParcels: ArcGISParcel[]
  onParcelSelect: (parcel: ArcGISParcel, selected: boolean) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  
  // Processing
  onProcessSelected: (parcels: ArcGISParcel[]) => void
  
  // Clear
  onClearParcels?: () => void
}

type Step = 'urban' | 'method' | 'area' | 'size' | 'select'
type SearchMode = 'idle' | 'draw' | 'zip' | 'county'

export function DiscoveryPanel({
  onDrawPolygon,
  onCancelDrawing,
  onClearDrawnPolygon,
  onMapClickMode,
  onBoundarySelect,
  isDrawing,
  drawnPolygon,
  clickedPoint,
  selectedBoundary,
  isLoadingBoundary,
  onShowUrbanOverlay,
  onUrbanAreaSelect,
  selectedUrbanArea,
  loadedParcels,
  isLoadingParcels,
  onRequestParcels,
  selectedParcels,
  onParcelSelect,
  onSelectAll,
  onDeselectAll,
  onProcessSelected,
  onClearParcels,
}: DiscoveryPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [step, setStep] = useState<Step>('urban')
  const [searchMode, setSearchMode] = useState<SearchMode>('idle')
  
  // Size filter state
  const [sizePreset, setSizePreset] = useState(0) // Index into SIZE_PRESETS
  const [customMinAcres, setCustomMinAcres] = useState('')
  const [customMaxAcres, setCustomMaxAcres] = useState('')
  const [useCustomSize, setUseCustomSize] = useState(false)
  
  // Current size filter
  const sizeFilter: SizeFilter = useMemo(() => {
    if (useCustomSize) {
      return {
        minAcres: customMinAcres ? parseFloat(customMinAcres) : undefined,
        maxAcres: customMaxAcres ? parseFloat(customMaxAcres) : undefined,
      }
    }
    const preset = SIZE_PRESETS[sizePreset]
    return {
      minAcres: preset.min,
      maxAcres: preset.max,
    }
  }, [sizePreset, customMinAcres, customMaxAcres, useCustomSize])
  
  // Filtered parcels based on size
  const filteredParcels = useMemo(() => {
    return filterParcelsBySize(loadedParcels, sizeFilter)
  }, [loadedParcels, sizeFilter])
  
  // Selected area geometry
  const selectedAreaGeometry = useMemo(() => {
    if (drawnPolygon) return drawnPolygon
    if (selectedBoundary?.geometry) return selectedBoundary.geometry
    return null
  }, [drawnPolygon, selectedBoundary])
  
  // Handle method selection
  const handleMethodSelect = useCallback((mode: SearchMode) => {
    setSearchMode(mode)
    
    if (mode === 'draw') {
      setStep('area')
      onMapClickMode(null)
    } else if (mode === 'zip' || mode === 'county') {
      setStep('area')
      onMapClickMode(mode)
    }
  }, [onMapClickMode])
  
  // Handle urban area continue
  const handleUrbanContinue = useCallback(() => {
    setStep('method')
    onShowUrbanOverlay?.(false)
  }, [onShowUrbanOverlay])
  
  // Handle area selection complete -> go to size filter
  const handleAreaComplete = useCallback(() => {
    if (selectedAreaGeometry) {
      setStep('size')
      onMapClickMode(null)
    }
  }, [selectedAreaGeometry, onMapClickMode])
  
  // Handle size filter complete -> load parcels
  const handleSizeComplete = useCallback(() => {
    if (selectedAreaGeometry) {
      setStep('select')
      onRequestParcels(selectedAreaGeometry)
    }
  }, [selectedAreaGeometry, onRequestParcels])
  
  // Handle process
  const handleProcess = useCallback(() => {
    if (selectedParcels.length > 0) {
      onProcessSelected(selectedParcels)
    }
  }, [selectedParcels, onProcessSelected])
  
  // Auto-advance when boundary is selected from map click
  useEffect(() => {
    if (selectedBoundary && step === 'area' && (searchMode === 'zip' || searchMode === 'county')) {
      handleAreaComplete()
    }
  }, [selectedBoundary, step, searchMode, handleAreaComplete])
  
  // Auto-advance when polygon is drawn
  useEffect(() => {
    if (drawnPolygon && step === 'area' && searchMode === 'draw') {
      handleAreaComplete()
    }
  }, [drawnPolygon, step, searchMode, handleAreaComplete])
  
  // Urban overlay control
  useEffect(() => {
    if (isExpanded && step === 'urban') {
      onShowUrbanOverlay?.(true)
      onMapClickMode('urban')
    }
  }, [isExpanded, step, onShowUrbanOverlay, onMapClickMode])
  
  // Handle back
  const handleBack = useCallback(() => {
    switch (step) {
      case 'method':
        setStep('urban')
        onShowUrbanOverlay?.(true)
        onMapClickMode('urban')
        break
      case 'area':
        setStep('method')
        setSearchMode('idle')
        onMapClickMode(null)
        onBoundarySelect(null, '', null)
        onClearDrawnPolygon?.()
        break
      case 'size':
        setStep('area')
        if (searchMode === 'draw') {
          onClearDrawnPolygon?.()
        } else {
          onBoundarySelect(null, '', null)
          onMapClickMode(searchMode as 'zip' | 'county')
        }
        break
      case 'select':
        setStep('size')
        onDeselectAll()
        break
    }
  }, [step, searchMode, onShowUrbanOverlay, onMapClickMode, onBoundarySelect, onClearDrawnPolygon, onDeselectAll])
  
  // Handle clear/reset
  const handleClear = useCallback(() => {
    setStep('urban')
    setSearchMode('idle')
    setSizePreset(0)
    setCustomMinAcres('')
    setCustomMaxAcres('')
    setUseCustomSize(false)
    onBoundarySelect(null, '', null)
    onClearDrawnPolygon?.()
    onDeselectAll()
    onClearParcels?.()
    onUrbanAreaSelect?.(null)
    onShowUrbanOverlay?.(true)
    onMapClickMode('urban')
  }, [onBoundarySelect, onClearDrawnPolygon, onDeselectAll, onClearParcels, onUrbanAreaSelect, onShowUrbanOverlay, onMapClickMode])
  
  // ESC key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isDrawing) {
          onCancelDrawing?.()
        } else if (drawnPolygon && step === 'area') {
          onClearDrawnPolygon?.()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isDrawing, drawnPolygon, step, onCancelDrawing, onClearDrawnPolygon])
  
  const isLoading = isLoadingBoundary || isLoadingParcels

  return (
    <div className="absolute top-4 right-4 z-20 w-80">
      <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-stone-200 overflow-hidden">
        {/* Header */}
        <div className="px-3 py-2.5 border-b border-stone-100 bg-stone-50/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Search className="h-3.5 w-3.5 text-stone-400" />
              <span className="text-xs font-semibold text-stone-700 uppercase tracking-wider">
                Discovery
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

        {/* Content */}
        {isExpanded && (
          <div className="p-3 max-h-[70vh] overflow-y-auto">
            
            {/* Step: Urban Area Selection */}
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
                          Metro areas have the best parcel data coverage
                        </p>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="space-y-3">
                    <div className="p-2.5 bg-indigo-50 rounded-md border border-indigo-200">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-indigo-800 truncate">
                            {selectedUrbanArea.name}
                          </p>
                          <p className="text-[10px] text-indigo-600">Metro Area Selected</p>
                        </div>
                        <button
                          onClick={() => onUrbanAreaSelect?.(null)}
                          className="p-1 hover:bg-indigo-100 rounded transition-colors"
                        >
                          <X className="h-3 w-3 text-indigo-500" />
                        </button>
                      </div>
                    </div>
                    <button
                      onClick={handleUrbanContinue}
                      className="w-full py-2.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
                    >
                      Continue <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Step: Method Selection */}
            {step === 'method' && (
              <div className="space-y-3">
                {/* Show selected urban area */}
                {selectedUrbanArea && (
                  <div className="p-2 bg-indigo-50/50 rounded-md border border-indigo-100 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 text-indigo-500" />
                      <span className="text-xs text-indigo-700 truncate">{selectedUrbanArea.name}</span>
                    </div>
                    <button
                      onClick={handleBack}
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
                </div>
                
                <div className="grid grid-cols-3 gap-2">
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
                </div>
              </div>
            )}

            {/* Step: Area Selection */}
            {step === 'area' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
                    {searchMode === 'draw' ? 'Draw Area' : searchMode === 'zip' ? 'Select ZIP Code' : 'Select County'}
                  </p>
                  <button onClick={handleBack} className="text-[10px] text-stone-400 hover:text-stone-600">
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
                          <p className="text-[10px] text-emerald-600 text-center">
                            Click points on map. Double-click to finish. Press ESC to cancel.
                          </p>
                        )}
                      </>
                    ) : (
                      <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                          <span className="text-xs font-medium text-emerald-700">Area drawn!</span>
                          <button
                            onClick={onClearDrawnPolygon}
                            className="ml-auto p-1 hover:bg-emerald-100 rounded"
                          >
                            <X className="h-3 w-3 text-emerald-600" />
                          </button>
                        </div>
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
                        <p className="text-sm text-stone-600 font-medium">Click on the map</p>
                        <p className="text-xs text-stone-400">
                          to select a {searchMode === 'zip' ? 'ZIP code' : 'county'}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Step: Size Filter */}
            {step === 'size' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
                    Filter by Size
                  </p>
                  <button onClick={handleBack} className="text-[10px] text-stone-400 hover:text-stone-600">
                    ← Back
                  </button>
                </div>

                {/* Selected area summary */}
                <div className="p-2 bg-stone-50 rounded-md border border-stone-200 flex items-center gap-2">
                  {searchMode === 'draw' && <Hexagon className="h-4 w-4 text-stone-500" />}
                  {searchMode === 'zip' && <Hash className="h-4 w-4 text-stone-500" />}
                  {searchMode === 'county' && <Map className="h-4 w-4 text-stone-500" />}
                  <span className="text-xs font-medium text-stone-700">
                    {searchMode === 'draw' && 'Drawn Area'}
                    {searchMode === 'zip' && `ZIP: ${selectedBoundary?.name || ''}`}
                    {searchMode === 'county' && (selectedBoundary?.name || 'County')}
                  </span>
                </div>

                {/* Size presets */}
                <div className="space-y-2">
                  <p className="text-[10px] text-stone-500 uppercase tracking-wider">
                    Parcel Size (acres)
                  </p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {SIZE_PRESETS.map((preset, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          setSizePreset(idx)
                          setUseCustomSize(false)
                        }}
                        className={cn(
                          "px-2 py-2 rounded-md text-xs font-medium border transition-colors",
                          !useCustomSize && sizePreset === idx
                            ? "bg-stone-800 text-white border-stone-800"
                            : "bg-white text-stone-600 border-stone-200 hover:bg-stone-50"
                        )}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                  
                  {/* Custom range */}
                  <div className="pt-2 border-t border-stone-100">
                    <button
                      onClick={() => setUseCustomSize(!useCustomSize)}
                      className="flex items-center gap-1.5 text-[10px] font-medium text-stone-500 hover:text-stone-700 mb-2"
                    >
                      <Filter className="h-3 w-3" />
                      Custom range
                      {useCustomSize ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </button>
                    
                    {useCustomSize && (
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          value={customMinAcres}
                          onChange={(e) => setCustomMinAcres(e.target.value)}
                          placeholder="Min"
                          className="w-20 px-2 py-1.5 bg-stone-50 border border-stone-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-stone-400"
                        />
                        <span className="text-[10px] text-stone-400">to</span>
                        <input
                          type="number"
                          value={customMaxAcres}
                          onChange={(e) => setCustomMaxAcres(e.target.value)}
                          placeholder="Max"
                          className="w-20 px-2 py-1.5 bg-stone-50 border border-stone-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-stone-400"
                        />
                        <span className="text-[10px] text-stone-400">ac</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Find parcels button */}
                <button
                  onClick={handleSizeComplete}
                  className="w-full py-2.5 bg-emerald-600 text-white rounded-md text-sm font-medium hover:bg-emerald-700 transition-colors flex items-center justify-center gap-2"
                >
                  <Search className="h-4 w-4" />
                  Find Parcels
                </button>
              </div>
            )}

            {/* Step: Select Parcels */}
            {step === 'select' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wider">
                    Select Parcels
                  </p>
                  <button onClick={handleBack} className="text-[10px] text-stone-400 hover:text-stone-600">
                    ← Back
                  </button>
                </div>

                {/* Filter summary */}
                <div className="p-2 bg-stone-50 rounded-md border border-stone-200 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Ruler className="h-3.5 w-3.5 text-stone-400" />
                    <span className="text-xs text-stone-600">
                      {sizeFilter.minAcres !== undefined && sizeFilter.maxAcres !== undefined
                        ? `${sizeFilter.minAcres} - ${sizeFilter.maxAcres} acres`
                        : sizeFilter.minAcres !== undefined
                        ? `${sizeFilter.minAcres}+ acres`
                        : sizeFilter.maxAcres !== undefined
                        ? `< ${sizeFilter.maxAcres} acres`
                        : 'Any size'}
                    </span>
                  </div>
                  <button
                    onClick={() => setStep('size')}
                    className="text-[10px] text-stone-400 hover:text-stone-600"
                  >
                    Change
                  </button>
                </div>

                {/* Loading state */}
                {isLoadingParcels && (
                  <div className="py-8 flex flex-col items-center gap-2">
                    <Loader2 className="h-8 w-8 text-stone-400 animate-spin" />
                    <p className="text-xs text-stone-500">Loading parcels from map...</p>
                  </div>
                )}

                {/* Parcels list */}
                {!isLoadingParcels && filteredParcels.length > 0 && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-stone-600">
                        {filteredParcels.length} parcel{filteredParcels.length !== 1 ? 's' : ''} found
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={onSelectAll}
                          className="text-[10px] text-emerald-600 hover:text-emerald-700"
                        >
                          Select All
                        </button>
                        <span className="text-stone-300">|</span>
                        <button
                          onClick={onDeselectAll}
                          className="text-[10px] text-stone-400 hover:text-stone-600"
                        >
                          Clear
                        </button>
                      </div>
                    </div>

                    <div className="max-h-48 overflow-y-auto space-y-1 border border-stone-100 rounded-md p-1">
                      {filteredParcels.map((parcel) => {
                        const isSelected = selectedParcels.some(p => p.id === parcel.id)
                        return (
                          <button
                            key={parcel.id}
                            onClick={() => onParcelSelect(parcel, !isSelected)}
                            className={cn(
                              "w-full p-2 rounded-md text-left transition-colors flex items-start gap-2",
                              isSelected
                                ? "bg-emerald-50 border border-emerald-200"
                                : "bg-white border border-stone-100 hover:bg-stone-50"
                            )}
                          >
                            {isSelected ? (
                              <SquareCheck className="h-4 w-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                            ) : (
                              <Square className="h-4 w-4 text-stone-300 flex-shrink-0 mt-0.5" />
                            )}
                            <div className="min-w-0 flex-1">
                              <p className="text-xs font-medium text-stone-700 truncate">
                                {parcel.address}
                              </p>
                              <p className="text-[10px] text-stone-400">
                                {parcel.acreage.toFixed(2)} acres • APN: {parcel.apn || 'N/A'}
                              </p>
                            </div>
                          </button>
                        )
                      })}
                    </div>

                    {/* Selection summary & process button */}
                    <div className="pt-2 border-t border-stone-100 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-stone-600">
                          {selectedParcels.length} selected
                        </span>
                      </div>
                      <button
                        onClick={handleProcess}
                        disabled={selectedParcels.length === 0}
                        className={cn(
                          "w-full py-2.5 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors",
                          selectedParcels.length > 0
                            ? "bg-emerald-600 text-white hover:bg-emerald-700"
                            : "bg-stone-200 text-stone-400 cursor-not-allowed"
                        )}
                      >
                        <ArrowRight className="h-4 w-4" />
                        Process Selected ({selectedParcels.length})
                      </button>
                    </div>
                  </>
                )}

                {/* No parcels found */}
                {!isLoadingParcels && filteredParcels.length === 0 && loadedParcels.length > 0 && (
                  <div className="py-6 text-center">
                    <ListFilter className="h-8 w-8 text-stone-300 mx-auto mb-2" />
                    <p className="text-xs text-stone-500">
                      No parcels match your size filter
                    </p>
                    <button
                      onClick={() => setStep('size')}
                      className="mt-2 text-xs text-emerald-600 hover:text-emerald-700"
                    >
                      Adjust filter
                    </button>
                  </div>
                )}

                {/* No parcels at all */}
                {!isLoadingParcels && loadedParcels.length === 0 && (
                  <div className="py-6 text-center">
                    <MapPin className="h-8 w-8 text-stone-300 mx-auto mb-2" />
                    <p className="text-xs text-stone-500">
                      No parcels found in this area
                    </p>
                    <p className="text-[10px] text-stone-400 mt-1">
                      Try zooming in or selecting a different area
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Clear button - always visible when not on first step */}
            {step !== 'urban' && (
              <div className="pt-3 mt-3 border-t border-stone-100">
                <button
                  onClick={handleClear}
                  className="w-full py-2 text-xs text-stone-400 hover:text-stone-600 transition-colors"
                >
                  Clear & Start Over
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
      <span className={cn("text-[9px]", active ? "text-stone-300" : "text-stone-400")}>
        {description}
      </span>
    </button>
  )
}

export default DiscoveryPanel
