import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSessionStore } from '@/stores/session'

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

describe('useSessionStore', () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage()
    setActivePinia(createPinia())
  })

  it('starts with no current session and empty list', () => {
    const s = useSessionStore()
    expect(s.currentSid).toBeNull()
    expect(s.sessions).toEqual([])
  })

  it('fetchList populates sessions', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: 1, title: 'hello', last_msg_at: null, message_count: 3 }]), {
        status: 200, headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useSessionStore()
    await s.fetchList()
    expect(s.sessions.length).toBe(1)
    expect(s.sessions[0].title).toBe('hello')
  })

  it('deleteSession removes from list', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    const s = useSessionStore()
    s.sessions = [{ id: 1, title: 'x', last_msg_at: null, message_count: 1 }]
    await s.deleteSession(1)
    expect(s.sessions.length).toBe(0)
  })

  it('selectSession sets currentSid', () => {
    const s = useSessionStore()
    s.selectSession(5)
    expect(s.currentSid).toBe(5)
  })

  it('reset clears currentSid', () => {
    const s = useSessionStore()
    s.currentSid = 5
    s.reset()
    expect(s.currentSid).toBeNull()
  })
})
