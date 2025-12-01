import axios, { AxiosError, AxiosInstance } from 'axios'
import { ApiError } from '@/types'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
const API_BASE_URL = `${BACKEND_URL}/api/v1`

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

apiClient.interceptors.request.use(
  (config) => {
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }

    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
    const isAuthEndpoint = config.url?.includes('/auth/')

    if (!isAuthEndpoint && token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token')
        window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  }
)

export { apiClient, API_BASE_URL, BACKEND_URL }

