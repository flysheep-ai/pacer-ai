<script setup lang="ts">
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import Toast from '@/components/Toast.vue'

const ui = useUiStore()
onMounted(() => ui.applyTheme())
</script>

<template>
  <RouterView />
  <Toast />
</template>
