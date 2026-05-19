import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter } from '@/router'
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

describe('router guards', () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage()
    setActivePinia(createPinia())
  })

  it('redirects authenticated user from / to /chat', async () => {
    localStorage.setItem('pacer_token', 'tk')
    localStorage.setItem('pacer_student_id', '1')
    void useAuthStore()
    const router = createRouter()
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/chat')
  })

  it('redirects unauthenticated user from /chat to /', async () => {
    const router = createRouter()
    await router.push('/chat')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('lets authenticated user visit /chat', async () => {
    localStorage.setItem('pacer_token', 'tk')
    void useAuthStore()
    const router = createRouter()
    await router.push('/chat')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/chat')
  })
})
