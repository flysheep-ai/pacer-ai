import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { startSSE, _setEventSourceImpl, _resetEventSourceImpl } from '@/api/sse'

class FakeEventSource {
  url: string
  onerror: ((e: Event) => void) | null = null
  static instances: FakeEventSource[] = []
  private listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(name: string, fn: (e: MessageEvent) => void): void {
    (this.listeners[name] ||= []).push(fn)
  }
  removeEventListener(): void {}
  close(): void {}
  emit(name: string, data: unknown): void {
    const ev = { data: JSON.stringify(data) } as unknown as MessageEvent
    this.listeners[name]?.forEach(fn => fn(ev))
  }
  emitError(): void { this.onerror?.(new Event('error')) }
}

describe('startSSE streaming events', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    _setEventSourceImpl(FakeEventSource as unknown as typeof EventSource)
    vi.useFakeTimers()
  })
  afterEach(() => {
    _resetEventSourceImpl()
    vi.useRealTimers()
  })

  it('dispatches assistant_start', () => {
    const h = vi.fn()
    startSSE('tk', { onAssistantMessage: () => {}, onAssistantStart: h, onAssistantDelta: () => {}, onAssistantDone: () => {} })
    FakeEventSource.instances[0].emit('assistant_start', { session_id: 1, message_id: 42, agent: 'a' })
    expect(h).toHaveBeenCalledWith({ session_id: 1, message_id: 42, agent: 'a' })
  })

  it('dispatches assistant_delta', () => {
    const h = vi.fn()
    startSSE('tk', { onAssistantMessage: () => {}, onAssistantStart: () => {}, onAssistantDelta: h, onAssistantDone: () => {} })
    FakeEventSource.instances[0].emit('assistant_delta', { message_id: 42, delta: 'hello' })
    expect(h).toHaveBeenCalledWith({ message_id: 42, delta: 'hello' })
  })

  it('dispatches assistant_done', () => {
    const h = vi.fn()
    startSSE('tk', { onAssistantMessage: () => {}, onAssistantStart: () => {}, onAssistantDelta: () => {}, onAssistantDone: h })
    FakeEventSource.instances[0].emit('assistant_done', { message_id: 42, agent: 'x', stop_reason: 'completed' })
    expect(h).toHaveBeenCalledWith({ message_id: 42, agent: 'x', stop_reason: 'completed' })
  })

  it('legacy assistant_message still fires', () => {
    const h = vi.fn()
    startSSE('tk', { onAssistantMessage: h })
    FakeEventSource.instances[0].emit('assistant_message', { session_id: 1, text: 'hi', agent: 'a' })
    expect(h).toHaveBeenCalled()
  })

  it('new handlers are optional', () => {
    expect(() => startSSE('tk', { onAssistantMessage: () => {} })).not.toThrow()
  })
})
