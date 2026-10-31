<template>
  <div class="modal-overlay">
    <form class="work-dialog" @submit.prevent="submit" @keydown.esc="$emit('close')">
      <div class="text-3xl font-bold">{{ name }}</div>
      <div class="text-2xl text-muted">남은 수량 {{ remaining }}개</div>
      <input ref="inputRef" v-model.number="quantity" class="work-scan text-center" type="number" min="1" :max="remaining" required />
      <div class="grid grid-cols-2 gap-4">
        <button type="submit" class="work-btn work-btn-primary">확인 (Enter)</button>
        <button type="button" class="work-btn" @click="$emit('close')">취소 (Esc)</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  remaining: { type: Number, required: true },
})
const emit = defineEmits(['confirm', 'close'])

const inputRef = ref(null)
const quantity = ref(props.remaining)

const submit = () => {
  if (Number.isInteger(quantity.value) && quantity.value >= 1 && quantity.value <= props.remaining) emit('confirm', quantity.value)
}

onMounted(() => {
  inputRef.value?.focus()
  inputRef.value?.select()
})
</script>
