<script setup lang="ts">
import { onMounted } from 'vue'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
onMounted(() => { void session.fetchList() })
</script>

<template>
  <div class="shell">
    <Sidebar />
    <main class="main">
      <TopBar />
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--paper-0);
}
.main {
  flex: 1;
  display: flex; flex-direction: column;
  min-width: 0;
}
</style>
