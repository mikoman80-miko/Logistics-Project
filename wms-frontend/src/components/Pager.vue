<template>
  <!-- 목록 페이지 이동. 서버가 돌려준 전체 건수(count)로 페이지 수를 셉니다. -->
  <div class="toolbar px-2.5 py-1.5 border-t border-line bg-surface-head">
    <span class="text-muted">총 {{ count.toLocaleString() }}건</span>
    <span class="flex-1"></span>
    <button type="button" class="btn btn-sm" :disabled="page <= 1" @click="$emit('change', 1)">처음</button>
    <button type="button" class="btn btn-sm" :disabled="page <= 1" @click="$emit('change', page - 1)">이전</button>
    <span class="w-[70px] text-center font-bold">{{ page }} / {{ pages }}</span>
    <button type="button" class="btn btn-sm" :disabled="page >= pages" @click="$emit('change', page + 1)">다음</button>
    <button type="button" class="btn btn-sm" :disabled="page >= pages" @click="$emit('change', pages)">끝</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  count: { type: Number, required: true },
  page: { type: Number, required: true },
  pageSize: { type: Number, default: 50 },
})
defineEmits(['change'])
const pages = computed(() => Math.max(1, Math.ceil(props.count / props.pageSize)))
</script>
