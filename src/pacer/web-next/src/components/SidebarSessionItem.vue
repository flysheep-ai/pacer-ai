<script setup lang="ts">
defineProps<{ session: { id: number; title: string; message_count: number } }>()
const emit = defineEmits<{ click: []; delete: [] }>()

function onDelete(e: Event): void {
  e.stopPropagation()
  emit('delete')
}
</script>
<template>
  <button type="button" class="item" @click="emit('click')">
    <span class="title">{{ session.title }}</span>
    <span class="count">{{ session.message_count }}</span>
    <button type="button" class="del" @click="onDelete" title="删除对话">×</button>
  </button>
</template>
<style scoped>
.item { display:flex; justify-content:space-between; align-items:center; padding:6px 12px; border-radius:var(--radius-sm); font-size:13px; width:100%; text-align:left; position:relative; }
.item:hover { background:var(--paper-2); }
.title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink-900); flex:1; min-width:0; }
.count { color:var(--ink-500); font-size:11px; flex-shrink:0; margin-left:8px; }
.del {
  display: none;
  width: 20px; height: 20px;
  align-items: center; justify-content: center;
  border-radius: var(--radius-xs);
  color: var(--ink-500);
  font-size: 14px;
  flex-shrink: 0; margin-left: 6px;
}
.item:hover .del { display: flex; }
.del:hover { color: var(--seal); background: var(--paper-2); }
</style>
