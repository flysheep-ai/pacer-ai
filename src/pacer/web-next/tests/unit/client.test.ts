import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, ApiError } from '@/api/client'

/**
 * happy-dom v15 exposes localStorage as a plain object without Storage prototype methods.
 * We mock the methods needed by the implementation and tests.
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

describe('apiFetch', () => {
  let orig: Storage

  beforeEach(() => {
    orig = globalThis.localStorage
    globalThis.localStorage = mockStorage()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    globalThis.localStorage = orig
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on 2xx', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const r = await apiFetch<{ ok: boolean }>('/x')
    expect(r).toEqual({ ok: true })
  })

  it('attaches Authorization header when token is set', async () => {
    localStorage.setItem('pacer_token', 'tk')
    const spy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    globalThis.fetch = spy as unknown as typeof fetch
    await apiFetch('/x')
    const req = spy.mock.calls[0]
    const headers = req[1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tk')
  })

  it('omits Authorization when no token', async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    globalThis.fetch = spy as unknown as typeof fetch
    await apiFetch('/x')
    const headers = spy.mock.calls[0][1].headers as Record<string, string>
    expect('Authorization' in headers).toBe(false)
  })

  it('throws ApiError on non-2xx with detail', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'nope' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    )
    await expect(apiFetch('/x')).rejects.toBeInstanceOf(ApiError)
    try {
      await apiFetch('/x')
    } catch (e) {
      expect((e as ApiError).status).toBe(404)
      expect((e as ApiError).detail).toBe('nope')
    }
  })

  it('serializes JSON body and sets content-type', async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    globalThis.fetch = spy as unknown as typeof fetch
    await apiFetch('/x', { method: 'POST', json: { a: 1 } })
    const init = spy.mock.calls[0][1]
    expect(init.body).toBe('{"a":1}')
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })
})
