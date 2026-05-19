<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import MessageList from '@/components/MessageList.vue'
import Composer from '@/components/Composer.vue'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'

const chat = useChatStore()
const session = useSessionStore()
const route = useRoute()

function onPreset(text: string): void { void chat.send(text) }

watch(() => route.params.sid, async (sid) => {
  if (sid) {
    const sidNum = Number(sid)
    session.currentSid = sidNum
    await chat.loadHistory(sidNum)
  }
}, { immediate: true })
</script>

<template>
  <AppShell>
    <MessageList @preset="onPreset" />
    <Composer />
  </AppShell>
</template>
