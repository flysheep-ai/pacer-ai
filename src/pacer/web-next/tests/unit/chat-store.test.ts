import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'

/**
 * happy-dom v15 exposes localStorage as a plain object without Storage prototype methods.
 * We mock it so both the store initialization and test assertions work.
 */
function mockStorage(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: vi.fn((k: string) => store[k] ?? null),
    setItem: vi.fn((k: string, v: string) => { store[k] = String(v) }),
    removeItem: vi.fn((k: string) => { delete store[k] }),
    clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]) }),
    get length() { return Object.keys(store).length },
    key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
  } as unknown as Storage
}

describe('useChatStore', () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage()
    setActivePinia(createPinia())
    localStorage.setItem('pacer_token', 'tk')
  })

  it('starts empty and not awaiting', () => {
    const s = useChatStore()
    expect(s.messages).toEqual([])
    expect(s.isAwaiting).toBe(false)
  })

  it('send pushes a user message immediately', async () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {})) as unknown as typeof fetch
    const s = useChatStore()
    void s.send('hello')
    expect(s.messages.length).toBe(1)
    expect(s.messages[0].role).toBe('user')
    expect(s.messages[0].content).toBe('hello')
    expect(s.isAwaiting).toBe(true)
  })

  it('send appends placeholder assistant from 202 ack', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        session_id: 42, assistant_message_id: 99,
      }), { status: 202, headers: { 'content-type': 'application/json' } }),
    )
    const s = useChatStore()
    await s.send('hello')
    expect(s.messages.length).toBe(2)
    expect(s.messages[1].role).toBe('assistant')
    expect(s.messages[1].content).toBe('')
    expect(s.messages[1].streaming).toBe(true)
    expect(s.messages[1].messageId).toBe(99)
    const session = useSessionStore()
    expect(session.currentSid).toBe(42)
  })

  it('receiveAssistantMessage adds assistant and stops awaiting', () => {
    const s = useChatStore()
    s.isAwaiting = true
    s.receiveAssistantMessage({ session_id: 42, text: 'hi', agent: 'homeroom' })
    expect(s.messages.length).toBe(1)
    expect(s.messages[0].role).toBe('assistant')
    expect(s.messages[0].content).toBe('hi')
    expect(s.isAwaiting).toBe(false)
  })

  it('deduplicates legacy assistant message via _lastAssistantContent', () => {
    const s = useChatStore()
    s.receiveAssistantMessage({ session_id: 42, text: 'reply', agent: 'homeroom' })
    expect(s.messages.filter(m => m.role === 'assistant').length).toBe(1)
    s.receiveAssistantMessage({ session_id: 42, text: 'reply', agent: 'homeroom' })
    expect(s.messages.filter(m => m.role === 'assistant').length).toBe(1)
  })

  it('reset clears messages and isAwaiting', () => {
    const s = useChatStore()
    s.messages.push({ role: 'user', content: 'x' })
    s.isAwaiting = true
    s.reset()
    expect(s.messages).toEqual([])
    expect(s.isAwaiting).toBe(false)
  })

  it('send marks error when network fails', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('net'))
    const s = useChatStore()
    await s.send('hello')
    expect(s.isAwaiting).toBe(false)
    expect(s.messages.length).toBe(2)
    expect(s.messages[1].role).toBe('assistant')
    expect(s.messages[1].content).toMatch(/出错/)
  })
})
