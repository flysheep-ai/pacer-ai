<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { FluidBackground } from '@/utils/fluid-background'

const { t } = useI18n()
const auth = useAuthStore()
const toast = useToast()
const router = useRouter()
const sid = ref('')
const pin = ref('')
const busy = ref(false)
const canvas = ref<HTMLCanvasElement | null>(null)
let fluid: FluidBackground | null = null

onMounted(() => {
  if (canvas.value) fluid = new FluidBackground(canvas.value)
})
onBeforeUnmount(() => {
  fluid?.destroy()
  fluid = null
})

async function onSubmit(): Promise<void> {
  if (busy.value) return
  const sidNum = Number(sid.value.trim())
  const pinTrim = pin.value.trim()
  if (!sidNum || !pinTrim) {
    toast.push({ type: 'error', text: t('login.fillRequired') })
    return
  }
  busy.value = true
  try {
    await auth.login(sidNum, pinTrim)
    await auth.loadProfile()
    await router.push('/chat')
  } catch {
    toast.push({ type: 'error', text: t('login.wrongCredentials') })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-root">
    <canvas ref="canvas" class="login-canvas" aria-hidden="true" />
    <form class="login-card" @submit.prevent="onSubmit">
      <div class="login-brand">
        <span class="login-brand-seal" aria-hidden="true" />
        <span class="login-brand-text">pacer</span>
      </div>
      <p class="login-sub">{{ t('login.subtitle') }}</p>
      <label class="login-field">
        <span>{{ t('login.studentId') }}</span>
        <input v-model="sid" type="text" inputmode="numeric" autofocus />
      </label>
      <label class="login-field">
        <span>{{ t('login.pin') }}</span>
        <input v-model="pin" type="password" />
      </label>
      <button type="submit" class="login-btn" :disabled="busy">
        {{ busy ? t('login.entering') : t('login.enter') }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-root {
  position: fixed; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--paper-0);
}
.login-canvas {
  position: fixed; inset: 0;
  width: 100%; height: 100%;
  background: transparent;
  pointer-events: none;
  z-index: 0;
}
.login-card {
  position: relative; z-index: 1;
  width: 360px;
  padding: var(--space-12) var(--space-8) var(--space-8);
  background: var(--paper-0);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-md);
}
.login-brand {
  display: flex; align-items: center; gap: var(--space-2);
  margin-bottom: var(--space-1);
}
.login-brand-seal {
  width: 10px; height: 10px;
  background: var(--seal);
  border-radius: var(--radius-xs);
}
.login-brand-text {
  font-family: var(--font-serif);
  font-size: 28px;
  letter-spacing: 0.04em;
  color: var(--ink-900);
}
.login-sub {
  font-family: var(--font-serif);
  color: var(--ink-500);
  font-size: 13px;
  margin-bottom: var(--space-8);
}
.login-field { display: block; margin-bottom: var(--space-4); }
.login-field span {
  display: block;
  font-size: 13px;
  color: var(--ink-700);
  margin-bottom: var(--space-2);
}
.login-field input {
  width: 100%;
  padding: 10px 12px;
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm);
  font-size: 15px;
  color: var(--ink-900);
  transition: border-color var(--motion-fast);
}
.login-field input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.login-btn {
  width: 100%;
  margin-top: var(--space-2);
  padding: 12px;
  background: var(--ink-900);
  color: var(--paper-0);
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  transition: opacity var(--motion-fast);
}
.login-btn:hover:not(:disabled) { opacity: 0.85; }
.login-btn:disabled { opacity: 0.5; cursor: default; }
</style>
