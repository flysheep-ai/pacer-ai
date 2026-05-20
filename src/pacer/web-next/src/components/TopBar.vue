<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import IconButton from './IconButton.vue'

const auth = useAuthStore()
const ui = useUiStore()
const title = computed(() => {
  const n = auth.profile?.name ?? '同学'
  return `${n} · pacer`
})
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <img class="logo" src="/icon.png" alt="pacer" />
      <span class="title">{{ title }}</span>
    </div>
    <IconButton aria-label="切换主题" @click="ui.toggleTheme">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
      </svg>
    </IconButton>
  </header>
</template>

<style scoped>
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-3) var(--space-6);
  border-bottom: 1px solid var(--ink-300);
  background: var(--paper-0);
}
.brand {
  display: flex; align-items: center; gap: var(--space-2);
}
.logo {
  width: 22px; height: 22px;
  border-radius: 6px;
  object-fit: contain;
  flex-shrink: 0;
}
.title {
  font-family: var(--font-serif);
  font-size: 15px;
  letter-spacing: 0.04em;
  color: var(--ink-900);
}
</style>
