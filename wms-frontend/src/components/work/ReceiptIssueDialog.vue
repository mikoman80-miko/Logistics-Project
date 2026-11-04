<template>
  <!-- 입고 검수 차이: 덜 옴(부족)·망가져 옴(파손)은 그만큼 더 받지 않고 이 줄을 마감하며, 더 옴(초과)은 기록만 합니다. -->
  <div class="modal-overlay">
    <form class="work-dialog w-[900px]!" @submit.prevent="submit" @keydown.esc="$emit('close')">
      <div class="text-3xl font-bold">{{ line.item_name }} · 검수 차이</div>
      <div class="text-2xl text-muted">발주 {{ line.order_quantity }}개 · 받음 {{ line.received_quantity }}개 · 남음 {{ line.remaining }}개</div>
      <div class="grid grid-cols-3 gap-4">
        <button v-for="option in kinds" :key="option.kind" type="button" class="work-btn h-28!" :disabled="option.kind !== '초과' && line.remaining < 1"
          :class="kind === option.kind ? 'work-btn-primary' : ''" @click="choose(option.kind)">
          <div class="text-4xl font-bold">{{ option.title }}</div>
          <div class="text-xl">{{ option.hint }}</div>
        </button>
      </div>
      <template v-if="kind">
        <label class="text-2xl font-bold">수량
          <input ref="qtyRef" v-model.number="quantity" class="work-scan text-center mt-2" type="number" min="1" :max="kind === '초과' ? undefined : line.remaining" required />
        </label>
        <label class="text-2xl font-bold">내용 <span class="font-normal text-muted">{{ kind === '파손' ? '(필수: 어디가 어떻게 망가졌는지)' : '(선택)' }}</span>
          <input v-model="note" class="work-scan mt-2" maxlength="200" @input="error = ''" placeholder="예: 상자 찢어짐, 2개 더 와서 반송" />
        </label>
      </template>
      <div v-if="error" class="text-2xl font-bold text-danger">{{ error }}</div>
      <div class="grid grid-cols-2 gap-4">
        <button type="submit" class="work-btn work-btn-primary" :disabled="!kind">기록 (Enter)</button>
        <button type="button" class="work-btn" @click="$emit('close')">닫기 (Esc)</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { nextTick, ref } from 'vue'

const props = defineProps({ line: { type: Object, required: true } })
const emit = defineEmits(['confirm', 'close'])
const kinds = [
  { kind: '부족', title: '덜 옴', hint: '남은 수량을 더 받지 않음' },
  { kind: '파손', title: '파손', hint: '망가진 것은 재고에 넣지 않음' },
  { kind: '초과', title: '더 옴', hint: '기록만 (반송 등)' },
]
const kind = ref('')
const quantity = ref(1)
const note = ref('')
const error = ref('')
const qtyRef = ref(null)

const choose = async (value) => {
  kind.value = value
  quantity.value = value === '부족' ? props.line.remaining : 1
  error.value = ''
  await nextTick()
  qtyRef.value?.focus()
  qtyRef.value?.select()
}

const submit = () => {
  if (!Number.isInteger(quantity.value) || quantity.value < 1) return (error.value = '수량을 1 이상으로 입력하세요.')
  if (kind.value !== '초과' && quantity.value > props.line.remaining) return (error.value = `남은 수량(${props.line.remaining}개)보다 많습니다.`)
  if (kind.value === '파손' && !note.value.trim()) return (error.value = '파손 내용을 적어 주세요.')
  emit('confirm', { kind: kind.value, quantity: quantity.value, note: note.value.trim() })
}
</script>
