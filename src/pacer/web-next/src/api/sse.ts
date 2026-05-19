export interface AssistantMessagePayload {
  session_id: number
  text: string
  agent: string
}

export interface SSEHandlers {
  onAssistantMessage: (payload: AssistantMessagePayload) => void
}

let EventSourceImpl: typeof EventSource = globalThis.EventSource

export function _setEventSourceImpl(impl: typeof EventSource): void {
  EventSourceImpl = impl
}
export function _resetEventSourceImpl(): void {
  EventSourceImpl = globalThis.EventSource
}

const BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]

export function startSSE(token: string, handlers: SSEHandlers): () => void {
  let stopped = false
  let attempt = 0
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function open(): void {
    if (stopped) return
    source = new EventSourceImpl(`/events/stream?token=${encodeURIComponent(token)}`)
    source.addEventListener('assistant_message', (e: MessageEvent) => {
      attempt = 0
      try {
        handlers.onAssistantMessage(JSON.parse(e.data) as AssistantMessagePayload)
      } catch (err) {
        console.warn('sse parse error', err)
      }
    })
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
