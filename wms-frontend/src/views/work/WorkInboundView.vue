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
      <section class="flex flex-col gap-5 min-h-0">
        <div v-if="activeLine" class="work-task">
          <div class="text-[56px] font-bold leading-tight">{{ activeLine.item_name }}</div>
          <div class="text-4xl font-mono">{{ activeLine.item_sku }}</div>
          <div class="text-[80px] font-bold leading-tight">
            <span class="text-primary">{{ activeLine.received_quantity }}</span> / {{ activeLine.order_quantity }}개
          </div>
          <div class="text-[44px] font-bold text-warning">📍 {{ activeLine.location_name || '위치 미지정' }}에 보관</div>
        </div>
        <div v-else class="work-task justify-center items-center flex-1 text-[56px] font-bold text-muted">
          상품 바코드를 스캔하세요
        </div>
        <div class="text-4xl font-bold text-center">{{ prompt }}</div>
        <ScanBox :paused="!!qtyLine" @scan="onScan" />
        <button v-if="activeLine && !activeLine.serial_tracked && !isDone(activeLine)" class="work-btn" @click="qtyLine = activeLine">수량 직접 입력</button>
      </section>

      <aside class="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <div class="text-3xl font-bold">{{ po.po_number }} · {{ po.supplier_name || '거래처 미지정' }}</div>
        <div v-for="line in po.items" :key="line.id" class="work-line" :class="{ 'is-done': isDone(line), 'is-current': line.item_sku === contextSku }">
          <div class="flex justify-between gap-3 font-bold">
            <span class="truncate">{{ isDone(line) ? '✔ ' : '' }}{{ line.item_name }}</span>
            <span class="shrink-0">{{ line.received_quantity }}/{{ line.order_quantity }}</span>
          </div>
          <div class="mt-1 text-xl text-muted">{{ line.serial_tracked ? '시리얼 스캔' : '수량 입고' }}</div>
        </div>
        <button class="work-btn mt-auto" @click="leave">발주서 목록으로</button>
      </aside>
    </div>

    <QuantityDialog v-if="qtyLine" :name="qtyLine.item_name" :remaining="qtyLine.order_quantity - qtyLine.received_quantity"
      @confirm="enterQuantity" @close="qtyLine = null" />
  </WorkLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'
import ScanBox from '../../components/work/ScanBox.vue'
import QuantityDialog from '../../components/work/QuantityDialog.vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { apiErrorMessage } from '../../utils/apiError'

const { ok, fail } = useWorkFeedback()
const poList = ref([])
const po = ref(null)
const contextSku = ref('')
const qtyLine = ref(null)

const isDone = (line) => line.received_quantity >= line.order_quantity
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
    if (po.value.status === '입고완료') await leave()
  } catch (err) {
    fail(apiErrorMessage(err, '입고 처리 중 오류가 발생했습니다.'))
  }
}

const onScan = async (code) => {
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
  contextSku.value = ''
  await load()
}

onMounted(load)
</script>
