<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import SuggestionChip from './SuggestionChip.vue'

const { t } = useI18n()
const auth = useAuthStore()
const emit = defineEmits<{ preset: [text: string] }>()

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return t('greeting.night')
  if (h < 12) return t('greeting.morning')
  if (h < 18) return t('greeting.afternoon')
  return t('greeting.evening')
})
const name = computed(() => auth.profile?.name ?? t('chat.classmate'))

const suggestions = computed(() => [
  t('greeting.suggestion1'),
  t('greeting.suggestion2'),
  t('greeting.suggestion3'),
  t('greeting.suggestion4'),
])
</script>

<template>
  <div class="empty">
    <h1>{{ greeting }}，{{ name }}</h1>
    <p>{{ t('greeting.intro') }}</p>
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
