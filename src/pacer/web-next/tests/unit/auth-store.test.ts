import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

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

describe('useAuthStore', () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('starts unauthenticated by default', () => {
    const s = useAuthStore()
    expect(s.isAuthenticated).toBe(false)
    expect(s.token).toBeNull()
  })

  it('hydrates from localStorage on first access', () => {
    localStorage.setItem('pacer_token', 'tk')
    localStorage.setItem('pacer_student_id', '42')
    const s = useAuthStore()
    expect(s.isAuthenticated).toBe(true)
    expect(s.token).toBe('tk')
    expect(s.studentId).toBe(42)
  })

  it('login() stores token and student id', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ token: 'tk', student_id: 7 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useAuthStore()
    await s.login(7, '0000')
    expect(s.token).toBe('tk')
    expect(s.studentId).toBe(7)
    expect(localStorage.getItem('pacer_token')).toBe('tk')
    expect(localStorage.getItem('pacer_student_id')).toBe('7')
  })

  it('login() throws on bad credentials', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'unauthorized' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useAuthStore()
    await expect(s.login(7, 'x')).rejects.toThrow()
    expect(s.token).toBeNull()
  })

  it('logout() clears state and storage', () => {
    localStorage.setItem('pacer_token', 'tk')
    localStorage.setItem('pacer_student_id', '7')
    const s = useAuthStore()
    s.logout()
    expect(s.token).toBeNull()
    expect(s.studentId).toBeNull()
    expect(localStorage.getItem('pacer_token')).toBeNull()
    expect(localStorage.getItem('pacer_student_id')).toBeNull()
  })

  it('loadProfile() fetches and stores profile', async () => {
    localStorage.setItem('pacer_token', 'tk')
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ name: '小明', grade: 3 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useAuthStore()
    await s.loadProfile()
    expect(s.profile?.name).toBe('小明')
  })
})
