<template>
  <WorkLayout title="집품 (여러 주문 한 번에)">
    <!-- 1. 주문 고르기 -->
    <div v-if="!started" class="flex flex-col gap-4 h-full min-h-0">
      <div class="text-4xl font-bold">함께 꺼낼 주문을 누르세요 <span class="text-3xl text-muted">({{ chosen.length }}건 선택)</span></div>
      <div v-if="orders.length === 0" class="work-empty">출고 대기 중인 주문이 없습니다.</div>
      <div class="flex flex-col gap-3 overflow-y-auto min-h-0">
        <button v-for="row in orders" :key="row.id" class="work-row work-row-due" :class="{ 'bg-primary-soft! border-primary!': chosen.includes(row.id) }" @click="toggle(row.id)">
          <span class="font-bold">{{ chosen.includes(row.id) ? '☑' : '☐' }} <b v-if="row.is_urgent" class="work-urgent">긴급</b>{{ row.order_no }}</span>
          <span>{{ row.customer }}</span>
          <span class="text-muted">{{ row.items.length }}종 {{ row.items.reduce((s, l) => s + l.quantity, 0) }}개</span>
          <span v-if="dueLabel(row, now)" class="text-2xl font-bold" :class="toneClass[dueLabel(row, now).tone]">{{ dueLabel(row, now).text }}</span>
        </button>
      </div>
      <div class="grid grid-cols-2 gap-4 shrink-0">
        <button class="work-btn" @click="router.push('/work/outbound')">출고 화면으로</button>
        <button class="work-btn work-btn-primary" :disabled="chosen.length === 0" @click="start">집품 시작 ({{ chosen.length }}건)</button>
      </div>
    </div>

    <!-- 2. 위치 순서대로 꺼내기 -->
    <div v-else class="grid grid-cols-[2fr_1fr] gap-6 h-full">
      <section class="flex flex-col gap-5 min-h-0">
        <div v-if="current" class="work-task">
          <div class="text-4xl text-muted">꺼낼 곳 {{ doneCount }} / {{ rows.length }} 완료</div>
          <div class="text-[64px] font-bold text-warning leading-tight">📍 {{ current.location_name }}</div>
          <div class="text-[52px] font-bold leading-tight">{{ current.name }}</div>
          <div class="text-4xl font-mono">{{ current.sku }}</div>
          <div class="text-[72px] font-bold leading-tight"><span class="text-primary">{{ picked[current.key] || 0 }}</span> / {{ current.quantity }}개</div>
          <div class="text-2xl text-muted">{{ current.orders.map(o => `${o.order_no} ${o.quantity}개`).join(' · ') }}</div>
          <div v-if="current.short" class="text-2xl text-danger font-bold">재고 위치 기록보다 많이 필요합니다. 기본 위치나 주변을 확인하세요.</div>
        </div>
        <div v-else class="work-task justify-center items-center flex-1 gap-6">
          <div class="text-[64px] font-bold text-success">✔ 집품 완료</div>
          <div class="text-3xl text-muted text-center">꺼낸 물건을 주문별로 나눠 출고 화면에서 스캔하세요.</div>
          <button class="work-btn work-btn-success w-full" @click="finish">출고 화면으로 (집품 끝내기)</button>
        </div>
        <template v-if="current">
          <div class="text-4xl font-bold text-center">상품 바코드를 꺼낸 개수만큼 스캔하세요</div>
          <ScanBox :paused="!!qtyRow" @scan="onScan" />
          <button class="work-btn" @click="qtyRow = current">수량 직접 입력</button>
        </template>
      </section>

      <aside class="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <div class="text-3xl font-bold">주문 {{ chosen.length }}건 · 위치 순서</div>
        <div v-for="row in rows" :key="row.key" class="work-line" :class="{ 'is-done': isDone(row), 'is-current': row.key === current?.key }">
          <div class="flex justify-between gap-3 font-bold">
            <span class="truncate">{{ isDone(row) ? '✔ ' : '' }}{{ row.name }}</span>
            <span class="shrink-0">{{ picked[row.key] || 0 }}/{{ row.quantity }}</span>
          </div>
          <div class="mt-1 text-xl text-muted">{{ row.location_name }}</div>
        </div>
        <button class="work-btn mt-auto" @click="cancelPicking">처음부터 다시 고르기</button>
      </aside>
    </div>

    <QuantityDialog v-if="qtyRow" :name="qtyRow.name" label="남은 수량" :remaining="qtyRow.quantity - (picked[qtyRow.key] || 0)"
      @confirm="enterQuantity" @close="qtyRow = null" />
  </WorkLayout>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'
