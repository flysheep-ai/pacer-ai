<script setup lang="ts">
defineProps<{ content: string }>()
</script>

<template>
  <div class="row">
    <div class="bubble">{{ content }}</div>
  </div>
</template>

<style scoped>
.row {
  display: flex; justify-content: flex-end;
  margin: 12px 0;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  background: var(--accent-soft);
  color: var(--ink-900);
  border-radius: var(--radius-md);
  border-bottom-right-radius: var(--radius-xs);
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
</style>
