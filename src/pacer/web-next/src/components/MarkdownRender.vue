<script setup lang="ts">
import { computed } from 'vue'
import { mdToHtml } from '@/utils/markdown'

const props = defineProps<{ text: string }>()
const html = computed(() => mdToHtml(props.text))
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md { font-size: 15px; line-height: 1.7; color: var(--ink-900); }
.md :deep(p) { margin: 0 0 10px; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: var(--paper-2);
  padding: 1px 4px;
  border-radius: var(--radius-xs);
}
.md :deep(pre) {
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  overflow-x: auto;
  margin: 10px 0;
}
.md :deep(pre code) {
  background: none; padding: 0;
  font-size: 13px;
  line-height: 1.5;
}
.md :deep(strong) { color: var(--ink-900); font-weight: 600; }
</style>
