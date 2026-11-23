<template>
  <div v-if="!layout" class="text-center text-danger font-bold">바코드로 표시할 수 없는 문자가 있습니다.</div>
  <svg v-else :viewBox="`0 0 ${total} ${height}`" :width="total * moduleWidth" :height="height" preserveAspectRatio="none"
    role="img" :aria-label="`바코드 ${value}`" class="block mx-auto">
    <rect v-for="(bar, i) in bars" :key="i" :x="bar.x" y="0" :width="bar.w" :height="height" fill="#000" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { code128Widths } from '../utils/code128'

const props = defineProps({
  value: { type: String, required: true },
  height: { type: Number, default: 60 },
  moduleWidth: { type: Number, default: 2 },
})

const QUIET = 10 // 바코드 앞뒤 여백(모듈 수). 스캐너가 시작과 끝을 찾는 데 필요합니다.

const layout = computed(() => {
  let widths
  try {
    widths = code128Widths(props.value)
  } catch {
    return null // 한글 등 Code128로 표현할 수 없는 값
  }
  const bars = []
  let x = QUIET
  widths.forEach((w, i) => {
    if (i % 2 === 0) bars.push({ x, w })
    x += w
  })
  return { bars, total: x + QUIET }
})
const bars = computed(() => layout.value?.bars || [])
const total = computed(() => layout.value?.total || 0)
</script>
