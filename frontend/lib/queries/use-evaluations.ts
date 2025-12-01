import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { evaluationsApi } from '../api/evaluations'
import { BatchEvaluateRequest } from '@/types'
import { toast } from '@/hooks/use-toast'

export function useDealWithEvaluation(dealId: string) {
  return useQuery({
    queryKey: ['deals', dealId, 'evaluation'],
    queryFn: () => evaluationsApi.getDealWithEvaluation(dealId),
    enabled: !!dealId,
  })
}

export function useEvaluateDeal() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (dealId: string) => evaluationsApi.evaluateDeal(dealId),
    onSuccess: (data, dealId) => {
      queryClient.invalidateQueries({ queryKey: ['deals', dealId] })
      queryClient.invalidateQueries({ queryKey: ['deals'] })
      toast({
        title: 'Evaluation completed',
        description: `Deal scored: ${data.deal_score?.toFixed(1) || 'N/A'}`,
      })
    },
    onError: (error: any) => {
      toast({
        variant: 'destructive',
        title: 'Evaluation failed',
        description: error.response?.data?.detail || 'Failed to evaluate deal',
      })
    },
  })
}

export function useBatchEvaluate() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: BatchEvaluateRequest) => evaluationsApi.batchEvaluate(request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['deals'] })
      toast({
        title: 'Batch evaluation completed',
        description: data.message,
      })
    },
    onError: (error: any) => {
      toast({
        variant: 'destructive',
        title: 'Batch evaluation failed',
        description: error.response?.data?.detail || 'Failed to evaluate deals',
      })
    },
  })
}

