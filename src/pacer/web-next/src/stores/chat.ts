import { defineStore } from 'pinia'
import { apiFetch } from '@/api/client'
import { useSessionStore } from './session'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  agent?: string
}

interface SendResponse {
  text: string
  session_id: number
  agent: string
}

interface AssistantPayload {
  session_id: number
  text: string
  agent: string
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as ChatMessage[],
    isAwaiting: false,
    _lastAssistantContent: null as string | null,
  }),
  actions: {
    reset(): void {
      this.messages = []
      this.isAwaiting = false
      this._lastAssistantContent = null
    },

    receiveAssistantMessage(payload: AssistantPayload): void {
      const session = useSessionStore()
      session.currentSid = payload.session_id
      if (this._lastAssistantContent === payload.text) return
      this._lastAssistantContent = payload.text
      this.messages.push({ role: 'assistant', content: payload.text, agent: payload.agent })
      this.isAwaiting = false
    },

    async send(text: string): Promise<void> {
      const trimmed = text.trim()
      if (!trimmed) return
      this.messages.push({ role: 'user', content: trimmed })
      this.isAwaiting = true
      const session = useSessionStore()

      try {
        const r = await apiFetch<SendResponse>('/message/send', {
          method: 'POST',
          json: { text: trimmed, session_id: session.currentSid },
        })
        session.currentSid = r.session_id
        if (this._lastAssistantContent !== r.text) {
          this._lastAssistantContent = r.text
          this.messages.push({ role: 'assistant', content: r.text, agent: r.agent })
        }
      } catch {
        this.messages.push({ role: 'assistant', content: '出错了，请稍后重试。' })
      } finally {
        this.isAwaiting = false
      }
    },
  },
})
