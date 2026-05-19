export interface AssistantMessagePayload {
  session_id: number
  text: string
  agent: string
}

export interface AssistantStartPayload {
  session_id: number
  message_id: number
  agent: string
}

export interface AssistantDeltaPayload {
  message_id: number
  delta: string
}

export interface AssistantDonePayload {
  message_id: number
  agent: string
  stop_reason: string
}

export interface SSEHandlers {
  onAssistantMessage: (payload: AssistantMessagePayload) => void
  onAssistantStart?: (payload: AssistantStartPayload) => void
  onAssistantDelta?: (payload: AssistantDeltaPayload) => void
  onAssistantDone?: (payload: AssistantDonePayload) => void
}

let EventSourceImpl: typeof EventSource = globalThis.EventSource

export function _setEventSourceImpl(impl: typeof EventSource): void {
  EventSourceImpl = impl
}
export function _resetEventSourceImpl(): void {
  EventSourceImpl = globalThis.EventSource
}

const BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]

function jsonHandler<T>(fn: ((payload: T) => void) | undefined): ((e: MessageEvent) => void) | undefined {
  if (!fn) return undefined
  return (e: MessageEvent) => {
    try {
      fn(JSON.parse(e.data) as T)
    } catch (err) {
      console.warn('sse parse error', err)
    }
  }
}

export function startSSE(token: string, handlers: SSEHandlers): () => void {
  let stopped = false
  let attempt = 0
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function open(): void {
    if (stopped) return
    source = new EventSourceImpl(`/events/stream?token=${encodeURIComponent(token)}`)
    const addJson = <T>(name: string, fn: ((payload: T) => void) | undefined) => {
      const h = jsonHandler(fn)
      if (h) source!.addEventListener(name, h)
    }
    addJson('assistant_message', handlers.onAssistantMessage)
    addJson('assistant_start', handlers.onAssistantStart)
    addJson('assistant_delta', handlers.onAssistantDelta)
    addJson('assistant_done', handlers.onAssistantDone)
    source.addEventListener('ping', () => { attempt = 0 })
    source.onerror = () => {
      source?.close()
      source = null
      if (stopped) return
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
      attempt += 1
      timer = setTimeout(open, delay)
    }
  }
  open()

  return () => {
    stopped = true
    if (timer !== null) clearTimeout(timer)
    source?.close()
    source = null
  }
}
