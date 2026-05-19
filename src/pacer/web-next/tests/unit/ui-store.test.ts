import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUiStore } from '@/stores/ui'

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

describe('useUiStore', () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage()
    setActivePinia(createPinia())
    document.documentElement.removeAttribute('data-theme')
  })

  it('defaults to light', () => {
    const s = useUiStore()
    expect(s.theme).toBe('light')
  })

  it('hydrates dark from localStorage', () => {
    localStorage.setItem('pacer_theme', 'dark')
    const s = useUiStore()
    expect(s.theme).toBe('dark')
  })

  it('applyTheme writes the documentElement attribute', () => {
    const s = useUiStore()
    s.theme = 'dark'
    s.applyTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('toggleTheme flips and persists', () => {
    const s = useUiStore()
    s.toggleTheme()
    expect(s.theme).toBe('dark')
    expect(localStorage.getItem('pacer_theme')).toBe('dark')
    s.toggleTheme()
    expect(s.theme).toBe('light')
    expect(localStorage.getItem('pacer_theme')).toBe('light')
  })

  it('applyTheme removes attribute for light theme', () => {
    document.documentElement.setAttribute('data-theme', 'dark')
    const s = useUiStore()
    s.theme = 'light'
    s.applyTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })
})
