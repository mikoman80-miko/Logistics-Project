<template>
  <div class="page overflow-y-auto">
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">입고 검수 차이 ({{ data.start_date }} ~ {{ data.end_date }})</span>
        <span class="text-muted">발주보다 덜 오거나(부족), 망가져 오거나(파손), 더 온(초과) 기록</span>
      </div>
      <div class="panel-body flex items-center gap-1.5">
        <input v-model="startDate" type="date" class="field w-[130px]" aria-label="시작일" />
        <span>~</span>
        <input v-model="endDate" type="date" class="field w-[130px]" aria-label="종료일" />
        <button v-for="days in [30, 90, 365]" :key="days" class="btn" @click="setRange(days)">최근 {{ days }}일</button>
        <button class="btn btn-success ml-2" @click="load">조회</button>
        <button class="btn" @click="exportExcel">엑셀 다운로드</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><span class="panel-title">거래처별</span><span class="text-muted">차이율 = (부족 + 파손) ÷ 이 기간 발주 수량</span></div>
      <div class="panel-body-flush">
        <table class="data-table">
          <thead><tr><th>거래처</th><th width="100">발주 수량</th><th width="80">부족</th><th width="80">파손</th><th width="80">초과</th><th width="80">기록</th><th width="90">차이율</th></tr></thead>
          <tbody>
            <tr v-if="!data.suppliers.length" class="empty-row"><td colspan="7">이 기간에 검수 차이 기록이 없습니다.</td></tr>
            <tr v-for="row in data.suppliers" :key="row.supplier">
              <td class="font-bold">{{ row.supplier }}</td>
              <td class="text-right">{{ row.ordered }}</td>
              <td class="text-right" :class="{ 'text-warning font-bold': row['부족'] }">{{ row['부족'] || '-' }}</td>
              <td class="text-right" :class="{ 'text-danger font-bold': row['파손'] }">{{ row['파손'] || '-' }}</td>
              <td class="text-right">{{ row['초과'] || '-' }}</td>
              <td class="text-right">{{ row.count }}건</td>
              <td class="text-right font-bold" :class="row.rate >= 5 ? 'text-danger' : row.rate ? 'text-warning' : ''">{{ row.rate === null ? '-' : `${row.rate}%` }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><span class="panel-title">기록 ({{ data.issues.length }}건)</span><span class="text-muted">줄을 누르면 발주서를 엽니다</span></div>
      <div class="panel-body-flush">
        <table class="data-table data-table-sm">
          <thead><tr><th width="140">일시</th><th width="160">발주번호</th><th width="140">거래처</th><th>상품</th><th width="60">구분</th><th width="60">수량</th><th>내용</th><th width="100">기록한 사람</th></tr></thead>
          <tbody>
            <tr v-if="!data.issues.length" class="empty-row"><td colspan="8">기록이 없습니다.</td></tr>
            <tr v-for="issue in data.issues" :key="issue.id" class="is-clickable" @click="router.push({ path: '/purchase-order', query: { q: issue.po_number } })">
              <td class="text-center">{{ issue.created_at.slice(0, 16).replace('T', ' ') }}</td>
              <td class="text-center font-bold text-primary">{{ issue.po_number }}</td>
              <td class="truncate">{{ issue.supplier || '-' }}</td>
              <td class="truncate">[{{ issue.sku }}] {{ issue.name }}</td>
              <td class="text-center font-bold" :class="{ 부족: 'text-warning', 파손: 'text-danger' }[issue.kind]">{{ issue.kind }}</td>
              <td class="text-right">{{ issue.quantity }}</td>
              <td class="truncate" :title="issue.note">{{ issue.note }}</td>
              <td class="text-center">{{ issue.user }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onActivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { downloadXlsxBook } from '../../utils/excel'
import { daysAgo, localDate } from '../../utils/date'
import { apiErrorMessage } from '../../utils/apiError'
import { useToastStore } from '../../stores/toastStore'

const router = useRouter()
const toast = useToastStore()
const startDate = ref(daysAgo(89))
const endDate = ref(localDate())
const data = ref({ start_date: '', end_date: '', suppliers: [], issues: [] })

const load = async () => {
  try {
    data.value = (await axios.get('/api/inventory/reports/receipt-issues/', { params: { start_date: startDate.value, end_date: endDate.value } })).data
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '검수 차이를 불러오지 못했습니다.'), 'error')
  }
}
const setRange = (days) => {
  startDate.value = daysAgo(days - 1)
  endDate.value = localDate()
  load()
}

const exportExcel = () => {
  const { suppliers, issues, start_date: start, end_date: end } = data.value
  if (!issues.length) return toast.addToast('내려받을 기록이 없습니다.', 'error')
  downloadXlsxBook(`입고검수차이_${start}_${end}`, [
    { name: '거래처별', headers: ['거래처', '발주 수량', '부족', '파손', '초과', '기록 수', '차이율(%)'],
      rows: suppliers.map(r => [r.supplier, r.ordered, r['부족'], r['파손'], r['초과'], r.count, r.rate ?? '']) },
    { name: '기록', headers: ['일시', '발주번호', '거래처', '상품코드', '상품명', '구분', '수량', '내용', '기록한 사람'],
      rows: issues.map(i => [i.created_at.slice(0, 16).replace('T', ' '), i.po_number, i.supplier, i.sku, i.name, i.kind, i.quantity, i.note, i.user]) },
  ])
}

onActivated(load)
</script>
