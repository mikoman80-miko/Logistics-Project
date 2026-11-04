<template>
  <div class="page overflow-y-auto">
    <div v-if="setupSteps.some(step => !step.done)" class="panel">
      <div class="panel-header"><span class="panel-title">처음 설정: 아래 순서대로 등록하세요</span></div>
      <div class="panel-body flex flex-col gap-1.5">
        <div v-for="(step, index) in setupSteps" :key="step.path" class="flex items-center gap-2.5">
          <span class="w-5 font-bold" :class="step.done ? 'text-success' : 'text-danger'">{{ step.done ? '✔' : index + 1 }}</span>
          <span class="w-[280px]">{{ step.label }}</span>
          <button v-if="!step.done" class="btn btn-primary btn-sm" @click="router.push(step.path)">등록하러 가기</button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
      <button v-for="card in cards" :key="card.title" class="today-card" @click="router.push(card.path)">
        <span class="text-heading font-bold">{{ card.title }}</span>
        <span class="text-[40px] font-bold leading-none my-2" :class="card.count() > 0 ? card.color : 'text-muted'">{{ card.count() }}</span>
        <span class="text-muted">{{ card.hint }}</span>
      </button>
    </div>

    <div v-if="today.carrier_issues.count > 0" class="panel">
      <div class="panel-header">
        <span class="panel-title text-danger">택배 확인 필요 {{ today.carrier_issues.count }}건</span>
        <span class="text-muted">운송장 발급·회수 요청 실패, 출고 후 하루 넘게 배송완료가 안 된 건</span>
      </div>
      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr><th width="70">구분</th><th width="180">번호</th><th width="180">고객</th><th>확인할 내용</th></tr>
          </thead>
          <tbody>
            <tr v-for="issue in today.carrier_issues.items" :key="issue.kind + issue.number" class="is-clickable" @click="openIssue(issue)">
              <td class="text-center">{{ issue.kind === 'order' ? '주문' : '반품' }}</td>
              <td class="text-center font-bold text-primary">{{ issue.number }}</td>
              <td class="truncate">{{ issue.customer }}</td>
              <td class="truncate text-danger" :title="issue.reason">{{ issue.reason }}</td>
            </tr>
            <tr v-if="today.carrier_issues.count > today.carrier_issues.items.length" class="empty-row">
              <td colspan="4">외 {{ today.carrier_issues.count - today.carrier_issues.items.length }}건은 주문·반품 관리에서 확인하세요.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><span class="panel-title">업무 흐름</span></div>
      <div class="panel-body grid grid-cols-1 lg:grid-cols-3 gap-2.5">
        <div v-for="flow in flows" :key="flow.title" class="border border-line p-2.5">
          <div class="font-bold text-title mb-1.5">{{ flow.title }}</div>
          <ol class="m-0 pl-5 leading-[1.8]">
            <li v-for="step in flow.steps" :key="step">{{ step }}</li>
          </ol>
          <button class="btn btn-sm mt-1.5" @click="router.push(flow.path)">{{ flow.action }}</button>
        </div>
      </div>
    </div>

    <div>
      <button class="btn btn-success btn-lg" @click="router.push('/work')">현장 작업 화면 열기 (입고·출고·반품 스캔)</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const today = ref({ orders: 0, purchase_orders: 0, returns: 0, low_stock: 0, carrier_issues: { count: 0, items: [] }, setup: { locations: true, items: true, suppliers: true } })

const cards = [
  { title: '출고 대기', count: () => today.value.orders, hint: '스캔 후 출고할 주문', path: '/orders', color: 'text-primary' },
  { title: '입고 예정', count: () => today.value.purchase_orders, hint: '아직 다 받지 못한 발주', path: '/purchase-order', color: 'text-primary' },
  { title: '반품 회수 대기', count: () => today.value.returns, hint: '돌아올 기기', path: '/returns', color: 'text-warning' },
  { title: '재고 부족', count: () => today.value.low_stock, hint: '안전 재고 이하 상품', path: '/stock', color: 'text-danger' },
]

const setupSteps = computed(() => [
  { label: '보관 위치 등록 (창고 구역, 랙)', done: today.value.setup.locations, path: '/locations' },
  { label: '상품 등록', done: today.value.setup.items, path: '/items' },
  { label: '거래처 등록', done: today.value.setup.suppliers, path: '/suppliers' },
])

const flows = [
  { title: '입고', steps: ['관리자가 발주를 등록합니다.', '물건이 오면 현장 화면에서 스캔합니다.', '재고가 자동으로 늘어납니다.'], path: '/purchase-order', action: '발주 관리로 이동' },
  { title: '출고', steps: ['관리자가 주문을 등록합니다.', '현장 화면의 안내대로 스캔합니다.', '출고 완료를 누르면 재고가 줄어듭니다.'], path: '/orders', action: '주문 관리로 이동' },
  { title: '반품', steps: ['관리자가 반품을 등록합니다.', '현장 화면에서 시리얼을 스캔합니다.', '기기 상태를 고르면 처리됩니다.'], path: '/returns', action: '반품 관리로 이동' },
]

// 해당 주문·반품 화면에서 그 건을 찾아 엽니다.
const openIssue = (issue) => router.push({ path: issue.kind === 'order' ? '/orders' : '/returns', query: { q: issue.number } })

onActivated(async () => {
  today.value = (await axios.get('/api/inventory/today/')).data
})
</script>
