<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { apiFetch } from '@/api/client'
import { useToast } from '@/composables/useToast'
import AppShell from '@/components/AppShell.vue'

const auth = useAuthStore()
const toast = useToast()
const form = ref({ name: '', school: '', target_school: '', stream: '' })
const saving = ref(false)

onMounted(async () => {
  await auth.loadProfile()
  const p = auth.profile
  if (p) form.value = { name: p.name || '', school: p.school || '', target_school: p.target_school || '', stream: p.stream || '' }
})

async function save(): Promise<void> {
  saving.value = true
  try {
    await apiFetch('/profile/', { method: 'PATCH', json: form.value })
    await auth.loadProfile()
    toast.push({ type: 'info', text: '已保存' })
  } catch { toast.push({ type: 'error', text: '保存失败' }) }
  finally { saving.value = false }
}
</script>
<template>
  <AppShell>
    <div class="page">
      <h1>个人中心</h1>
      <label class="field"><span>姓名</span><input v-model="form.name" /></label>
      <label class="field"><span>学校</span><input v-model="form.school" /></label>
      <label class="field"><span>目标学校</span><input v-model="form.target_school" /></label>
      <label class="field"><span>分科</span><input v-model="form.stream" /></label>
      <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
    </div>
  </AppShell>
</template>
<style scoped>
.page { max-width:640px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:28px; margin-bottom:var(--space-6); }
.field { display:block; margin-bottom:var(--space-5); }
.field span { display:block; font-size:14px; color:var(--ink-700); margin-bottom:var(--space-1); }
.field input { width:100%; padding:12px 14px; background:var(--paper-1); border:1px solid var(--ink-300); border-radius:var(--radius-sm); font-size:16px; color:var(--ink-900); }
.field input:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 2px var(--accent-soft); }
.btn { padding:12px 28px; background:var(--ink-900); color:var(--paper-0); border-radius:var(--radius-sm); font-size:15px; cursor:pointer; }
.btn:disabled { opacity:0.5; cursor:wait; }
</style>
