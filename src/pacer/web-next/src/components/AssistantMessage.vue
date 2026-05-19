<script setup lang="ts">
import MarkdownRender from './MarkdownRender.vue'

const props = defineProps<{
  content: string
  agent?: string
  streaming?: boolean
  stopReason?: string
}>()

function agentLabel(agent: string | undefined): string {
  if (agent === 'subject_teacher') return '学科老师'
  if (agent === 'mood_companion') return '心态陪伴'
  return ''
}

function badgeText(): string {
  if (props.streaming) return '正在回答…'
  if (props.stopReason === 'user_stopped') return '已停止'
  return agentLabel(props.agent)
}
</script>

<template>
  <div class="row" :class="{ stopped: stopReason === 'user_stopped' }">
    <span v-if="badgeText()" class="badge">{{ badgeText() }}</span>
    <MarkdownRender :text="content" />
    <span v-if="streaming" class="cursor" aria-hidden="true" />
  </div>
</template>

<style scoped>
.row {
  position: relative;
  padding: 4px 0 4px 16px;
  margin: 14px 0;
  border-left: 2px solid var(--accent);
}
.row.stopped { border-left-style: dashed; }
.badge {
  display: inline-block;
  font-family: var(--font-serif);
  font-size: 11px;
  color: var(--ink-500);
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}
.cursor {
  display: inline-block;
  width: 1px; height: 1em;
  background: var(--accent);
  margin-left: 1px;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .cursor { animation: none; } }
</style>
