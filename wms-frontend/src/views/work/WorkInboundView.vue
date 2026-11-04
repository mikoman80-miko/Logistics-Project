<template>
  <WorkLayout title="입고">
    <!-- 발주서 선택 -->
    <div v-if="!po" class="flex flex-col gap-4">
      <div class="text-4xl font-bold">입고할 발주서를 누르세요</div>
      <div v-if="poList.length === 0" class="work-empty">입고 대기 중인 발주서가 없습니다.</div>
      <button v-for="row in poList" :key="row.id" class="work-row" @click="po = row">
        <span class="font-bold">{{ row.po_number }}</span>
        <span>{{ row.supplier_name || '거래처 미지정' }}</span>
        <span class="text-muted">{{ row.status }}</span>
      </button>
    </div>

    <!-- 스캔 작업 -->
    <div v-else class="grid grid-cols-[2fr_1fr] gap-6 h-full">
      <section v-if="isComplete" class="work-task justify-center items-center gap-8">
        <div class="text-[64px] font-bold text-success">✔ 모든 품목 입고 완료</div>
        <div class="text-3xl text-muted">잘못 스캔한 품목은 오른쪽의 [입고 취소]로 되돌릴 수 있습니다.</div>
        <button ref="doneRef" class="work-btn work-btn-success w-full h-32! text-5xl!" @click="leave">발주서 목록으로 (Enter)</button>
      </section>

      <section v-else class="flex flex-col gap-5 min-h-0">
        <div v-if="activeLine" class="work-task">
          <div class="text-[56px] font-bold leading-tight">{{ activeLine.item_name }}</div>
          <div class="text-4xl font-mono">{{ activeLine.item_sku }}</div>
          <div class="text-[80px] font-bold leading-tight">
            <span class="text-primary">{{ activeLine.received_quantity }}</span> / {{ activeLine.order_quantity }}개
          </div>
          <div class="text-[44px] font-bold text-warning">📍 {{ activeLine.location_name || '위치 미지정' }}에 보관
            <span v-if="location.isVerified(activeLine)" class="text-success text-4xl">✔ 위치 확인</span>
          </div>
          <div v-if="activeLine.location_barcode && !location.isVerified(activeLine)" class="text-2xl text-muted">선반의 위치 라벨을 스캔하면 맞는 자리인지 확인합니다.</div>
        </div>
        <div v-else class="work-task justify-center items-center flex-1 text-[56px] font-bold text-muted">
          상품 바코드를 스캔하세요
        </div>
        <div class="text-4xl font-bold text-center">{{ prompt }}</div>
        <ScanBox :paused="!!qtyLine || !!cancelLine" @scan="onScan" />
        <button v-if="activeLine && !activeLine.serial_tracked && !isDone(activeLine)" class="work-btn" @click="qtyLine = activeLine">수량 직접 입력</button>
      </section>

      <aside class="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <div class="text-3xl font-bold">{{ po.po_number }} · {{ po.supplier_name || '거래처 미지정' }}</div>
        <div v-for="line in po.items" :key="line.id" class="work-line" :class="{ 'is-done': isDone(line), 'is-current': line.item_sku === contextSku }">
          <div class="flex justify-between gap-3 font-bold">
            <span class="truncate">{{ isDone(line) ? '✔ ' : '' }}{{ line.item_name }}</span>
            <span class="shrink-0">{{ line.received_quantity }}/{{ line.order_quantity }}</span>
          </div>
          <div class="flex justify-between items-center mt-1 text-xl text-muted">
            <span>{{ line.serial_tracked ? '시리얼 스캔' : '수량 입고' }}</span>
            <button v-if="line.received_quantity > 0" class="work-link" @click="cancelLine = line">입고 취소</button>
          </div>
        </div>
        <button class="work-btn mt-auto" @click="leave">발주서 목록으로</button>
      </aside>
    </div>

    <QuantityDialog v-if="qtyLine" :name="qtyLine.item_name" :remaining="qtyLine.order_quantity - qtyLine.received_quantity"
      @confirm="enterQuantity" @close="qtyLine = null" />

    <!-- 입고 취소: 시리얼 관리 품목은 취소할 시리얼을 스캔하고, 그 외는 수량을 입력합니다. -->
    <SerialDialog v-if="cancelLine?.serial_tracked" :name="cancelLine.item_name" message="입고를 취소할 기기의 시리얼을 스캔하세요"
      @confirm="cancelSerial" @close="cancelLine = null" />
    <QuantityDialog v-else-if="cancelLine" :name="`${cancelLine.item_name} 입고 취소`" label="입고된 수량"
      :remaining="cancelLine.received_quantity" @confirm="cancelQuantity" @close="cancelLine = null" />
  </WorkLayout>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'
