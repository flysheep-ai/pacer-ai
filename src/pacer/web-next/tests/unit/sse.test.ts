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

describe('startSSE', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    _setEventSourceImpl(FakeEventSource as unknown as typeof EventSource)
    vi.useFakeTimers()
  })
  afterEach(() => {
    _resetEventSourceImpl()
    vi.useRealTimers()
  })

  it('opens with token in query string', () => {
    startSSE('tk', { onAssistantMessage: () => {} })
    expect(FakeEventSource.instances[0].url).toBe('/events/stream?token=tk')
  })

  it('dispatches assistant_message events', () => {
    const handler = vi.fn()
    startSSE('tk', { onAssistantMessage: handler })
    FakeEventSource.instances[0].emit('assistant_message', {
      session_id: 1, text: 'hi', agent: 'a',
    })
    expect(handler).toHaveBeenCalledWith({ session_id: 1, text: 'hi', agent: 'a' })
  })

  it('ignores ping events', () => {
    const handler = vi.fn()
    startSSE('tk', { onAssistantMessage: handler })
    FakeEventSource.instances[0].emit('ping', {})
    expect(handler).not.toHaveBeenCalled()
  })

  it('reconnects with backoff on error', () => {
    startSSE('tk', { onAssistantMessage: () => {} })
    expect(FakeEventSource.instances.length).toBe(1)
    FakeEventSource.instances[0].emitError()
    vi.advanceTimersByTime(1000)
    expect(FakeEventSource.instances.length).toBe(2)
    FakeEventSource.instances[1].emitError()
    vi.advanceTimersByTime(2000)
    expect(FakeEventSource.instances.length).toBe(3)
  })

  it('stop() prevents reconnection', () => {
    const stop = startSSE('tk', { onAssistantMessage: () => {} })
    FakeEventSource.instances[0].emitError()
    stop()
    vi.advanceTimersByTime(60000)
    expect(FakeEventSource.instances.length).toBe(1)
  })
})
