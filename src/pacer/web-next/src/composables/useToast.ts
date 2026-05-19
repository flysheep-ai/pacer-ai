import { ref } from 'vue'

export type ToastType = 'info' | 'error'

export interface Toast {
  id: number
  type: ToastType
  text: string
}

const _toasts = ref<Toast[]>([])
let _id = 0
const MAX = 3
const AUTO_DISMISS_MS = 3000

export function _resetToastsForTest(): void { _toasts.value = []; _id = 0 }

export function useToast() {
  function push(t: Omit<Toast, 'id'>): number {
    const id = ++_id
    _toasts.value = [..._toasts.value, { id, ...t }]
    while (_toasts.value.length > MAX) _toasts.value.shift()
    setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
    return id
  }
  function dismiss(id: number): void {
    _toasts.value = _toasts.value.filter(t => t.id !== id)
  }
  return { toasts: _toasts, push, dismiss }
}
