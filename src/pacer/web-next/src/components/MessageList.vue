<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAutoScroll } from '@/composables/useAutoScroll'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import EmptyState from './EmptyState.vue'

const emit = defineEmits<{ preset: [text: string] }>()
const chat = useChatStore()
const scrollEl = ref<HTMLElement | null>(null)

const tick = computed(() => `${chat.messages.length}-${chat.isAwaiting ? 1 : 0}`)
useAutoScroll(scrollEl, tick)
</script>

<template>
  <div ref="scrollEl" class="list">
    <div class="inner">
      <EmptyState v-if="chat.messages.length === 0" @preset="emit('preset', $event)" />
      <template v-else>
        <template v-for="(m, i) in chat.messages" :key="i">
          <UserMessage v-if="m.role === 'user'" :content="m.content" :image-base64="m.imageBase64" />
          <AssistantMessage v-else :content="m.content" :agent="m.agent" :streaming="m.streaming" :stop-reason="m.stopReason" />
        </template>
        <div v-if="chat.isAwaiting" class="typing" aria-label="正在输入">
          <span /><span /><span />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-8) 0;
  scroll-behavior: smooth;
}
.inner {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 var(--space-6);
  display: flex; flex-direction: column;
}
.typing {
  display: flex; gap: 5px;
  padding: 14px 0 14px 18px;
  border-left: 2px solid var(--accent);
  margin: 14px 0;
}
.typing span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--ink-300);
  animation: bounce 1.4s infinite both;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-5px); opacity: 1; }
}
</style>
