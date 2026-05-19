import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/chat'

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

describe('chatStore streaming', () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage()
    setActivePinia(createPinia())
    localStorage.setItem('pacer_token', 'tk')
  })

  it('send returns message id after ack', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 42, assistant_message_id: 99 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    const mid = await s.send('hello')
    expect(mid).toBe(99)
    expect(s.messages.length).toBe(2) // user + placeholder
    expect(s.messages[1].streaming).toBe(true)
    expect(s.messages[1].content).toBe('')
  })

  it('appendDelta adds text to the streaming message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'Hello' })
    s.receiveDelta({ message_id: 10, delta: ' world' })
    expect(s.messages[1].content).toBe('Hello world')
    expect(s.messages[1].streaming).toBe(true)
    expect(s.isStreaming).toBe(true)
  })

  it('finalizeStream seals the message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'Done' })
    s.receiveDone({ message_id: 10, agent: 'subject_teacher', stop_reason: 'completed' })
    expect(s.messages[1].streaming).toBe(false)
    expect(s.isStreaming).toBe(false)
    expect(s.messages[1].agent).toBe('subject_teacher')
  })

  it('stopStreaming marks message as stopped', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
          status: 202,
          headers: { 'content-type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'partial' })
    await s.stopStreaming()
    expect(s.messages[1].streaming).toBe(false)
    expect(s.isStreaming).toBe(false)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/message/10/stop',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('reset clears streaming state', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'x' })
    s.reset()
    expect(s.messages).toEqual([])
    expect(s.isStreaming).toBe(false)
  })

  it('ignores deltas for unknown message_id', () => {
    const s = useChatStore()
    s.receiveDelta({ message_id: 999, delta: 'orphan' })
    expect(s.messages.length).toBe(0)
  })
})
