import { defineStore } from 'pinia'
import { apiFetch } from '@/api/client'
import { useSessionStore } from './session'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  agent?: string
  streaming?: boolean
  stopReason?: string
  messageId?: number
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

    async send(text: string): Promise<number | null> {
      const trimmed = text.trim()
      if (!trimmed) return null
      this.messages.push({ role: 'user', content: trimmed })
      this.isAwaiting = true
      const session = useSessionStore()

      try {
        const r = await apiFetch<SendAck>('/message/send', {
          method: 'POST',
          json: { text: trimmed, session_id: session.currentSid },
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
        this.messages.push({ role: 'assistant', content: '出错了，请稍后重试。' })
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
