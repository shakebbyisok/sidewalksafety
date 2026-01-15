import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { propertyAnalysisApi } from '@/lib/api/property-analysis'
import type { PropertyAnalysisRequest } from '@/types'

/**
 * Hook to fetch a single property analysis.
 * Automatically refetches while status is 'processing'.
 */
export function usePropertyAnalysis(analysisId: string | undefined) {
  return useQuery({
    queryKey: ['property-analysis', analysisId],
    queryFn: () => propertyAnalysisApi.getAnalysis(analysisId!),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      // Refetch every 3 seconds while processing
      const data = query.state.data
      if (data?.status === 'processing' || data?.status === 'pending') {
        return 3000
      }
      return false
    },
  })
}

/**
 * Hook to list property analyses.
 */
export function usePropertyAnalyses(params?: {
  limit?: number
  offset?: number
  status?: string
}) {
  return useQuery({
    queryKey: ['property-analyses', params],
    queryFn: () => propertyAnalysisApi.listAnalyses(params),
  })
}

/**
 * Hook to start a new property analysis.
 */
export function useStartPropertyAnalysis() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: PropertyAnalysisRequest) => 
      propertyAnalysisApi.startAnalysis(request),
    onSuccess: () => {
      // Invalidate analyses list
      queryClient.invalidateQueries({ queryKey: ['property-analyses'] })
    },
  })
}

/**
 * Hook to get analysis for a specific deal/parking lot.
 */
export function usePropertyAnalysisForDeal(dealId: string | undefined) {
  return useQuery({
    queryKey: ['property-analysis', 'deal', dealId],
    queryFn: async () => {
      // List analyses and find one matching the deal
      const response = await propertyAnalysisApi.listAnalyses({ limit: 100 })
      return response.results.find(a => a.parking_lot_id === dealId) || null
    },
    enabled: !!dealId,
  })
}


