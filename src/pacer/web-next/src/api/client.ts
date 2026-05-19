const TOKEN_KEY = 'pacer_token'

export class ApiError extends Error {
  status: number
  detail: string
  code: string | undefined
  constructor(status: number, detail: string, code?: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.code = code
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  json?: unknown
  body?: BodyInit
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { json, body, headers: rawHeaders, ...rest } = options
  const headers: Record<string, string> = { ...(rawHeaders as Record<string, string>) }

  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}`

  let finalBody = body
  if (json !== undefined) {
    finalBody = JSON.stringify(json)
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(path, { ...rest, headers, body: finalBody })

  let payload: unknown = null
  const ct = res.headers.get('content-type') ?? ''
  if (ct.includes('application/json')) {
    payload = await res.json().catch(() => null)
  } else {
    payload = await res.text().catch(() => '')
  }

  if (!res.ok) {
    const p = payload as { detail?: string; code?: string } | null
    throw new ApiError(res.status, p?.detail ?? res.statusText, p?.code)
  }
  return payload as T
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token === null) localStorage.removeItem(TOKEN_KEY)
  else localStorage.setItem(TOKEN_KEY, token)
}
