import { defineStore } from 'pinia'
import { apiFetch } from '@/api/client'
import { i18n } from '@/i18n'
import { useSessionStore } from './session'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  agent?: string
  streaming?: boolean
  stopReason?: string
  messageId?: number
  imageBase64?: string
}

interface SendAck {
  session_id: number
  assistant_message_id: number
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
    _streamingMid: null as number | null,
    _lastAssistantContent: null as string | null,
  }),
  getters: {
    isStreaming: (s) => s._streamingMid !== null,
  },
  actions: {
    reset(): void {
      this.messages = []
      this.isAwaiting = false
      this._streamingMid = null
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

    async send(text: string, imageBase64?: string): Promise<number | null> {
      const trimmed = text.trim()
      if (!trimmed && !imageBase64) return null
      this.messages.push({ role: 'user', content: trimmed, imageBase64 })
      this.isAwaiting = true
      const session = useSessionStore()

      try {
        const body: Record<string, unknown> = { text: trimmed, session_id: session.currentSid }
        if (imageBase64) body.image_base64 = imageBase64
        const r = await apiFetch<SendAck>('/message/send', {
          method: 'POST',
          json: body,
        })
        session.currentSid = r.session_id
        this.messages.push({
          role: 'assistant',
          content: '',
          streaming: true,
          messageId: r.assistant_message_id,
        })
        this._streamingMid = r.assistant_message_id
        return r.assistant_message_id
      } catch {
        this.messages.push({ role: 'assistant', content: i18n.global.t('chat.errorRetry') })
        this.isAwaiting = false
        return null
      }
    },

    receiveDelta(payload: { message_id: number; delta: string }): void {
      const target = this.messages.find(
        (m) => m.streaming === true && m.messageId === payload.message_id,
      )
      if (target) {
        target.content += payload.delta
      }
    },

    receiveDone(payload: { message_id: number; agent: string; stop_reason: string }): void {
      const target = this.messages.find(
        (m) => m.streaming === true && m.messageId === payload.message_id,
      )
      if (target) {
        target.streaming = false
        target.agent = payload.agent
        if (payload.stop_reason === 'user_stopped') {
          target.stopReason = 'user_stopped'
        }
      }
      this.isAwaiting = false
      this._streamingMid = null
    },

    async loadHistory(sid: number): Promise<void> {
      this.reset()
      try {
        const msgs = await apiFetch<Array<{
          id: number; role: string; agent: string | null;
          content: string; status: string | null;
        }>>(`/sessions/${sid}/messages`)
        this.messages = msgs.map(m => {
          let content = m.content
          let imageBase64: string | undefined
          if (m.role === 'user' && m.content.startsWith('{')) {
            try {
              const parsed = JSON.parse(m.content) as { text: string; image_base64?: string }
              content = parsed.text
              imageBase64 = parsed.image_base64
            } catch { /* not JSON, keep as-is */ }
          }
          return {
            role: m.role as 'user' | 'assistant',
            content,
            agent: m.agent ?? undefined,
            streaming: m.status === 'streaming',
            stopReason: m.status === 'failed' && m.role === 'assistant' ? 'user_stopped' : undefined,
            imageBase64,
          }
        })
      } catch {
        this.messages = []
      }
    },

    async stopStreaming(): Promise<void> {
      const mid = this._streamingMid
      if (mid === null) return
      try {
        await apiFetch(`/message/${mid}/stop`, { method: 'POST' })
      } catch {
        // Best-effort; mark the message as stopped regardless
      }
      const target = this.messages.find(
        (m) => m.streaming === true && m.messageId === mid,
      )
      if (target) {
        target.streaming = false
        target.stopReason = 'user_stopped'
      }
      this.isAwaiting = false
      this._streamingMid = null
    },
  },
})
