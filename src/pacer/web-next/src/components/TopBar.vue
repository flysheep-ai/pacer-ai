<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { switchLang } from '@/i18n'
import IconButton from './IconButton.vue'

const { t } = useI18n()
const auth = useAuthStore()
const ui = useUiStore()
const title = computed(() => {
  const n = auth.profile?.name ?? t('chat.classmate')
  return `${n} · pacer`
})
const langLabel = computed(() => t('lang.switch'))
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <img class="logo" src="/icon.png" alt="pacer" />
      <span class="title">{{ title }}</span>
    </div>
    <div class="actions">
      <button class="lang-btn" @click="switchLang">{{ langLabel }}</button>
      <IconButton :aria-label="t('theme.toggle')" @click="ui.toggleTheme">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
        </svg>
      </IconButton>
    </div>
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
.actions {
  display: flex; align-items: center; gap: var(--space-2);
}
.lang-btn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--ink-400);
  border-radius: var(--radius-sm);
  background: var(--paper-0);
  color: var(--ink-700);
  cursor: pointer;
  transition: background var(--motion-fast);
}
.lang-btn:hover {
  background: var(--paper-2);
  color: var(--ink-900);
}
</style>
