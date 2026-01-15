import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { dealsApi } from '../api/deals'
import { GeographicSearchRequest } from '@/types'
import { toast } from '@/hooks/use-toast'

// Stale time: 30 seconds - data is considered fresh for 30s
const STALE_TIME = 30 * 1000

// Cache time: 5 minutes - keep data in cache for 5 minutes after it becomes stale
const CACHE_TIME = 5 * 60 * 1000

// Refetch interval: 60 seconds - only refetch if window is focused
const REFETCH_INTERVAL = 60 * 1000

export function useDeals(status?: string) {
  return useQuery({
    queryKey: ['deals', status],
    queryFn: () => dealsApi.getDeals(status),
    staleTime: STALE_TIME,
    gcTime: CACHE_TIME,
    refetchInterval: REFETCH_INTERVAL,
    refetchIntervalInBackground: false, // Don't refetch when tab is not visible
  })
}

export function useDeal(id: string) {
  return useQuery({
    queryKey: ['deals', id],
    queryFn: () => dealsApi.getDeal(id),
    enabled: !!id,
    staleTime: STALE_TIME,
    gcTime: CACHE_TIME,
  })
}

export interface MapBounds {
  minLat?: number
  maxLat?: number
  minLng?: number
  maxLng?: number
}

export function useDealsForMap(params?: MapBounds & { status?: string }) {
  return useQuery({
    queryKey: ['deals', 'map', params],
    queryFn: () => dealsApi.getDealsForMap(params),
    staleTime: STALE_TIME,
    gcTime: CACHE_TIME,
    refetchInterval: REFETCH_INTERVAL,
    refetchIntervalInBackground: false,
    // Keep previous data while fetching new bounds
    placeholderData: (previousData) => previousData,
  })
}

export function useScrapeDeals() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: GeographicSearchRequest) => dealsApi.discover(request),
    onSuccess: (data, variables) => {
      // Invalidate after a short delay to allow backend to process
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['deals'] })
      }, 3000)
      
      const isContactFirst = variables.mode === 'contact_first'
      toast({
        title: isContactFirst ? 'Lead Discovery Started' : 'Property Discovery Started',
        description: isContactFirst 
          ? 'Finding decision-maker contacts and their properties...'
          : 'Discovering properties. They will appear on the map as found.',
      })
    },
    onError: (error: any) => {
      toast({
        variant: 'destructive',
        title: 'Discovery failed',
        description: error.response?.data?.detail || 'Failed to start discovery',
      })
    },
  })
}
