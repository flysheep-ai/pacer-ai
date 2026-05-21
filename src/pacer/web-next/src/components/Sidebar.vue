<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import SidebarSessionItem from './SidebarSessionItem.vue'

const { t } = useI18n()
const auth = useAuthStore()
const session = useSessionStore()
const chat = useChatStore()
const router = useRouter()

const presetTexts = [
  '帮我制定今天的学习计划',
  '帮我复盘最近的错题',
  '生成今天的学习日报',
] as const

const presetLabels = computed(() => ({
  '帮我制定今天的学习计划': t('nav.todayPlan'),
  '帮我复盘最近的错题': t('nav.errorReview'),
  '生成今天的学习日报': t('nav.dailyReport'),
}))

function newChat(): void {
  session.reset()
  chat.reset()
  void router.push('/chat')
}

async function logout(): Promise<void> {
  auth.logout()
  session.reset()
  chat.reset()
  await router.push('/')
}

function preset(p: { text: string }): void {
  void chat.send(p.text)
}

function selectChat(sid: number): void {
  session.selectSession(sid)
  void router.push(`/chat/${sid}`)
}

async function deleteChat(sid: number): Promise<void> {
  await session.deleteSession(sid)
  if (session.currentSid === sid) {
    chat.reset()
    void router.push('/chat')
  }
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <span class="brand-seal" aria-hidden="true" />
      <span class="brand-text">{{ t('nav.brand') }}</span>
    </div>

    <button class="row primary" type="button" @click="newChat">{{ t('nav.newChat') }}</button>

    <div class="section">{{ t('nav.shortcuts') }}</div>
    <button
      v-for="pt in presetTexts"
      :key="pt"
      class="row"
      type="button"
      @click="preset({ text: pt })"
    >
      {{ presetLabels[pt] }}
    </button>

    <div class="section">{{ t('nav.pages') }}</div>
    <button class="row" type="button" @click="router.push('/me')">{{ t('nav.profile') }}</button>
    <button class="row" type="button" @click="router.push('/errors')">{{ t('nav.errors') }}</button>
    <button class="row" type="button" @click="router.push('/plan')">{{ t('nav.plan') }}</button>
    <button class="row" type="button" @click="router.push('/mastery')">{{ t('nav.mastery') }}</button>

    <div class="section">{{ t('nav.history') }}</div>
    <div v-if="session.loading" class="hint">…</div>
    <div class="session-scroll">
      <SidebarSessionItem
        v-for="s in session.sessions"
        :key="s.id"
        :session="s"
        @click="selectChat(s.id)"
        @delete="deleteChat(s.id)"
      />
    </div>

    <div class="footer">
      <button class="footer-row" type="button" @click="logout">{{ t('nav.logout') }}</button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px;
  min-width: 240px;
  background: var(--paper-1);
  border-right: 1px solid var(--ink-300);
  display: flex; flex-direction: column;
  padding: var(--space-5) var(--space-3);
  gap: var(--space-1);
}
.brand {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-5);
}
.brand-seal {
  width: 9px; height: 9px;
  background: var(--seal);
  border-radius: var(--radius-xs);
}
.brand-text {
  font-family: var(--font-serif);
  font-size: 18px;
  letter-spacing: 0.04em;
}
.row {
  text-align: left;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--ink-900);
  transition: background var(--motion-fast);
}
.row:hover { background: var(--paper-2); }
.row.primary { font-weight: 500; }
.section {
  font-size: 11px;
  color: var(--ink-500);
  letter-spacing: 0.08em;
  padding: var(--space-4) var(--space-3) var(--space-1);
}
.hint { color:var(--ink-500); font-size:13px; padding:4px 12px; }
.session-scroll { flex: 1; overflow-y: auto; min-height: 0; }
.footer { border-top: 1px solid var(--ink-300); padding: var(--space-2) 0; margin-top: var(--space-2); flex-shrink: 0; }
.footer-row {
  text-align: left;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--ink-700);
  transition: background var(--motion-fast);
  width: 100%;
}
.footer-row:hover { background: var(--paper-2); color: var(--ink-900); }

@media (max-width: 640px) {
  .sidebar { display: none; }
}
</style>
