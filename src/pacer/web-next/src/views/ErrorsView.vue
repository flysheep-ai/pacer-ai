<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

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
      <h1>错题本</h1>
      <p v-if="loading" class="hint">翻阅中…</p>
      <p v-else-if="errors.length === 0" class="empty">暂未记下错题</p>
      <div v-for="e in errors" :key="e.id" class="card">
        <div class="meta">{{ e.error_type }} · {{ e.source }}</div>
        <div class="answer">你的答案: {{ e.user_answer || '——' }}</div>
        <div class="answer">正确答案: {{ e.correct_answer || '——' }}</div>
        <div v-if="e.explanation_text" class="explain">{{ e.explanation_text }}</div>
        <div class="actions">
          <button
            class="review-btn"
            :disabled="reviewing === e.id"
            @click="startReview(e)"
          >
            {{ reviewing === e.id ? '正在准备…' : '开始复盘' }}
          </button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:720px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:24px; margin-bottom:var(--space-6); }
.hint,.empty { color:var(--ink-500); font-family:var(--font-serif); font-size:15px; text-align:center; padding:var(--space-12) 0; }
.card { background:var(--paper-1); border:1px solid var(--ink-300); border-radius:var(--radius-md); padding:var(--space-4); margin-bottom:var(--space-3); }
.meta { font-size:11px; color:var(--ink-500); margin-bottom:var(--space-2); }
.answer { font-size:14px; color:var(--ink-700); margin-bottom:4px; }
.explain { font-size:13px; color:var(--ink-900); margin-top:var(--space-2); border-top:1px solid var(--ink-300); padding-top:var(--space-2); }
.actions { margin-top:var(--space-3); display:flex; justify-content:flex-end; }
.review-btn { font-size:13px; padding:6px 12px; border:1px solid var(--ink-700); background:var(--paper-0); color:var(--ink-900); border-radius:var(--radius-sm); cursor:pointer; }
.review-btn:hover:not(:disabled) { background:var(--ink-900); color:var(--paper-0); }
.review-btn:disabled { opacity:0.5; cursor:wait; }
</style>
