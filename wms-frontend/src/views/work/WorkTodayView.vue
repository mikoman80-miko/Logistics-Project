<template>
  <WorkLayout title="오늘 내 작업">
    <div class="flex flex-col gap-6 h-full min-h-0">
      <div class="grid grid-cols-3 gap-6 shrink-0">
        <div v-for="card in cards" :key="card.label" class="work-task items-center">
          <span class="text-3xl text-muted">{{ card.label }}</span>
          <span class="text-[64px] font-bold leading-tight" :class="card.color">{{ card.value.toLocaleString() }}</span>
        </div>
      </div>

      <div v-if="loading" class="work-empty">불러오는 중...</div>
      <div v-else-if="logs.length === 0" class="work-empty">오늘 처리한 작업이 아직 없습니다.</div>
      <div v-else class="flex-1 min-h-0 overflow-y-auto bg-white border-2 border-line-strong rounded">
        <table class="w-full border-collapse text-2xl">
          <thead class="sticky top-0 bg-surface-head">
            <tr>
              <th class="p-3 w-[130px]">시각</th>
              <th class="p-3 w-[130px]">구분</th>
              <th class="p-3 text-left">상품</th>
              <th class="p-3 w-[120px] text-right">수량</th>
              <th class="p-3 text-left">내용</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" class="border-t border-line">
              <td class="p-3 text-center font-mono">{{ timeOf(log.timestamp) }}</td>
              <td class="p-3 text-center font-bold" :class="log.quantity_changed > 0 ? 'text-success' : log.quantity_changed < 0 ? 'text-primary' : 'text-muted'">{{ log.action_display }}</td>
              <td class="p-3 truncate max-w-0">{{ log.item_name }} <span class="text-xl text-muted font-mono">{{ log.item_sku }}</span></td>
              <td class="p-3 text-right font-bold">{{ log.quantity_changed > 0 ? '+' : '' }}{{ log.quantity_changed }}</td>
              <td class="p-3 text-xl text-muted truncate max-w-0" :title="log.description">{{ log.description }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="total > logs.length" class="p-3 text-center text-xl text-muted">최근 {{ logs.length }}건만 표시합니다. (전체 {{ total }}건)</div>
      </div>
    </div>
  </WorkLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'

// 로그인한 작업자가 오늘 처리한 입출고 기록 (최근 200건)
const logs = ref([])
const total = ref(0)
const loading = ref(true)

const sum = (filter) => logs.value.filter(filter).reduce((acc, log) => acc + Math.abs(log.quantity_changed), 0)
const cards = computed(() => [
  { label: '입고한 수량', value: sum(log => log.quantity_changed > 0), color: 'text-success' },
  { label: '출고한 수량', value: sum(log => log.quantity_changed < 0), color: 'text-primary' },
  { label: '처리 건수', value: total.value, color: 'text-ink' },
])
const timeOf = (value) => new Date(value).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })

onMounted(async () => {
  const today = new Date().toLocaleDateString('sv-SE')
  try {
    const res = await axios.get('/api/inventory/logs/', { params: { mine: 1, start_date: today, end_date: today, page_size: 200 } })
    logs.value = res.data.results
    total.value = res.data.count
  } finally {
    loading.value = false
  }
})
</script>
