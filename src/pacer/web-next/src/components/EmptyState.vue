<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import SuggestionChip from './SuggestionChip.vue'

const auth = useAuthStore()
const emit = defineEmits<{ preset: [text: string] }>()

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const name = computed(() => auth.profile?.name ?? '同学')

const suggestions = [
  '帮我讲一道导数题',
  '帮我制定今天的学习计划',
  '帮我分析一下这道错题',
  '最近有点焦虑，想聊聊',
]
</script>

<template>
  <div class="empty">
    <h1>{{ greeting }}，{{ name }}</h1>
    <p>我是你的 AI 班主任。试试下面这些，或者直接问我任何问题。</p>
    <div class="chips">
      <SuggestionChip
        v-for="s in suggestions"
        :key="s"
        :label="s"
        @click="emit('preset', s)"
      />
    </div>
  </div>
</template>

<style scoped>
.empty {
  flex: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: var(--space-12) var(--space-8);
  text-align: center;
}
.empty h1 {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--ink-900);
  margin-bottom: var(--space-3);
}
.empty p {
  color: var(--ink-500);
  font-size: 14px;
  max-width: 420px;
  margin-bottom: var(--space-8);
}
.chips {
  display: flex; flex-wrap: wrap; gap: var(--space-2);
  justify-content: center;
  max-width: 540px;
}
</style>
