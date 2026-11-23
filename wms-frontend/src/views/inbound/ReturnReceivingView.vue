<template>
  <div class="page">
    <div v-if="isFormOpen" class="modal-overlay">
      <form class="modal w-[600px]" @submit.prevent="submitReturn">
        <div class="modal-header">반품 등록</div>
        <div class="modal-content flex flex-col gap-2.5">
          <label class="field-label">고객명
            <input v-model="form.customer" class="field w-full mt-1" maxlength="100" required />
          </label>
          <label class="field-label">반품 사유
            <select v-model="form.reason" class="field w-full mt-1" required>
              <option v-for="reason in RETURN_REASONS" :key="reason" :value="reason">{{ reason }}</option>
            </select>
          </label>
          <div class="flex gap-4">
            <label class="flex items-center gap-1"><input v-model="mode" type="radio" value="serial" /> 시리얼 기기</label>
            <label class="flex items-center gap-1"><input v-model="mode" type="radio" value="quantity" /> 수량 상품 (시리얼 없음)</label>
          </div>
          <label v-if="mode === 'serial'" class="field-label">출고된 시리얼 <span class="font-normal text-muted">(최근 {{ SERIAL_LIMIT }}개, 없으면 검색)</span>
            <input v-model="serialQuery" class="field w-full mt-1" placeholder="시리얼, 상품코드, 상품명 검색" aria-label="시리얼 검색" @input="searchSerials" />
            <select v-model="form.serial" class="field w-full mt-1" aria-label="반품할 시리얼" required>
              <option :value="null" disabled>{{ shippedSerials.length ? '시리얼 선택' : '찾는 출고 시리얼이 없습니다' }}</option>
              <option v-for="serial in shippedSerials" :key="serial.id" :value="serial.id">
                {{ serial.serial_number }} ({{ serial.item_name }})
              </option>
            </select>
          </label>
          <template v-else>
            <div class="grid grid-cols-[1fr_110px] gap-2">
              <label class="field-label">상품
                <select v-model="form.item" class="field w-full mt-1" required @change="loadOrdersWithItem">
                  <option :value="null" disabled>상품 선택</option>
                  <option v-for="item in quantityItems" :key="item.id" :value="item.id">[{{ item.sku }}] {{ item.name }}</option>
                </select>
              </label>
              <label class="field-label">수량
                <input v-model.number="form.quantity" type="number" min="1" class="field field-num w-full mt-1" required />
              </label>
            </div>
            <label class="field-label">원래 주문 <span class="font-normal text-muted">(고르면 그 주문에서 나간 수량까지만 반품하고, 배송지에서 회수합니다)</span>
              <select v-model="form.sales_order" class="field w-full mt-1" :disabled="!form.item">
                <option :value="null">고르지 않음</option>
                <option v-for="order in ordersWithItem" :key="order.id" :value="order.id">{{ order.order_no }} · {{ order.customer }}</option>
              </select>
            </label>
          </template>
          <div class="pt-2 border-t border-line">
            <div class="font-bold mb-1.5">회수지 <span class="font-normal text-muted">비워 두면 원래 출고한 주문의 배송지로 회수를 요청합니다.</span></div>
            <ShippingAddressFields :model="form" name-label="보내는 분(고객)" :required="false" />
          </div>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">등록</button>
          <button type="button" class="btn btn-lg" @click="isFormOpen = false">닫기</button>
        </div>
      </form>
    </div>

    <!-- 택배 회수 상세 -->
    <div v-if="detail" class="modal-overlay" @click.self="detail = null">
      <div class="modal w-[640px]">
        <div class="modal-header">[{{ detail.return_no }}] 택배 회수</div>
        <div class="modal-content">
          <CarrierPanel :record="detail" title="회수">
            <button v-if="detail.waybill_no" class="btn btn-sm" :disabled="isSaving" @click="track">회수 조회</button>
          </CarrierPanel>
          <form v-if="!detail.waybill_no && detail.status === '회수대기'" @submit.prevent="requestPickup">
            <div class="font-bold mb-1.5">회수지 확인 후 회수 요청</div>
            <ShippingAddressFields :model="pickupForm" name-label="보내는 분(고객)" />
            <button type="submit" class="btn btn-primary mt-2.5" :disabled="isSaving">회수 요청</button>
          </form>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-lg" @click="detail = null">닫기</button>
        </div>
      </div>
    </div>

    <div class="panel flex-1 overflow-hidden">
      <div class="panel-header">
        <span class="panel-title">반품 목록</span>
        <div class="flex gap-1">
          <select v-model="statusFilter" class="field field-sm">
            <option value="">전체</option>
            <option value="회수대기">회수 대기</option>
            <option value="회수완료">회수 완료</option>
            <option value="취소됨">취소됨</option>
          </select>
          <button class="btn btn-primary btn-sm" @click="openForm">반품 등록</button>
          <button class="btn btn-success btn-sm" @click="router.push('/work/return')">현장 화면에서 회수</button>
        </div>
      </div>
      <ListFilter :model="filter" placeholder="반품번호, 고객, 시리얼, 운송장, 상품" @apply="load(1)" />
      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th width="170">반품번호</th>
              <th width="160">고객</th>
              <th width="110">사유</th>
              <th width="180">시리얼 / 수량</th>
              <th>상품명</th>
              <th width="90">상태</th>
              <th width="110">택배 회수</th>
              <th width="90">관리</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="returns.length === 0" class="empty-row">
              <td colspan="8">{{ filter.q || filter.start_date || filter.end_date ? '조건에 맞는 반품이 없습니다.' : '반품이 없습니다. 고객이 반품을 요청하면 [반품 등록]을 누르세요.' }}</td>
            </tr>
            <tr v-for="row in returns" :key="row.id">
              <td class="text-center font-bold text-primary">{{ row.return_no }}</td>
              <td class="truncate">{{ row.customer }}</td>
              <td class="text-center">{{ row.reason }}</td>
              <td class="text-center font-mono">{{ row.serial_number || `수량 ${row.quantity}개` }}</td>
              <td class="truncate">{{ row.item_name }}</td>
              <td class="text-center font-bold" :title="row.result">{{ row.status }}<span v-if="row.result" class="block text-caption font-normal text-muted">{{ row.result }}</span></td>
              <td class="text-center">
                <button class="btn btn-link" :class="row.carrier_error ? 'text-danger!' : ''" @click="openDetail(row)">
                  {{ row.carrier_error ? '요청 실패' : (row.carrier_status || (row.status === '회수대기' ? '요청하기' : '-')) }}
                </button>
              </td>
              <td class="text-center">
                <button v-if="row.status === '회수대기'" class="btn btn-danger btn-sm" @click="cancelReturn(row)">취소</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager :count="returnCount" :page="page" @change="load" />
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import { apiErrorMessage } from '../../utils/apiError'
import ShippingAddressFields from '../../components/ShippingAddressFields.vue'
import CarrierPanel from '../../components/CarrierPanel.vue'
import ListFilter from '../../components/ListFilter.vue'
import Pager from '../../components/Pager.vue'
import { useDialogStore } from '../../stores/dialogStore'
import axios from 'axios'

