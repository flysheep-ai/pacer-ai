<script setup lang="ts">
defineProps<{ label: string }>()
defineEmits<{ click: [] }>()
</script>

<template>
  <button type="button" class="chip" @click="$emit('click')">
    {{ label }}
  </button>
</template>

<style scoped>
.chip {
  padding: 8px 14px;
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--ink-700);
  background: var(--paper-0);
  transition: border-color var(--motion-fast), color var(--motion-fast), background var(--motion-fast);
}
.chip:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}
</style>
