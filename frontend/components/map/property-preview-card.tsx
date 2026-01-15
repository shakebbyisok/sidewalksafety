'use client'

import { useState } from 'react'
import { 
  X, 
  Loader2, 
  User,
  Camera,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  RotateCcw,
  Crosshair,
  Layers
} from 'lucide-react'
import { parkingLotsApi, RegridLookupResponse, PropertyPreviewResponse } from '@/lib/api/parking-lots'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'

interface PropertyPreviewCardProps {
  lat: number
  lng: number
  onClose: () => void
  onPolygonReady?: (polygon: any) => void
  onDiscoverArea?: () => void
}

type Phase = 'choice' | 'loading_regrid' | 'regrid_ready' | 'capturing' | 'complete' | 'error' | 'no_parcel'

export function PropertyPreviewCard({ lat, lng, onClose, onPolygonReady, onDiscoverArea }: PropertyPreviewCardProps) {
  const router = useRouter()
  const queryClient = useQueryClient()
  
  const [phase, setPhase] = useState<Phase>('choice')
  const [regridData, setRegridData] = useState<RegridLookupResponse | null>(null)
  const [captureData, setCaptureData] = useState<PropertyPreviewResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showImage, setShowImage] = useState(false)

  const handleAnalyzeProperty = async () => {
    setPhase('loading_regrid')
    setError(null)
    
    try {
      const data = await parkingLotsApi.regridLookup(lat, lng)
      setRegridData(data)
      
      if (data.has_parcel && data.polygon_geojson) {
        onPolygonReady?.(data.polygon_geojson)
        setPhase('regrid_ready')
      } else {
        setPhase('no_parcel')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Lookup failed')
      setPhase('error')
    }
  }

  const handleCapture = async () => {
    setPhase('capturing')
    setError(null)
    
    try {
      const data = await parkingLotsApi.captureProperty({ 
        lat, lng, 
        address: regridData?.parcel?.address,
        zoom: 20 
      })
      setCaptureData(data)
      setPhase('complete')
      queryClient.invalidateQueries({ queryKey: ['deals'] })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Capture failed')
      setPhase('error')
    }
  }

  const handleViewDetails = () => {
    if (captureData?.property_id) {
      router.push(`/parking-lots/${captureData.property_id}`)
    }
  }

  const handleRetry = () => {
    setPhase('choice')
    setError(null)
    setRegridData(null)
    setCaptureData(null)
  }

  const fmt = (n: number | undefined | null, decimals = 0) => 
    n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: decimals })

  return (
    <div className="bg-stone-50 text-stone-800 rounded-lg shadow-lg border border-stone-200 overflow-hidden w-72 text-sm">
      {/* Header */}
      <div className="px-3 py-2 border-b border-stone-200 flex items-center justify-between bg-stone-100/80">
        <div className="flex items-center gap-2">
          <Crosshair className="h-3.5 w-3.5 text-stone-500" />
          <span className="font-mono text-xs text-stone-500">
            {lat.toFixed(5)}, {lng.toFixed(5)}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-stone-200 transition-colors text-stone-400 hover:text-stone-600"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Content */}
      <div className="p-3">
        
        {/* ===== CHOICE ===== */}
        {phase === 'choice' && (
          <div className="space-y-2">
            <button
              onClick={handleAnalyzeProperty}
              className="w-full flex items-center gap-2 px-3 py-2 bg-stone-800 hover:bg-stone-700 text-white rounded text-xs font-medium transition-colors"
            >
              <Crosshair className="h-3.5 w-3.5" />
              Analyze Property
            </button>
            {onDiscoverArea && (
              <button
                onClick={onDiscoverArea}
                className="w-full flex items-center gap-2 px-3 py-2 bg-stone-200 hover:bg-stone-300 text-stone-700 rounded text-xs font-medium transition-colors"
              >
                <Layers className="h-3.5 w-3.5" />
                Discover Area
              </button>
            )}
          </div>
        )}

        {/* ===== LOADING ===== */}
        {phase === 'loading_regrid' && (
          <div className="flex items-center gap-2 py-2">
            <Loader2 className="h-4 w-4 animate-spin text-stone-500" />
            <span className="text-xs text-stone-500">Looking up parcel...</span>
          </div>
        )}

        {/* ===== NO PARCEL ===== */}
        {phase === 'no_parcel' && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-amber-600">
              <AlertCircle className="h-4 w-4" />
              <span className="text-xs">No parcel data found</span>
            </div>
            <button
              onClick={handleRetry}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 bg-stone-200 hover:bg-stone-300 rounded text-xs transition-colors text-stone-600"
            >
              <RotateCcw className="h-3 w-3" />
              Retry
            </button>
          </div>
        )}

        {/* ===== REGRID READY ===== */}
        {phase === 'regrid_ready' && regridData?.parcel && (
          <div className="space-y-3">
            {/* Parcel Info */}
            <div className="space-y-1">
              <div className="font-medium text-stone-900 truncate text-[13px]">
                {regridData.parcel.address || 'Unknown'}
              </div>
              {regridData.parcel.owner && (
                <div className="flex items-center gap-1.5 text-xs text-stone-500">
                  <User className="h-3 w-3" />
                  <span className="truncate">{regridData.parcel.owner}</span>
                </div>
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-stone-100 rounded px-2 py-1.5">
                <div className="text-stone-400 text-[10px] uppercase tracking-wide">Area</div>
                <div className="font-mono font-medium text-stone-700">{fmt(regridData.parcel.area_acres, 2)} ac</div>
              </div>
              <div className="bg-stone-100 rounded px-2 py-1.5">
                <div className="text-stone-400 text-[10px] uppercase tracking-wide">Use</div>
                <div className="font-medium truncate text-stone-700">{regridData.parcel.land_use || '—'}</div>
              </div>
            </div>

            {/* Capture */}
            <button
              onClick={handleCapture}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition-colors"
            >
              <Camera className="h-3.5 w-3.5" />
              Capture Imagery
            </button>
            <div className="text-[10px] text-stone-400 text-center">
              {(regridData.parcel.area_acres || 0) > 10 ? '~60-120s for large parcels' : '~10-30s'}
            </div>
          </div>
        )}

        {/* ===== CAPTURING ===== */}
        {phase === 'capturing' && (
          <div className="flex items-center gap-2 py-2">
            <Loader2 className="h-4 w-4 animate-spin text-emerald-600" />
            <span className="text-xs text-stone-500">Capturing satellite imagery...</span>
          </div>
        )}

        {/* ===== COMPLETE ===== */}
        {phase === 'complete' && captureData && (
          <div className="space-y-3">
            {/* Success */}
            <div className="flex items-center gap-1.5 text-emerald-600 text-xs">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Property saved</span>
            </div>

            {/* Image */}
            {captureData.image_base64 && (
              <div 
                onClick={() => setShowImage(!showImage)}
                className="relative rounded overflow-hidden cursor-pointer border border-stone-200"
              >
                <img 
                  src={`data:image/jpeg;base64,${captureData.image_base64}`}
                  alt="Satellite"
                  className={`w-full ${showImage ? 'h-auto' : 'h-24 object-cover'}`}
                />
                {!showImage && (
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-stone-900/80 to-transparent px-2 py-1">
                    <span className="text-[10px] text-white/80">
                      {captureData.image_size.width}×{captureData.image_size.height}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-stone-100 rounded px-2 py-1.5">
                <div className="text-stone-400 text-[10px] uppercase tracking-wide">Area</div>
                <div className="font-mono text-stone-700">{fmt(captureData.area_sqft)} ft²</div>
              </div>
              <div className="bg-stone-100 rounded px-2 py-1.5">
                <div className="text-stone-400 text-[10px] uppercase tracking-wide">Owner</div>
                <div className="truncate text-stone-700">{captureData.regrid?.owner?.split(' ')[0] || '—'}</div>
              </div>
            </div>

            {/* View Details */}
            <button
              onClick={handleViewDetails}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-stone-800 hover:bg-stone-700 text-white rounded text-xs font-medium transition-colors"
            >
              View Details
              <ArrowRight className="h-3 w-3" />
            </button>
          </div>
        )}

        {/* ===== ERROR ===== */}
        {phase === 'error' && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-red-600 text-xs">
              <AlertCircle className="h-4 w-4" />
              <span>{error}</span>
            </div>
            <button
              onClick={handleRetry}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 bg-stone-200 hover:bg-stone-300 rounded text-xs transition-colors text-stone-600"
            >
              <RotateCcw className="h-3 w-3" />
              Retry
            </button>
          </div>
        )}

      </div>
    </div>
  )
}