const RETURN_REASONS = ['단순변심', '전원불량', '액정파손', '기타']

const router = useRouter()
const route = useRoute()
const store = useInventoryStore()
const toast = useToastStore()
const dialog = useDialogStore()

const returns = ref([])
const statusFilter = ref('회수대기')
const filter = ref({ q: '', start_date: '', end_date: '' })
const isFormOpen = ref(false)
const isSaving = ref(false)
const emptyAddress = () => ({ contact_name: '', contact_phone: '', zipcode: '', address: '', address_detail: '' })
const form = ref({ customer: '', reason: RETURN_REASONS[0], serial: null, ...emptyAddress() })
const detail = ref(null)
const pickupForm = ref(emptyAddress())
// 반품은 50건씩 나눠 불러옵니다.
const page = ref(1)
const returnCount = ref(0)
const load = async (toPage = page.value) => {
  const data = await store.fetchPage('/api/inventory/returns/', { status: statusFilter.value, ...filter.value }, toPage)
  if (!data.results.length && toPage > 1) return load(toPage - 1)
  returns.value = data.results
  returnCount.value = data.count
  page.value = toPage
}

// 출고한 시리얼과 주문은 계속 늘어나므로 전부 받지 않고, 최근 것과 검색 결과만 받습니다.
const SERIAL_LIMIT = 50
const shippedSerials = ref([])
const serialQuery = ref('')
let serialTimer
const fetchShippedSerials = async () => {
  const data = await store.fetchPage('/api/inventory/serials/', { status: '출고완료', q: serialQuery.value.trim() }, 1, SERIAL_LIMIT)
  shippedSerials.value = data.results
  if (!shippedSerials.value.some(s => s.id === form.value.serial)) form.value.serial = null
}
const searchSerials = () => {
  clearTimeout(serialTimer)
  serialTimer = setTimeout(fetchShippedSerials, 300)
}

