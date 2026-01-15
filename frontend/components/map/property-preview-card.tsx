'use client'

import { useState, useRef, useEffect } from 'react'
import { 
  X, 
  Loader2, 
  User,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  RotateCcw,
  Crosshair,
  Layers,
  Play,
  Building2,
  Phone,
  Mail,
  TrendingUp,
  Radio,
} from 'lucide-react'
import { parkingLotsApi, RegridLookupResponse } from '@/lib/api/parking-lots'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { useProcessParcelStream, ProcessParcelProgress } from '@/lib/hooks/use-process-parcel-stream'
import { cn } from '@/lib/utils'

interface PropertyPreviewCardProps {
  lat: number
  lng: number
  onClose: () => void
  onPolygonReady?: (polygon: any) => void
  onDiscoverArea?: () => void
}

type Phase = 'choice' | 'loading_regrid' | 'regrid_ready' | 'processing' | 'complete' | 'error' | 'no_parcel'

export function PropertyPreviewCard({ lat, lng, onClose, onPolygonReady, onDiscoverArea }: PropertyPreviewCardProps) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const streamLogRef = useRef<HTMLDivElement>(null)
  
  const [phase, setPhase] = useState<Phase>('choice')
  const [regridData, setRegridData] = useState<RegridLookupResponse | null>(null)
  const [propertyId, setPropertyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [finalStats, setFinalStats] = useState<ProcessParcelProgress['stats'] | null>(null)
  const [contactInfo, setContactInfo] = useState<{ phone?: string; email?: string; company?: string } | null>(null)

  const { 
    startProcessing, 
    stopProcessing, 
    isProcessing, 
    progress, 
    currentMessage,
    clearProgress 
  } = useProcessParcelStream()

  // Auto-scroll stream log
  useEffect(() => {
    if (streamLogRef.current && progress.length > 0) {
      streamLogRef.current.scrollTop = streamLogRef.current.scrollHeight
    }
  }, [progress])

  // Handle completion from stream
  useEffect(() => {
    if (currentMessage?.type === 'complete') {
      setPhase('complete')
      setFinalStats(currentMessage.stats || null)
    } else if (currentMessage?.type === 'contact_found') {
      setContactInfo({
        phone: currentMessage.phone,
        email: currentMessage.email,
        company: currentMessage.company,
      })
    } else if (currentMessage?.type === 'error') {
      setPhase('error')
      setError(currentMessage.message)
    }
  }, [currentMessage])

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

  const handleProcessParcel = async () => {
    setPhase('processing')
    setError(null)
    clearProgress()
    setFinalStats(null)
    setContactInfo(null)
    
    try {
      // First capture the property to get a property_id
      const captureData = await parkingLotsApi.captureProperty({ 
        lat, lng, 
        address: regridData?.parcel?.address,
        zoom: 20 
      })
      
      if (!captureData?.property_id) {
        throw new Error('Failed to create property')
      }
      
      setPropertyId(captureData.property_id)
      queryClient.invalidateQueries({ queryKey: ['deals'] })
      
      // Now start the streaming process
      await startProcessing({
        propertyId: captureData.property_id,
      })
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Processing failed')
      setPhase('error')
    }
  }

  const handleViewDetails = () => {
    if (propertyId) {
      router.push(`/parking-lots/${propertyId}`)
    }
  }

  const handleRetry = () => {
    setPhase('choice')
    setError(null)
    setRegridData(null)
    setPropertyId(null)
    setFinalStats(null)
    setContactInfo(null)
    clearProgress()
  }

  const fmt = (n: number | undefined | null, decimals = 0) => 
    n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: decimals })

  // Render a single progress item - matches discovery card style exactly
  const renderProgressItem = (msg: ProcessParcelProgress, idx: number) => {
    const isLatest = idx === progress.length - 1
    const isComplete = msg.type === 'complete'
    const isError = msg.type === 'error' || msg.type.endsWith('_error')
    const isContactFound = msg.type === 'contact_found'
    
    // Get status indicator - same as discovery
    const getStatusDot = () => {
      if (isComplete) return <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" />
      if (isError) return <X className="h-3 w-3 text-red-500 shrink-0" />
      if (isContactFound) return <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
      if (isLatest && isProcessing) return <Loader2 className="h-3 w-3 animate-spin text-amber-500 shrink-0" />
      return <span className="w-3 h-3 flex items-center justify-center text-stone-300 shrink-0">•</span>
    }
    
    return (
      <div 
        key={idx}
        className={cn(
          'flex items-start gap-2 px-2 py-1 rounded text-[11px]',
          isComplete ? 'bg-emerald-50' :
          isError ? 'bg-red-50' :
          isContactFound ? 'bg-green-50' :
          isLatest && isProcessing ? 'bg-amber-50' :
          'bg-transparent'
        )}
      >
        <span className="mt-0.5">{getStatusDot()}</span>
        <div className="flex-1 min-w-0">
          <span className={cn(
            'block leading-tight',
            isComplete ? 'text-emerald-700 font-medium' :
            isError ? 'text-red-600' :
            isContactFound ? 'text-green-700' :
            isLatest && isProcessing ? 'text-stone-800' : 'text-stone-500'
          )}>
            {msg.message}
          </span>
          {msg.details && (
            <span className="block text-[10px] text-stone-400">{msg.details}</span>
          )}
          {isContactFound && (msg.phone || msg.email) && (
            <div className="flex flex-wrap gap-2 mt-0.5">
              {msg.phone && (
                <span className="inline-flex items-center gap-1 text-[10px] text-green-600">
                  <Phone className="h-2.5 w-2.5" />
                  {msg.phone}
                </span>
              )}
              {msg.email && (
                <span className="inline-flex items-center gap-1 text-[10px] text-green-600">
                  <Mail className="h-2.5 w-2.5" />
                  {msg.email}
                </span>
              )}
            </div>
          )}
          {isComplete && msg.stats && (
            <div className="flex flex-wrap gap-2 mt-1 text-[10px]">
              {msg.stats.lead_score != null && (
                <>
                  <span className="text-amber-600 font-medium">Score: {msg.stats.lead_score}/100</span>
                  <span className="text-stone-400">•</span>
                </>
              )}
              <span className={msg.stats.has_contact ? 'text-emerald-600 font-medium' : 'text-stone-400'}>
                {msg.stats.has_contact ? 'Contact found' : 'No contact'}
              </span>
              {msg.stats.duration && (
                <>
                  <span className="text-stone-400">•</span>
                  <span className="text-stone-500">{msg.stats.duration}</span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-stone-50 text-stone-800 rounded-lg shadow-lg border border-stone-200 overflow-hidden w-80 text-sm">
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

            {/* Process Parcel Button */}
            <button
              onClick={handleProcessParcel}
              className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition-colors"
            >
              <Play className="h-3.5 w-3.5" />
              Process Parcel
            </button>
            <div className="text-[10px] text-stone-400 text-center">
              Full analysis: imagery, VLM scoring, contact enrichment
            </div>
          </div>
        )}

        {/* ===== PROCESSING (Streaming) - Same style as discovery card ===== */}
        {phase === 'processing' && (
          <div className="space-y-2">
            {/* Header with live indicator - same as discovery */}
            <div className="flex items-center justify-between px-2 py-1.5 bg-stone-100 border border-stone-200 rounded">
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Radio className="h-3.5 w-3.5 text-amber-600" />
                  <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 bg-amber-500 rounded-full animate-pulse" />
                </div>
                <span className="text-[11px] font-medium text-stone-700">Processing parcel</span>
              </div>
            </div>

            {/* Progress messages - fixed height scrollable - same as discovery */}
            <div 
              ref={streamLogRef}
              className="h-44 overflow-y-auto border border-stone-200 rounded bg-white"
            >
              {progress.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="h-5 w-5 animate-spin text-amber-500" />
                    <span className="text-xs text-stone-500">Starting...</span>
                  </div>
                </div>
              ) : (
                <div className="p-1.5 space-y-1">
                  {progress.map((msg, idx) => renderProgressItem(msg, idx))}
                </div>
              )}
            </div>

            {/* Cancel button when processing */}
            {isProcessing && (
              <button
                onClick={stopProcessing}
                className="w-full px-3 py-1.5 bg-stone-200 text-stone-600 rounded text-xs font-medium hover:bg-stone-300 transition-colors"
              >
                Cancel
              </button>
            )}

            {/* View Details when complete */}
            {!isProcessing && progress.some(m => m.type === 'complete') && (
              <button
                onClick={handleViewDetails}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-stone-800 hover:bg-stone-700 text-white rounded text-xs font-medium transition-colors"
              >
                View Details
                <ArrowRight className="h-3 w-3" />
              </button>
            )}
          </div>
        )}

        {/* ===== COMPLETE ===== */}
        {phase === 'complete' && (
          <div className="space-y-3">
            {/* Success Header */}
            <div className="flex items-center gap-1.5 text-emerald-600 text-xs">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Processing complete</span>
            </div>

            {/* Results Summary */}
            <div className="space-y-2">
              {/* Lead Score */}
              {finalStats?.lead_score != null && (
                <div className="bg-stone-100 rounded-lg p-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-amber-500" />
                    <span className="text-xs text-stone-600">Lead Score</span>
                  </div>
                  <span className={cn(
                    'text-lg font-bold font-mono',
                    finalStats.lead_score >= 70 ? 'text-emerald-600' :
                    finalStats.lead_score >= 40 ? 'text-amber-600' : 'text-stone-500'
                  )}>
                    {finalStats.lead_score}
                  </span>
                </div>
              )}

              {/* Contact Info */}
              {contactInfo && (contactInfo.phone || contactInfo.email) ? (
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-2.5 space-y-1.5">
                  {contactInfo.company && (
                    <div className="flex items-center gap-2 text-xs">
                      <Building2 className="h-3.5 w-3.5 text-emerald-600" />
                      <span className="text-stone-700 truncate">{contactInfo.company}</span>
                    </div>
                  )}
                  {contactInfo.phone && (
                    <div className="flex items-center gap-2 text-xs">
                      <Phone className="h-3.5 w-3.5 text-emerald-600" />
                      <span className="font-mono text-stone-700">{contactInfo.phone}</span>
                    </div>
                  )}
                  {contactInfo.email && (
                    <div className="flex items-center gap-2 text-xs">
                      <Mail className="h-3.5 w-3.5 text-emerald-600" />
                      <span className="text-stone-700 truncate">{contactInfo.email}</span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-stone-100 rounded-lg p-2.5 text-xs text-stone-500 text-center">
                  No contact information found
                </div>
              )}

              {/* Duration & Cost */}
              {(finalStats?.duration || finalStats?.cost) && (
                <div className="flex items-center justify-center gap-3 text-[10px] text-stone-400">
                  {finalStats.duration && <span>{finalStats.duration}</span>}
                  {finalStats.cost && <span>{finalStats.cost}</span>}
                </div>
              )}
            </div>

            {/* View Details Button */}
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
