import { defineStore } from 'pinia'
import { apiFetch, setToken } from '@/api/client'

interface Profile {
  id?: number
  name?: string
  grade?: number
  school?: string | null
  target_school?: string | null
  stream?: string | null
}

interface LoginResponse {
  token: string
  student_id: number
}

const SID_KEY = 'pacer_student_id'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('pacer_token') as string | null,
    studentId: (() => {
      const raw = localStorage.getItem(SID_KEY)
      return raw === null ? null : Number(raw)
    })() as number | null,
    profile: null as Profile | null,
  }),
  getters: {
    isAuthenticated: (s) => s.token !== null,
  },
  actions: {
    async login(studentId: number, pin: string): Promise<void> {
      const r = await apiFetch<LoginResponse>('/auth/login', {
        method: 'POST',
        json: { student_id: studentId, pin },
      })
      this.token = r.token
      this.studentId = r.student_id
      setToken(r.token)
      localStorage.setItem(SID_KEY, String(r.student_id))
    },
    logout(): void {
      this.token = null
      this.studentId = null
      this.profile = null
      setToken(null)
      localStorage.removeItem(SID_KEY)
    },
    async loadProfile(): Promise<void> {
      if (!this.token) return
      this.profile = await apiFetch<Profile>('/profile/')
    },
  },
})
