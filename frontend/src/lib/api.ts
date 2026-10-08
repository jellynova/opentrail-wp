import axios from 'axios'
import { useAuthStore } from '../store/auth'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true, // for httpOnly refresh cookie
})

// Request interceptor: attach Bearer token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response interceptor: handle 401, attempt token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    const axiosError = error as {
      response?: { status: number }
      config: { _retry?: boolean; headers: Record<string, string> } & Parameters<typeof api>[0]
    }
    if (axiosError.response?.status === 401 && !axiosError.config._retry) {
      axiosError.config._retry = true
      try {
        const res = await axios.post('/api/v1/auth/refresh', {}, { withCredentials: true })
        const { access_token } = res.data as { access_token: string }
        useAuthStore.getState().setAuth(useAuthStore.getState().user!, access_token)
        axiosError.config.headers.Authorization = `Bearer ${access_token}`
        return api(axiosError.config)
      } catch {
        useAuthStore.getState().clearAuth()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
