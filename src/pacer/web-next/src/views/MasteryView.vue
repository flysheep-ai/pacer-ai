<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

const { t, tm } = useI18n()

type KP = {
  knowledge_point_id: number
  point_name: string
  mastery_score: number
  correct_count: number
  wrong_count: number
}
type MasteryData = Record<string, KP[]>

const data = ref<MasteryData | null>(null)
const loading = ref(true)
const expanded = ref<string | null>(null)
const reviewing = ref<number | null>(null)
const router = useRouter()

function subjectLabel(key: string): string {
  return (tm('mastery.subjects') as Record<string, string>)[key] ?? key
}

onMounted(async () => {
  try { data.value = await apiFetch<MasteryData>('/mastery') }
  catch { /* keep null */ }
  finally { loading.value = false }
})

const subjects = computed(() => {
  if (!data.value) return []
  return Object.entries(data.value).map(([subject, kps]) => {
    const total = kps.length
    const avg = total === 0 ? 0
      : kps.reduce((s, kp) => s + kp.mastery_score, 0) / total
    return {
      subject,
      label: subjectLabel(subject),
      kps,
      avg: Math.round(avg * 100),
      total,
    }
  })
})

const top5Weak = computed(() => {
  if (!data.value) return []
  const all: (KP & { subject: string })[] = []
  for (const [subject, kps] of Object.entries(data.value)) {
    for (const kp of kps) {
      if (kp.correct_count + kp.wrong_count >= 1) {
        all.push({ ...kp, subject })
      }
    }
  }
  all.sort((a, b) => a.mastery_score - b.mastery_score)
  return all.slice(0, 5)
})

function toggleExpand(subject: string): void {
  expanded.value = expanded.value === subject ? null : subject
}

async function startReview(kp: KP & { subject: string }): Promise<void> {
  if (reviewing.value !== null) return
  reviewing.value = kp.knowledge_point_id
  try {
    const r = await apiFetch<{ session_id: number }>(
      '/mastery/start-review',
      { method: 'POST', json: { knowledge_point_id: kp.knowledge_point_id } },
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
      <h1>{{ t('mastery.title') }}</h1>
      <p v-if="loading" class="hint">{{ t('mastery.loading') }}</p>
      <p v-else-if="subjects.length === 0" class="empty">
        {{ t('mastery.empty') }}
      </p>
      <template v-else>
        <div class="subject-grid">
          <button
            v-for="s in subjects" :key="s.subject"
            class="subject-card"
            :class="{ active: expanded === s.subject }"
            @click="toggleExpand(s.subject)"
          >
            <div class="subject-name">{{ s.label }}</div>
            <div class="subject-bar"><div class="subject-fill" :style="{ width: s.avg + '%' }" /></div>
            <div class="subject-pct">{{ s.avg }}%</div>
          </button>
        </div>

        <div v-if="top5Weak.length > 0" class="section">
          <h2>{{ t('mastery.weakest') }}</h2>
          <div
            v-for="kp in top5Weak" :key="kp.subject + kp.point_name"
            class="weak-row"
          >
            <span class="weak-label">{{ kp.point_name }} · {{ subjectLabel(kp.subject) }}</span>
            <div class="weak-bar"><div class="weak-fill" :style="{ width: Math.round(kp.mastery_score * 100) + '%' }" /></div>
            <span class="weak-pct">{{ Math.round(kp.mastery_score * 100) }}%</span>
            <button
              class="review-btn"
              :disabled="reviewing === kp.knowledge_point_id"
              @click.stop="startReview(kp)"
            >
              →
            </button>
          </div>
        </div>

        <div v-if="expanded" class="section">
          <h2>{{ subjectLabel(expanded) }} {{ t('mastery.details') }}</h2>
          <div
            v-for="kp in data?.[expanded] ?? []"
            :key="kp.point_name"
            class="kp-row"
          >
            <span class="kp-name">{{ kp.point_name }}</span>
            <div class="kp-bar"><div class="kp-fill" :style="{ width: Math.round(kp.mastery_score * 100) + '%' }" /></div>
            <span class="kp-pct">{{ Math.round(kp.mastery_score * 100) }}%</span>
            <span class="kp-counts">{{ kp.correct_count }}/{{ kp.correct_count + kp.wrong_count }}</span>
          </div>
        </div>
      </template>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:960px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:28px; margin-bottom:var(--space-6); }
.hint, .empty { color:var(--ink-500); font-family:var(--font-serif); font-size:16px; text-align:center; padding:var(--space-12) 0; }

.subject-grid { display:flex; flex-wrap:wrap; gap:var(--space-3); margin-bottom:var(--space-6); }
.subject-card {
  flex:1 1 calc(33.333% - var(--space-3));
  min-width:160px;
  background:var(--paper-1); border:1px solid var(--ink-300);
  border-radius:var(--radius-md); padding:var(--space-4);
  cursor:pointer; text-align:left;
  transition: border-color var(--motion-fast);
}
.subject-card:hover, .subject-card.active { border-color:var(--ink-900); }
.subject-name { font-size:15px; font-weight:500; color:var(--ink-900); margin-bottom:var(--space-2); }
.subject-bar { height:6px; background:var(--ink-300); border-radius:3px; overflow:hidden; margin-bottom:var(--space-1); }
.subject-fill { height:100%; background:var(--ink-900); transition:width 0.3s; }
.subject-pct { font-size:13px; color:var(--ink-700); }

.section { margin-bottom:var(--space-6); }
.section h2 { font-family:var(--font-serif); font-size:18px; margin-bottom:var(--space-3); color:var(--ink-800); }

.weak-row { display:flex; align-items:center; gap:var(--space-3); padding:var(--space-2) 0; }
.weak-label { flex:1; font-size:14px; color:var(--ink-900); }
.weak-bar { width:120px; height:5px; background:var(--ink-300); border-radius:3px; overflow:hidden; flex-shrink:0; }
.weak-fill { height:100%; background:var(--ink-900); transition:width 0.3s; }
.weak-pct { font-size:13px; color:var(--ink-700); width:36px; text-align:right; flex-shrink:0; }
.review-btn {
  font-size:14px; width:28px; height:28px; border:1px solid var(--ink-500);
  background:var(--paper-0); color:var(--ink-700); border-radius:var(--radius-sm);
  cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center;
}
.review-btn:hover:not(:disabled) { background:var(--ink-900); color:var(--paper-0); }
.review-btn:disabled { opacity:0.3; cursor:wait; }

.kp-row { display:flex; align-items:center; gap:var(--space-3); padding:var(--space-2) 0; border-bottom:1px solid var(--ink-200); }
.kp-name { flex:1; font-size:14px; color:var(--ink-900); }
.kp-bar { width:120px; height:5px; background:var(--ink-300); border-radius:3px; overflow:hidden; flex-shrink:0; }
.kp-fill { height:100%; background:var(--ink-900); transition:width 0.3s; }
.kp-pct { font-size:13px; color:var(--ink-700); width:36px; text-align:right; }
.kp-counts { font-size:12px; color:var(--ink-500); width:48px; text-align:right; }
</style>
