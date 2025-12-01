import { useMutation, useQuery } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { UserLogin, UserCreate } from '@/types'
import { useAuth } from '../providers/auth-provider'
import { toast } from '@/hooks/use-toast'
import { useRouter } from 'next/navigation'

export function useLogin() {
  const { login } = useAuth()
  const router = useRouter()

  return useMutation({
    mutationFn: (credentials: UserLogin) => authApi.login(credentials),
    onSuccess: (data) => {
      login(data.access_token, data.user)
      toast({
        title: 'Welcome back!',
        description: `Logged in as ${data.user.email}`,
      })
      router.push('/dashboard')
    },
    onError: (error: any) => {
      toast({
        variant: 'destructive',
        title: 'Login failed',
        description: error.response?.data?.detail || 'Invalid email or password',
      })
    },
  })
}

export function useRegister() {
  const { login } = useAuth()
  const router = useRouter()

  return useMutation({
    mutationFn: (data: UserCreate) => authApi.register(data),
    onSuccess: (response) => {
      login(response.access_token, response.user)
      toast({
        title: 'Account created!',
        description: 'Welcome to Sidewalk Safety!',
      })
      router.push('/dashboard')
    },
    onError: (error: any) => {
      const errorMessage =
        error.response?.data?.detail ||
        error.message ||
        'Could not create account. Please try again.'
      toast({
        variant: 'destructive',
        title: 'Registration failed',
        description: errorMessage,
      })
    },
  })
}

export function useCurrentUser() {
  return useQuery({
    queryKey: ['current-user'],
    queryFn: authApi.getCurrentUser,
    enabled: typeof window !== 'undefined' && !!localStorage.getItem('auth_token'),
  })
}

