<template>
  <div class="flex flex-col w-full h-full box-border p-1.5 gap-2.5">
    <div class="panel">
      <div class="panel-header panel-title">조회 기간</div>
      <div class="p-2 flex items-center gap-1.5 text-body flex-wrap">
        <input v-model="startDate" type="date" class="field w-[130px]" aria-label="시작일" />
        <span>~</span>
        <input v-model="endDate" type="date" class="field w-[130px]" aria-label="종료일" />
        <button v-for="range in ranges" :key="range.label" class="btn" @click="setRange(range.days)">{{ range.label }}</button>
        <button class="btn btn-success ml-2.5" :disabled="isLoading" @click="load">조회</button>
        <button class="btn" @click="exportExcel">엑셀 다운로드</button>
        <span class="ml-auto text-caption text-muted">건수: 발주·주문·반품은 문서 수, 이동·조정은 처리한 줄 수 (최대 93일)</span>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">작업자별 실적 ({{ report.start_date }} ~ {{ report.end_date }}, {{ report.workers.length }}명)</span>
        <span class="text-caption text-muted">줄을 누르면 아래 일자별 표를 그 사람만 봅니다.</span>
      </div>
      <div class="overflow-x-auto">
        <table class="data-table data-table-sm">
          <thead>
            <tr>
              <th rowspan="2" width="220">작업자</th>
              <th v-for="work in report.works" :key="work" colspan="2">{{ work }}</th>
              <th rowspan="2" width="80">처리 줄 합계</th>
              <th rowspan="2" width="150">첫 작업</th>
              <th rowspan="2" width="150">마지막 작업</th>
            </tr>
            <tr>
              <template v-for="work in report.works" :key="work"><th width="55">건</th><th width="60">수량</th></template>
            </tr>
          </thead>
          <tbody>
            <tr v-if="report.workers.length === 0">
              <td :colspan="report.works.length * 2 + 4" class="text-center">이 기간에 기록된 작업이 없습니다.</td>
            </tr>
            <tr v-for="row in report.workers" :key="row.user_id ?? 'none'" class="cursor-pointer"
              :class="{ 'bg-primary-soft': selected === row.user_id }" @click="selected = selected === row.user_id ? undefined : row.user_id">
              <td class="whitespace-nowrap">
                <span class="font-bold">{{ row.name }}</span>
                <span class="text-caption text-muted ml-1.5">{{ row.username }}{{ row.is_staff ? ' · 관리자' : '' }}</span>
              </td>
              <template v-for="work in report.works" :key="work">
                <td class="text-right" :class="{ 'text-muted': !row.works[work].count }">{{ row.works[work].count || '-' }}</td>
                <td class="text-right" :class="{ 'text-muted': !row.works[work].quantity }">{{ row.works[work].quantity || '-' }}</td>
              </template>
              <td class="text-right font-bold">{{ row.lines }}</td>
              <td class="text-center whitespace-nowrap">{{ formatTime(row.first) }}</td>
              <td class="text-center whitespace-nowrap">{{ formatTime(row.last) }}</td>
            </tr>
            <tr v-if="report.workers.length > 1" class="font-bold bg-[#f9f9f9]">
              <td>합계</td>
              <template v-for="work in report.works" :key="work">
                <td class="text-right">{{ total(work, 'count') }}</td>
                <td class="text-right">{{ total(work, 'quantity') }}</td>
              </template>
              <td class="text-right">{{ report.workers.reduce((s, w) => s + w.lines, 0) }}</td>
              <td colspan="2"></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel flex-1 min-h-0">
      <div class="panel-header">
        <span class="panel-title">일자별 처리 줄 수 (상품 줄 기준) {{ selectedName ? `· ${selectedName}` : '' }}</span>
        <button v-if="selected !== undefined" class="btn btn-sm" @click="selected = undefined">전체 보기</button>
      </div>
      <div class="flex-1 overflow-y-auto">
        <table class="data-table data-table-sm">
          <thead>
            <tr>
              <th width="110">날짜</th>
              <th>작업자</th>
              <th v-for="work in report.works" :key="work" width="80">{{ work }}</th>
              <th width="80">합계</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="dailyRows.length === 0"><td :colspan="report.works.length + 3" class="text-center">기록이 없습니다.</td></tr>
            <tr v-for="day in dailyRows" :key="`${day.date}-${day.user_id}`">
              <td class="text-center font-mono">{{ day.date }}</td>
              <td>{{ day.name }}</td>
              <td v-for="work in report.works" :key="work" class="text-right" :class="{ 'text-muted': !day.works[work] }">{{ day.works[work] || '-' }}</td>
              <td class="text-right font-bold">{{ day.lines }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import axios from 'axios'
import { downloadXlsxBook } from '../../utils/excel'
import { daysAgo, localDate } from '../../utils/date'
import { apiErrorMessage } from '../../utils/apiError'
import { useToastStore } from '../../stores/toastStore'

const toast = useToastStore()
const ranges = [{ label: '오늘', days: 0 }, { label: '최근 7일', days: 6 }, { label: '최근 30일', days: 29 }]
const startDate = ref(daysAgo(6))
const endDate = ref(localDate())
const report = ref({ works: [], workers: [], daily: [], start_date: '', end_date: '' })
const selected = ref(undefined)  // 고른 작업자 id (기록 없는 사용자는 null)
const isLoading = ref(false)

const setRange = (days) => {
  startDate.value = daysAgo(days)
  endDate.value = localDate()
  load()
}

const load = async () => {
  isLoading.value = true
  try {
    report.value = (await axios.get('/api/inventory/reports/workers/', { params: { start_date: startDate.value, end_date: endDate.value } })).data
    if (!report.value.workers.some(w => w.user_id === selected.value)) selected.value = undefined
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '실적을 불러오지 못했습니다.'), 'error')
  } finally {
    isLoading.value = false
  }
}

const total = (work, key) => report.value.workers.reduce((sum, w) => sum + w.works[work][key], 0)
const selectedName = computed(() => report.value.workers.find(w => w.user_id === selected.value)?.name)
const dailyRows = computed(() => (selected.value === undefined ? report.value.daily : report.value.daily.filter(d => d.user_id === selected.value)))
const formatTime = (value) => (value ? value.slice(0, 16).replace('T', ' ') : '-')

const exportExcel = () => {
  const { works, workers, daily, start_date: start, end_date: end } = report.value
  if (!workers.length) return toast.addToast('내려받을 실적이 없습니다.', 'error')
  downloadXlsxBook(`작업자실적_${start}_${end}`, [
    {
      name: '작업자별',
      headers: ['작업자', '아이디', '관리자', ...works.flatMap(w => [`${w} 건`, `${w} 수량`]), '처리 줄 합계', '첫 작업', '마지막 작업'],
      rows: workers.map(w => [w.name, w.username, w.is_staff ? 'Y' : '', ...works.flatMap(k => [w.works[k].count, w.works[k].quantity]), w.lines, formatTime(w.first), formatTime(w.last)]),
    },
    {
      name: '일자별',
      headers: ['날짜', '작업자', ...works, '합계'],
      rows: daily.map(d => [d.date, d.name, ...works.map(k => d.works[k]), d.lines]),
    },
  ])
}

onActivated(load)
</script>
