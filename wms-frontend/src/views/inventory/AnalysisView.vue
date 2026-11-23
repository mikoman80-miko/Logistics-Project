<template>
  <div class="page overflow-y-auto">
    <div class="panel">
      <div class="panel-header">
        <div class="flex items-center gap-1">
          <span class="panel-title mr-2">재고·반품 분석</span>
          <button class="tab" :class="{ 'is-active': tab === 'aging' }" @click="tab = 'aging'">재고 회전·장기 재고</button>
          <button class="tab" :class="{ 'is-active': tab === 'returns' }" @click="tab = 'returns'">반품 분석</button>
        </div>
        <button class="btn" @click="exportExcel">엑셀 다운로드</button>
      </div>

      <!-- 재고 회전 -->
      <template v-if="tab === 'aging'">
        <div class="panel-body flex items-center gap-1.5 flex-wrap">
          <span>최근</span>
          <button v-for="days in [30, 90, 180, 365]" :key="days" class="btn" :class="{ 'btn-primary': aging.days === days }" @click="loadAging(days)">{{ days }}일</button>
          <span>출고 기준</span>
          <label class="ml-4 flex items-center gap-1"><input v-model="agingOnly" type="checkbox" /> 장기 재고만 보기</label>
          <input v-model="agingQuery" class="field w-[220px] ml-2" placeholder="상품코드, 상품명, 카테고리" aria-label="상품 검색" />
        </div>
        <div class="grid grid-cols-4 gap-2.5 px-2 pb-2">
          <div v-for="card in agingCards" :key="card.title" class="today-card cursor-default">
            <span class="text-heading font-bold">{{ card.title }}</span>
            <span class="text-[32px] font-bold leading-none my-2" :class="card.value ? card.color : 'text-muted'">{{ card.value.toLocaleString() }}</span>
            <span class="text-muted">{{ card.hint }}</span>
          </div>
        </div>
        <div>
          <table class="data-table data-table-sm">
            <thead>
              <tr>
                <th width="130">상품코드</th><th>상품명</th><th width="100">카테고리</th><th width="40">ABC</th><th width="70">재고</th>
                <th width="90">{{ aging.days }}일 출고</th><th width="80">재고 일수</th><th width="70">회전율</th><th width="100">마지막 출고</th><th width="100">마지막 입고</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!agingRows.length" class="empty-row"><td colspan="10">해당하는 상품이 없습니다.</td></tr>
              <tr v-for="row in agingRows" :key="row.id" :class="{ 'row-warning': row.aging }">
                <td class="text-center font-mono">{{ row.sku }}</td>
                <td class="truncate">{{ row.name }} <span v-if="row.aging" class="text-caption font-bold text-warning">장기 재고</span></td>
                <td class="truncate">{{ row.category }}</td>
                <td class="text-center">{{ row.abc_grade || '-' }}</td>
                <td class="text-right font-bold">{{ row.quantity }}</td>
                <td class="text-right">{{ row.outbound }}</td>
                <td class="text-right" :class="row.cover_days !== null && row.cover_days <= 7 ? 'text-danger font-bold' : ''">{{ row.cover_days === null ? '-' : `${row.cover_days}일` }}</td>
                <td class="text-right">{{ row.turnover ?? '-' }}</td>
                <td class="text-center">{{ row.last_out || '없음' }}<div v-if="row.idle_days" class="text-caption text-muted">{{ row.idle_days }}일 전</div></td>
                <td class="text-center">{{ row.last_in || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="panel-body text-caption text-muted">
          재고 일수 = 지금 재고 ÷ 하루 평균 출고량 (이만큼 버틸 수 있음, 7일 이하는 빨간색) · 회전율 = 기간 출고량 ÷ 지금 재고 · 장기 재고 = 재고가 있는데 기간 동안 출고가 없음
        </div>
      </template>

      <!-- 반품 분석 -->
      <template v-else>
        <div class="panel-body flex items-center gap-1.5">
          <input v-model="startDate" type="date" class="field w-[130px]" aria-label="시작일" />
          <span>~</span>
          <input v-model="endDate" type="date" class="field w-[130px]" aria-label="종료일" />
          <button v-for="days in [30, 90, 365]" :key="days" class="btn" @click="setReturnRange(days)">최근 {{ days }}일</button>
          <button class="btn btn-success ml-2" @click="loadReturns">조회</button>
        </div>
        <div class="grid grid-cols-4 gap-2.5 px-2 pb-2">
          <div v-for="card in returnCards" :key="card.title" class="today-card cursor-default">
            <span class="text-heading font-bold">{{ card.title }}</span>
            <span class="text-[32px] font-bold leading-none my-2">{{ card.value }}</span>
            <span class="text-muted">{{ card.hint }}</span>
          </div>
        </div>
        <div class="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-2.5 px-2 pb-2">
          <table class="data-table data-table-sm">
            <thead><tr><th>사유</th><th width="70">건수</th><th width="70">수량</th><th width="80">비중</th></tr></thead>
            <tbody>
              <tr v-if="!returns.by_reason.length" class="empty-row"><td colspan="4">반품이 없습니다.</td></tr>
              <tr v-for="row in returns.by_reason" :key="row.reason">
                <td class="font-bold">{{ row.reason }}</td><td class="text-right">{{ row.count }}</td><td class="text-right">{{ row.quantity }}</td><td class="text-right">{{ row.share }}%</td>
              </tr>
            </tbody>
          </table>
          <table class="data-table data-table-sm">
            <thead><tr><th>처리 결과 (회수 완료)</th><th width="70">건수</th></tr></thead>
            <tbody>
              <tr v-if="!returns.by_result.length" class="empty-row"><td colspan="2">회수 완료된 반품이 없습니다.</td></tr>
              <tr v-for="row in returns.by_result" :key="row.result"><td>{{ row.result }}</td><td class="text-right">{{ row.count }}</td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <table class="data-table data-table-sm">
            <thead><tr><th width="130">상품코드</th><th>상품명</th><th width="70">반품 건</th><th width="70">반품 수량</th><th width="80">같은 기간 출고</th><th width="80">반품률</th><th width="120">주된 사유</th></tr></thead>
            <tbody>
              <tr v-if="!returns.by_item.length" class="empty-row"><td colspan="7">반품이 없습니다.</td></tr>
              <tr v-for="row in returns.by_item" :key="row.sku">
                <td class="text-center font-mono">{{ row.sku }}</td><td class="truncate">{{ row.name }}</td>
                <td class="text-right">{{ row.count }}</td><td class="text-right font-bold">{{ row.quantity }}</td><td class="text-right">{{ row.shipped }}</td>
                <td class="text-right font-bold" :class="row.rate >= 10 ? 'text-danger' : row.rate >= 5 ? 'text-warning' : ''">{{ row.rate === null ? '-' : `${row.rate}%` }}</td>
                <td class="text-center">{{ row.top_reason }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="panel-body text-caption text-muted">반품률 = 기간 반품 수량 ÷ 같은 기간 출고 수량 (10% 이상 빨간색, 5% 이상 주황색) · 취소된 반품은 빼고 셉니다.</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref, watch } from 'vue'
import axios from 'axios'
import { downloadXlsx } from '../../utils/excel'
import { daysAgo, localDate } from '../../utils/date'
import { apiErrorMessage } from '../../utils/apiError'
import { useToastStore } from '../../stores/toastStore'

const toast = useToastStore()
const tab = ref('aging')

const aging = ref({ days: 90, items: [], summary: { stocked: 0, aging_items: 0, aging_quantity: 0, no_stock_moving: 0 } })
const agingOnly = ref(false)
const agingQuery = ref('')
const agingRows = computed(() => {
  const q = agingQuery.value.trim().toLowerCase()
  return aging.value.items
    .filter(r => !agingOnly.value || r.aging)
    .filter(r => !q || [r.sku, r.name, r.category].some(v => v.toLowerCase().includes(q)))
    .sort((a, b) => (b.aging - a.aging) || ((a.cover_days ?? 1e9) - (b.cover_days ?? 1e9)))
})
const agingCards = computed(() => {
  const s = aging.value.summary
  return [
    { title: '재고 있는 상품', value: s.stocked, hint: '종', color: 'text-ink' },
    { title: '장기 재고', value: s.aging_items, hint: `${aging.value.days}일 동안 출고 없음`, color: 'text-warning' },
    { title: '장기 재고 수량', value: s.aging_quantity, hint: '개 (처분·판촉 검토)', color: 'text-warning' },
    { title: '재고 없는데 팔리는 상품', value: s.no_stock_moving, hint: '종 (발주 확인)', color: 'text-danger' },
  ]
})

const loadAging = async (days = aging.value.days) => {
  try {
    aging.value = (await axios.get('/api/inventory/reports/stock-aging/', { params: { days } })).data
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '재고 분석을 불러오지 못했습니다.'), 'error')
  }
}

