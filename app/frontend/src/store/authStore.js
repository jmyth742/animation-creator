import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { post, get } from '../api/client'

export const useAuthStore = create(
  persist(
    (set, getState) => ({
      token: null,
      user: null,

      login: async (email, password) => {
        const data = await post('/auth/login', { email, password })
        localStorage.setItem('sb_token', data.token)
        set({ token: data.token, user: data.user })
        return data.user
      },

      register: async (email, password) => {
        const data = await post('/auth/register', { email, password })
        localStorage.setItem('sb_token', data.token)
        set({ token: data.token, user: data.user })
        return data.user
      },

      logout: () => {
        localStorage.removeItem('sb_token')
        set({ token: null, user: null })
      },

      fetchMe: async () => {
        try {
          const user = await get('/auth/me')
          set({ user })
          return user
        } catch {
          // Token may be invalid — clear it
          localStorage.removeItem('sb_token')
          set({ token: null, user: null })
        }
      },
    }),
    {
      name: 'auth_storage',
      partialize: (state) => ({ token: state.token, user: state.user }),
    }
  )
)
