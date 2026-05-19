<script setup lang="ts">
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
onMounted(() => ui.applyTheme())
</script>

<template>
  <RouterView />
</template>
