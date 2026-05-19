<script setup lang="ts">
defineProps<{ content: string; imageBase64?: string }>()
</script>

<template>
  <div class="row">
    <div class="bubble">
      <img v-if="imageBase64" :src="'data:image/jpeg;base64,' + imageBase64" class="img" alt="上传的图片" />
      <span v-if="content">{{ content }}</span>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex; justify-content: flex-end;
  margin: 12px 0;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  background: var(--accent-soft);
  color: var(--ink-900);
  border-radius: var(--radius-md);
  border-bottom-right-radius: var(--radius-xs);
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
.img {
  max-width: 240px;
  max-height: 240px;
  border-radius: var(--radius-sm);
  display: block;
  margin-bottom: 6px;
}
</style>
