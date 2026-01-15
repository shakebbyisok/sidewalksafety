import { apiClient } from './client'

export interface UserSettings {
  email: string
  company_name: string
  phone: string | null
  has_openrouter_key: boolean
  openrouter_key_preview: string | null
  use_own_openrouter_key: boolean
  default_scoring_prompt: string | null
}

export interface UpdateOpenRouterKeyRequest {
  api_key?: string | null
  enabled: boolean
}

export interface UpdateProfileRequest {
  company_name?: string
  phone?: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

export const settingsApi = {
  getSettings: async (): Promise<UserSettings> => {
    const response = await apiClient.get('/settings')
    return response.data
  },

  updateProfile: async (data: UpdateProfileRequest): Promise<UserSettings> => {
    const response = await apiClient.patch('/settings/profile', data)
    return response.data
  },

  updateOpenRouterKey: async (data: UpdateOpenRouterKeyRequest): Promise<UserSettings> => {
    const response = await apiClient.patch('/settings/openrouter-key', data)
    return response.data
  },

  deleteOpenRouterKey: async (): Promise<UserSettings> => {
    const response = await apiClient.delete('/settings/openrouter-key')
    return response.data
  },

  updateScoringPrompt: async (scoring_prompt: string | null): Promise<UserSettings> => {
    const response = await apiClient.patch('/settings/scoring-prompt', { scoring_prompt })
    return response.data
  },

  changePassword: async (data: ChangePasswordRequest): Promise<{ message: string }> => {
    const response = await apiClient.post('/settings/change-password', data)
    return response.data
  },
}