const startDate = ref(daysAgo(89))
const endDate = ref(localDate())
const returns = ref({ start_date: '', end_date: '', summary: { returns: 0, quantity: 0, shipped: 0, rate: null, waiting: 0 }, by_reason: [], by_item: [], by_result: [] })
const returnCards = computed(() => {
  const s = returns.value.summary
  return [
    { title: '반품', value: `${s.returns}건`, hint: `${s.quantity}개` },
    { title: '같은 기간 출고', value: `${s.shipped}개`, hint: '출고 수량' },
    { title: '반품률', value: s.rate === null ? '-' : `${s.rate}%`, hint: '반품 수량 ÷ 출고 수량' },
    { title: '회수 대기', value: `${s.waiting}건`, hint: '아직 돌아오지 않음' },
  ]
})
const loadReturns = async () => {
  try {
    returns.value = (await axios.get('/api/inventory/reports/returns/', { params: { start_date: startDate.value, end_date: endDate.value } })).data
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '반품 분석을 불러오지 못했습니다.'), 'error')
  }
}
const setReturnRange = (days) => {
  startDate.value = daysAgo(days - 1)
  endDate.value = localDate()
  loadReturns()
}

const exportExcel = () => {
  if (tab.value === 'aging') {
    downloadXlsx(`재고회전_${aging.value.days}일_${localDate()}`, '재고 회전',
      ['상품코드', '상품명', '카테고리', 'ABC', '재고', `${aging.value.days}일 출고`, '재고 일수', '회전율', '마지막 출고', '마지막 입고', '장기 재고'],
      agingRows.value.map(r => [r.sku, r.name, r.category, r.abc_grade, r.quantity, r.outbound, r.cover_days ?? '', r.turnover ?? '', r.last_out || '', r.last_in || '', r.aging ? 'Y' : '']))
  } else {
    const { by_item: items, start_date: start, end_date: end } = returns.value
    downloadXlsx(`반품분석_${start}_${end}`, '상품별 반품', ['상품코드', '상품명', '반품 건', '반품 수량', '같은 기간 출고', '반품률(%)', '주된 사유'],
      items.map(r => [r.sku, r.name, r.count, r.quantity, r.shipped, r.rate ?? '', r.top_reason]))
  }
}

watch(tab, (value) => (value === 'aging' ? loadAging() : loadReturns()))
onActivated(() => (tab.value === 'aging' ? loadAging() : loadReturns()))
</script>
