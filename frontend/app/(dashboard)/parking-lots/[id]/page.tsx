'use client'

import { useParkingLot, useParkingLotBusinesses } from '@/lib/queries/use-parking-lots'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatNumber, cn } from '@/lib/utils'
import { 
  MapPin, 
  Building2, 
  ArrowLeft,
  Phone,
  Globe,
  ExternalLink,
  CheckCircle2,
  Copy,
  AlertCircle,
  User,
  Satellite,
  Maximize2,
  X,
  Calendar,
  Layers,
  Hash,
  Ruler,
  TreePine,
  MapPinned,
  CalendarDays,
  Sparkles,
  Star,
  Loader2,
  Mail,
  Linkedin,
  UserSearch,
  Briefcase,
  Route,
} from 'lucide-react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PropertyAnalysisMap } from '@/components/map/property-analysis-map'
import { parkingLotsApi, AnalyzePropertyRequest } from '@/lib/api/parking-lots'
import { scoringPromptsApi } from '@/lib/api/scoring-prompts'

export default function ParkingLotDetailPage() {
  const params = useParams()
  const router = useRouter()
  const queryClient = useQueryClient()
  const parkingLotId = params.id as string
  const { data: parkingLot, isLoading, error } = useParkingLot(parkingLotId)
  const { data: businesses } = useParkingLotBusinesses(parkingLotId)
  const [copied, setCopied] = useState(false)
  const [showFullImage, setShowFullImage] = useState(false)
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false)
  const [showEnrichmentStepsModal, setShowEnrichmentStepsModal] = useState(false)
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null)
  const [customPrompt, setCustomPrompt] = useState('')
  const [useCustom, setUseCustom] = useState(false)
  const [enrichmentResult, setEnrichmentResult] = useState<{ 
    flow?: string
    steps?: string[]
    enrichment_detailed_steps?: any[]
  } | null>(null)

  // Fetch saved prompts
  const { data: savedPrompts } = useQuery({
    queryKey: ['scoring-prompts'],
    queryFn: scoringPromptsApi.list,
  })

  // Analyze mutation
  const analyzeMutation = useMutation({
    mutationFn: (request: AnalyzePropertyRequest) => 
      parkingLotsApi.analyzeProperty(parkingLotId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['parking-lot', parkingLotId] })
      setShowAnalyzeModal(false)
    },
  })

  // Enrich mutation
  const enrichMutation = useMutation({
    mutationFn: () => parkingLotsApi.enrichProperty(parkingLotId),
    onSuccess: (data) => {
      // Store the enrichment result to show flow
      if (data.enrichment_flow || data.enrichment_steps || data.enrichment_detailed_steps) {
        setEnrichmentResult({ 
          flow: data.enrichment_flow, 
          steps: data.enrichment_steps,
          enrichment_detailed_steps: data.enrichment_detailed_steps
        })
      }
      queryClient.invalidateQueries({ queryKey: ['parking-lot', parkingLotId] })
    },
  })

  const handleAnalyze = () => {
    const request: AnalyzePropertyRequest = {}
    if (useCustom && customPrompt.trim()) {
      request.custom_prompt = customPrompt.trim()
    } else if (selectedPromptId) {
      request.scoring_prompt_id = selectedPromptId
    }
    analyzeMutation.mutate(request)
  }

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) {
    return (
      <div className="h-full bg-stone-50">
        <div className="h-full flex flex-col">
          <div className="px-4 py-3 border-b border-stone-200 bg-white">
            <Skeleton className="h-5 w-48" />
          </div>
          <div className="flex-1 flex">
            <Skeleton className="flex-1" />
            <div className="w-80 border-l border-stone-200 bg-stone-50 p-4 space-y-4">
              <Skeleton className="h-44 rounded-lg" />
              <Skeleton className="h-32 rounded-lg" />
              <Skeleton className="h-28 rounded-lg" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (error || !parkingLot) {
    return (
      <div className="h-full bg-stone-50 flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-14 h-14 rounded-xl border-2 border-dashed border-stone-300 flex items-center justify-center mx-auto">
            <AlertCircle className="h-6 w-6 text-stone-400" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-stone-800">Property Not Found</h2>
            <p className="text-sm text-stone-500 mt-1">
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
  const displayName = primaryBusiness?.name || parkingLot.operator_name || parkingLot.address || 'Property'
  const displayAddress = parkingLot.address || 'Address not available'
  
  // Analysis data
  const analysis = parkingLot.property_analysis
  const propertyBoundary = analysis?.property_boundary?.polygon
  const regrid = parkingLot.regrid || analysis?.property_boundary

  return (
    <div className="h-full bg-stone-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-stone-200 bg-white shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/dashboard">
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0 shrink-0 hover:bg-stone-100">
              <ArrowLeft className="h-4 w-4 text-stone-600" />
            </Button>
          </Link>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-stone-800 truncate">{displayName}</h1>
            <div className="text-xs text-stone-500 flex items-center gap-1 truncate">
              <MapPin className="h-3 w-3 shrink-0" />
              <span className="truncate">{displayAddress}</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-mono text-stone-400 hidden sm:block">
            {parkingLot.centroid?.lat?.toFixed(5)}, {parkingLot.centroid?.lng?.toFixed(5)}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 hover:bg-stone-100"
            onClick={handleCopyLink}
          >
            {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5 text-stone-500" />}
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Map */}
        <div className="flex-1 relative">
          {(parkingLot.latitude || parkingLot.centroid?.lat) && (parkingLot.longitude || parkingLot.centroid?.lng) ? (
            <PropertyAnalysisMap
              latitude={parkingLot.latitude ?? parkingLot.centroid.lat}
              longitude={parkingLot.longitude ?? parkingLot.centroid.lng}
              propertyBoundary={propertyBoundary}
              height="100%"
              showLegend={false}
              showControls={true}
              initialZoom={18}
              className="w-full h-full"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-stone-100">
              <div className="text-center">
                <MapPin className="h-12 w-12 text-stone-300 mx-auto mb-3" />
                <p className="text-sm text-stone-500">No location data</p>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="w-80 border-l border-stone-200 bg-stone-50 overflow-y-auto">
          <div className="p-4 space-y-4">
            
            {/* Satellite Image */}
            {parkingLot.satellite_image_base64 && (
              <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-stone-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded bg-sky-100 flex items-center justify-center">
                      <Satellite className="h-3 w-3 text-sky-600" />
                    </div>
                    <span className="text-xs font-medium text-stone-600">Satellite Capture</span>
                  </div>
                  <button 
                    onClick={() => setShowFullImage(true)}
                    className="p-1 rounded hover:bg-stone-100 transition-colors"
                  >
                    <Maximize2 className="h-3.5 w-3.5 text-stone-400" />
                  </button>
                </div>
                <div 
                  className="relative cursor-pointer group"
                  onClick={() => setShowFullImage(true)}
                >
                  <img 
                    src={`data:image/jpeg;base64,${parkingLot.satellite_image_base64}`}
                    alt="Satellite"
                    className="w-full h-44 object-cover"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                    <Maximize2 className="h-5 w-5 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>
              </div>
            )}
              
            {/* Property Info */}
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
              <div className="px-3 py-2 border-b border-stone-100 flex items-center gap-2">
                <div className="w-5 h-5 rounded bg-emerald-100 flex items-center justify-center">
                  <Ruler className="h-3 w-3 text-emerald-600" />
                </div>
                <span className="text-xs font-medium text-stone-600">Property</span>
              </div>
              <div className="p-3 space-y-2.5">
                {parkingLot.area_sqft && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-stone-500">Area</span>
                    <span className="text-sm tabular-nums font-semibold text-stone-800 tracking-tight">
                      {formatNumber(parkingLot.area_sqft, 0)} <span className="text-xs font-normal text-stone-400">ft²</span>
                    </span>
                </div>
              )}
                {regrid?.area_acres && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-stone-500">Acres</span>
                    <span className="text-sm tabular-nums font-semibold text-stone-800 tracking-tight">
                      {Number(regrid.area_acres).toFixed(2)} <span className="text-xs font-normal text-stone-400">ac</span>
                    </span>
            </div>
                )}
                {regrid?.land_use && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <TreePine className="h-3 w-3 text-stone-400" />
                      <span className="text-xs text-stone-500">Land Use</span>
              </div>
                    <span className="text-xs font-medium text-stone-700 truncate ml-2 max-w-[140px]">
                      {regrid.land_use}
                  </span>
                </div>
              )}
                {regrid?.zoning && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <MapPinned className="h-3 w-3 text-stone-400" />
                      <span className="text-xs text-stone-500">Zoning</span>
                    </div>
                    <span className="text-xs font-mono font-semibold text-stone-700 bg-stone-100 px-1.5 py-0.5 rounded">
                      {regrid.zoning}
                    </span>
                  </div>
                )}
                {regrid?.year_built && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <CalendarDays className="h-3 w-3 text-stone-400" />
                      <span className="text-xs text-stone-500">Year Built</span>
                    </div>
                    <span className="text-sm tabular-nums font-semibold text-stone-800">{regrid.year_built}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Owner Info */}
            {regrid?.owner && (
              <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-stone-100 flex items-center gap-2">
                  <div className="w-5 h-5 rounded bg-violet-100 flex items-center justify-center">
                    <User className="h-3 w-3 text-violet-600" />
                  </div>
                  <span className="text-xs font-medium text-stone-600">Owner</span>
                </div>
                <div className="p-3 space-y-2">
                  <p className="text-sm font-semibold text-stone-800">{regrid.owner}</p>
                  {(regrid.parcel_id || regrid.apn) && (
                    <div className="flex items-center gap-1.5">
                      <Hash className="h-3 w-3 text-stone-400" />
                      <span className="text-xs font-mono text-stone-500">{regrid.parcel_id || regrid.apn}</span>
                    </div>
                  )}
                  {regrid.source === 'regrid' && (
                    <div className="flex items-center gap-1.5 mt-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      <span className="text-[11px] text-emerald-600 font-medium">Regrid Verified</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Lead Contact (Enrichment) */}
            {regrid?.owner && (
              <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-stone-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded bg-blue-100 flex items-center justify-center">
                      <UserSearch className="h-3 w-3 text-blue-600" />
                    </div>
                    <span className="text-xs font-medium text-stone-600">Lead Contact</span>
                  </div>
                  {parkingLot.contact?.status === 'success' && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                      ENRICHED
                    </span>
                  )}
                </div>
                <div className="p-3">
                  {parkingLot.contact?.email || parkingLot.contact?.name || parkingLot.contact?.phone ? (
                    <div className="space-y-2.5">
                      {/* Contact/Company Name & Title */}
                      {(parkingLot.contact.name || parkingLot.contact.company) && (
                        <div>
                          <p className="text-sm font-semibold text-stone-800">
                            {parkingLot.contact.name || parkingLot.contact.company}
                          </p>
                          {parkingLot.contact.title && (
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <Briefcase className="h-3 w-3 text-stone-400" />
                              <span className="text-[11px] text-stone-500">{parkingLot.contact.title}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Email */}
                      {parkingLot.contact.email && (
                        <a 
                          href={`mailto:${parkingLot.contact.email}`}
                          className="flex items-center gap-2 text-xs text-blue-600 hover:text-blue-700 transition-colors"
                        >
                          <Mail className="h-3.5 w-3.5 text-blue-500" />
                          <span>{parkingLot.contact.email}</span>
                        </a>
                      )}

                      {/* Phone */}
                      {parkingLot.contact.phone && (
                        <a 
                          href={`tel:${parkingLot.contact.phone}`}
                          className="flex items-center gap-2 text-xs text-stone-600 hover:text-stone-800 transition-colors"
                        >
                          <Phone className="h-3.5 w-3.5 text-stone-400" />
                          <span>{parkingLot.contact.phone}</span>
                        </a>
                      )}

                      {/* Company Website */}
                      {parkingLot.contact.company_website && (
                        <a 
                          href={parkingLot.contact.company_website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 text-xs text-blue-600 hover:text-blue-700 transition-colors"
                        >
                          <ExternalLink className="h-3.5 w-3.5 text-blue-500" />
                          <span className="truncate">{new URL(parkingLot.contact.company_website).hostname}</span>
                        </a>
                      )}

                      {/* LinkedIn */}
                      {parkingLot.contact.linkedin_url && (
                        <a 
                          href={parkingLot.contact.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 text-xs text-blue-600 hover:text-blue-700 transition-colors"
                        >
                          <Linkedin className="h-3.5 w-3.5" />
                          <span className="truncate">LinkedIn Profile</span>
                          <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                      )}

                      {/* Enrichment Flow Button */}
                      {(parkingLot.enrichment_steps?.length || parkingLot.enrichment_flow) && (
                        <div className="pt-2 border-t border-stone-100">
                          <button
                            onClick={() => setShowEnrichmentStepsModal(true)}
                            className="flex items-center gap-1.5 text-[11px] text-stone-500 hover:text-stone-700 transition-colors"
                          >
                            <Sparkles className="h-3 w-3" />
                            <span>How we found this</span>
                            <ExternalLink className="h-2.5 w-2.5" />
                          </button>
                        </div>
                      )}

                      {/* Enriched timestamp */}
                      {parkingLot.contact.enriched_at && (
                        <div className="text-[10px] text-stone-400 pt-1 flex items-center gap-1">
                          <span>via {parkingLot.contact.source || 'LLM Enrichment'}</span>
                          <span>•</span>
                          <span>{new Date(parkingLot.contact.enriched_at).toLocaleDateString()}</span>
                        </div>
                      )}
                    </div>
                  ) : parkingLot.contact?.status === 'not_found' ? (
                    <div className="text-center py-2">
                      <p className="text-xs text-stone-500">No contact found for this owner</p>
                      <div className="mt-2 flex items-center justify-center gap-2">
                        {(parkingLot.enrichment_steps?.length || parkingLot.enrichment_flow || enrichmentResult?.steps?.length) && (
                          <button
                            onClick={() => setShowEnrichmentStepsModal(true)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium text-stone-600 hover:bg-stone-50 rounded-md transition-colors"
                          >
                            <Route className="h-3 w-3" />
                            View Steps
                          </button>
                        )}
                        <button
                          onClick={() => enrichMutation.mutate()}
                          disabled={enrichMutation.isPending}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium text-blue-600 hover:bg-blue-50 rounded-md transition-colors disabled:text-stone-400"
                        >
                          {enrichMutation.isPending ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <UserSearch className="h-3 w-3" />
                          )}
                          Try Again
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-stone-400">Not enriched yet</span>
                      <button
                        onClick={() => enrichMutation.mutate()}
                        disabled={enrichMutation.isPending}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium text-blue-600 hover:bg-blue-50 rounded-md transition-colors disabled:text-stone-400 disabled:hover:bg-transparent"
                      >
                        {enrichMutation.isPending ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Finding...
                          </>
                        ) : (
                          <>
                            <UserSearch className="h-3 w-3" />
                            Find Contact
                          </>
                        )}
                      </button>
                    </div>
                  )}
                  {/* Show enrichment flow result button */}
                  {enrichmentResult?.steps?.length && !parkingLot.enrichment_flow && (
                    <div className="mt-2">
                      <button
                        onClick={() => setShowEnrichmentStepsModal(true)}
                        className="flex items-center gap-1.5 px-2 py-1.5 bg-blue-50 hover:bg-blue-100 rounded-md text-[11px] text-blue-600 transition-colors"
                      >
                        <Sparkles className="h-3 w-3" />
                        <span>View enrichment steps</span>
                      </button>
                    </div>
                  )}
                  {enrichMutation.isError && (
                    <div className="mt-2 flex items-center gap-2 p-2 bg-red-50 rounded text-[11px] text-red-600">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                      <span>Enrichment failed. Check API key.</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Business Contact */}
            {primaryBusiness && (
              <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-stone-100 flex items-center gap-2">
                  <div className="w-5 h-5 rounded bg-amber-100 flex items-center justify-center">
                    <Building2 className="h-3 w-3 text-amber-600" />
                  </div>
                  <span className="text-xs font-medium text-stone-600">Business</span>
                </div>
                <div className="p-3 space-y-2.5">
                  <div>
                    <p className="text-sm font-semibold text-stone-800">{primaryBusiness.name}</p>
                    {primaryBusiness.category && (
                      <p className="text-[11px] text-stone-400 mt-0.5">{primaryBusiness.category}</p>
                    )}
                  </div>
                {primaryBusiness.phone && (
                  <a 
                    href={`tel:${primaryBusiness.phone}`}
                      className="flex items-center gap-2 text-xs text-stone-600 hover:text-stone-800 transition-colors"
                  >
                      <Phone className="h-3.5 w-3.5 text-stone-400" />
                    <span>{primaryBusiness.phone}</span>
                  </a>
                )}
                {primaryBusiness.website && (
                  <a 
                    href={primaryBusiness.website}
                    target="_blank"
                    rel="noopener noreferrer"
                      className="flex items-center gap-2 text-xs text-stone-600 hover:text-stone-800 transition-colors"
                  >
                      <Globe className="h-3.5 w-3.5 text-stone-400" />
                    <span className="truncate">{primaryBusiness.website.replace(/^https?:\/\//, '')}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                )}
                </div>
              </div>
            )}

            {/* AI Analysis */}
            {parkingLot.lead_score !== null && parkingLot.lead_score !== undefined ? (
              <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-stone-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded bg-violet-100 flex items-center justify-center">
                      <Layers className="h-3 w-3 text-violet-600" />
                    </div>
                    <span className="text-xs font-medium text-stone-600">AI Analysis</span>
                  </div>
                  {parkingLot.lead_quality && (
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                      parkingLot.lead_quality === 'high' 
                        ? 'bg-emerald-100 text-emerald-700' 
                        : parkingLot.lead_quality === 'medium'
                        ? 'bg-amber-100 text-amber-700'
                        : 'bg-stone-100 text-stone-600'
                    }`}>
                      {parkingLot.lead_quality.toUpperCase()}
                    </span>
                  )}
                </div>
                <div className="p-3 space-y-3">
                  {/* Lead Score */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-stone-500">Lead Score</span>
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${
                            parkingLot.lead_score >= 70 ? 'bg-emerald-500' :
                            parkingLot.lead_score >= 40 ? 'bg-amber-500' : 'bg-stone-400'
                          }`}
                          style={{ width: `${parkingLot.lead_score}%` }}
                        />
                      </div>
                      <span className="text-sm font-semibold tabular-nums text-stone-800">
                        {Math.round(parkingLot.lead_score)}
                      </span>
                    </div>
                  </div>

                  {/* Surface Breakdown */}
                  {(parkingLot.paved_percentage || parkingLot.building_percentage || parkingLot.landscaping_percentage) && (
                    <div className="space-y-1.5">
                      <span className="text-[10px] text-stone-400 uppercase tracking-wide">Surface</span>
                      <div className="flex h-2 rounded-full overflow-hidden bg-stone-100">
                        {parkingLot.paved_percentage > 0 && (
                          <div 
                            className="bg-stone-600" 
                            style={{ width: `${parkingLot.paved_percentage}%` }}
                            title={`Paved: ${parkingLot.paved_percentage}%`}
                          />
                        )}
                        {parkingLot.building_percentage > 0 && (
                          <div 
                            className="bg-stone-400" 
                            style={{ width: `${parkingLot.building_percentage}%` }}
                            title={`Buildings: ${parkingLot.building_percentage}%`}
                          />
                        )}
                        {parkingLot.landscaping_percentage > 0 && (
                          <div 
                            className="bg-emerald-400" 
                            style={{ width: `${parkingLot.landscaping_percentage}%` }}
                            title={`Landscaping: ${parkingLot.landscaping_percentage}%`}
                          />
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-[10px] text-stone-500">
                        {parkingLot.paved_percentage > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-sm bg-stone-600" />
                            Paved {parkingLot.paved_percentage}%
                          </span>
                        )}
                        {parkingLot.building_percentage > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-sm bg-stone-400" />
                            Buildings {parkingLot.building_percentage}%
                          </span>
                        )}
                        {parkingLot.landscaping_percentage > 0 && (
                          <span className="flex items-center gap-1">
                            <span className="w-2 h-2 rounded-sm bg-emerald-400" />
                            Green {parkingLot.landscaping_percentage}%
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* AI Reasoning */}
                  {parkingLot.analysis_notes && (
                    <div className="pt-2 border-t border-stone-100">
                      <span className="text-[10px] text-stone-400 uppercase tracking-wide">AI Reasoning</span>
                      <p className="mt-1 text-[11px] text-stone-600 leading-relaxed">
                        {parkingLot.analysis_notes}
                      </p>
                    </div>
                  )}

                  {/* Analyzed timestamp */}
                  {parkingLot.analyzed_at && (
                    <div className="text-[10px] text-stone-400 pt-1">
                      Analyzed {new Date(parkingLot.analyzed_at).toLocaleString()}
                  </div>
                )}
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-stone-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-stone-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded bg-violet-100 flex items-center justify-center">
                      <Layers className="h-3 w-3 text-violet-600" />
                    </div>
                    <span className="text-xs font-medium text-stone-600">AI Analysis</span>
                  </div>
                </div>
                <div className="p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-stone-400">Not yet analyzed</span>
                    <button
                      onClick={() => setShowAnalyzeModal(true)}
                      disabled={!parkingLot.satellite_image_base64}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium text-violet-600 hover:bg-violet-50 rounded-md transition-colors disabled:text-stone-400 disabled:hover:bg-transparent disabled:cursor-not-allowed"
                    >
                      <Sparkles className="h-3 w-3" />
                      Analyze
                    </button>
                  </div>
                  {!parkingLot.satellite_image_base64 && (
                    <p className="text-[10px] text-stone-400 mt-1.5">Capture imagery first</p>
                )}
                </div>
              </div>
            )}

            {/* Meta */}
            <div className="flex items-center justify-between px-1 text-[11px] text-stone-400">
              {parkingLot.created_at && (
                <div className="flex items-center gap-1.5">
                  <Calendar className="h-3 w-3" />
                  <span>{new Date(parkingLot.created_at).toLocaleDateString()}</span>
                </div>
              )}
              <span className="font-mono text-[10px] px-1.5 py-0.5 bg-stone-200 rounded text-stone-500">
                {parkingLot.status || 'captured'}
              </span>
            </div>

          </div>
        </div>
      </div>
      
      {/* Full Image Modal */}
      {showFullImage && parkingLot.satellite_image_base64 && (
        <div 
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setShowFullImage(false)}
        >
          <button
            onClick={() => setShowFullImage(false)}
            className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors text-white"
          >
            <X className="h-6 w-6" />
          </button>
          <div className="relative max-w-[90vw] max-h-[90vh]">
            <img 
              src={`data:image/jpeg;base64,${parkingLot.satellite_image_base64}`}
              alt="Satellite - full size"
              className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            />
            <div className="absolute bottom-4 left-4 bg-black/70 text-white px-3 py-1.5 rounded-lg text-sm font-medium">
              {displayAddress}
      </div>
      </div>
    </div>
      )}

      {/* Analyze Modal */}
      {showAnalyzeModal && (
        <div 
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => !analyzeMutation.isPending && setShowAnalyzeModal(false)}
        >
          <div 
            className="bg-white rounded-xl shadow-xl w-full max-w-sm overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-stone-100 flex items-center justify-between">
              <span className="text-sm font-medium text-stone-700">Select Scoring Criteria</span>
              <button
                onClick={() => setShowAnalyzeModal(false)}
                disabled={analyzeMutation.isPending}
                className="p-1 rounded hover:bg-stone-100 transition-colors disabled:opacity-50"
              >
                <X className="h-4 w-4 text-stone-400" />
              </button>
            </div>

            {/* Content */}
            <div className="p-4 space-y-3">
              {/* Saved Prompts */}
              {savedPrompts && savedPrompts.length > 0 ? (
                <div className="space-y-1.5 max-h-40 overflow-y-auto">
                  {savedPrompts.map((prompt) => (
                    <button
                      key={prompt.id}
                      onClick={() => {
                        setSelectedPromptId(prompt.id)
                        setUseCustom(false)
                      }}
                      disabled={analyzeMutation.isPending}
                      className={cn(
                        'w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-left transition-all',
                        selectedPromptId === prompt.id && !useCustom
                          ? 'bg-violet-50 border-violet-300'
                          : 'bg-stone-50 border-stone-200 hover:bg-stone-100'
                      )}
                    >
                      <div className={cn(
                        'w-3.5 h-3.5 rounded-full border-2 shrink-0',
                        selectedPromptId === prompt.id && !useCustom
                          ? 'border-violet-500 bg-violet-500'
                          : 'border-stone-300'
                      )} />
                      <span className="text-xs font-medium text-stone-700 truncate flex-1">
                        {prompt.title}
                      </span>
                      {prompt.is_default && (
                        <Star className="h-3 w-3 text-amber-500 fill-current shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-stone-400 text-center py-2">
                  No saved prompts. Using default criteria.
                </p>
              )}

              {/* Custom Option */}
              <button
                onClick={() => {
                  setUseCustom(true)
                  setSelectedPromptId(null)
                }}
                disabled={analyzeMutation.isPending}
                className={cn(
                  'w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-left transition-all',
                  useCustom
                    ? 'bg-violet-50 border-violet-300'
                    : 'bg-stone-50 border-stone-200 hover:bg-stone-100'
                )}
              >
                <div className={cn(
                  'w-3.5 h-3.5 rounded-full border-2 shrink-0',
                  useCustom ? 'border-violet-500 bg-violet-500' : 'border-stone-300'
                )} />
                <span className="text-xs font-medium text-stone-700">Custom criteria</span>
              </button>

              {useCustom && (
                <textarea
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  placeholder="HIGH: Large parking with damage...&#10;MEDIUM: Moderate paved areas...&#10;LOW: Small or well-maintained..."
                  disabled={analyzeMutation.isPending}
                  className="w-full h-20 px-3 py-2 text-xs border border-stone-200 rounded-lg resize-none focus:ring-1 focus:ring-violet-400 focus:border-violet-400"
                />
              )}

              {/* Error */}
              {analyzeMutation.isError && (
                <div className="flex items-center gap-2 p-2 bg-red-50 rounded text-[11px] text-red-600">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  <span>Analysis failed</span>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-stone-100 flex items-center justify-end gap-2">
              <button
                onClick={() => setShowAnalyzeModal(false)}
                disabled={analyzeMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium text-stone-600 hover:bg-stone-100 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleAnalyze}
                disabled={analyzeMutation.isPending || (useCustom && !customPrompt.trim() && !selectedPromptId && savedPrompts?.length === 0)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-stone-800 text-white text-xs font-medium rounded-lg hover:bg-stone-900 disabled:bg-stone-300 disabled:cursor-not-allowed transition-colors"
              >
                {analyzeMutation.isPending ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3 w-3" />
                    Run Analysis
                  </>
                )}
              </button>
            </div>
          </div>
      </div>
      )}

      {/* Enrichment Steps Modal */}
      {showEnrichmentStepsModal && (
        <div 
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => setShowEnrichmentStepsModal(false)}
        >
          <div 
            className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-stone-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
                  <Route className="h-3.5 w-3.5 text-white" />
                </div>
                <span className="text-sm font-medium text-stone-700">Enrichment Process</span>
              </div>
              <button
                onClick={() => setShowEnrichmentStepsModal(false)}
                className="p-1 rounded hover:bg-stone-100 transition-colors"
              >
                <X className="h-4 w-4 text-stone-400" />
              </button>
            </div>

            {/* Steps */}
            <div className="p-4 max-h-[60vh] overflow-y-auto">
              <div className="space-y-0">
                {(parkingLot?.enrichment_detailed_steps || enrichmentResult?.enrichment_detailed_steps || 
                  (parkingLot?.enrichment_steps || enrichmentResult?.steps || []).map((step: string) => ({
                    description: step,
                    status: 'success' as const
                  }))
                ).map((step: any, index: number, arr: any[]) => {
                  const isLast = index === arr.length - 1
                  const isSuccess = step.status === 'success'
                  const isFailed = step.status === 'failed'
                  
                  return (
                    <div key={index} className="flex items-start gap-3 pb-4 last:pb-0">
                      {/* Vertical line and dot */}
                      <div className="flex flex-col items-center">
                        <div className={cn(
                          "w-2.5 h-2.5 rounded-full shrink-0 mt-1.5",
                          isLast && isSuccess 
                            ? "bg-emerald-500 ring-2 ring-emerald-200" 
                            : isFailed
                            ? "bg-red-400"
                            : "bg-violet-400"
                        )} />
                        {index < arr.length - 1 && (
                          <div className={cn(
                            "w-0.5 flex-1 min-h-[60px]",
                            isFailed ? "bg-red-200" : "bg-gradient-to-b from-violet-300 to-violet-200"
                          )} />
                        )}
                      </div>
                      {/* Step content */}
                      <div className="flex-1 min-w-0 pb-3">
                        <div className="flex items-center gap-2">
                          <div className={cn(
                            "text-xs font-medium",
                            isLast && isSuccess 
                              ? "text-emerald-700" 
                              : isFailed
                              ? "text-red-600"
                              : "text-stone-700"
                          )}>
                            {step.description}
                          </div>
                          {step.source && (
                            <span className="text-[9px] px-1.5 py-0.5 bg-stone-100 text-stone-500 rounded font-medium">
                              {step.source}
                            </span>
                          )}
                        </div>
                        {step.output && (
                          <div className="mt-1 text-xs text-stone-600 bg-stone-50 rounded px-2 py-1">
                            {step.output}
                          </div>
                        )}
                        {step.url && (
                          <a 
                            href={step.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-1 text-[10px] text-blue-500 hover:text-blue-700 hover:underline flex items-center gap-1 truncate"
                          >
                            <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                            <span className="truncate">{step.url}</span>
                          </a>
                        )}
                        {step.reasoning && (
                          <div className={cn(
                            "mt-1 text-[10px] italic",
                            isFailed ? "text-red-500" : "text-stone-500"
                          )}>
                            {step.reasoning}
                          </div>
                        )}
                        {step.confidence !== undefined && step.confidence !== null && (
                          <div className="mt-1 flex items-center gap-1.5">
                            <div className="h-1 w-16 bg-stone-200 rounded-full overflow-hidden">
                              <div 
                                className={cn(
                                  "h-full rounded-full",
                                  step.confidence >= 0.7 ? "bg-emerald-500" :
                                  step.confidence >= 0.4 ? "bg-amber-500" : "bg-red-400"
                                )}
                                style={{ width: `${Math.round(step.confidence * 100)}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-stone-400">
                              {Math.round(step.confidence * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-stone-100">
              <button
                onClick={() => setShowEnrichmentStepsModal(false)}
                className="w-full px-3 py-2 text-xs font-medium text-stone-600 hover:bg-stone-100 rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
