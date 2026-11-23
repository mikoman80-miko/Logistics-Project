<template>
  <div class="page overflow-y-auto">
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">일일 마감</span>
        <span v-if="data.closed" class="font-bold text-success">✔ 마감됨 · {{ data.closed.closed_by }} · {{ formatTime(data.closed.closed_at) }}</span>
        <span v-else class="font-bold text-warning">마감 전 (지금 기준 계산: {{ formatTime(summary.calculated_at) }})</span>
      </div>
      <div class="panel-body flex items-center gap-1.5 flex-wrap">
        <button class="btn" aria-label="전날" @click="shift(-1)">◀</button>
        <input v-model="day" type="date" class="field w-[130px]" aria-label="마감일" :max="data.today" @change="load" />
        <button class="btn" aria-label="다음날" :disabled="day >= data.today" @click="shift(1)">▶</button>
        <button class="btn" @click="goToday">오늘</button>
        <input v-model="note" class="field w-[320px] ml-4" maxlength="200" placeholder="마감 메모 (예: 택배 늦게 옴, 내일 재고 조사)" aria-label="마감 메모" />
        <button class="btn btn-primary" :disabled="isBusy" @click="close">{{ data.closed ? '다시 마감' : '마감하기' }}</button>
        <button class="btn" @click="exportExcel">엑셀 다운로드</button>
        <span v-if="data.closed?.note" class="ml-auto text-muted">메모: {{ data.closed.note }}</span>
      </div>
      <div v-if="data.closed" class="alert alert-info mx-2 mb-2">마감 때 저장한 내용입니다. 마감 뒤 처리한 일까지 넣으려면 [다시 마감]을 누르세요.</div>
    </div>

    <div class="text-heading font-bold">처리 실적</div>
    <div class="grid grid-cols-3 lg:grid-cols-6 gap-2.5">
      <div v-for="card in doneCards" :key="card.title" class="today-card cursor-default">
        <span class="text-heading font-bold">{{ card.title }}</span>
        <span class="text-[36px] font-bold leading-none my-2" :class="card.value ? card.color : 'text-muted'">{{ card.value }}</span>
        <span class="text-muted">{{ card.hint }}</span>
      </div>
    </div>

    <div class="text-heading font-bold">남은 일 <span class="text-caption text-muted font-normal">({{ data.closed ? '마감 시점' : '지금' }} 기준)</span></div>
    <div class="grid grid-cols-3 lg:grid-cols-5 gap-2.5">
      <button v-for="card in backlogCards" :key="card.title" class="today-card" @click="router.push(card.path)">
        <span class="text-heading font-bold">{{ card.title }}</span>
        <span class="text-[36px] font-bold leading-none my-2" :class="card.value ? card.color : 'text-muted'">{{ card.value }}</span>
        <span class="text-muted">{{ card.hint }}</span>
      </button>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-2.5">
      <div class="panel">
        <div class="panel-header"><span class="panel-title">출고 대기 주문 (오래된 순)</span><span class="text-muted">{{ backlog.orders }}건</span></div>
        <div class="panel-body-flush">
          <table class="data-table data-table-sm">
            <thead><tr><th width="180">주문번호</th><th>고객</th><th width="150">접수</th></tr></thead>
            <tbody>
              <tr v-if="!backlog.pending_orders.length"><td colspan="3" class="text-center">출고 대기 주문이 없습니다.</td></tr>
              <tr v-for="order in backlog.pending_orders" :key="order.order_no" class="is-clickable" @click="router.push({ path: '/orders', query: { q: order.order_no } })">
                <td class="text-center font-bold text-primary">{{ order.order_no }}</td>
                <td class="truncate">{{ order.customer }}</td>
                <td class="text-center" :class="{ 'text-warning font-bold': order.created_at.slice(0, 10) < data.date }">{{ formatTime(order.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header"><span class="panel-title">작업자별 처리</span><span class="text-muted">건수 (문서·줄)</span></div>
        <div class="panel-body-flush">
          <table class="data-table data-table-sm">
            <thead><tr><th>작업자</th><th>작업</th><th width="80">처리 줄</th></tr></thead>
            <tbody>
              <tr v-if="!summary.workers.length"><td colspan="3" class="text-center">이날 기록된 작업이 없습니다.</td></tr>
              <tr v-for="worker in summary.workers" :key="worker.username">
                <td class="whitespace-nowrap">{{ worker.name }} <span class="text-caption text-muted">{{ worker.username }}</span></td>
                <td>{{ Object.entries(worker.works).map(([work, count]) => `${work} ${count}`).join(' · ') }}</td>
                <td class="text-right font-bold">{{ worker.lines }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="backlog.carrier_issues.count" class="panel">
        <div class="panel-header"><span class="panel-title text-danger">택배 확인 필요 {{ backlog.carrier_issues.count }}건</span></div>
        <div class="panel-body-flush">
          <table class="data-table data-table-sm">
            <thead><tr><th width="60">구분</th><th width="180">번호</th><th>확인할 내용</th></tr></thead>
            <tbody>
              <tr v-for="issue in backlog.carrier_issues.items" :key="issue.kind + issue.number">
                <td class="text-center">{{ issue.kind === 'order' ? '주문' : '반품' }}</td>
                <td class="text-center font-bold">{{ issue.number }}</td>
                <td class="truncate text-danger" :title="issue.reason">{{ issue.reason }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="backlog.low_stock.count" class="panel">
        <div class="panel-header"><span class="panel-title text-warning">안전재고 이하 {{ backlog.low_stock.count }}종</span></div>
        <div class="panel-body-flush">
          <table class="data-table data-table-sm">
            <thead><tr><th width="140">상품코드</th><th>상품명</th><th width="80">재고</th><th width="80">안전재고</th></tr></thead>
            <tbody>
              <tr v-for="item in backlog.low_stock.items" :key="item.sku">
                <td class="text-center font-mono">{{ item.sku }}</td>
                <td class="truncate">{{ item.name }}</td>
                <td class="text-right font-bold text-danger">{{ item.quantity }}</td>
                <td class="text-right">{{ item.safety_stock }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><span class="panel-title">최근 마감 기록</span><span class="text-muted">줄을 누르면 그날을 봅니다</span></div>
      <div class="panel-body-flush">
        <table class="data-table data-table-sm">
          <thead><tr><th width="110">날짜</th><th width="110">마감한 사람</th><th width="150">마감 시각</th><th width="90">출고</th><th width="110">남은 출고대기</th><th>메모</th></tr></thead>
          <tbody>
            <tr v-if="!data.history.length"><td colspan="6" class="text-center">아직 마감한 날이 없습니다.</td></tr>
            <tr v-for="row in data.history" :key="row.date" class="is-clickable" :class="{ 'bg-primary-soft': row.date === data.date }" @click="openDay(row.date)">
              <td class="text-center font-mono">{{ row.date }}</td>
              <td class="text-center">{{ row.closed_by }}</td>
              <td class="text-center">{{ formatTime(row.closed_at) }}</td>
              <td class="text-right">{{ row.outbound }}건</td>
              <td class="text-right" :class="{ 'text-warning font-bold': row.backlog_orders }">{{ row.backlog_orders }}건</td>
              <td class="truncate" :title="row.note">{{ row.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { downloadXlsxBook } from '../../utils/excel'
import { localDate } from '../../utils/date'
import { apiErrorMessage } from '../../utils/apiError'
import { useToastStore } from '../../stores/toastStore'
import { useDialogStore } from '../../stores/dialogStore'

const router = useRouter()
const toast = useToastStore()
const dialog = useDialogStore()
const emptySummary = {
  inbound: { documents: 0, quantity: 0 }, inbound_cancel: { documents: 0, quantity: 0 }, outbound: { documents: 0, quantity: 0 },
  returns: { documents: 0, quantity: 0, results: [] }, moves: 0, adjust: { lines: 0, plus: 0, minus: 0 },
  received: { orders: 0, returns: 0, purchase_orders: 0 },
  backlog: { orders: 0, orders_carried: 0, pending_orders: [], returns: 0, purchase_orders: 0, overdue_purchase_orders: 0,
    carrier_issues: { count: 0, items: [] }, low_stock: { count: 0, items: [] } },
  workers: [], calculated_at: '',
}
const day = ref(localDate())
const note = ref('')
const isBusy = ref(false)
const data = ref({ date: day.value, today: day.value, closed: null, summary: emptySummary, history: [] })
const summary = computed(() => data.value.summary)
const backlog = computed(() => summary.value.backlog)
const formatTime = (value) => (value ? value.slice(0, 16).replace('T', ' ') : '-')

const doneCards = computed(() => {
  const s = summary.value
  return [
    { title: '입고', value: s.inbound.documents, hint: `발주 ${s.inbound.documents}건 · ${s.inbound.quantity}개`, color: 'text-primary' },
    { title: '출고', value: s.outbound.documents, hint: `주문 ${s.outbound.documents}건 · ${s.outbound.quantity}개`, color: 'text-primary' },
    { title: '반품 회수', value: s.returns.documents, hint: s.returns.results.map(r => `${r.result} ${r.count}`).join(' · ') || `${s.returns.quantity}개`, color: 'text-primary' },
    { title: '입고 취소', value: s.inbound_cancel.documents, hint: `${s.inbound_cancel.quantity}개`, color: 'text-warning' },
    { title: '재고 조정', value: s.adjust.lines, hint: `+${s.adjust.plus} / -${s.adjust.minus} · 이동 ${s.moves}건`, color: 'text-warning' },
    { title: '새로 접수', value: s.received.orders, hint: `주문 ${s.received.orders} · 반품 ${s.received.returns} · 발주 ${s.received.purchase_orders}`, color: 'text-ink' },
  ]
})

const backlogCards = computed(() => {
  const b = backlog.value
  return [
    { title: '출고 대기', value: b.orders, hint: `이월 ${b.orders_carried}건` + (b.orders_due ? ` · 마감 지남 ${b.orders_due.overdue}건 · 긴급 ${b.orders_due.urgent}건` : ''), color: 'text-danger', path: '/orders' },
    { title: '회수 대기', value: b.returns, hint: '반품 회수를 기다리는 건', color: 'text-warning', path: '/returns' },
    { title: '입고 대기', value: b.purchase_orders, hint: `예정일 지남 ${b.overdue_purchase_orders}건`, color: 'text-warning', path: '/purchase-order' },
    { title: '택배 확인', value: b.carrier_issues.count, hint: '운송장·회수 요청 실패, 배송 지연', color: 'text-danger', path: '/today' },
    { title: '재고 부족', value: b.low_stock.count, hint: '안전재고 이하 상품', color: 'text-danger', path: '/purchase-order?suggest=1' },
  ]
})

const load = async () => {
  try {
    data.value = (await axios.get('/api/inventory/reports/daily/', { params: { date: day.value } })).data
    note.value = data.value.closed?.note || ''
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '마감 내용을 불러오지 못했습니다.'), 'error')
  }
}

const openDay = (value) => {
  day.value = value
  load()
}
const shift = (days) => {
  const date = new Date(`${day.value}T00:00:00`)
  date.setDate(date.getDate() + days)
  openDay(localDate(date))
}
const goToday = () => openDay(localDate())

const close = async () => {
  const again = !!data.value.closed
  const message = again ? `${day.value} 마감을 지금 기준으로 다시 계산해 덮어씁니다.` : `${day.value}을(를) 마감합니다. 지금까지의 처리 실적과 남은 일이 저장되고 알림으로 보내집니다.`
  if (!(await dialog.confirm(message, { title: again ? '다시 마감' : '일일 마감', okText: again ? '다시 마감' : '마감' }))) return
  isBusy.value = true
  try {
    const res = await axios.post('/api/inventory/reports/daily/', { date: day.value, note: note.value })
    toast.addToast(res.data.message, 'success')
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '마감하지 못했습니다.'), 'error')
  } finally {
    isBusy.value = false
  }
}

const exportExcel = () => {
  const s = summary.value
  const b = s.backlog
  const status = data.value.closed ? `마감 ${formatTime(data.value.closed.closed_at)} (${data.value.closed.closed_by})` : `마감 전 (${formatTime(s.calculated_at)} 기준)`
  downloadXlsxBook(`일일마감_${data.value.date}`, [
    {
      name: '요약',
      headers: ['구분', '항목', '값', '비고'],
      rows: [
        ['마감', '날짜', data.value.date, status],
        ['마감', '메모', data.value.closed?.note || '', ''],
        ['처리', '입고', s.inbound.documents, `${s.inbound.quantity}개`],
        ['처리', '출고', s.outbound.documents, `${s.outbound.quantity}개`],
        ['처리', '반품 회수', s.returns.documents, s.returns.results.map(r => `${r.result} ${r.count}`).join(', ')],
        ['처리', '입고 취소', s.inbound_cancel.documents, `${s.inbound_cancel.quantity}개`],
        ['처리', '재고 조정', s.adjust.lines, `+${s.adjust.plus} / -${s.adjust.minus}`],
        ['처리', '위치 이동', s.moves, ''],
        ['접수', '새 주문', s.received.orders, ''],
        ['접수', '새 반품', s.received.returns, ''],
        ['접수', '새 발주', s.received.purchase_orders, ''],
        ['남은 일', '출고 대기', b.orders, `이월 ${b.orders_carried}건`],
        ['남은 일', '회수 대기', b.returns, ''],
        ['남은 일', '입고 대기', b.purchase_orders, `예정일 지남 ${b.overdue_purchase_orders}건`],
        ['남은 일', '택배 확인', b.carrier_issues.count, ''],
        ['남은 일', '재고 부족', b.low_stock.count, ''],
      ],
    },
    { name: '출고대기', headers: ['주문번호', '고객', '접수'], rows: b.pending_orders.map(o => [o.order_no, o.customer, formatTime(o.created_at)]) },
    { name: '작업자', headers: ['작업자', '아이디', '작업', '처리 줄'], rows: s.workers.map(w => [w.name, w.username, Object.entries(w.works).map(([k, v]) => `${k} ${v}`).join(', '), w.lines]) },
    { name: '재고부족', headers: ['상품코드', '상품명', '재고', '안전재고'], rows: b.low_stock.items.map(i => [i.sku, i.name, i.quantity, i.safety_stock]) },
  ])
}

onActivated(load)
</script>
