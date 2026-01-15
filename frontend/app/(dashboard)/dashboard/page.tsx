'use client'

import { useState, useCallback, useRef, useMemo, useEffect } from 'react'
import { useDeals, useDealsForMap, useScrapeDeals, MapBounds } from '@/lib/queries/use-deals'
import { InteractiveMap } from '@/components/map/interactive-map'
import { DiscoveryCard } from '@/components/map/discovery-card'
import { PropertyPreviewCard } from '@/components/map/property-preview-card'
import { useDiscoveryStream } from '@/lib/hooks/use-discovery-stream'

type ClickMode = 'property' | 'discovery'
import { DealMapResponse, DiscoveryMode, PropertyCategory } from '@/types'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { 
  ChevronLeft,
  ChevronRight,
  MapPin,
  Clock,
  CheckCircle2,
  Building2,
  ExternalLink,
  Target,
  Layers,
  Square,
  User,
  Hash,
  ArrowRight,
  Gauge,
} from 'lucide-react'

type ScoreFilter = 'all' | 'lead' | 'critical' | 'poor' | 'fair' | 'good'

// Debounce delay for bounds changes (ms)
const BOUNDS_DEBOUNCE_MS = 500

export default function DashboardPage() {
  const router = useRouter()
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [scoreFilter, setScoreFilter] = useState<ScoreFilter>('all')
  const [selectedDeal, setSelectedDeal] = useState<DealMapResponse | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [clickedLocation, setClickedLocation] = useState<{ lat: number; lng: number } | null>(null)
  const [previewPolygon, setPreviewPolygon] = useState<any>(null)
  const [clickMode, setClickMode] = useState<ClickMode>('property')
  
  const [mapBounds, setMapBounds] = useState<MapBounds | undefined>(undefined)
  const boundsTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const hasMapLoadedOnce = useRef(false)
  const scrapeDeals = useScrapeDeals()
  
  // Streaming discovery hook
  const discoveryStream = useDiscoveryStream()

  const { data: dealsData, isLoading } = useDeals(statusFilter)
  const allDeals = useMemo(() => {
    return Array.isArray(dealsData) ? dealsData : []
  }, [dealsData])
  
  const deals = useMemo(() => {
    let filtered = allDeals
    if (scoreFilter === 'all') return filtered
    
    return filtered.filter(d => {
      if (d.score === null || d.score === undefined) return false
      switch (scoreFilter) {
        case 'lead': return d.score < 50
        case 'critical': return d.score <= 30
        case 'poor': return d.score > 30 && d.score <= 50
        case 'fair': return d.score > 50 && d.score <= 70
        case 'good': return d.score > 70
        default: return true
      }
    })
  }, [allDeals, scoreFilter])
  
  const { data: mapDealsData, isLoading: isLoadingMap } = useDealsForMap({ 
    status: statusFilter,
    ...mapBounds,
  })
  const mapDeals = Array.isArray(mapDealsData) ? mapDealsData : []
  
  if (mapDealsData && !hasMapLoadedOnce.current) hasMapLoadedOnce.current = true
  const showMapLoading = isLoadingMap && !hasMapLoadedOnce.current

  const handleViewDetails = (dealId: string) => router.push(`/parking-lots/${dealId}`)
  
  const handleMapClick = useCallback((lat: number, lng: number) => {
    setSelectedDeal(null)
    setClickedLocation({ lat, lng })
    setPreviewPolygon(null)
    setClickMode('property')
  }, [])

  const handlePolygonReady = useCallback((polygon: any) => {
    setPreviewPolygon(polygon)
  }, [])

  const handleBoundsChange = useCallback((bounds: { minLat: number; maxLat: number; minLng: number; maxLng: number }) => {
    if (boundsTimeoutRef.current) {
      clearTimeout(boundsTimeoutRef.current)
    }
    boundsTimeoutRef.current = setTimeout(() => {
      setMapBounds(bounds)
    }, BOUNDS_DEBOUNCE_MS)
  }, [])

  useEffect(() => {
    return () => {
      if (boundsTimeoutRef.current) {
        clearTimeout(boundsTimeoutRef.current)
      }
    }
  }, [])

  const handleDiscover = (params: {
    type: 'zip' | 'county'
    value: string
    state?: string
    businessTypeIds?: string[]
    maxResults?: number
    scoringPrompt?: string
    mode?: DiscoveryMode
    city?: string
    jobTitles?: string[]
    industries?: string[]
    propertyCategories?: PropertyCategory[]
    minAcres?: number
    maxAcres?: number
  }) => {
    // Use streaming for regrid_first mode
    if (params.mode === 'regrid_first') {
      discoveryStream.startStream({
        area_type: params.type,
        value: params.value,
        state: params.state,
        max_results: params.maxResults || (params.type === 'zip' ? 10 : 30),
        business_type_ids: params.businessTypeIds,
        scoring_prompt: params.scoringPrompt,
        mode: params.mode,
        city: params.city,
        job_titles: params.jobTitles,
        industries: params.industries,
        property_categories: params.propertyCategories,
        min_acres: params.minAcres,
        max_acres: params.maxAcres,
      })
    } else {
      // Use regular mutation for other modes
      scrapeDeals.mutate({
        area_type: params.type, 
        value: params.value,
        state: params.state,
        max_results: params.maxResults || (params.type === 'zip' ? 10 : 30),
        business_type_ids: params.businessTypeIds,
        scoring_prompt: params.scoringPrompt,
        mode: params.mode,
        city: params.city,
        job_titles: params.jobTitles,
        industries: params.industries,
        property_categories: params.propertyCategories,
        min_acres: params.minAcres,
        max_acres: params.maxAcres,
      }, { onSuccess: () => setClickedLocation(null) })
    }
  }

  const counts = {
    all: allDeals.length,
    pending: allDeals.filter(d => d.status === 'pending').length,
    analyzed: allDeals.filter(d => d.status === 'evaluated').length,
    leads: allDeals.filter(d => d.score !== null && d.score !== undefined && d.score < 50).length,
  }

  return (
    <div className="h-full flex bg-stone-100">
      {/* Side Panel */}
      <div className={cn(
        'h-full bg-stone-50 border-r border-stone-200 flex flex-col transition-all duration-200',
        panelOpen ? 'w-80' : 'w-0'
      )}>
        {panelOpen && (
          <>
            {/* Panel Header */}
            <div className="flex-shrink-0 px-3 py-3 border-b border-stone-200 bg-white">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded bg-stone-100 flex items-center justify-center">
                    <Layers className="h-3.5 w-3.5 text-stone-500" />
                  </div>
                  <span className="text-sm font-semibold text-stone-800">Parcels</span>
                  <span className="text-xs font-mono text-stone-400">{counts.all}</span>
                </div>
                <button 
                  onClick={() => setPanelOpen(false)}
                  className="p-1 rounded hover:bg-stone-100 transition-colors"
                >
                  <ChevronLeft className="h-4 w-4 text-stone-400" />
                </button>
              </div>

              {/* Filter Chips */}
              <div className="flex gap-1.5">
                <FilterChip 
                  active={!statusFilter} 
                  onClick={() => setStatusFilter(undefined)}
                  count={counts.all}
                >
                  All
                </FilterChip>
                <FilterChip 
                  active={statusFilter === 'pending'} 
                  onClick={() => setStatusFilter('pending')}
                  count={counts.pending}
                >
                  Pending
                </FilterChip>
                <FilterChip 
                  active={statusFilter === 'evaluated'} 
                  onClick={() => setStatusFilter('evaluated')}
                  count={counts.analyzed}
                >
                  Captured
                </FilterChip>
                </div>
                
              {/* Leads Quick Filter */}
                {counts.leads > 0 && (
                  <button
                    onClick={() => setScoreFilter(scoreFilter === 'lead' ? 'all' : 'lead')}
                    className={cn(
                    'mt-2 w-full flex items-center justify-between px-2 py-1.5 rounded text-xs font-medium transition-all',
                      scoreFilter === 'lead'
                      ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300'
                      : 'bg-stone-100 text-stone-500 hover:bg-stone-200 hover:text-stone-700'
                    )}
                  >
                    <span className="flex items-center gap-1.5">
                      <Target className="h-3 w-3" />
                    Leads
                    </span>
                  <span className="font-mono">{counts.leads}</span>
                  </button>
                )}
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="p-3 space-y-2">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="h-20 bg-stone-200/50 rounded-lg animate-pulse" />
                  ))}
                </div>
              ) : deals.length > 0 ? (
                <div className="p-2 space-y-2">
                  {deals.map((deal) => (
                    <ParcelItem
                      key={deal.id}
                      deal={deal}
                      isSelected={selectedDeal?.id === deal.id}
                      onClick={() => { setSelectedDeal(deal as any); setClickedLocation(null) }}
                      onViewDetails={() => handleViewDetails(deal.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                  <div className="w-12 h-12 rounded-xl border-2 border-dashed border-stone-300 flex items-center justify-center mb-3">
                    <MapPin className="h-5 w-5 text-stone-400" strokeWidth={1.5} />
                  </div>
                  <p className="text-sm font-medium text-stone-600">No parcels found</p>
                  <p className="text-xs text-stone-400 mt-1">
                    {scoreFilter !== 'all' ? 'Try adjusting filters' : 'Click on map to analyze'}
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Toggle Button */}
      {!panelOpen && (
        <button
          onClick={() => setPanelOpen(true)}
          className="absolute top-16 left-0 z-20 h-8 px-1 bg-white border border-stone-200 rounded-r-md hover:bg-stone-50 transition-colors shadow-sm"
        >
          <ChevronRight className="h-4 w-4 text-stone-500" />
        </button>
      )}

      {/* Map Area */}
      <div className="flex-1 relative">
        {showMapLoading ? (
          <div className="h-full flex items-center justify-center bg-stone-200/50">
            <div className="flex flex-col items-center gap-2">
              <div className="h-6 w-6 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
              <span className="text-xs text-stone-500">Loading map...</span>
            </div>
          </div>
        ) : (
          <InteractiveMap
            deals={mapDeals}
            selectedDeal={selectedDeal}
            onDealSelect={(deal) => { setSelectedDeal(deal); setClickedLocation(null); setPreviewPolygon(null) }}
            onViewDetails={handleViewDetails}
            onBoundsChange={handleBoundsChange}
            onMapClick={handleMapClick}
            clickedLocation={clickedLocation}
            previewPolygon={previewPolygon}
          />
        )}

        {/* Property Preview or Discovery Card */}
        {clickedLocation && (
          <div className="absolute top-4 right-4 z-30">
            {clickMode === 'property' ? (
              <PropertyPreviewCard
                lat={clickedLocation.lat}
                lng={clickedLocation.lng}
                onClose={() => {
                  setClickedLocation(null)
                  setPreviewPolygon(null)
                  setClickMode('property')
                }}
                onPolygonReady={handlePolygonReady}
                onDiscoverArea={() => setClickMode('discovery')}
              />
            ) : (
            <DiscoveryCard
              lat={clickedLocation.lat}
              lng={clickedLocation.lng}
              onDiscover={handleDiscover}
              onClose={() => {
                setClickedLocation(null)
                setPreviewPolygon(null)
                setClickMode('property')
                discoveryStream.clearProgress()
              }}
              isDiscovering={scrapeDeals.isPending}
              isStreaming={discoveryStream.isStreaming}
              streamProgress={discoveryStream.progress}
              currentMessage={discoveryStream.currentMessage}
            />
            )}
          </div>
        )}

        {/* Map Legend */}
        <div className="absolute bottom-4 left-4 z-10">
          <div className="flex items-center gap-3 px-3 py-2 bg-white/95 backdrop-blur-sm border border-stone-200 rounded-lg text-[11px] shadow-sm">
            <LegendItem color="bg-emerald-500" label="Critical" />
            <LegendItem color="bg-lime-500" label="Poor" />
            <LegendItem color="bg-amber-500" label="Fair" />
            <LegendItem color="bg-red-400" label="Good" />
            <LegendItem color="bg-stone-400" label="Pending" />
          </div>
        </div>
      </div>
    </div>
  )
}

// Components

function FilterChip({ 
  active, 
  onClick, 
  count, 
  children 
}: { 
  active: boolean
  onClick: () => void
  count: number
  children: React.ReactNode 
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 rounded text-xs font-medium transition-all flex items-center gap-1.5',
        active
          ? 'bg-stone-800 text-white'
          : 'bg-stone-100 text-stone-500 hover:bg-stone-200 hover:text-stone-700'
      )}
    >
      {children}
      <span className={cn(
        'font-mono text-[10px]',
        active ? 'text-stone-300' : 'text-stone-400'
      )}>
        {count}
      </span>
    </button>
  )
}

function ParcelItem({ 
  deal, 
  isSelected, 
  onClick, 
  onViewDetails,
}: { 
  deal: any
  isSelected: boolean
  onClick: () => void
  onViewDetails: () => void
}) {
  const hasBusiness = deal.has_business || deal.business
  const hasContact = deal.has_contact || deal.contact_email || deal.contact_phone
  const pavedArea = deal.paved_area_sqft
  const boundarySource = deal.property_boundary_source
  const owner = deal.regrid_owner
  const leadScore = deal.lead_score ?? deal.score
  const isRegridFirst = deal.discovery_source === 'regrid_first'

  // Display name priority: business > contact company > address
  const displayName = deal.display_name || deal.business?.name || deal.business_name || deal.contact_company || deal.address || 'Property'
  const subtitle = deal.address && displayName !== deal.address ? deal.address : null

  const formatNumber = (n: number | null | undefined) => {
    if (n === null || n === undefined) return '—'
    return n.toLocaleString()
  }

  // Get score styling based on lead score (inverted - lower is better for leads)
  const getScoreStyle = (score: number | null | undefined) => {
    if (score === null || score === undefined) return null
    if (score >= 70) return { bg: 'bg-emerald-500', text: 'text-white', label: 'High' }
    if (score >= 40) return { bg: 'bg-amber-500', text: 'text-white', label: 'Medium' }
    return { bg: 'bg-stone-400', text: 'text-white', label: 'Low' }
  }

  const scoreStyle = getScoreStyle(leadScore)

  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-white rounded-lg border cursor-pointer transition-all group',
        isSelected 
          ? 'border-stone-400 shadow-md' 
          : 'border-stone-200 hover:border-stone-300 hover:shadow-sm'
      )}
    >
      <div className="p-3">
        {/* Header with Lead Score */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-stone-800 truncate">
              {displayName}
            </p>
            {subtitle && (
              <p className="text-[11px] text-stone-400 truncate">{subtitle}</p>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {/* Lead Score Badge */}
            {scoreStyle && leadScore !== null && leadScore !== undefined && (
              <div className={cn(
                'flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums',
                scoreStyle.bg, scoreStyle.text
              )}>
                <Gauge className="h-2.5 w-2.5" />
                {Math.round(leadScore)}
              </div>
            )}
            <button 
              onClick={(e) => { e.stopPropagation(); onViewDetails() }}
              className="p-1.5 rounded hover:bg-stone-100 transition-all opacity-0 group-hover:opacity-100"
            >
              <ArrowRight className="h-3.5 w-3.5 text-stone-400" />
            </button>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-2 mb-2">
          {pavedArea && (
            <div className="flex items-center gap-1.5">
              <Square className="h-3 w-3 text-stone-400" />
              <span className="text-xs">
                <span className="font-semibold text-stone-700 tabular-nums">{formatNumber(Math.round(pavedArea))}</span>
                <span className="text-stone-400 ml-0.5">ft²</span>
              </span>
            </div>
          )}
          {owner && (
            <div className="flex items-center gap-1.5 min-w-0">
              <User className="h-3 w-3 text-stone-400 shrink-0" />
              <span className="text-xs text-stone-600 truncate">{owner.length > 15 ? owner.split(' ')[0] : owner}</span>
            </div>
          )}
        </div>

        {/* Tags */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {boundarySource === 'regrid' && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded text-[10px] font-medium">
              <CheckCircle2 className="h-2.5 w-2.5" />
              Regrid
            </span>
          )}
          {hasBusiness && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-[10px] font-medium">
              <Building2 className="h-2.5 w-2.5" />
              Business
            </span>
          )}
          {hasContact && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded text-[10px] font-medium">
              <User className="h-2.5 w-2.5" />
              Contact
            </span>
          )}
          <span className={cn(
            'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
            deal.status === 'evaluated' || deal.status === 'imagery_captured' || deal.status === 'analyzed'
              ? 'bg-sky-50 text-sky-600'
              : 'bg-stone-100 text-stone-500'
          )}>
            {deal.status === 'evaluated' || deal.status === 'imagery_captured' || deal.status === 'analyzed' ? (
              <CheckCircle2 className="h-2.5 w-2.5" />
            ) : (
              <Clock className="h-2.5 w-2.5" />
            )}
            {deal.status === 'imagery_captured' ? 'Captured' : deal.status === 'analyzed' ? 'Analyzed' : deal.status}
          </span>
        </div>
      </div>
    </div>
  )
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={cn('w-2 h-2 rounded-full', color)} />
      <span className="text-stone-500">{label}</span>
    </div>
  )
}
