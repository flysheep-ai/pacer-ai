<script setup lang="ts">
import { ref, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/chat'
import { useToast } from '@/composables/useToast'
import IconButton from './IconButton.vue'

const { t } = useI18n()
const chat = useChatStore()
const toast = useToast()
const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const attachedImage = ref<string | null>(null)
const attachedImageName = ref('')
const uploading = ref(false)
const MAX_TEXT = 8000

const canSend = computed(() => !chat.isAwaiting && !chat.isStreaming && (!!text.value.trim() || !!attachedImage.value))

function autoResize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

async function onSend(): Promise<void> {
  if (!canSend.value) return
  const msg = text.value.trim()
  if (msg.length > MAX_TEXT) {
    toast.push({ type: 'error', text: t('chat.messageTooLong') })
    return
  }
  const img = attachedImage.value
  text.value = ''
  attachedImage.value = null
  attachedImageName.value = ''
  await nextTick()
  autoResize()
  await chat.send(msg, img ?? undefined)
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

function removeImage(): void {
  attachedImage.value = null
  attachedImageName.value = ''
}

async function onFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    toast.push({ type: 'error', text: t('chat.unsupportedImage') })
    input.value = ''
    return
  }
  if (file.size > 8 * 1024 * 1024) {
    toast.push({ type: 'error', text: t('chat.imageTooLarge') })
    input.value = ''
    return
  }
  // Read file as base64 client-side
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result as string
    // dataUrl format: "data:image/jpeg;base64,xxxxx"
    const base64 = dataUrl.split(',')[1]
    attachedImage.value = base64
    attachedImageName.value = file.name
  }
  reader.readAsDataURL(file)
  input.value = ''
}
</script>

<template>
  <div class="wrap">
    <div class="composer">
      <IconButton
        :aria-label="t('chat.uploadImage')"
        :title="uploading ? t('chat.uploading') : t('chat.uploadImage')"
        @click="fileInput?.click()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <path d="M21 15l-5-5L5 21"/>
        </svg>
      </IconButton>
      <div v-if="attachedImage" class="image-preview">
        <img :src="'data:image/jpeg;base64,' + attachedImage" :alt="t('chat.preview')" />
        <button type="button" class="remove-img" @click="removeImage" :title="t('chat.removeImage')">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
      <textarea
        ref="textarea"
        v-model="text"
        class="input"
        rows="1"
        :placeholder="attachedImage ? t('chat.describeImage') : t('chat.placeholder')"
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
        :title="t('chat.stopOutput')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="1"/>
        </svg>
      </button>
      <button
        v-else
        type="button"
        class="send"
        :disabled="!canSend"
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
.image-preview {
  position: relative;
  display: inline-flex;
  align-items: center;
  margin: 4px 0;
}
.image-preview img {
  height: 48px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--ink-300);
}
.remove-img {
  position: absolute;
  top: -6px; right: -6px;
  width: 20px; height: 20px;
  border-radius: 50%;
  background: var(--ink-900);
  color: var(--paper-0);
  display: flex; align-items: center; justify-content: center;
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
