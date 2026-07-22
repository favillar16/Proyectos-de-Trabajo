import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import api from '../services/api'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      usuario: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,

      login: async (username, password) => {
        const response = await api.post('/auth/login/', { username, password })
        const { access, refresh, ...userData } = response.data

        // Guardar token en axios
        api.defaults.headers.common['Authorization'] = `Bearer ${access}`

        set({
          token: access,
          refreshToken: refresh,
          isAuthenticated: true,
        })

        // Obtener datos del usuario
        const meResponse = await api.get('/usuarios/me/')
        set({ usuario: meResponse.data })

        return meResponse.data
      },

      logout: () => {
        delete api.defaults.headers.common['Authorization']
        set({
          usuario: null,
          token: null,
          refreshToken: null,
          isAuthenticated: false,
        })
      },

      refreshAccessToken: async () => {
        const { refreshToken } = get()
        if (!refreshToken) return null

        const response = await api.post('/auth/refresh/', { refresh: refreshToken })
        const { access } = response.data

        api.defaults.headers.common['Authorization'] = `Bearer ${access}`
        set({ token: access })

        return access
      },

      setUsuario: (usuario) => set({ usuario }),
    }),
    {
      name: 'ceramica-auth',
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        usuario: state.usuario,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
