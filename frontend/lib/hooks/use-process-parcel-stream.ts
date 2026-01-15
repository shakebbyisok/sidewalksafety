'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

export interface ProcessParcelProgress {
  type: 
    | 'started' 
    | 'regrid' 
    | 'regrid_complete' 
    | 'regrid_warning' 
    | 'regrid_error'
    | 'classifying' 
    | 'classified'
    | 'imagery' 
    | 'imagery_complete' 
    | 'imagery_error'
    | 'analyzing' 
    | 'analyzing_error'
    | 'scoring'
    | 'enriching' 
    | 'enrichment_complete'
    | 'enrichment_error'
    | 'contact_found' 
    | 'complete' 
    | 'error'
  message: string
  details?: string
  category?: string
  score?: number
  reasoning?: string
  zoom?: number
  phone?: string
  email?: string
  company?: string
  confidence?: number
  steps_taken?: number
  stats?: {
    lead_score?: number | null
    has_contact?: boolean
    duration?: string
    cost?: string | null
  }
}

interface ProcessParcelParams {
  propertyId: string
  scoringPromptId?: string
  customPrompt?: string
}

export function useProcessParcelStream() {
  const [isProcessing, setIsProcessing] = useState(false)
  const [progress, setProgress] = useState<ProcessParcelProgress[]>([])
  const [currentMessage, setCurrentMessage] = useState<ProcessParcelProgress | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const queryClient = useQueryClient()

  const stopProcessing = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsProcessing(false)
  }, [])

  const startProcessing = useCallback(async (params: ProcessParcelParams) => {
    // Reset state
    setProgress([])
    setCurrentMessage(null)
    setIsProcessing(true)

    // Create abort controller
    abortControllerRef.current = new AbortController()

    try {
      // Get auth token
      const token = localStorage.getItem('auth_token')
      if (!token) {
        throw new Error('Not authenticated')
      }

      // Build request body
      const body: Record<string, string | undefined> = {}
      if (params.scoringPromptId) {
        body.scoring_prompt_id = params.scoringPromptId
      }
      if (params.customPrompt) {
        body.custom_prompt = params.customPrompt
      }

      // Use fetch with ReadableStream for SSE
      const baseUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
      const response = await fetch(
        `${baseUrl}/api/v1/parking-lots/${params.propertyId}/process/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache',
          },
          body: JSON.stringify(body),
          signal: abortControllerRef.current.signal,
        }
      )

      if (!response.ok) {
        throw new Error(`Processing failed: ${response.statusText}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      // Process stream in real-time
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true })
        
        // Process all complete lines in the buffer
        let newlineIndex
        while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
          const line = buffer.slice(0, newlineIndex).trim()
          buffer = buffer.slice(newlineIndex + 1)
          
          // Skip empty lines
          if (!line) continue
          
          // Parse SSE data line
          if (line.startsWith('data: ')) {
            try {
              const jsonStr = line.slice(6)
              const data = JSON.parse(jsonStr) as ProcessParcelProgress
              
              // Update state immediately for real-time feel
              setProgress(prev => [...prev, data])
              setCurrentMessage(data)

              // Handle completion
              if (data.type === 'complete') {
                const stats = data.stats
                if (stats?.has_contact) {
                  toast.success('Contact found', {
                    description: `Lead score: ${stats.lead_score || 'N/A'}/100`
                  })
                } else {
                  toast.info('Processing complete', {
                    description: stats?.lead_score 
                      ? `Lead score: ${stats.lead_score}/100`
                      : 'Property processed'
                  })
                }
                // Refresh property data
                queryClient.invalidateQueries({ queryKey: ['parking-lot', params.propertyId] })
                queryClient.invalidateQueries({ queryKey: ['parking-lots'] })
              } else if (data.type === 'error') {
                toast.error(data.message)
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e, line)
            }
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Cancelled by user
        return
      }
      console.error('Process stream error:', error)
      const errorMsg = error instanceof Error ? error.message : 'Processing failed'
      toast.error(errorMsg)
      setProgress(prev => [...prev, { type: 'error', message: errorMsg }])
    } finally {
      setIsProcessing(false)
    }
  }, [queryClient])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopProcessing()
    }
  }, [stopProcessing])

  return {
    startProcessing,
    stopProcessing,
    isProcessing,
    progress,
    currentMessage,
    clearProgress: () => {
      setProgress([])
      setCurrentMessage(null)
    },
  }
}
