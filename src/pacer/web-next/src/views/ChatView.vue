<script setup lang="ts">
import AppShell from '@/components/AppShell.vue'
import MessageList from '@/components/MessageList.vue'
import Composer from '@/components/Composer.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
function onPreset(text: string): void { void chat.send(text) }
</script>

<template>
  <AppShell>
    <MessageList @preset="onPreset" />
    <Composer />
  </AppShell>
</template>
