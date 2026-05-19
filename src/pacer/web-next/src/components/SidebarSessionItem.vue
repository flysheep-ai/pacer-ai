<script setup lang="ts">
defineProps<{ session: { id: number; title: string; message_count: number } }>()
defineEmits<{ click: [] }>()
</script>
<template>
  <button type="button" class="item" @click="$emit('click')">
    <span class="title">{{ session.title }}</span>
    <span class="count">{{ session.message_count }}</span>
  </button>
</template>
<style scoped>
.item { display:flex; justify-content:space-between; align-items:center; padding:6px 12px; border-radius:var(--radius-sm); font-size:13px; width:100%; text-align:left; }
.item:hover { background:var(--paper-2); }
.title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink-900); }
.count { color:var(--ink-500); font-size:11px; flex-shrink:0; margin-left:8px; }
</style>
