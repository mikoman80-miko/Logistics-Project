<template>
  <div class="modal-overlay">
    <form class="work-dialog" @submit.prevent="submit" @keydown.esc="$emit('close')">
      <div class="text-3xl font-bold">{{ name }}</div>
      <div class="text-2xl text-muted">{{ message }}</div>
      <input ref="inputRef" v-model="value" class="work-scan" type="text" autocomplete="off" spellcheck="false" placeholder="시리얼 스캔" />
      <div class="grid grid-cols-2 gap-4">
        <button type="submit" class="work-btn work-btn-danger">확인 (Enter)</button>
        <button type="button" class="work-btn" @click="$emit('close')">닫기 (Esc)</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

defineProps({
  name: { type: String, required: true },
  message: { type: String, required: true },
})
const emit = defineEmits(['confirm', 'close'])

const inputRef = ref(null)
const value = ref('')

const submit = () => {
  const code = value.value.trim()
  if (code) emit('confirm', code)
}

onMounted(() => inputRef.value?.focus())
</script>
