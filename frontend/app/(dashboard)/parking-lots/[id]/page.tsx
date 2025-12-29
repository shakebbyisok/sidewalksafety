'use client'

import { useParkingLot, useParkingLotBusinesses } from '@/lib/queries/use-parking-lots'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusChip } from '@/components/ui'
import { formatNumber, cn } from '@/lib/utils'
import { 
  MapPin, 
  Building2, 
  ArrowLeft,
  Phone,
  Globe,
  ExternalLink,
  CheckCircle2,
  Clock,
  Copy,
  AlertCircle,
  Target,
  AlertTriangle,
  Ruler,
  Loader2,
  User,
  FileText,
  Car,
  Construction,
} from 'lucide-react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useState } from 'react'
import { PropertyAnalysisMap } from '@/components/map/property-analysis-map'

export default function ParkingLotDetailPage() {
  const params = useParams()
  const router = useRouter()
  const parkingLotId = params.id as string
  const { data: parkingLot, isLoading, error } = useParkingLot(parkingLotId)
  const { data: businesses } = useParkingLotBusinesses(parkingLotId)
  const [copied, setCopied] = useState(false)

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Inverted score colors: bad condition = green (opportunity for sales)
  const getScoreStyle = (score: number | null | undefined) => {
    if (score === null || score === undefined) {
      return { bg: 'bg-muted', text: 'text-muted-foreground', label: 'Not evaluated', color: 'gray' }
    }
    if (score <= 30) return { bg: 'bg-emerald-100 dark:bg-emerald-950', text: 'text-emerald-700 dark:text-emerald-400', label: 'Critical - High Priority', color: 'emerald' }
    if (score <= 50) return { bg: 'bg-lime-100 dark:bg-lime-950', text: 'text-lime-700 dark:text-lime-400', label: 'Poor - Good Opportunity', color: 'lime' }
    if (score <= 70) return { bg: 'bg-amber-100 dark:bg-amber-950', text: 'text-amber-700 dark:text-amber-400', label: 'Fair - Moderate', color: 'amber' }
    return { bg: 'bg-red-100 dark:bg-red-950', text: 'text-red-700 dark:text-red-400', label: 'Good Condition', color: 'red' }
  }

  if (isLoading) {
    return (
      <div className="h-full bg-background">
        <div className="h-full flex flex-col">
          <div className="px-4 py-3 border-b">
            <Skeleton className="h-5 w-48" />
          </div>
          <div className="flex-1 flex">
            <Skeleton className="flex-1" />
            <div className="w-80 border-l p-4 space-y-4">
              <Skeleton className="h-24" />
              <Skeleton className="h-32" />
              <Skeleton className="h-48" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (error || !parkingLot) {
    return (
      <div className="h-full bg-background flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-14 h-14 rounded-xl border-2 border-dashed border-border flex items-center justify-center mx-auto">
            <AlertCircle className="h-6 w-6 text-muted-foreground/30" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">Property Not Found</h2>
            <p className="text-sm text-muted-foreground mt-1">
              The property doesn't exist or you don't have access.
            </p>
          </div>
          <Link href="/dashboard">
            <Button variant="outline" size="sm" className="mt-2">
              <ArrowLeft className="h-3.5 w-3.5 mr-1.5" />
              Back to Dashboard
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  const primaryBusiness = parkingLot.business || businesses?.find(b => b.is_primary) || businesses?.[0]
  const hasBusinessData = !!primaryBusiness || (businesses && businesses.length > 0)
  const displayName = primaryBusiness?.name || parkingLot.operator_name || 'Property'
  const displayAddress = parkingLot.address || 'Address not available'
  const conditionScore = parkingLot.condition_score ?? null
  const isLead = conditionScore !== null && conditionScore < 50
  const scoreStyle = getScoreStyle(conditionScore)
  
  // Analysis data
  const analysis = parkingLot.property_analysis
  const propertyBoundary = analysis?.property_boundary?.polygon
  
  // NEW: Use surfaces breakdown from Grounded SAM
  const surfaces = analysis?.surfaces
  const surfacesGeoJSON = analysis?.surfaces_geojson
  
  // LEGACY: Fall back to old asphaltGeoJSON
  const asphaltGeoJSON = analysis?.private_asphalt_geojson
  
  // Damage markers from tiles (if available)
  const damageMarkers = analysis?.tiles?.flatMap(tile => {
    const markers: any[] = []
    if (tile.crack_count > 0 || tile.pothole_count > 0) {
      // Create a marker at tile center for tiles with damage
      markers.push({
        lat: tile.center_lat,
        lng: tile.center_lng,
        type: tile.pothole_count > 0 ? 'pothole' : 'crack',
        severity: (tile.condition_score ?? 100) <= 30 ? 'severe' : 
                  (tile.condition_score ?? 100) <= 50 ? 'moderate' : 'minor',
      })
    }
    return markers
  }) || []

  return (
    <div className="h-full bg-background flex flex-col">
      {/* Compact Header Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b bg-card shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/dashboard">
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0 shrink-0">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-foreground truncate">{displayName}</h1>
            <div className="text-xs text-muted-foreground flex items-center gap-1 truncate">
              <MapPin className="h-3 w-3 shrink-0" />
              <span className="truncate">{displayAddress}</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2 shrink-0">
          {isLead && (
            <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white text-[10px]">
              <Target className="h-3 w-3 mr-1" />
              Lead
            </Badge>
          )}
          {analysis?.lead_quality && (
            <Badge 
              variant="outline" 
              className={cn(
                'text-[10px] uppercase',
                analysis.lead_quality === 'premium' ? 'border-amber-500 text-amber-600' :
                analysis.lead_quality === 'high' ? 'border-emerald-500 text-emerald-600' :
                analysis.lead_quality === 'standard' ? 'border-blue-500 text-blue-600' :
                'border-muted-foreground text-muted-foreground'
              )}
            >
              {analysis.lead_quality}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={handleCopyLink}
          >
            {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      {/* Main Content: Map + Sidebar */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Interactive Map */}
        <div className="flex-1 relative">
          {(parkingLot.latitude || parkingLot.centroid?.lat) && (parkingLot.longitude || parkingLot.centroid?.lng) ? (
            <PropertyAnalysisMap
              latitude={parkingLot.latitude ?? parkingLot.centroid.lat}
              longitude={parkingLot.longitude ?? parkingLot.centroid.lng}
              propertyBoundary={propertyBoundary}
              surfaces={surfaces}
              surfacesGeoJSON={surfacesGeoJSON}
              asphaltAreas={asphaltGeoJSON}
              damageMarkers={damageMarkers}
              height="100%"
              showLegend={true}
              showControls={true}
              initialZoom={18}
              className="w-full h-full"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-muted/30">
              <div className="text-center">
                <MapPin className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">No location data available</p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Info Sidebar */}
        <div className="w-80 border-l bg-card overflow-y-auto">
          <div className="p-4 space-y-4">
            
            {/* Condition Score Card */}
            <div className={cn('rounded-xl p-4', scoreStyle.bg)}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Pavement Condition</p>
                  <div className="flex items-baseline gap-2">
                    <span className={cn('text-3xl font-bold tabular-nums', scoreStyle.text)}>
                      {conditionScore !== null ? Math.round(conditionScore) : '—'}
                    </span>
                    <span className="text-sm text-muted-foreground">/100</span>
                  </div>
                  <p className={cn('text-xs mt-1', scoreStyle.text)}>{scoreStyle.label}</p>
                </div>
                {isLead && (
                  <div className="bg-emerald-500 text-white rounded-full p-2">
                    <Target className="h-5 w-5" />
                  </div>
                )}
              </div>
              
              {/* Progress bar */}
              {conditionScore !== null && (
                <div className="mt-3 h-2 bg-white/30 dark:bg-black/20 rounded-full overflow-hidden">
                  <div 
                    className={cn('h-full rounded-full transition-all', 
                      scoreStyle.color === 'emerald' ? 'bg-emerald-500' :
                      scoreStyle.color === 'lime' ? 'bg-lime-500' :
                      scoreStyle.color === 'amber' ? 'bg-amber-500' :
                      'bg-red-500'
                    )}
                    style={{ width: `${100 - conditionScore}%` }}
                  />
                </div>
              )}
            </div>

            {/* Surface Detection Results */}
            <div className="border rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Surface Analysis</h3>
                {analysis?.detection_method === 'grounded_sam' && (
                  <Badge variant="outline" className="text-[9px] h-4 px-1.5 bg-purple-500/10 text-purple-600 border-purple-500/30">
                    AI Detected
                  </Badge>
                )}
              </div>
              
              {/* Surface Type Breakdown */}
              <div className="space-y-2">
                {/* Paved Surfaces (detected via Roboflow) */}
                <SurfaceRow
                  color="#374151"
                  label="Paved Surfaces"
                  area={surfaces?.asphalt?.area_sqft || analysis?.private_asphalt_area_sqft || 0}
                  isMain
                />
                
                {/* Concrete (if separately detected) */}
                {(surfaces?.concrete?.area_sqft ?? 0) > 0 && (
                  <SurfaceRow
                    color="#9CA3AF"
                    label="Concrete"
                    area={surfaces?.concrete?.area_sqft || 0}
                  />
                )}
                
                {/* Total paved */}
                <div className="pt-2 border-t flex items-center justify-between">
                  <span className="text-xs font-medium">Total Paved Area</span>
                  <span className="text-sm font-bold tabular-nums">
                    {formatNumber(
                      analysis?.total_paved_area_sqft || 
                      ((surfaces?.asphalt?.area_sqft || 0) + (surfaces?.concrete?.area_sqft || 0)) ||
                      analysis?.private_asphalt_area_sqft || 
                      0, 
                      0
                    )} sq ft
                  </span>
                </div>
              </div>
              
              {/* Public roads filtered info */}
              {analysis?.public_road_area_m2 && analysis.public_road_area_m2 > 0 && (
                <div className="text-[10px] text-muted-foreground bg-muted/50 rounded px-2 py-1 flex items-center gap-1">
                  <AlertCircle className="h-3 w-3 shrink-0" />
                  {formatNumber(analysis.public_road_area_m2 * 10.764, 0)} sq ft of public roads excluded
                </div>
              )}
            </div>
            
            {/* Damage Analysis */}
            <div className="border rounded-xl p-4 space-y-3">
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Damage Detected</h3>
              
              <div className="grid grid-cols-2 gap-3">
                <MetricCard
                  icon={AlertTriangle}
                  label="Cracks"
                  value={analysis?.total_crack_count || 0}
                  unit="found"
                  color={(analysis?.total_crack_count || 0) > 0 ? 'orange' : 'gray'}
                />
                <MetricCard
                  icon={Construction}
                  label="Potholes"
                  value={analysis?.total_pothole_count || 0}
                  unit="found"
                  color={(analysis?.total_pothole_count || 0) > 0 ? 'red' : 'gray'}
                />
              </div>
              
              {/* Hotspots */}
              {(analysis?.hotspot_count ?? 0) > 0 && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                  <span className="text-xs font-medium text-red-600">
                    {analysis?.hotspot_count} severe damage hotspots
                  </span>
                </div>
              )}
            </div>

            {/* Property Owner Info */}
            {analysis?.property_boundary && (
              <div className="border rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Property Details</h3>
                
                {analysis.property_boundary.owner && (
                  <div className="flex items-start gap-3">
                    <User className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">Owner</p>
                      <p className="text-sm font-medium">{analysis.property_boundary.owner}</p>
                    </div>
                  </div>
                )}
                
                {analysis.property_boundary.parcel_id && (
                  <div className="flex items-start gap-3">
                    <FileText className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">Parcel ID</p>
                      <p className="text-sm font-medium font-mono">{analysis.property_boundary.parcel_id}</p>
                    </div>
                  </div>
                )}
                
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <Badge variant="outline" className="text-[10px] h-5">
                    {analysis.property_boundary.source === 'regrid' ? '✓ Regrid Verified' : analysis.property_boundary.source}
                  </Badge>
                </div>
              </div>
            )}

            {/* Business Contact */}
            {primaryBusiness && (
              <div className="border rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Business Contact</h3>
                
                <div className="flex items-start gap-3">
                  <Building2 className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium">{primaryBusiness.name}</p>
                    {primaryBusiness.category && (
                      <p className="text-xs text-muted-foreground">{primaryBusiness.category}</p>
                    )}
                  </div>
                </div>
                
                {primaryBusiness.phone && (
                  <a 
                    href={`tel:${primaryBusiness.phone}`}
                    className="flex items-center gap-3 text-sm hover:text-primary transition-colors"
                  >
                    <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span>{primaryBusiness.phone}</span>
                  </a>
                )}
                
                {primaryBusiness.website && (
                  <a 
                    href={primaryBusiness.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 text-sm hover:text-primary transition-colors"
                  >
                    <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="truncate">{primaryBusiness.website.replace(/^https?:\/\//, '')}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                )}
              </div>
            )}

            {/* Analysis Info */}
            {analysis && (
              <div className="text-[10px] text-muted-foreground space-y-1">
                <div className="flex items-center justify-between">
                  <span>Analysis Type:</span>
                  <span className="font-medium uppercase">{analysis.analysis_type || 'standard'}</span>
                </div>
                {analysis.total_tiles && (
                  <div className="flex items-center justify-between">
                    <span>Tiles Analyzed:</span>
                    <span className="font-medium">{analysis.analyzed_tiles}/{analysis.total_tiles}</span>
                  </div>
                )}
                {analysis.analyzed_at && (
                  <div className="flex items-center justify-between">
                    <span>Analyzed:</span>
                    <span className="font-medium">{new Date(analysis.analyzed_at).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Metric card component
function MetricCard({
  icon: Icon,
  label,
  value,
  unit,
  color = 'gray',
}: {
  icon: React.ElementType
  label: string
  value: number | string
  unit: string
  color?: 'emerald' | 'orange' | 'red' | 'blue' | 'gray'
}) {
  const colorClasses = {
    emerald: 'text-emerald-600 dark:text-emerald-400',
    orange: 'text-orange-600 dark:text-orange-400',
    red: 'text-red-600 dark:text-red-400',
    blue: 'text-blue-600 dark:text-blue-400',
    gray: 'text-muted-foreground',
  }
  
  return (
    <div className="bg-muted/30 rounded-lg p-3">
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className={cn('h-3.5 w-3.5', colorClasses[color])} />
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={cn('text-lg font-bold tabular-nums', colorClasses[color])}>{value}</span>
        <span className="text-xs text-muted-foreground">{unit}</span>
      </div>
    </div>
  )
}

// Surface row component for surface breakdown
function SurfaceRow({
  color,
  label,
  area,
  isMain = false,
}: {
  color: string
  label: string
  area: number
  isMain?: boolean
}) {
  return (
    <div className={cn(
      "flex items-center justify-between py-1.5",
      isMain && "font-medium"
    )}>
      <div className="flex items-center gap-2">
        <div 
          className="w-3 h-3 rounded-sm flex-shrink-0" 
          style={{ backgroundColor: color }}
        />
        <span className="text-xs">{label}</span>
      </div>
      <span className={cn("text-xs tabular-nums", isMain && "font-semibold")}>
        {formatNumber(area, 0)} sq ft
      </span>
    </div>
  )
}
