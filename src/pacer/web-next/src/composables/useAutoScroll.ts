import { watch, type Ref } from 'vue'

export function useAutoScroll(
  elementRef: Ref<HTMLElement | null>,
  dep: Ref<unknown>,
): void {
  watch(dep, () => {
    const el = elementRef.value
    if (!el) return
    queueMicrotask(() => {
      el.scrollTop = el.scrollHeight
    })
  }, { flush: 'post' })
}