import ScanBox from '../../components/work/ScanBox.vue'
import QuantityDialog from '../../components/work/QuantityDialog.vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { isLocationCode, useLocationCheck } from '../../composables/useLocationCheck'
import { useDialogStore } from '../../stores/dialogStore'
import { buildPickList } from '../../utils/pickList'
import { dueLabel, sortByDue, toneClass, useNow } from '../../utils/due'

// 집품은 재고를 바꾸지 않습니다. 꺼낸 개수만 세고, 실제 출고는 주문별 출고 화면에서 합니다.
// 화면을 벗어났다 돌아와도 이어서 하도록 진행 상황을 브라우저에 저장합니다.
const STORAGE_KEY = 'wms_picking'
const router = useRouter()
const dialog = useDialogStore()
const { ok, fail } = useWorkFeedback()
const location = useLocationCheck()
const now = useNow()
const orders = ref([])
const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
const chosen = ref(saved?.chosen || [])
const picked = ref(saved?.picked || {})
const started = ref(!!saved?.started)
const qtyRow = ref(null)

const rows = computed(() => buildPickList(orders.value.filter(o => chosen.value.includes(o.id))))
const isDone = (row) => (picked.value[row.key] || 0) >= row.quantity
const current = computed(() => rows.value.find(row => !isDone(row)))
const doneCount = computed(() => rows.value.filter(isDone).length)

watch([chosen, picked, started], () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ chosen: chosen.value, picked: picked.value, started: started.value }))
}, { deep: true })

const toggle = (id) => {
  chosen.value = chosen.value.includes(id) ? chosen.value.filter(x => x !== id) : [...chosen.value, id]
}
const start = () => {
  picked.value = {}
  started.value = true
}

const addPicked = (row, count) => {
  picked.value = { ...picked.value, [row.key]: (picked.value[row.key] || 0) + count }
  ok(`${row.name} ${picked.value[row.key]}/${row.quantity}`)
}

const onScan = (code) => {
  if (isLocationCode(code)) return location.check(code, current.value && { ...current.value, id: current.value.key }, '에서 꺼냅니다',
    current.value?.barcode ? [{ barcode: current.value.barcode, location_name: current.value.location_name }] : [])
  // 지금 위치의 상품이 맞으면 그 줄을, 아니면 같은 상품의 다른 줄을 채웁니다.
  const row = current.value?.sku === code ? current.value : rows.value.find(r => r.sku === code && !isDone(r))
  if (!row) {
    const known = rows.value.some(r => r.sku === code)
    return fail(known ? `[${code}] 필요한 만큼 이미 꺼냈습니다.` : `[${code}] 이번 집품에 없는 상품입니다.`)
  }
  addPicked(row, 1)
}

const enterQuantity = (quantity) => {
  const row = qtyRow.value
  qtyRow.value = null
  addPicked(row, quantity)
}

const reset = () => {
  started.value = false
  chosen.value = []
  picked.value = {}
  location.reset()
  localStorage.removeItem(STORAGE_KEY)
}

const cancelPicking = async () => {
  if (!(await dialog.confirm('지금까지 센 집품 기록을 지우고 주문을 다시 고릅니다.', { title: '처음부터', okText: '다시 고르기', large: true, focusCancel: true }))) return
  reset()
}

const finish = () => {
  reset()
  router.push('/work/outbound')
}

onMounted(async () => {
  orders.value = sortByDue((await axios.get('/api/inventory/orders/', { params: { status: '출고대기' } })).data)
  // 그사이 출고되거나 취소된 주문은 집품에서 뺍니다.
  chosen.value = chosen.value.filter(id => orders.value.some(o => o.id === id))
  if (started.value && chosen.value.length === 0) reset()
})
</script>
