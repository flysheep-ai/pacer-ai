<script setup lang="ts">
defineProps<{
  ariaLabel: string
  title?: string
}>()
</script>

<template>
  <button
    type="button"
    class="icon-btn"
    :aria-label="ariaLabel"
    :title="title ?? ariaLabel"
  >
    <slot />
  </button>
</template>

<style scoped>
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border-radius: var(--radius-sm);
  color: var(--ink-500);
  transition: background var(--motion-fast), color var(--motion-fast);
}
.icon-btn:hover { background: var(--paper-2); color: var(--ink-900); }
.icon-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.icon-btn :slotted(svg) { width: 18px; height: 18px; }
</style>
