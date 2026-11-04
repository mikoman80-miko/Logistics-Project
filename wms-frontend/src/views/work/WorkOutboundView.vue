<template>
  <WorkLayout title="출고">
    <!-- 주문 선택 -->
    <div v-if="!order" class="flex flex-col gap-4">
      <div class="text-4xl font-bold">출고할 주문을 누르세요</div>
      <div v-if="orders.length === 0" class="work-empty">출고 대기 중인 주문이 없습니다.</div>
      <button v-for="row in orders" :key="row.id" class="work-row" @click="order = row">
        <span class="font-bold">{{ row.order_no }}</span>
        <span>{{ row.customer }}</span>
        <span class="text-muted">{{ row.items.length }}종 {{ totalQuantity(row) }}개</span>
      </button>
    </div>

    <!-- 스캔 작업 -->
    <div v-else class="grid grid-cols-[2fr_1fr] gap-6 h-full">
      <section class="flex flex-col gap-5 min-h-0">
        <template v-if="current">
          <div class="work-task">
            <div class="text-4xl text-muted">{{ doneLines }} / {{ order.items.length }} 품목 완료</div>
            <div class="text-[64px] font-bold text-warning leading-tight">📍 {{ current.location_name || '위치 미지정' }}</div>
            <div class="text-[56px] font-bold leading-tight">{{ current.item_name }}</div>
            <div class="text-4xl font-mono">{{ current.item_sku }}</div>
            <div class="text-[80px] font-bold leading-tight">
              <span class="text-primary">{{ current.picked_quantity }}</span> / {{ current.quantity }}개
            </div>
          </div>
          <div class="text-4xl font-bold text-center">{{ prompt }}</div>
          <ScanBox :paused="!!qtyLine" @scan="onScan" />
          <button v-if="canEnterQuantity" class="work-btn" @click="qtyLine = current">수량 직접 입력</button>
        </template>

        <div v-else class="work-task justify-center items-center flex-1">
          <div class="text-[64px] font-bold text-success">✔ 모든 품목 스캔 완료</div>
          <div v-if="order.waybill_no" class="flex items-center gap-6 text-4xl">
            <span>운송장 <b class="font-mono">{{ order.waybill_no }}</b></span>
            <button class="work-btn" @click="labelOpen = true">송장 출력</button>
          </div>
          <div v-else-if="order.carrier_error" class="text-3xl text-danger font-bold">운송장 없음: 관리자에게 운송장 발급을 요청하세요.</div>
          <button ref="completeRef" class="work-btn work-btn-success w-full h-32! text-5xl!" :disabled="isSaving" @click="complete">출고 완료 (Enter)</button>
        </div>
      </section>

      <aside class="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <div class="text-3xl font-bold">{{ order.order_no }} · {{ order.customer }}</div>
        <div v-for="line in sortedLines" :key="line.id" class="work-line" :class="{ 'is-done': isDone(line), 'is-current': line.id === current?.id }">
          <div class="flex justify-between gap-3 font-bold">
            <span class="truncate">{{ isDone(line) ? '✔ ' : '' }}{{ line.item_name }}</span>
            <span class="shrink-0">{{ line.picked_quantity }}/{{ line.quantity }}</span>
          </div>
          <div class="flex justify-between items-center mt-1 text-xl text-muted">
            <span>{{ line.location_name || '위치 미지정' }}</span>
            <button v-if="line.picked_quantity > 0" class="work-link" @click="resetLine(line)">다시 스캔</button>
          </div>
        </div>
        <button class="work-btn mt-auto" @click="leave">주문 목록으로</button>
      </aside>
    </div>

    <ShippingLabelModal v-if="labelOpen" :order="order" @close="labelOpen = false" />

    <QuantityDialog v-if="qtyLine" :name="qtyLine.item_name" :remaining="qtyLine.quantity - qtyLine.picked_quantity"
      @confirm="enterQuantity" @close="qtyLine = null" />
  </WorkLayout>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'
import ScanBox from '../../components/work/ScanBox.vue'
import QuantityDialog from '../../components/work/QuantityDialog.vue'
import ShippingLabelModal from '../../components/ShippingLabelModal.vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { apiErrorMessage } from '../../utils/apiError'

const { ok, fail } = useWorkFeedback()
const orders = ref([])
const order = ref(null)
const contextSku = ref('')
const qtyLine = ref(null)
const isSaving = ref(false)
const completeRef = ref(null)
const labelOpen = ref(false)

const isDone = (line) => line.picked_quantity >= line.quantity
const totalQuantity = (row) => row.items.reduce((sum, line) => sum + line.quantity, 0)

// 창고 안에서 짧게 움직이도록 보관 위치 순서로 안내합니다.
const sortedLines = computed(() => [...(order.value?.items || [])].sort((a, b) => (a.location_name || '').localeCompare(b.location_name || '')))
const current = computed(() => sortedLines.value.find(line => !isDone(line)))
const doneLines = computed(() => order.value.items.filter(isDone).length)
const canEnterQuantity = computed(() => current.value && !current.value.serial_tracked && contextSku.value === current.value.item_sku)
const prompt = computed(() => {
  if (!current.value) return ''
  if (!current.value.serial_tracked) return '상품 바코드를 스캔하세요'
  return contextSku.value === current.value.item_sku ? '시리얼을 스캔하세요' : '시리얼 또는 상품 바코드를 스캔하세요'
})

const load = async () => {
  const res = await axios.get('/api/inventory/orders/', { params: { status: '출고대기' } })
  orders.value = res.data.reverse()
}

const applyResult = (data) => {
  order.value = data.order
  ok(data.message)
}

const onScan = async (code) => {
  try {
    const res = await axios.post(`/api/inventory/orders/${order.value.id}/scan/`, { code, sku: contextSku.value })
    const scannedSku = res.data.sku || (res.data.order.items.some(line => line.item_sku === code) ? code : contextSku.value)
    contextSku.value = scannedSku
    applyResult(res.data)
  } catch (err) {
    fail(apiErrorMessage(err, '스캔 처리 중 오류가 발생했습니다.'))
  }
}

const enterQuantity = async (quantity) => {
  const line = qtyLine.value
  qtyLine.value = null
  try {
    const res = await axios.post(`/api/inventory/orders/${order.value.id}/scan/`, { code: line.item_sku, quantity })
    applyResult(res.data)
  } catch (err) {
    fail(apiErrorMessage(err, '수량 처리 중 오류가 발생했습니다.'))
  }
}

const resetLine = async (line) => {
  if (!confirm(`[${line.item_name}] 스캔을 지우고 다시 하시겠습니까?`)) return
  try {
    const res = await axios.post(`/api/inventory/orders/${order.value.id}/reset_line/`, { line: line.id })
    contextSku.value = ''
    applyResult(res.data)
  } catch (err) {
    fail(apiErrorMessage(err, '처리 중 오류가 발생했습니다.'))
  }
}

const complete = async () => {
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/orders/${order.value.id}/complete/`)
    ok(res.data.message)
    await leave()
  } catch (err) {
    fail(apiErrorMessage(err, '출고 처리 중 오류가 발생했습니다. 재고는 차감되지 않았습니다.'))
  } finally {
    isSaving.value = false
  }
}

const leave = async () => {
  order.value = null
  contextSku.value = ''
  await load()
}

watch(current, async (line) => {
  if (order.value && !line) {
    await nextTick()
    completeRef.value?.focus()
  }
})

onMounted(load)
</script>
