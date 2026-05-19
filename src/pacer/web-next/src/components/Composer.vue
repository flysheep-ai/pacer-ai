<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useToast } from '@/composables/useToast'
import { apiFetch, ApiError } from '@/api/client'
import IconButton from './IconButton.vue'

const chat = useChatStore()
const toast = useToast()
const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const MAX_TEXT = 8000

function autoResize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

async function onSend(): Promise<void> {
  if (chat.isAwaiting) return
  const t = text.value.trim()
  if (!t) return
  if (t.length > MAX_TEXT) {
    toast.push({ type: 'error', text: '消息过长' })
    return
  }
  text.value = ''
  await nextTick()
  autoResize()
  await chat.send(t)
}

async function onStop(): Promise<void> {
  await chat.stopStreaming()
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void onSend()
  }
}

interface UploadResponse {
  auto_filled_stem?: string
  auto_routed_to_subject?: string
}

async function onFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    toast.push({ type: 'error', text: '只支持 jpg / png / webp' })
    input.value = ''
    return
  }
  if (file.size > 8 * 1024 * 1024) {
    toast.push({ type: 'error', text: '图片不能超过 8MB' })
    input.value = ''
    return
  }
  uploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    const r = await apiFetch<UploadResponse>('/upload/image', { method: 'POST', body: fd })
    if (r.auto_filled_stem) {
      text.value = r.auto_filled_stem
      await nextTick()
      autoResize()
      textarea.value?.focus()
    }
  } catch (err) {
    const msg = err instanceof ApiError ? err.detail : '上传失败'
    toast.push({ type: 'error', text: msg })
  } finally {
    uploading.value = false
    input.value = ''
  }
}
</script>

<template>
  <div class="wrap">
    <div class="composer">
      <IconButton
        aria-label="上传题目图片"
        :title="uploading ? '正在上传…' : '上传题目图片'"
        @click="fileInput?.click()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <path d="M21 15l-5-5L5 21"/>
        </svg>
      </IconButton>
      <textarea
        ref="textarea"
        v-model="text"
        class="input"
        rows="1"
        placeholder="输入消息，或拍照上传题目…"
        @keydown="onKeydown"
        @input="autoResize"
      />
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        @change="onFile"
      />
      <button
        v-if="chat.isStreaming"
        type="button"
        class="stop-btn"
        @click="onStop"
        title="停止输出"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="1"/>
        </svg>
      </button>
      <button
        v-else
        type="button"
        class="send"
        :disabled="chat.isAwaiting || !text.trim()"
        @click="onSend"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <path d="M2 21l21-9L2 3v7l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  padding: var(--space-3) var(--space-6) var(--space-5);
  background: var(--paper-0);
}
.composer {
  max-width: 720px; margin: 0 auto;
  display: flex; gap: var(--space-2); align-items: flex-end;
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-md);
  padding: 6px 6px 6px 12px;
  transition: border-color var(--motion-fast), box-shadow var(--motion-fast);
}
.composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.input {
  flex: 1;
  border: none; outline: none; resize: none;
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.5;
  padding: 8px 0;
  max-height: 180px;
  background: transparent;
  color: var(--ink-900);
}
.input::placeholder { color: var(--ink-500); }
.send {
  width: 32px; height: 32px;
  border-radius: var(--radius-sm);
  background: var(--ink-900);
  color: var(--paper-0);
  display: inline-flex; align-items: center; justify-content: center;
  transition: opacity var(--motion-fast), transform var(--motion-fast);
}
.send:hover:not(:disabled) { opacity: 0.85; }
.send:active:not(:disabled) { transform: scale(0.95); }
.send:disabled { opacity: 0.35; cursor: default; }
.stop-btn {
  width: 32px; height: 32px;
  border-radius: var(--radius-sm);
  background: var(--seal);
  color: var(--paper-0);
  display: inline-flex; align-items: center; justify-content: center;
  transition: opacity var(--motion-fast);
}
.stop-btn:hover { opacity: 0.85; }
</style>
