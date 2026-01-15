import { apiClient } from './client'

export interface ScoringPrompt {
  id: string
  title: string
  prompt: string
  is_default: boolean
  created_at: string
  updated_at: string | null
}

export interface CreateScoringPromptRequest {
  title: string
  prompt: string
  is_default?: boolean
}

export interface UpdateScoringPromptRequest {
  title?: string
  prompt?: string
  is_default?: boolean
}

export const scoringPromptsApi = {
  list: async (): Promise<ScoringPrompt[]> => {
    const response = await apiClient.get('/scoring-prompts')
    return response.data
  },

  get: async (id: string): Promise<ScoringPrompt> => {
    const response = await apiClient.get(`/scoring-prompts/${id}`)
    return response.data
  },

  create: async (data: CreateScoringPromptRequest): Promise<ScoringPrompt> => {
    const response = await apiClient.post('/scoring-prompts', data)
    return response.data
  },

  update: async (id: string, data: UpdateScoringPromptRequest): Promise<ScoringPrompt> => {
    const response = await apiClient.patch(`/scoring-prompts/${id}`, data)
    return response.data
  },

  delete: async (id: string): Promise<{ message: string }> => {
    const response = await apiClient.delete(`/scoring-prompts/${id}`)
    return response.data
  },
}

