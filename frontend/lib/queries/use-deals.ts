import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { dealsApi } from '../api/deals'
import { GeographicSearchRequest } from '@/types'
import { toast } from '@/hooks/use-toast'

export function useDeals(status?: string) {
  return useQuery({
    queryKey: ['deals', status],
    queryFn: () => dealsApi.getDeals(status),
  })
}

export function useDeal(id: string) {
  return useQuery({
    queryKey: ['deals', id],
    queryFn: () => dealsApi.getDeal(id),
    enabled: !!id,
  })
}

export function useDealsForMap(params?: {
  min_lat?: number
  max_lat?: number
  min_lng?: number
  max_lng?: number
  status?: string
}) {
  return useQuery({
    queryKey: ['deals', 'map', params],
    queryFn: () => dealsApi.getDealsForMap(params),
  })
}

export function useScrapeDeals() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: GeographicSearchRequest) => dealsApi.scrape(request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['deals'] })
      toast({
        title: 'Scraping completed',
        description: data.message,
      })
    },
    onError: (error: any) => {
      toast({
        variant: 'destructive',
        title: 'Scraping failed',
        description: error.response?.data?.detail || 'Failed to scrape deals',
      })
    },
  })
}

