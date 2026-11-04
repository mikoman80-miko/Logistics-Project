<template>
  <div class="flex flex-col h-full">
    <div v-if="isFormOpen" class="modal-overlay">
      <form class="modal w-[720px]" @submit.prevent="submitOrder">
        <div class="modal-header">출고 주문 등록</div>
        <div class="modal-content">
          <div v-if="store.items.length === 0" class="alert alert-warning">등록된 상품이 없습니다. 기본 설정 → 상품에서 먼저 등록하세요.</div>
          <div class="toolbar mb-2.5">
            <label class="field-label">거래처/고객</label>
            <input v-model="form.customer" class="field w-[220px]" maxlength="100" required />
            <label class="field-label ml-2.5">비고</label>
            <input v-model="form.note" class="field flex-1" maxlength="200" />
          </div>
          <OrderLinesEditor :lines="form.items" :items="store.items" />
          <div class="mt-3 pt-2.5 border-t border-line">
            <div class="font-bold mb-1.5">배송지 <span class="font-normal text-muted">등록하면 택배사에 운송장 발급을 요청합니다.</span></div>
            <ShippingAddressFields :model="form" />
          </div>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">등록</button>
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

    <div class="page-split">
      <div class="panel w-full md:w-[420px] shrink-0">
        <div class="panel-header">
          <span class="panel-title">출고 주문 목록</span>
          <div class="flex gap-1">
            <select v-model="statusFilter" class="field field-sm">
              <option value="출고대기">출고 대기</option>
              <option value="출고완료">출고 완료</option>
              <option value="취소됨">취소됨</option>
            </select>
            <button class="btn btn-primary btn-sm" @click="openForm">주문 등록</button>
          </div>
        </div>
        <div class="panel-body-flush">
          <table class="data-table">
            <thead>
              <tr>
                <th width="150">주문번호</th>
                <th>거래처/고객</th>
                <th width="50">품목</th>
                <th width="70">택배</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="orders.length === 0" class="empty-row">
                <td colspan="4">주문이 없습니다. [주문 등록]을 눌러 추가하세요.</td>
              </tr>
              <tr v-for="order in orders" :key="order.id" class="is-clickable" :class="{ 'is-selected': selected?.id === order.id }" @click="selected = order">
                <td class="text-center font-bold text-primary">{{ order.order_no }}</td>
                <td class="truncate">{{ order.customer }}</td>
                <td class="text-right">{{ order.items.length }}종</td>
                <td class="text-center truncate" :class="order.carrier_error ? 'text-danger font-bold' : ''">{{ order.carrier_error ? '오류' : (order.carrier_status || '-') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="selected" class="panel flex-1">
        <div class="panel-header">
          <span class="panel-title">[{{ selected.order_no }}] {{ selected.customer }} ({{ selected.status }})</span>
          <div v-if="selected.status === '출고대기'" class="flex gap-1">
            <button class="btn btn-success btn-sm" @click="router.push('/work/outbound')">현장 화면에서 출고</button>
            <button class="btn btn-danger btn-sm" @click="cancelOrder">주문 취소</button>
          </div>
        </div>
        <div class="panel-body">
          <CarrierPanel :record="selected">
            <button v-if="selected.waybill_no" class="btn btn-sm" @click="labelOrder = selected">송장 출력</button>
            <button v-if="selected.waybill_no" class="btn btn-sm" :disabled="isSaving" @click="track">배송 조회</button>
            <button v-if="!selected.waybill_no && selected.status === '출고대기'" class="btn btn-sm btn-primary" @click="openWaybill">운송장 발급</button>
          </CarrierPanel>
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
import { onActivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import OrderLinesEditor from '../../components/OrderLinesEditor.vue'
import ShippingAddressFields from '../../components/ShippingAddressFields.vue'
import ShippingLabelModal from '../../components/ShippingLabelModal.vue'
import CarrierPanel from '../../components/CarrierPanel.vue'
import axios from 'axios'
import { apiErrorMessage } from '../../utils/apiError'

const router = useRouter()
const store = useInventoryStore()
const toast = useToastStore()

const orders = ref([])
const selected = ref(null)
const statusFilter = ref('출고대기')
const isFormOpen = ref(false)
const isSaving = ref(false)
const emptyAddress = () => ({ contact_name: '', contact_phone: '', zipcode: '', address: '', address_detail: '' })
const form = ref({ customer: '', note: '', items: [], ...emptyAddress() })
const waybillForm = ref(null)
const labelOrder = ref(null)

const loadOrders = async () => {
  orders.value = await store.fetchOrders(statusFilter.value)
  if (selected.value) selected.value = orders.value.find(o => o.id === selected.value.id) || null
}

const openForm = async () => {
  await store.fetchItems()
  form.value = { customer: '', note: '', items: [{ item: null, quantity: 1 }], ...emptyAddress() }
  isFormOpen.value = true
}

const submitOrder = async () => {
  isSaving.value = true
  try {
    const created = await store.createOrder(form.value)
    if (created.carrier_error) toast.addToast(`주문 ${created.order_no} 등록 완료. 운송장 발급 실패: ${created.carrier_error}`, 'error', 7000)
    else toast.addToast(`주문 ${created.order_no} 등록 완료${created.waybill_no ? ` (운송장 ${created.waybill_no})` : ''}`, 'success')
    isFormOpen.value = false
    statusFilter.value = '출고대기'
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '주문 등록 중 오류가 발생했습니다.'), 'error', 5000)
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

const cancelOrder = async () => {
  if (!confirm(`[${selected.value.order_no}] 주문을 취소하시겠습니까?`)) return
  try {
    const result = await store.cancelOrder(selected.value.id)
    toast.addToast(result.message, 'info')
    selected.value = null
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '주문 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

watch(statusFilter, () => {
  selected.value = null
  loadOrders()
})

onActivated(loadOrders)
</script>
