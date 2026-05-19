import { describe, it, expect, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useAutoScroll } from '@/composables/useAutoScroll'
import { useToast, _resetToastsForTest } from '@/composables/useToast'

describe('useAutoScroll', () => {
  it('scrolls element to bottom when watched value changes', async () => {
    const el = document.createElement('div')
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true })
    el.scrollTop = 0
    const r = ref(el as HTMLElement | null)
    const dep = ref(0)
    useAutoScroll(r, dep)
    dep.value = 1
    await nextTick()
    expect(el.scrollTop).toBe(1000)
  })
})

describe('useToast', () => {
  beforeEach(() => _resetToastsForTest())

  it('push adds a toast', () => {
    const { toasts, push } = useToast()
    push({ type: 'info', text: 'hi' })
    expect(toasts.value.length).toBe(1)
    expect(toasts.value[0].text).toBe('hi')
  })

  it('dismiss removes a toast', () => {
    const { toasts, push, dismiss } = useToast()
    const id = push({ type: 'error', text: 'bad' })
    dismiss(id)
    expect(toasts.value.length).toBe(0)
  })

  it('caps at 3 concurrent toasts', () => {
    const { toasts, push } = useToast()
    push({ type: 'info', text: '1' })
    push({ type: 'info', text: '2' })
    push({ type: 'info', text: '3' })
    push({ type: 'info', text: '4' })
    expect(toasts.value.length).toBe(3)
    expect(toasts.value[0].text).toBe('2')
  })
})
