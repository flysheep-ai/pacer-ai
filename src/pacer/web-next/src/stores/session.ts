import { defineStore } from 'pinia'
import { apiFetch } from '@/api/client'

export interface SessionItem {
  id: number
  title: string
  last_msg_at: string | null
  message_count: number
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    currentSid: null as number | null,
    sessions: [] as SessionItem[],
    loading: false,
  }),
  actions: {
    reset(): void { this.currentSid = null },
    async fetchList(): Promise<void> {
      this.loading = true
      try { this.sessions = await apiFetch<SessionItem[]>('/sessions/') }
      catch { /* noop */ }
      finally { this.loading = false }
    },
    selectSession(sid: number): void { this.currentSid = sid },
    async deleteSession(sid: number): Promise<void> {
      await apiFetch(`/sessions/${sid}`, { method: 'DELETE' })
      this.sessions = this.sessions.filter(s => s.id !== sid)
      if (this.currentSid === sid) this.currentSid = null
    },
  },
})
