<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

const plans = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try { const r = await apiFetch<any>('/plans'); plans.value = r.items || [] }
  catch {}
  finally { loading.value = false }
})
</script>
<template>
  <AppShell>
    <div class="page">
      <h1>学习计划</h1>
      <p v-if="loading" class="hint">翻阅中…</p>
      <p v-else-if="plans.length===0" class="empty">今天还没有计划</p>
      <div v-for="p in plans" :key="p.id" class="card">
        <div class="type">{{ p.type === 'daily' ? '日计划' : '周计划' }}</div>
        <div class="content">{{ p.content }}</div>
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
.type { font-size:11px; color:var(--ink-500); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:var(--space-2); }
.content { font-size:14px; color:var(--ink-900); white-space:pre-wrap; }
.feedback { font-size:13px; color:var(--ink-700); margin-top:var(--space-2); border-top:1px solid var(--ink-300); padding-top:var(--space-2); }
</style>
