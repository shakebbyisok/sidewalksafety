'use client'

import { useState, useCallback, useRef, useMemo, useEffect } from 'react'
import { useDeals, useDealsForMap, useScrapeDeals, MapBounds } from '@/lib/queries/use-deals'
import { InteractiveMap } from '@/components/map/interactive-map'
import { DiscoveryCard } from '@/components/map/discovery-card'
import { DealMapResponse } from '@/types'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { Chip, ChipGroup, StatusChip } from '@/components/ui'
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
  AlertTriangle,
  Circle,
  Square,
  Zap,
  ShieldCheck,
  ShieldAlert
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
  
  // Map bounds state with debouncing
  const [mapBounds, setMapBounds] = useState<MapBounds | undefined>(undefined)
  const boundsTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const hasMapLoadedOnce = useRef(false)
  const scrapeDeals = useScrapeDeals()

  const { data: dealsData, isLoading } = useDeals(statusFilter)
  const allDeals = Array.isArray(dealsData) ? dealsData : []
  
  // Apply score filter
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
  
  // Pass bounds to map query for PostGIS spatial filtering
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
  }, [])

  // Debounced bounds change handler
  const handleBoundsChange = useCallback((bounds: { minLat: number; maxLat: number; minLng: number; maxLng: number }) => {
    // Clear any pending timeout
    if (boundsTimeoutRef.current) {
      clearTimeout(boundsTimeoutRef.current)
    }
    
    // Set new timeout for debounced update
    boundsTimeoutRef.current = setTimeout(() => {
      setMapBounds(bounds)
    }, BOUNDS_DEBOUNCE_MS)
  }, [])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (boundsTimeoutRef.current) {
        clearTimeout(boundsTimeoutRef.current)
      }
    }
  }, [])

  const handleDiscover = (type: 'zip' | 'county', value: string, state?: string, businessTypeIds?: string[], maxResults?: number) => {
    scrapeDeals.mutate({
      area_type: type, value,
      state: type === 'county' ? state : undefined,
      max_results: maxResults || (type === 'zip' ? 10 : 30),
      business_type_ids: businessTypeIds,
    }, { onSuccess: () => setClickedLocation(null) })
  }

  const counts = {
    all: allDeals.length,
    pending: allDeals.filter(d => d.status === 'pending').length,
    analyzed: allDeals.filter(d => d.status === 'evaluated').length,
    leads: allDeals.filter(d => d.score !== null && d.score !== undefined && d.score < 50).length,
  }

  // Helper to get score color (inverted: bad = green opportunity)
  const getScoreColor = (score: number | null | undefined) => {
    if (score === null || score === undefined) {
      return { bg: 'bg-muted', text: 'text-muted-foreground' }
    }
    // Inverted logic: Low score (bad condition) = Green (opportunity!)
    if (score <= 30) return { bg: 'bg-emerald-100 dark:bg-emerald-950', text: 'text-emerald-700 dark:text-emerald-400' }
    if (score <= 50) return { bg: 'bg-lime-100 dark:bg-lime-950', text: 'text-lime-700 dark:text-lime-400' }
    if (score <= 70) return { bg: 'bg-amber-100 dark:bg-amber-950', text: 'text-amber-700 dark:text-amber-400' }
    // High score (good condition) = Red/Muted (not interesting)
    return { bg: 'bg-red-100 dark:bg-red-950', text: 'text-red-700 dark:text-red-400' }
  }

  return (
    <div className="h-full flex">
      {/* Side Panel */}
      <div className={cn(
        'h-full bg-card border-r border-border flex flex-col transition-all duration-200',
        panelOpen ? 'w-80' : 'w-0'
      )}>
        {panelOpen && (
          <>
            {/* Panel Header */}
            <div className="flex-shrink-0 p-3 border-b border-border space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-semibold">Parking Lots</span>
                  <span className="text-xs text-muted-foreground">({counts.all})</span>
                </div>
                <button 
                  onClick={() => setPanelOpen(false)}
                  className="p-1 rounded hover:bg-muted transition-colors"
                >
                  <ChevronLeft className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>

              {/* Status Filter Chips */}
              <ChipGroup>
                <Chip 
                  active={!statusFilter} 
                  onClick={() => setStatusFilter(undefined)}
                  count={counts.all}
                  icon={Circle}
                >
                  All
                </Chip>
                <Chip 
                  active={statusFilter === 'pending'} 
                  onClick={() => setStatusFilter('pending')}
                  count={counts.pending}
                  icon={Clock}
                >
                  Pending
                </Chip>
                <Chip 
                  active={statusFilter === 'evaluated'} 
                  onClick={() => setStatusFilter('evaluated')}
                  count={counts.analyzed}
                  icon={CheckCircle2}
                >
                  Analyzed
                </Chip>
              </ChipGroup>

              {/* Score Filter - Clickable Segmented Bar */}
              <div className="pt-2 border-t border-border space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Condition</span>
                  {scoreFilter !== 'all' && (
                    <button 
                      onClick={() => setScoreFilter('all')}
                      className="text-[10px] text-muted-foreground hover:text-foreground"
                    >
                      Clear
                    </button>
                  )}
                </div>
                
                {/* Clickable Segmented Bar */}
                <div className="flex h-6 rounded-md overflow-hidden border border-border">
                  <SegmentButton 
                    active={scoreFilter === 'critical'}
                    onClick={() => setScoreFilter(scoreFilter === 'critical' ? 'all' : 'critical')}
                    color="bg-emerald-500"
                    label="Critical"
                    flex={30}
                  />
                  <SegmentButton 
                    active={scoreFilter === 'poor'}
                    onClick={() => setScoreFilter(scoreFilter === 'poor' ? 'all' : 'poor')}
                    color="bg-lime-500"
                    label="Poor"
                    flex={20}
                  />
                  <SegmentButton 
                    active={scoreFilter === 'fair'}
                    onClick={() => setScoreFilter(scoreFilter === 'fair' ? 'all' : 'fair')}
                    color="bg-amber-500"
                    label="Fair"
                    flex={20}
                  />
                  <SegmentButton 
                    active={scoreFilter === 'good'}
                    onClick={() => setScoreFilter(scoreFilter === 'good' ? 'all' : 'good')}
                    color="bg-red-400"
                    label="Good"
                    flex={30}
                  />
                </div>

                {/* Lead Quick Filter */}
                {counts.leads > 0 && (
                  <button
                    onClick={() => setScoreFilter(scoreFilter === 'lead' ? 'all' : 'lead')}
                    className={cn(
                      'w-full flex items-center justify-between px-2 py-1.5 rounded-md text-xs font-medium transition-all',
                      scoreFilter === 'lead'
                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 ring-1 ring-emerald-500/30'
                        : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                  >
                    <span className="flex items-center gap-1.5">
                      <Target className="h-3 w-3" />
                      All Leads
                    </span>
                    <span className="tabular-nums">{counts.leads}</span>
                  </button>
                )}
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="p-3 space-y-2">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="h-20 bg-muted/50 rounded-lg animate-pulse" />
                  ))}
                </div>
              ) : deals.length > 0 ? (
                <div className="divide-y divide-border">
                  {deals.map((deal) => (
                    <ParkingLotItem
                      key={deal.id}
                      deal={deal}
                      isSelected={selectedDeal?.id === deal.id}
                      onClick={() => { setSelectedDeal(deal as any); setClickedLocation(null) }}
                      onViewDetails={() => handleViewDetails(deal.id)}
                      getScoreColor={getScoreColor}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                  <div className="w-14 h-14 rounded-xl border-2 border-dashed border-border flex items-center justify-center mb-3">
                    <MapPin className="h-6 w-6 text-muted-foreground/30" strokeWidth={1.5} />
                  </div>
                  <p className="text-sm font-medium">No parking lots found</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {scoreFilter !== 'all' ? 'Try adjusting filters' : 'Click on the map to discover'}
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
          className="absolute top-16 left-0 z-20 h-8 px-1 bg-card border-y border-r border-border rounded-r-md hover:bg-muted transition-colors"
        >
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        </button>
      )}

      {/* Map Area */}
      <div className="flex-1 relative">
        {showMapLoading ? (
          <div className="h-full flex items-center justify-center bg-muted/30">
            <div className="flex flex-col items-center gap-2">
              <div className="h-6 w-6 border-2 border-muted-foreground/30 border-t-foreground rounded-full animate-spin" />
              <span className="text-xs text-muted-foreground">Loading map...</span>
            </div>
          </div>
        ) : (
          <InteractiveMap
            deals={mapDeals}
            selectedDeal={selectedDeal}
            onDealSelect={(deal) => { setSelectedDeal(deal); setClickedLocation(null) }}
            onViewDetails={handleViewDetails}
            onBoundsChange={handleBoundsChange}
            onMapClick={handleMapClick}
            clickedLocation={clickedLocation}
          />
        )}

        {/* Discovery Card */}
        {clickedLocation && (
          <div className="absolute top-4 right-4 z-30">
            <DiscoveryCard
              lat={clickedLocation.lat}
              lng={clickedLocation.lng}
              onDiscover={handleDiscover}
              onClose={() => setClickedLocation(null)}
              isDiscovering={scrapeDeals.isPending}
            />
          </div>
        )}

        {/* Map Legend - Inverted colors */}
        <div className="absolute bottom-4 left-4 z-10">
          <div className="flex items-center gap-3 px-3 py-2 bg-card/95 backdrop-blur-sm border border-border rounded-lg text-[11px] shadow-sm">
            <LegendItem color="bg-emerald-500" label="Critical" />
            <LegendItem color="bg-lime-500" label="Poor" />
            <LegendItem color="bg-amber-500" label="Fair" />
            <LegendItem color="bg-red-400" label="Good" />
            <LegendItem color="bg-muted-foreground" label="Pending" />
          </div>
        </div>
      </div>
    </div>
  )
}

// Components

function ParkingLotItem({ 
  deal, 
  isSelected, 
  onClick, 
  onViewDetails,
  getScoreColor
}: { 
  deal: any
  isSelected: boolean
  onClick: () => void
  onViewDetails: () => void
  getScoreColor: (score: number | null | undefined) => { bg: string; text: string }
}) {
  const hasBusiness = deal.has_business || deal.business
  const isLead = deal.score !== null && deal.score !== undefined && deal.score < 50
  const score = deal.score
  const scoreStyle = getScoreColor(score)
  
  // Analysis data
  const pavedArea = deal.paved_area_sqft
  const crackCount = deal.crack_count
  const potholeCount = deal.pothole_count
  const boundarySource = deal.property_boundary_source
  const leadQuality = deal.lead_quality

  // Format number with commas
  const formatNumber = (n: number | null | undefined) => {
    if (n === null || n === undefined) return '—'
    return n.toLocaleString()
  }

  return (
    <div
      onClick={onClick}
      className={cn(
        'px-3 py-3 cursor-pointer transition-all group',
        isSelected ? 'bg-muted' : 'hover:bg-muted/50',
        isLead && !isSelected && 'border-l-2 border-l-emerald-500'
      )}
    >
      <div className="flex items-start gap-3">
        {/* Score Circle - Inverted colors */}
        <div className={cn(
          'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 text-sm font-bold',
          scoreStyle.bg,
          scoreStyle.text
        )}>
          {score !== null && score !== undefined ? Math.round(score) : '—'}
        </div>

        <div className="flex-1 min-w-0">
          {/* Title */}
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <span className="text-sm font-medium truncate">
              {deal.business?.name || deal.business_name || 'Unknown Location'}
            </span>
            <button 
              onClick={(e) => { e.stopPropagation(); onViewDetails() }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-background transition-all flex-shrink-0"
            >
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </div>

          {/* Address */}
          <p className="text-xs text-muted-foreground truncate mb-1.5">{deal.address}</p>

          {/* Metrics Row - NEW */}
          {(pavedArea || crackCount !== undefined || potholeCount !== undefined) && (
            <div className="flex items-center gap-3 mb-1.5 text-[10px]">
              {pavedArea !== null && pavedArea !== undefined && (
                <div className="flex items-center gap-1">
                  <Square className="h-3 w-3 text-emerald-500" />
                  <span className="text-muted-foreground">
                    <span className="font-medium text-foreground">{formatNumber(Math.round(pavedArea))}</span> sqft
                  </span>
                </div>
              )}
              {crackCount !== null && crackCount !== undefined && crackCount > 0 && (
                <div className="flex items-center gap-1">
                  <Zap className="h-3 w-3 text-amber-500" />
                  <span className="text-muted-foreground">
                    <span className="font-medium text-foreground">{crackCount}</span> cracks
                  </span>
                </div>
              )}
              {potholeCount !== null && potholeCount !== undefined && potholeCount > 0 && (
                <div className="flex items-center gap-1">
                  <Circle className="h-3 w-3 text-red-500" />
                  <span className="text-muted-foreground">
                    <span className="font-medium text-foreground">{potholeCount}</span> potholes
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Tags */}
          <div className="flex items-center gap-1 flex-wrap">
            {/* Lead Quality - NEW */}
            {leadQuality === 'HIGH' && (
              <StatusChip status="success" icon={Target}>High Lead</StatusChip>
            )}
            {leadQuality === 'MEDIUM' && (
              <StatusChip status="info" icon={Target}>Med Lead</StatusChip>
            )}

            {/* Regrid verification - NEW */}
            {boundarySource === 'regrid' && (
              <StatusChip status="success" icon={ShieldCheck}>Regrid</StatusChip>
            )}
            {boundarySource === 'estimated' && (
              <StatusChip status="warning" icon={ShieldAlert}>Est.</StatusChip>
            )}

            {/* Status */}
            <StatusChip 
              status={deal.status === 'evaluated' ? 'success' : deal.status === 'evaluating' ? 'info' : 'warning'}
              icon={deal.status === 'evaluated' ? CheckCircle2 : Clock}
            >
              {deal.status}
            </StatusChip>

            {/* Business indicator */}
            {hasBusiness ? (
              <StatusChip status="info" icon={Building2}>Business</StatusChip>
            ) : (
              <StatusChip status="warning" icon={AlertTriangle}>No biz</StatusChip>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={cn('w-2 h-2 rounded-full', color)} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  )
}

function SegmentButton({ 
  active, 
  onClick, 
  color, 
  label,
  flex
}: { 
  active: boolean
  onClick: () => void
  color: string
  label: string
  flex: number
}) {
  return (
    <button
      onClick={onClick}
      style={{ flex }}
      className={cn(
        'relative text-[9px] font-medium transition-all border-r border-border last:border-r-0',
        'flex items-center justify-center',
        active 
          ? 'text-white shadow-inner' 
          : 'bg-muted/30 text-muted-foreground hover:bg-muted/60 hover:text-foreground'
      )}
    >
      {/* Color fill when active */}
      <div className={cn(
        'absolute inset-0 transition-opacity',
        color,
        active ? 'opacity-100' : 'opacity-0'
      )} />
      <span className="relative z-10">{label}</span>
    </button>
  )
}
