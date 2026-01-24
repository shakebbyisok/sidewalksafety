'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { boundariesApi, BoundaryLayer, BoundaryLayerResponse } from '@/lib/api/boundaries'
import { ViewportBounds } from '@/lib/api/search'
import { Layers, Map, Building, Hash, Loader2, ChevronDown, X, Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BoundaryLayerSelectorProps {
  viewport: ViewportBounds | null
  onLayerData: (data: BoundaryLayerResponse | null, layerId: string | null) => void
}

const LAYER_ICONS: Record<string, React.ReactNode> = {
  states: <Map className="h-3.5 w-3.5" />,
  counties: <Building className="h-3.5 w-3.5" />,
  zips: <Hash className="h-3.5 w-3.5" />,
  urban_areas: <Layers className="h-3.5 w-3.5" />,
}

const LAYER_COLORS: Record<string, { stroke: string; fill: string }> = {
  states: { stroke: '#6366f1', fill: 'rgba(99, 102, 241, 0.08)' },
  counties: { stroke: '#f59e0b', fill: 'rgba(245, 158, 11, 0.08)' },
  zips: { stroke: '#10b981', fill: 'rgba(16, 185, 129, 0.05)' },
  urban_areas: { stroke: '#ef4444', fill: 'rgba(239, 68, 68, 0.08)' },
}

// Debounce viewport changes to prevent excessive refetching
function useStableViewport(viewport: ViewportBounds | null, delay: number = 1000) {
  const [stableViewport, setStableViewport] = useState(viewport)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    
    timeoutRef.current = setTimeout(() => {
      setStableViewport(viewport)
    }, delay)

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [viewport, delay])

  return stableViewport
}

