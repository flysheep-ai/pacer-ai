<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

type Task = {
  id: string
  subject?: string
  duration_min?: number
  note?: string
  done?: boolean
}
type Plan = {
  id: number
  type: string
  tasks: Task[]
  feedback?: string
  date?: string
}

const plans = ref<Plan[]>([])
const loading = ref(true)

onMounted(async () => {
  try { const r = await apiFetch<{ items: Plan[] }>('/plans'); plans.value = r.items || [] }
  catch { /* leave empty */ }
  finally { loading.value = false }
})

function progress(p: Plan): { done: number; total: number; pct: number } {
  const total = p.tasks.length
  const done = p.tasks.filter(t => t.done).length
  return { done, total, pct: total === 0 ? 0 : Math.round((done / total) * 100) }
}

async function toggleTask(plan: Plan, task: Task): Promise<void> {
  if (!task.id) return  // legacy unmigrated row — backfill not yet run
  const before = task.done === true
  task.done = !before
  try {
    await apiFetch(`/plans/${plan.id}/tasks/${task.id}`, {
      method: 'PATCH',
      json: { done: task.done },
    })
  } catch {
    task.done = before
  }
}

function describe(t: Task): string {
  const parts: string[] = []
  if (t.subject) parts.push(t.subject)
  if (t.duration_min) parts.push(`${t.duration_min} 分钟`)
  if (t.note) parts.push(t.note)
  return parts.join(' · ') || '任务'
}
</script>

<template>
  <AppShell>
    <div class="page">
      <h1>学习计划</h1>
      <p v-if="loading" class="hint">翻阅中…</p>
      <p v-else-if="plans.length === 0" class="empty">今天还没有计划</p>
      <div v-for="p in plans" :key="p.id" class="card">
        <div class="head">
          <div class="type">{{ p.type === 'daily' ? '日计划' : '周计划' }}</div>
          <div class="progress">{{ progress(p).done }}/{{ progress(p).total }}</div>
        </div>
        <div class="bar"><div class="fill" :style="{ width: progress(p).pct + '%' }"></div></div>
        <ul class="tasks">
          <li v-for="t in p.tasks" :key="t.id ?? Math.random()" class="task" :class="{ done: t.done }">
            <label>
              <input type="checkbox" :checked="t.done === true" :disabled="!t.id" @change="toggleTask(p, t)" />
              <span>{{ describe(t) }}</span>
            </label>
          </li>
        </ul>
        <div v-if="p.feedback" class="feedback">{{ p.feedback }}</div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:720px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:24px; margin-bottom:var(--space-6); }
.hint,.empty { color:var(--ink-500); font-family:var(--font-serif); font-size:15px; text-align:center; padding:var(--space-12) 0; }
.card { background:var(--paper-1); border:1px solid var(--ink-300); border-radius:var(--radius-md); padding:var(--space-4); margin-bottom:var(--space-3); }
.head { display:flex; justify-content:space-between; align-items:baseline; }
.type { font-size:11px; color:var(--ink-500); text-transform:uppercase; letter-spacing:0.06em; }
.progress { font-size:12px; color:var(--ink-700); }
.bar { height:4px; background:var(--ink-300); border-radius:2px; margin:var(--space-2) 0 var(--space-3); overflow:hidden; }
.fill { height:100%; background:var(--ink-900); transition:width 0.2s; }
.tasks { list-style:none; padding:0; margin:0; }
.task { font-size:14px; color:var(--ink-900); padding:6px 0; }
.task label { display:flex; gap:var(--space-2); align-items:center; cursor:pointer; }
.task.done span { color:var(--ink-500); text-decoration:line-through; }
.feedback { font-size:13px; color:var(--ink-700); margin-top:var(--space-2); border-top:1px solid var(--ink-300); padding-top:var(--space-2); }
</style>
