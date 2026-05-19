<script setup lang="ts">
import { computed, watch } from 'vue'
import { mdToHtml, setMarkdownTheme } from '@/utils/markdown'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ text: string }>()
const ui = useUiStore()

const html = computed(() => mdToHtml(props.text))

watch(() => ui.theme, (t) => setMarkdownTheme(t), { immediate: true })
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md { font-size: 15px; line-height: 1.7; color: var(--ink-900); word-break: break-word; }
.md :deep(p) { margin: 0 0 10px; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(code) {
  font-family: var(--font-mono); font-size: 0.9em;
  background: var(--paper-2); padding: 1px 4px; border-radius: var(--radius-xs);
}
.md :deep(pre) {
  background: var(--paper-1); border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm); padding: 12px 14px; overflow-x: auto; margin: 10px 0;
}
.md :deep(pre code) { background: none; padding: 0; font-size: 13px; line-height: 1.5; }
.md :deep(strong) { color: var(--ink-900); font-weight: 600; }
.md :deep(h1), .md :deep(h2), .md :deep(h3) {
  font-family: var(--font-serif); margin: 16px 0 8px; letter-spacing: 0.04em;
}
.md :deep(h1) { font-size: 20px; }
.md :deep(h2) { font-size: 17px; }
.md :deep(h3) { font-size: 15px; }
.md :deep(table) { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
.md :deep(th), .md :deep(td) { border: 1px solid var(--ink-300); padding: 6px 10px; text-align: left; }
.md :deep(th) { background: var(--paper-1); font-weight: 600; }
.md :deep(blockquote) {
  border-left: 2px solid var(--ink-300); margin: 10px 0; padding: 4px 12px;
  color: var(--ink-700); font-style: italic;
}
.md :deep(ul), .md :deep(ol) { padding-left: 20px; margin: 8px 0; }
.md :deep(li) { margin: 2px 0; }
.md :deep(hr) { border: none; border-top: 1px solid var(--ink-300); margin: 16px 0; }
.md :deep(a) { color: var(--accent); text-decoration: underline; }
</style>
