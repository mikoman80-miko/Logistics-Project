<template>
  <div class="flex flex-col h-full">
    <div v-if="isFormOpen" class="modal-overlay">
      <form class="modal w-[720px]" @submit.prevent="submitOrder">
        <div class="modal-header">{{ editingId ? '주문 수정' : '출고 주문 등록' }}</div>
        <div class="modal-content">
          <div v-if="store.items.length === 0" class="alert alert-warning">등록된 상품이 없습니다. 기본 설정 → 상품에서 먼저 등록하세요.</div>
          <div class="toolbar mb-2.5">
            <label class="field-label">거래처/고객</label>
            <input v-model="form.customer" class="field w-[220px]" maxlength="100" required />
            <label class="field-label ml-2.5">비고</label>
            <input v-model="form.note" class="field flex-1" maxlength="200" />
          </div>
          <div v-if="linesLocked" class="alert alert-warning">스캔을 시작한 주문이라 품목은 바꿀 수 없습니다. 현장 화면에서 [다시 스캔]으로 지운 뒤 수정하세요.</div>
          <OrderLinesEditor v-else :lines="form.items" :items="store.items" />
          <div class="mt-3 pt-2.5 border-t border-line">
            <div class="font-bold mb-1.5">배송지 <span class="font-normal text-muted">{{ editingId ? '배송지를 바꾸면 기존 송장을 취소하고 새로 발급합니다.' : '등록하면 택배사에 운송장 발급을 요청합니다.' }}</span></div>
            <ShippingAddressFields :model="form" />
          </div>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">{{ editingId ? '저장' : '등록' }}</button>
          <button type="button" class="btn btn-lg" @click="isFormOpen = false">닫기</button>
        </div>
      </form>
    </div>

    <!-- 운송장 발급 다시 시도 (주소 수정 포함) -->
    <div v-if="waybillForm" class="modal-overlay">
      <form class="modal w-[600px]" @submit.prevent="issueWaybill">
        <div class="modal-header">운송장 발급</div>
        <div class="modal-content">
          <div v-if="selected?.carrier_error" class="alert alert-danger">{{ selected.carrier_error }}</div>
          <ShippingAddressFields :model="waybillForm" />
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">발급 요청</button>
          <button type="button" class="btn btn-lg" @click="waybillForm = null">닫기</button>
        </div>
      </form>
    </div>

    <ShippingLabelModal v-if="labelOrder" :order="labelOrder" @close="labelOrder = null" />
    <AddressImportModal v-if="importOpen" @close="importOpen = false" @saved="loadOrders()" />
    <PickListPrintModal v-if="pickListOpen" :orders="pickOrders" @close="pickListOpen = false" />

    <div class="page-split">
      <div class="panel w-full md:w-[520px] shrink-0">
        <div class="panel-header">
          <span class="panel-title">출고 주문 목록</span>
          <div class="flex gap-1">
            <select v-model="statusFilter" class="field field-sm">
              <option value="">전체</option>
              <option value="출고대기">출고 대기</option>
              <option value="출고완료">출고 완료</option>
              <option value="취소됨">취소됨</option>
            </select>
            <button class="btn btn-primary btn-sm" @click="openForm">주문 등록</button>
          </div>
        </div>
        <ListFilter :model="filter" placeholder="주문번호, 고객, 운송장, 상품" @apply="loadOrders(1)" />
        <div class="toolbar px-2.5 py-1.5 border-b border-line bg-surface-head">
          <span class="text-muted">선택 {{ checkedIds.length }}건</span>
          <button class="btn btn-sm" :disabled="checkedIds.length < 2 || isSaving" title="받는 분과 배송지가 같은 출고대기 주문을 운송장 하나로 보냅니다" @click="bundleOrders">묶음배송</button>
          <button class="btn btn-sm" :disabled="!pickOrders.length" :title="checkedIds.length ? '고른 주문의 품목을 위치 순서로 인쇄합니다' : '고른 주문이 없으면 목록의 출고대기 주문 전부를 인쇄합니다'" @click="pickListOpen = true">집품 리스트 인쇄 ({{ pickOrders.length }}건)</button>
          <span class="flex-1"></span>
          <button class="btn btn-sm" @click="importOpen = true">배송지 일괄 등록</button>
        </div>
        <div class="panel-body-flush">
          <table class="data-table">
            <thead>
              <tr>
                <th width="28"></th>
                <th width="165">주문번호</th>
                <th>거래처/고객</th>
                <th width="50">품목</th>
                <th width="150">출고 마감</th>
                <th width="70">택배</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="orders.length === 0" class="empty-row">
                <td colspan="6">{{ isFiltered ? '조건에 맞는 주문이 없습니다.' : '주문이 없습니다. [주문 등록]을 눌러 추가하세요.' }}</td>
              </tr>
              <tr v-for="order in orders" :key="order.id" class="is-clickable" :class="{ 'is-selected': selected?.id === order.id }" @click="selected = order">
                <td class="text-center" @click.stop>
                  <input v-if="canBundle(order)" v-model="checkedIds" type="checkbox" :value="order.id" :aria-label="`${order.order_no} 선택`" />
                </td>
                <td class="text-center font-bold text-primary whitespace-nowrap">{{ order.order_no }}</td>
                <td class="truncate"><span v-if="order.is_urgent" class="mr-1 px-1 text-caption font-bold text-white bg-danger">긴급</span>{{ order.customer }}
                  <span v-if="order.bundle_orders.length" class="ml-1 px-1 text-caption font-bold text-primary border border-primary">묶음</span>
                  <span v-else-if="bundleCandidates.has(order.id)" class="ml-1 px-1 text-caption text-warning border border-warning" title="같은 배송지의 출고대기 주문이 있습니다">묶음 가능</span>
                </td>
                <td class="text-right">{{ order.items.length }}종</td>
                <td class="text-center truncate" :class="dueLabel(order, now) && toneClass[dueLabel(order, now).tone]">{{ dueLabel(order, now)?.text.replace(' 마감 · ', ' · ') || '-' }}</td>
                <td class="text-center truncate" :class="order.carrier_error ? 'text-danger font-bold' : ''">{{ order.carrier_error ? '오류' : (order.carrier_status || '-') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pager :count="orderCount" :page="page" @change="loadOrders" />
      </div>

      <div v-if="selected" class="panel flex-1">
        <div class="panel-header">
          <span class="panel-title">[{{ selected.order_no }}] {{ selected.customer }} ({{ selected.status }})</span>
          <div v-if="selected.status === '출고대기'" class="flex gap-1">
            <button class="btn btn-success btn-sm" @click="router.push('/work/outbound')">현장 화면에서 출고</button>
            <button class="btn btn-sm" :class="{ 'btn-danger': !selected.is_urgent }" :disabled="isSaving" @click="toggleUrgent">{{ selected.is_urgent ? '긴급 해제' : '긴급 지정' }}</button>
            <button class="btn btn-sm" @click="openEdit">주문 수정</button>
            <button class="btn btn-danger btn-sm" @click="cancelOrder">주문 취소</button>
          </div>
        </div>
        <div class="panel-body">
          <CarrierPanel :record="selected">
            <button v-if="selected.waybill_no" class="btn btn-sm" @click="labelOrder = selected">송장 출력</button>
            <button v-if="selected.waybill_no" class="btn btn-sm" :disabled="isSaving" @click="track">배송 조회</button>
            <button v-if="!selected.waybill_no && selected.status === '출고대기'" class="btn btn-sm btn-primary" @click="openWaybill">운송장 발급</button>
          </CarrierPanel>
          <div v-if="selected.bundle_orders.length" class="alert alert-info flex items-center gap-2">
            <span class="flex-1">묶음배송 (운송장 하나로 함께 보냄): {{ selected.bundle_orders.join(', ') }}
              <span class="font-normal">· 대표 {{ selected.bundle_orders[0] }}</span></span>
            <button v-if="selected.status === '출고대기'" class="btn btn-sm" :disabled="isSaving" @click="unbundle">묶음 해제</button>
          </div>
          <div v-if="selected.split_from_no" class="alert alert-info">부분 출고 후 남은 수량으로 만든 주문입니다. (원래 주문 {{ selected.split_from_no }})</div>
          <div v-if="selected.note" class="alert alert-info">비고: {{ selected.note }}</div>
          <table class="data-table">
            <thead>
              <tr>
                <th width="130">보관 위치</th>
                <th width="150">상품코드</th>
                <th>상품명</th>
                <th width="80">시리얼</th>
                <th width="80">지시 수량</th>
                <th width="80">스캔 수량</th>
                <th width="80">현재 재고</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in selected.items" :key="line.id" :class="{ 'row-success': line.picked_quantity >= line.quantity }">
                <td class="text-center">{{ line.location_name || '미지정' }}</td>
                <td class="text-center font-mono">{{ line.item_sku }}</td>
                <td class="truncate">{{ line.item_name }}</td>
                <td class="text-center">{{ line.serial_tracked ? '관리' : '-' }}</td>
                <td class="text-right font-bold">{{ line.quantity }}</td>
                <td class="text-right font-bold">{{ line.picked_quantity }}</td>
                <td class="text-right">{{ line.current_quantity }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="panel flex-1 justify-center items-center">
        <div class="text-muted font-bold text-heading">왼쪽에서 주문을 선택하면 품목이 보입니다.</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import OrderLinesEditor from '../../components/OrderLinesEditor.vue'
import ShippingAddressFields from '../../components/ShippingAddressFields.vue'
import ShippingLabelModal from '../../components/ShippingLabelModal.vue'
import CarrierPanel from '../../components/CarrierPanel.vue'
import ListFilter from '../../components/ListFilter.vue'
import AddressImportModal from '../../components/AddressImportModal.vue'
import PickListPrintModal from '../../components/PickListPrintModal.vue'
import Pager from '../../components/Pager.vue'
import { useDialogStore } from '../../stores/dialogStore'
import axios from 'axios'
import { apiErrorMessage } from '../../utils/apiError'
import { dueLabel, toneClass, useNow } from '../../utils/due'

const router = useRouter()
const now = useNow()
const route = useRoute()
const store = useInventoryStore()
const toast = useToastStore()
const dialog = useDialogStore()

const orders = ref([])
const selected = ref(null)
const statusFilter = ref('출고대기')
const isFormOpen = ref(false)
const isSaving = ref(false)
const emptyAddress = () => ({ contact_name: '', contact_phone: '', zipcode: '', address: '', address_detail: '' })
const form = ref({ customer: '', note: '', items: [], ...emptyAddress() })
const waybillForm = ref(null)
const labelOrder = ref(null)
const filter = ref({ q: '', start_date: '', end_date: '' })
const isFiltered = computed(() => !!(filter.value.q || filter.value.start_date || filter.value.end_date))
const editingId = ref(null)
const importOpen = ref(false)
const checkedIds = ref([])

// 묶음배송: 출고대기이고 아직 묶이지 않은 주문만 고를 수 있습니다.
// 집품 리스트: 고른 주문, 없으면 목록의 출고대기 주문 전부
const pickListOpen = ref(false)
const pickOrders = computed(() => {
  const waiting = orders.value.filter(o => o.status === '출고대기')
  return checkedIds.value.length ? waiting.filter(o => checkedIds.value.includes(o.id)) : waiting
})

const canBundle = (order) => order.status === '출고대기' && order.bundle_orders.length === 0
const addressKey = (o) => [o.contact_name, (o.contact_phone || '').replace(/\D/g, ''), o.zipcode, o.address, o.address_detail]
  .map(v => String(v || '').trim().replace(/\s+/g, ' ')).join('|')
// 같은 배송지로 가는 다른 출고대기 주문이 있는 주문 (목록에 "묶음 가능" 표시)
const bundleCandidates = computed(() => {
  const groups = new Map()
  for (const order of orders.value.filter(o => canBundle(o) && o.address)) {
    const key = addressKey(order)
    groups.set(key, [...(groups.get(key) || []), order.id])
  }
  return new Set([...groups.values()].filter(ids => ids.length > 1).flat())
})
const linesLocked = ref(false)

// 주문은 계속 쌓이므로 50건씩 나눠 불러옵니다. (다른 곳에서 부르면 지금 페이지를 다시 읽음)
const page = ref(1)
const orderCount = ref(0)
const loadOrders = async (toPage = page.value) => {
  const data = await store.fetchPage('/api/inventory/orders/', { status: statusFilter.value, ...filter.value }, toPage)
  if (!data.results.length && toPage > 1) return loadOrders(toPage - 1)  // 마지막 페이지가 비면 앞으로
  orders.value = data.results
  orderCount.value = data.count
  page.value = toPage
  checkedIds.value = checkedIds.value.filter(id => orders.value.some(o => o.id === id && canBundle(o)))
  if (selected.value) selected.value = orders.value.find(o => o.id === selected.value.id) || null
}

const openForm = async () => {
  await store.fetchItems()
  form.value = { customer: '', note: '', items: [{ item: null, quantity: 1 }], ...emptyAddress() }
  editingId.value = null
  linesLocked.value = false
  isFormOpen.value = true
}

const openEdit = async () => {
  await store.fetchItems()
  const order = selected.value
  const { customer, note, contact_name, contact_phone, zipcode, address, address_detail } = order
  form.value = { customer, note, contact_name, contact_phone, zipcode, address, address_detail,
    items: order.items.map(line => ({ item: line.item, quantity: line.quantity })) }
  editingId.value = order.id
  linesLocked.value = order.items.some(line => line.picked_quantity > 0)
  isFormOpen.value = true
}

const submitEdit = async () => {
  const { items, ...fields } = form.value
  const body = linesLocked.value ? fields : { ...fields, items }
  const res = await axios.post(`/api/inventory/orders/${editingId.value}/edit/`, body)
  applyOrder(res.data.order)
  toast.addToast(res.data.message, res.data.order.carrier_error ? 'error' : 'success', 6000)
  isFormOpen.value = false
}

const submitOrder = async () => {
  isSaving.value = true
  try {
    if (editingId.value) return await submitEdit()
    const created = await store.createOrder(form.value)
    if (created.carrier_error) toast.addToast(`주문 ${created.order_no} 등록 완료. 운송장 발급 실패: ${created.carrier_error}`, 'error', 7000)
    else toast.addToast(`주문 ${created.order_no} 등록 완료${created.waybill_no ? ` (운송장 ${created.waybill_no})` : ''}`, 'success')
    isFormOpen.value = false
    statusFilter.value = '출고대기'
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, editingId.value ? '주문 수정 중 오류가 발생했습니다.' : '주문 등록 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

// 택배 요청 결과로 받은 주문을 목록과 상세에 반영합니다.
const applyOrder = (order) => {
  const index = orders.value.findIndex(o => o.id === order.id)
  if (index >= 0) orders.value[index] = order
  selected.value = order
}

const openWaybill = () => {
  const { contact_name, contact_phone, zipcode, address, address_detail } = selected.value
  waybillForm.value = { contact_name, contact_phone, zipcode, address, address_detail }
}

const issueWaybill = async () => {
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/orders/${selected.value.id}/issue_waybill/`, waybillForm.value)
    applyOrder(res.data.order)
    waybillForm.value = null
    toast.addToast(res.data.message, 'success')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '운송장 발급 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const track = async () => {
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/orders/${selected.value.id}/track/`)
    applyOrder(res.data.order)
    toast.addToast(res.data.message, 'info')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '배송 조회 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const bundleOrders = async () => {
  const picked = orders.value.filter(o => checkedIds.value.includes(o.id))
  if (!(await dialog.confirm(`${picked.map(o => o.order_no).join(', ')}\n${picked.length}건을 운송장 하나로 묶습니다. 대표 주문은 가장 먼저 등록한 주문이고, 나머지 주문의 송장은 취소합니다.`, { title: '묶음배송', okText: '묶기' }))) return
  isSaving.value = true
  try {
    const res = await axios.post('/api/inventory/orders/bundle/', { ids: checkedIds.value })
    toast.addToast(res.data.message, 'success', 6000)
    checkedIds.value = []
    await loadOrders()
    selected.value = orders.value.find(o => o.id === res.data.order.id) || res.data.order
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '묶음배송 처리 중 오류가 발생했습니다.'), 'error', 6000)
  } finally {
    isSaving.value = false
  }
}

const toggleUrgent = async () => {
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/orders/${selected.value.id}/urgent/`, { urgent: !selected.value.is_urgent })
    toast.addToast(res.data.message, 'success')
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '긴급 표시를 바꾸지 못했습니다.'), 'error')
  } finally {
    isSaving.value = false
  }
}

const unbundle = async () => {
  if (!(await dialog.confirm('묶음을 풀고 대표 주문을 뺀 나머지 주문에 운송장을 새로 발급합니다.', { title: '묶음 해제', okText: '해제' }))) return
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/orders/${selected.value.id}/unbundle/`)
    toast.addToast(res.data.message, 'success', 6000)
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '묶음 해제 중 오류가 발생했습니다.'), 'error', 6000)
  } finally {
    isSaving.value = false
  }
}

const cancelOrder = async () => {
  const waybill = selected.value.waybill_no ? `\n운송장 ${selected.value.waybill_no}도 택배사에 취소를 요청합니다.` : ''
  if (!(await dialog.confirm(`[${selected.value.order_no}] 주문을 취소하시겠습니까?${waybill}`, { danger: true, okText: '주문 취소', cancelText: '닫기' }))) return
  try {
    const result = await store.cancelOrder(selected.value.id)
    toast.addToast(result.message, 'info')
    selected.value = null
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '주문 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

let keepSelection = false
watch(statusFilter, () => {
  if (keepSelection) return (keepSelection = false)  // 아래 onActivated가 직접 조회합니다.
  selected.value = null
  loadOrders(1)
})

// 다른 화면에서 /orders?q=주문번호 로 들어오면 그 주문을 찾아 엽니다.
onActivated(async () => {
  const q = route.query.q
  if (!q) return loadOrders()
  filter.value = { q, start_date: '', end_date: '' }
  router.replace({ query: {} })
  if (statusFilter.value) {
    keepSelection = true
    statusFilter.value = ''
  }
  await loadOrders(1)
  if (orders.value.length === 1) selected.value = orders.value[0]
})
</script>
