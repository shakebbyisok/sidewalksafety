import { apiClient } from './client'
import { Token, UserCreate, UserLogin, User } from '@/types'

export const authApi = {
  register: async (data: UserCreate): Promise<Token> => {
    const { data: response } = await apiClient.post<Token>('/auth/register', data)
    return response
  },

  login: async (data: UserLogin): Promise<Token> => {
    const { data: response } = await apiClient.post<Token>('/auth/login', data)
    return response
  },

  getCurrentUser: async (): Promise<User> => {
    const { data } = await apiClient.get<User>('/auth/me')
    return data
  },
}

