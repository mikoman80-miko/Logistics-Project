<template>
  <!-- 목록 검색: 검색어와 등록일 기간. Enter 또는 [검색]으로 적용합니다. -->
  <form class="toolbar px-2.5 py-1.5 border-b border-line bg-white" @submit.prevent="apply">
    <input v-model="model.q" class="field field-sm flex-1 min-w-[140px]" :placeholder="placeholder" maxlength="100" />
    <input v-model="model.start_date" type="date" class="field field-sm w-[128px]" aria-label="시작일" />
    <span>~</span>
    <input v-model="model.end_date" type="date" class="field field-sm w-[128px]" aria-label="종료일" />
    <button type="button" class="btn btn-sm" @click="setDays(7)">7일</button>
    <button type="button" class="btn btn-sm" @click="setDays(30)">30일</button>
    <button type="submit" class="btn btn-sm btn-primary">검색</button>
    <button v-if="isFiltered" type="button" class="btn btn-sm" @click="reset">초기화</button>
  </form>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  model: { type: Object, required: true }, // { q, start_date, end_date }
  placeholder: { type: String, default: '번호, 거래처, 상품 검색' },
})
const emit = defineEmits(['apply'])

const isFiltered = computed(() => !!(props.model.q || props.model.start_date || props.model.end_date))
const localDate = (date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10)

const apply = () => emit('apply')
const setDays = (days) => {
  const today = new Date()
  props.model.end_date = localDate(today)
  props.model.start_date = localDate(new Date(today.getTime() - (days - 1) * 86400000))
  apply()
}
const reset = () => {
  Object.assign(props.model, { q: '', start_date: '', end_date: '' })
  apply()
}
</script>
