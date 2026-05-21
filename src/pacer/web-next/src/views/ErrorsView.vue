<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

const { t } = useI18n()

type ErrorRow = {
  id: number
  error_type: string
  source: string
  user_answer: string | null
  correct_answer: string | null
  explanation_text: string | null
}

const errors = ref<ErrorRow[]>([])
const loading = ref(true)
const reviewing = ref<number | null>(null)
const router = useRouter()

onMounted(async () => {
  try { const r = await apiFetch<{ items: ErrorRow[] }>('/errors'); errors.value = r.items || [] }
  catch { /* keep empty */ }
  finally { loading.value = false }
})

async function startReview(e: ErrorRow): Promise<void> {
  if (reviewing.value !== null) return
  reviewing.value = e.id
  try {
    const r = await apiFetch<{ session_id: number }>(
      `/errors/${e.id}/start-review`,
      { method: 'POST' },
    )
    router.push(`/chat/${r.session_id}`)
  } catch {
    reviewing.value = null
  }
}
</script>

<template>
  <AppShell>
    <div class="page">
      <h1>{{ t('errors.title') }}</h1>
      <p v-if="loading" class="hint">{{ t('errors.loading') }}</p>
      <p v-else-if="errors.length === 0" class="empty">{{ t('errors.empty') }}</p>
      <div v-for="e in errors" :key="e.id" class="card">
        <div class="meta">{{ e.error_type }} · {{ e.source }}</div>
        <div class="answer">{{ t('errors.yourAnswer') }}: {{ e.user_answer || '——' }}</div>
        <div class="answer">{{ t('errors.correctAnswer') }}: {{ e.correct_answer || '——' }}</div>
        <div v-if="e.explanation_text" class="explain">{{ e.explanation_text }}</div>
        <div class="actions">
          <button
            class="review-btn"
            :disabled="reviewing === e.id"
            @click="startReview(e)"
          >
            {{ reviewing === e.id ? t('errors.preparing') : t('errors.startReview') }}
          </button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:960px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:28px; margin-bottom:var(--space-6); }
.hint,.empty { color:var(--ink-500); font-family:var(--font-serif); font-size:16px; text-align:center; padding:var(--space-12) 0; }
.card { background:var(--paper-1); border:1px solid var(--ink-300); border-radius:var(--radius-md); padding:var(--space-6); margin-bottom:var(--space-4); }
.meta { font-size:12px; color:var(--ink-500); margin-bottom:var(--space-2); }
.answer { font-size:15px; color:var(--ink-700); margin-bottom:6px; }
.explain { font-size:14px; color:var(--ink-900); margin-top:var(--space-3); border-top:1px solid var(--ink-300); padding-top:var(--space-3); }
.actions { margin-top:var(--space-3); display:flex; justify-content:flex-end; }
.review-btn { font-size:14px; padding:8px 16px; border:1px solid var(--ink-700); background:var(--paper-0); color:var(--ink-900); border-radius:var(--radius-sm); cursor:pointer; }
.review-btn:hover:not(:disabled) { background:var(--ink-900); color:var(--paper-0); }
.review-btn:disabled { opacity:0.5; cursor:wait; }
</style>
