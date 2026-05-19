<script setup lang="ts">
import { useToast } from '@/composables/useToast'
const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="toast-root" aria-live="polite">
    <button
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="t.type"
      type="button"
      @click="dismiss(t.id)"
    >
      {{ t.text }}
    </button>
  </div>
</template>

<style scoped>
.toast-root {
  position: fixed;
  right: var(--space-6);
  bottom: var(--space-6);
  display: flex; flex-direction: column; gap: var(--space-2);
  z-index: 100;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  text-align: left;
  padding: 10px 14px;
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  color: var(--ink-900);
  font-size: 13px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-hover);
  animation: toast-in var(--motion-mid);
}
.toast.error { border-color: var(--seal); }
@keyframes toast-in {
  from { transform: translateY(8px); opacity: 0; }
  to   { transform: translateY(0);   opacity: 1; }
}
</style>