import ScanBox from '../../components/work/ScanBox.vue'
import QuantityDialog from '../../components/work/QuantityDialog.vue'
import SerialDialog from '../../components/work/SerialDialog.vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { isLocationCode, useLocationCheck } from '../../composables/useLocationCheck'
import { apiErrorMessage } from '../../utils/apiError'

const { ok, fail } = useWorkFeedback()
const location = useLocationCheck()
const poList = ref([])
const po = ref(null)
const contextSku = ref('')
const qtyLine = ref(null)
const cancelLine = ref(null)
const doneRef = ref(null)

const isDone = (line) => line.received_quantity >= line.order_quantity
const isComplete = computed(() => po.value?.status === '입고완료')
const activeLine = computed(() => po.value?.items.find(line => line.item_sku === contextSku.value))
const prompt = computed(() => {
  const line = activeLine.value
  if (!line || isDone(line) || !line.serial_tracked) return '상품 바코드를 스캔하세요'
  return '시리얼을 스캔하세요'
})

const load = async () => {
  const res = await axios.get('/api/inventory/purchase-orders/')
  poList.value = res.data.filter(row => row.status === '발주대기' || row.status === '입고중').reverse()
}

const receive = async (body) => {
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${po.value.id}/receive_inbound/`, body)
    po.value = res.data.po
    ok(res.data.message)
  } catch (err) {
    fail(apiErrorMessage(err, '입고 처리 중 오류가 발생했습니다.'))
  }
}

const cancelReceipt = async (body) => {
  cancelLine.value = null
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${po.value.id}/cancel_receipt/`, body)
    po.value = res.data.po
    ok(res.data.message)
  } catch (err) {
    fail(apiErrorMessage(err, '입고 취소 중 오류가 발생했습니다.'))
  }
}
const cancelSerial = (code) => cancelReceipt({ sku: cancelLine.value.item_sku, serial_number: code })
const cancelQuantity = (quantity) => cancelReceipt({ sku: cancelLine.value.item_sku, quantity })

// 전 품목을 받으면 바로 나가지 않고, 잘못 스캔한 것을 되돌릴 기회를 줍니다.
watch(isComplete, async (done) => {
  if (done) {
    await nextTick()
    doneRef.value?.focus()
  }
})

const onScan = async (code) => {
  if (isLocationCode(code)) return location.check(code, activeLine.value, '에 보관합니다')
  const line = po.value.items.find(row => row.item_sku === code)
  if (line) {
    contextSku.value = code
    if (line.serial_tracked) ok(`${line.item_name}: 시리얼을 스캔하세요`)
    else await receive({ sku: code, quantity: 1 })
    return
  }
  const active = activeLine.value
  if (!active?.serial_tracked) {
    fail(`[${code}] 이 발주서에 없는 상품입니다.`)
    return
  }
  await receive({ sku: active.item_sku, serial_number: code })
}

const enterQuantity = async (quantity) => {
  const line = qtyLine.value
  qtyLine.value = null
  await receive({ sku: line.item_sku, quantity })
}

const leave = async () => {
  po.value = null
  location.reset()
  contextSku.value = ''
  await load()
}

onMounted(load)
</script>
