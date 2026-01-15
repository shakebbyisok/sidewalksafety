'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

export interface DiscoveryProgress {
  type: 'started' | 'searching' | 'found' | 'processing' | 'imagery' | 'analyzing' | 'scoring' | 'enriching' | 'contact_found' | 'progress' | 'complete' | 'error'
  message: string
  details?: string
  current?: number
  total?: number
  address?: string
  owner?: string
  score?: number
  phone?: string
  email?: string
  company?: string
  stats?: {
    found?: number
    analyzed?: number
    enriched?: number
    duration?: string
    cost?: string
  }
}

interface StreamDiscoveryParams {
  area_type: 'zip' | 'county'
  value: string
  state?: string
  max_results?: number
  business_type_ids?: string[]
  scoring_prompt?: string
  mode?: 'business_first' | 'contact_first' | 'regrid_first'
  city?: string
  job_titles?: string[]
  industries?: string[]
  property_categories?: string[]
  min_acres?: number
  max_acres?: number
}

export function useDiscoveryStream() {
  const [isStreaming, setIsStreaming] = useState(false)
  const [progress, setProgress] = useState<DiscoveryProgress[]>([])
  const [currentMessage, setCurrentMessage] = useState<DiscoveryProgress | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const queryClient = useQueryClient()

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsStreaming(false)
  }, [])

  const startStream = useCallback(async (params: StreamDiscoveryParams) => {
    // Reset state
    setProgress([])
    setCurrentMessage(null)
    setIsStreaming(true)

    try {
      // Get auth token
      const token = localStorage.getItem('auth_token')
      if (!token) {
        throw new Error('Not authenticated')
      }

      // Build request body
      const body = {
        area_type: params.area_type,
        value: params.value,
        state: params.state,
        max_results: params.max_results || 10,
        business_type_ids: params.business_type_ids,
        scoring_prompt: params.scoring_prompt,
        mode: params.mode || 'regrid_first',
        city: params.city,
        job_titles: params.job_titles,
        industries: params.industries,
        property_categories: params.property_categories,
        min_acres: params.min_acres,
        max_acres: params.max_acres,
      }

      // Use fetch with ReadableStream for SSE (EventSource doesn't support POST with body)
      const baseUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
      const response = await fetch(`${baseUrl}/api/v1/discover/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`Discovery failed: ${response.statusText}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        
        // Parse SSE events
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as DiscoveryProgress
              setProgress(prev => [...prev, data])
              setCurrentMessage(data)

              // Handle completion
              if (data.type === 'complete') {
                const stats = data.stats
                toast.success(data.message, {
                  description: stats 
                    ? `Found ${stats.found} properties, enriched ${stats.enriched} contacts`
                    : undefined
                })
                // Refresh deals list
                queryClient.invalidateQueries({ queryKey: ['deals'] })
                queryClient.invalidateQueries({ queryKey: ['parking-lots'] })
              } else if (data.type === 'error') {
                toast.error(data.message)
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e)
            }
          }
        }
      }
    } catch (error) {
      console.error('Stream error:', error)
      const errorMsg = error instanceof Error ? error.message : 'Discovery failed'
      toast.error(errorMsg)
      setProgress(prev => [...prev, { type: 'error', message: errorMsg, icon: '❌' }])
    } finally {
      setIsStreaming(false)
    }
  }, [queryClient])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopStream()
    }
  }, [stopStream])

  return {
    startStream,
    stopStream,
    isStreaming,
    progress,
    currentMessage,
    clearProgress: () => setProgress([]),
  }
}
