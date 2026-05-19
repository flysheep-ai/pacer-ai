import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSessionStore } from '@/stores/session'

describe('useSessionStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts with no current session', () => {
    const s = useSessionStore()
    expect(s.currentSid).toBeNull()
  })

  it('reset clears the sid', () => {
    const s = useSessionStore()
    s.currentSid = 5
    s.reset()
    expect(s.currentSid).toBeNull()
  })
})
