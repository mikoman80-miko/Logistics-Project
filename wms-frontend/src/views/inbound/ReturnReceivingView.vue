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
          <label class="field-label">출고된 시리얼
            <select v-model="form.serial" class="field w-full mt-1" required>
              <option :value="null" disabled>시리얼 선택</option>
              <option v-for="serial in shippedSerials" :key="serial.id" :value="serial.id">
                {{ serial.serial_number }} ({{ serial.item_name }})
              </option>
            </select>
          </label>
          <div class="pt-2 border-t border-line">
            <div class="font-bold mb-1.5">회수지 <span class="font-normal text-muted">비워 두면 그 기기를 출고한 주문의 배송지로 회수를 요청합니다.</span></div>
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
            <option value="회수대기">회수 대기</option>
            <option value="회수완료">회수 완료</option>
            <option value="취소됨">취소됨</option>
          </select>
          <button class="btn btn-primary btn-sm" @click="openForm">반품 등록</button>
          <button class="btn btn-success btn-sm" @click="router.push('/work/return')">현장 화면에서 회수</button>
        </div>
      </div>
      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th width="170">반품번호</th>
              <th width="160">고객</th>
              <th width="110">사유</th>
              <th width="180">시리얼</th>
              <th>상품명</th>
              <th width="90">상태</th>
              <th width="110">택배 회수</th>
              <th width="90">관리</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="returns.length === 0" class="empty-row">
              <td colspan="8">반품이 없습니다. 고객이 반품을 요청하면 [반품 등록]을 누르세요.</td>
            </tr>
            <tr v-for="row in returns" :key="row.id">
              <td class="text-center font-bold text-primary">{{ row.return_no }}</td>
              <td class="truncate">{{ row.customer }}</td>
              <td class="text-center">{{ row.reason }}</td>
              <td class="text-center font-mono">{{ row.serial_number }}</td>
              <td class="truncate">{{ row.item_name }}</td>
              <td class="text-center font-bold">{{ row.status }}</td>
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
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import { apiErrorMessage } from '../../utils/apiError'
import ShippingAddressFields from '../../components/ShippingAddressFields.vue'
import CarrierPanel from '../../components/CarrierPanel.vue'
import axios from 'axios'

const RETURN_REASONS = ['단순변심', '전원불량', '액정파손', '기타']

const router = useRouter()
const store = useInventoryStore()
const toast = useToastStore()

const returns = ref([])
const statusFilter = ref('회수대기')
const isFormOpen = ref(false)
const isSaving = ref(false)
const emptyAddress = () => ({ contact_name: '', contact_phone: '', zipcode: '', address: '', address_detail: '' })
const form = ref({ customer: '', reason: RETURN_REASONS[0], serial: null, ...emptyAddress() })
const detail = ref(null)
const pickupForm = ref(emptyAddress())
const shippedSerials = computed(() => store.serials.filter(s => s.status === '출고완료'))

const load = async () => {
  returns.value = await store.fetchReturns(statusFilter.value)
}

const openForm = async () => {
  await store.fetchSerials()
  if (shippedSerials.value.length === 0) return toast.addToast('출고 완료된 시리얼이 없어 반품을 등록할 수 없습니다.', 'error')
  form.value = { customer: '', reason: RETURN_REASONS[0], serial: null, ...emptyAddress() }
  isFormOpen.value = true
}

const submitReturn = async () => {
  isSaving.value = true
  try {
    const created = await store.createReturn(form.value)
    if (created.carrier_error) toast.addToast(`반품 ${created.return_no} 등록 완료. 회수 요청 실패: ${created.carrier_error}`, 'error', 7000)
    else toast.addToast(`반품 ${created.return_no} 등록 완료${created.waybill_no ? ` (회수 운송장 ${created.waybill_no})` : ''}`, 'success')
    isFormOpen.value = false
    statusFilter.value = '회수대기'
    await load()
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
  if (!confirm(`[${row.return_no}] 반품을 취소하시겠습니까?`)) return
  try {
    const result = await store.cancelReturn(row.id)
    toast.addToast(result.message, 'info')
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '반품 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

watch(statusFilter, load)

onActivated(load)
</script>
