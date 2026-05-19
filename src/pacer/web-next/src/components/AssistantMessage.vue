<script setup lang="ts">
import MarkdownRender from './MarkdownRender.vue'

defineProps<{ content: string; agent?: string }>()

function agentLabel(agent: string | undefined): string {
  if (agent === 'subject_teacher') return '学科老师'
  if (agent === 'mood_companion') return '心态陪伴'
  return ''
}
</script>

<template>
  <div class="row">
    <span v-if="agentLabel(agent)" class="badge">{{ agentLabel(agent) }}</span>
    <MarkdownRender :text="content" />
  </div>
</template>

<style scoped>
.row {
  position: relative;
  padding: 4px 0 4px 16px;
  margin: 14px 0;
  border-left: 2px solid var(--accent);
}
.badge {
  display: inline-block;
  font-family: var(--font-serif);
  font-size: 11px;
  color: var(--ink-500);
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}
</style>