const mode = ref('serial')
const quantityItems = computed(() => store.items.filter(item => !item.serial_tracked))
const ordersWithItem = ref([])
const loadOrdersWithItem = async () => {
  form.value.sales_order = null
  ordersWithItem.value = form.value.item
    ? (await store.fetchPage('/api/inventory/orders/', { status: '출고완료', item: form.value.item }, 1, 100)).results
    : []
}

const openForm = async () => {
  serialQuery.value = ''
  ordersWithItem.value = []
  form.value = { serial: null }
  await Promise.all([fetchShippedSerials(), store.fetchItems()])
  mode.value = shippedSerials.value.length ? 'serial' : 'quantity'
  form.value = { customer: '', reason: RETURN_REASONS[0], serial: null, item: null, quantity: 1, sales_order: null, ...emptyAddress() }
  isFormOpen.value = true
}

const submitReturn = async () => {
  isSaving.value = true
  try {
    const { serial, item, quantity, sales_order, ...common } = form.value
    const body = mode.value === 'serial' ? { ...common, serial } : { ...common, item, quantity, sales_order }
    const created = await store.createReturn(body)
    if (created.carrier_error) toast.addToast(`반품 ${created.return_no} 등록 완료. 회수 요청 실패: ${created.carrier_error}`, 'error', 7000)
    else toast.addToast(`반품 ${created.return_no} 등록 완료${created.waybill_no ? ` (회수 운송장 ${created.waybill_no})` : ''}`, 'success')
    isFormOpen.value = false
    statusFilter.value = '회수대기'
    await load(1)
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '반품 등록 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const openDetail = (row) => {
  detail.value = row
  const { contact_name, contact_phone, zipcode, address, address_detail } = row
  pickupForm.value = { contact_name, contact_phone, zipcode, address, address_detail }
}

const applyReturn = (row) => {
  const index = returns.value.findIndex(r => r.id === row.id)
  if (index >= 0) returns.value[index] = row
  detail.value = row
}

const callCarrier = async (path, body, fallback) => {
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/returns/${detail.value.id}/${path}/`, body)
    applyReturn(res.data.return)
    toast.addToast(res.data.message, 'info')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, fallback), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}
const requestPickup = () => callCarrier('request_pickup', pickupForm.value, '회수 요청 중 오류가 발생했습니다.')
const track = () => callCarrier('track', {}, '회수 조회 중 오류가 발생했습니다.')

const cancelReturn = async (row) => {
  if (!(await dialog.confirm(`[${row.return_no}] 반품을 취소하시겠습니까?`, { danger: true, okText: '반품 취소', cancelText: '닫기' }))) return
  try {
    const result = await store.cancelReturn(row.id)
    toast.addToast(result.message, 'info')
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '반품 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

watch(statusFilter, () => load(1))

// 다른 화면에서 /returns?q=반품번호 로 들어오면 그 반품을 찾아 상세를 엽니다.
onActivated(async () => {
  const q = route.query.q
  if (q) {
    filter.value = { q, start_date: '', end_date: '' }
    router.replace({ query: {} })
    statusFilter.value = ''
  }
  await load(q ? 1 : page.value)
  if (q && returns.value.length === 1) openDetail(returns.value[0])
})
</script>
