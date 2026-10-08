import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import type { User } from '@/types'

interface LoginCredentials {
  username: string
  password: string
}

interface LoginResponse {
  access_token: string
  token_type: string
}

export function useLogin() {
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async (credentials: LoginCredentials) => {
      // OAuth2 password grant uses form-urlencoded
      const params = new URLSearchParams()
      params.append('username', credentials.username)
      params.append('password', credentials.password)
      const res = await api.post<LoginResponse>('/v1/auth/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      return res.data
    },
    onSuccess: async (data) => {
      // Fetch user info after login
      const meRes = await api.get<User>('/v1/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      setAuth(meRes.data, data.access_token)
      navigate('/')
    },
  })
}

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => api.get<User>('/v1/auth/me').then((r) => r.data),
    staleTime: 1000 * 60 * 10,
  })
}