export function BoundaryLayerSelector({ viewport, onLayerData }: BoundaryLayerSelectorProps) {
  const [selectedLayer, setSelectedLayer] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [isVisible, setIsVisible] = useState(true)
  
  // Use stable viewport to prevent excessive refetching
  const stableViewport = useStableViewport(viewport, 1500)

  // Fetch available layers
  const { data: layers, isLoading: isLoadingLayers } = useQuery({
    queryKey: ['boundary-layers'],
    queryFn: boundariesApi.getLayers,
    staleTime: 60000,
  })

  // All layers load ALL features now
  const queryEnabled = !!selectedLayer
  
  const { data: layerData, isLoading: isLoadingData, isFetching } = useQuery({
    queryKey: ['boundary-layer-all', selectedLayer],
    queryFn: async () => {
      if (!selectedLayer) return null
      // Load ALL features for any layer
      return boundariesApi.getLayer(selectedLayer, undefined, 50000) // High limit for ZIPs
    },
    enabled: queryEnabled,
    staleTime: 600000,  // Keep data fresh for 10 minutes
    gcTime: 1800000,    // Keep in cache for 30 minutes
  })

  // Track what we last sent to parent to prevent duplicate calls
  const lastSentRef = useRef<{ layerId: string | null; featureCount: number }>({ layerId: null, featureCount: 0 })
  
  // Update parent when layer data changes
  useEffect(() => {
    const newLayerId = isVisible && layerData && layerData.features.length > 0 ? selectedLayer : null
    const newFeatureCount = layerData?.features?.length ?? 0
    
    // Skip if we'd send the same data
    if (lastSentRef.current.layerId === newLayerId && 
        lastSentRef.current.featureCount === newFeatureCount) {
      return
    }
    
    lastSentRef.current = { layerId: newLayerId, featureCount: newFeatureCount }
    
    if (newLayerId && layerData) {
      onLayerData(layerData, newLayerId)
    } else {
      onLayerData(null, null)
    }
  }, [layerData, selectedLayer, isVisible, onLayerData])

  const handleLayerSelect = (layerId: string) => {
    if (selectedLayer === layerId) {
      setSelectedLayer(null)
      setIsExpanded(false)
    } else {
      setSelectedLayer(layerId)
      setIsVisible(true)
    }
  }

  const handleClear = useCallback(() => {
    setSelectedLayer(null)
    setIsExpanded(false)
    onLayerData(null, null)
  }, [onLayerData])

  const handleToggleVisibility = useCallback(() => {
    setIsVisible(v => !v)
  }, [])

  const availableLayers = layers?.filter(l => l.available) || []
  const selectedLayerInfo = layers?.find(l => l.id === selectedLayer)

  return (
    <div className="absolute bottom-4 right-4 z-20">
      <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-lg border border-stone-200 overflow-hidden">
        {/* Header - clickable div instead of button to avoid nesting issues */}
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          {/* Left side - clickable to expand */}
          <div 
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity flex-1"
          >
            <Layers className="h-4 w-4 text-stone-500" />
            <span className="text-xs font-medium text-stone-700">
              {selectedLayer ? selectedLayerInfo?.name || selectedLayer : 'Boundary Layers'}
            </span>
            {(isLoadingData || isFetching) && (
              <Loader2 className="h-3 w-3 text-stone-400 animate-spin" />
            )}
          </div>
          
          {/* Right side - action buttons */}
          <div className="flex items-center gap-1">
            {selectedLayer && (
              <>
                <button
                  onClick={handleToggleVisibility}
                  className="p-1 rounded hover:bg-stone-200 transition-colors"
                  title={isVisible ? 'Hide layer' : 'Show layer'}
                >
                  {isVisible ? (
                    <Eye className="h-3.5 w-3.5 text-stone-500" />
                  ) : (
                    <EyeOff className="h-3.5 w-3.5 text-stone-400" />
                  )}
                </button>
                <button
                  onClick={handleClear}
                  className="p-1 rounded hover:bg-stone-200 transition-colors"
                  title="Clear layer"
                >
                  <X className="h-3.5 w-3.5 text-stone-400" />
                </button>
              </>
            )}
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-1 rounded hover:bg-stone-200 transition-colors"
            >
              <ChevronDown className={cn(
                'h-4 w-4 text-stone-400 transition-transform',
                isExpanded && 'rotate-180'
              )} />
            </button>
          </div>
        </div>

        {/* Expanded layer list */}
        {isExpanded && (
          <div className="border-t border-stone-200 p-2 space-y-1">
            {isLoadingLayers ? (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 text-stone-400 animate-spin" />
              </div>
            ) : (
              availableLayers.map(layer => {
                const colors = LAYER_COLORS[layer.id]
                const isSelected = selectedLayer === layer.id
                
                return (
                  <button
                    key={layer.id}
                    onClick={() => handleLayerSelect(layer.id)}
                    className={cn(
                      'w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition-all',
                      isSelected
                        ? 'bg-stone-100 ring-1 ring-stone-300'
                        : 'hover:bg-stone-50'
                    )}
                  >
                    <div 
                      className="w-4 h-4 rounded border-2 flex items-center justify-center"
                      style={{ 
                        borderColor: colors?.stroke || '#6b7280',
                        backgroundColor: isSelected ? colors?.fill : 'transparent'
                      }}
                    >
                      {isSelected && (
                        <div 
                          className="w-2 h-2 rounded-sm"
                          style={{ backgroundColor: colors?.stroke }}
                        />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-stone-700">{layer.name}</div>
                      <div className="text-[10px] text-stone-400">
                        {layer.size_mb.toFixed(1)} MB
                        {layer.loaded && ' • Cached'}
                      </div>
                    </div>
                  </button>
                )
              })
            )}
            
            {/* Info text */}
            {selectedLayer && (
              <p className="text-[10px] text-stone-400 px-2 pt-1 border-t border-stone-100">
                {selectedLayer === 'zips' 
                  ? '⚠️ Loading 33k+ ZIP codes (may take 30-60s)'
                  : selectedLayer === 'states'
                  ? 'All 56 US states & territories'
                  : selectedLayer === 'counties'
                  ? 'All ~3,200 US counties'
                  : 'All ~3,500 US urban areas'}
              </p>
            )}
          </div>
        )}

        {/* Stats when layer is selected and collapsed */}
        {selectedLayer && !isExpanded && layerData && (
          <div className="border-t border-stone-200 px-3 py-1.5">
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-stone-500">
                {layerData.returned || layerData.features.length} boundaries
              </span>
              {layerData.truncated && (
                <span className="text-amber-600">Zoom in for more</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export { LAYER_COLORS }
