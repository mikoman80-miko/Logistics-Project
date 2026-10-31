<template>
  <div class="flex flex-col h-full">
    <div v-if="isReturnFormOpen" class="modal-overlay">
      <form class="modal w-[480px]" @submit.prevent="submitReturn">
        <div class="modal-header">반품 회수 등록</div>
        <div class="modal-content flex flex-col gap-2.5">
          <label class="field-label">고객명
            <input v-model="returnForm.customer" class="field w-full mt-1" maxlength="100" required />
          </label>
          <label class="field-label">반품 사유
            <select v-model="returnForm.reason" class="field w-full mt-1" required>
              <option v-for="reason in RETURN_REASONS" :key="reason" :value="reason">{{ reason }}</option>
            </select>
          </label>
          <label class="field-label">출고된 시리얼
            <select v-model="returnForm.serial" class="field w-full mt-1" required>
              <option :value="null" disabled>시리얼 선택</option>
              <option v-for="serial in shippedSerials" :key="serial.id" :value="serial.id">
                {{ serial.serial_number }} ({{ serial.item_name }})
              </option>
            </select>
          </label>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">등록</button>
          <button type="button" class="btn btn-lg" @click="isReturnFormOpen = false">닫기</button>
        </div>
      </form>
    </div>
    <div class="flex gap-2.5 h-full">
      <!-- 📦 좌측: 회수 예정(반품/AS) 목록 -->
      <div class="panel w-[350px] shrink-0">
        <div
          class="panel-header">
          <span class="panel-title">회수 예정 목록</span>
          <div class="flex gap-1">
            <button v-if="isAdmin" class="btn btn-primary btn-sm" @click="openReturnForm">반품 등록</button>
            <button class="btn btn-sm" @click="loadReturns">새로고침</button>
          </div>
        </div>
        <div class="panel-body-flush">
          <table class="data-table">
            <thead>
              <tr>
                <th
                  width="100">회수번호</th>
                <th
                 >
                  고객명(사유)</th>
                <th
                  width="80">S/N</th>
                <th
                  width="80">상태</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="returnOrders.length === 0">
                <td colspan="4" class="text-center">예정된 회수 내역이 없습니다.</td>
              </tr>
              <tr v-for="order in returnOrders" :key="order.id" class="is-clickable"
                :class="{ 'is-selected': selectedReturn?.id === order.id }" @click="selectedReturn = order">
                <td class="text-center font-bold text-danger">{{ order.returnNo }}
                </td>
                <td class="truncate">{{ order.customer }} <span
                    class="text-[10px] text-muted">({{ order.reason }})</span></td>
                <td class="text-center font-mono">{{ order.expectedSerial }}</td>
                <td class="text-center font-bold" :class="statusColor(order.status)">
                  {{ order.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 🎯 우측: 반입 스캔 및 품질 판정 보드 -->
      <div class="panel flex-1"
        v-if="selectedReturn">
        <div
          class="panel-header panel-title">
          <span>[{{ selectedReturn.returnNo }}] 기기 반입 스캔 및 품질 검수</span>
        </div>
        <div class="panel-body">
          <div class="alert alert-info">※ 반입된 박스를
            개봉하고 기기의 시리얼 번호(S/N)를 스캔하여 회수를 확정하십시오.</div>

          <div class="scan-box mb-3.5">
            <form @submit.prevent="handleReturnScan" class="flex gap-2.5 items-center">
              <strong class="text-body">회수 기기 S/N 스캔:</strong>
              <input ref="scanInputRef" v-model="scanSerialVal" type="text"
                class="field field-scan w-[300px]"
                placeholder="S/N 스캔 후 Enter" autofocus autocomplete="off"
                :disabled="selectedReturn.status === '회수완료'" />
              <button type="submit"
                class="btn btn-success btn-lg"
                :disabled="selectedReturn.status === '회수완료'">스캔 확인</button>
            </form>
          </div>

          <!-- 스캔 완료 후 품질 판정 영역 -->
          <div v-if="isScanned" class="border border-success bg-[#f1f8e9] p-[15px]">
            <h3 class="mt-0 text-primary text-heading mb-2">✓ 기기 회수 확인 (S/N: {{ scanSerialVal }})</h3>
            <table class="form-table max-w-[600px] mb-3.5">
              <tbody>
                <tr>
                  <th class="w-[120px]">
                    외관 및 품질 판정</th>
                  <td>
                    <select v-model="inspectedQuality"
                      class="field w-full">
                      <option value="양품A급">양품A급 (단순변심/박스개봉)</option>
                      <option value="양품B급">양품B급 (미세스크래치)</option>
                      <option value="AS진행중">AS진행중 (고장수리 요망)</option>
                      <option value="사용불가">사용불가 (파손/침수)</option>
                    </select>
                  </td>
                </tr>
                <tr v-if="inspectedQuality === 'AS진행중' || inspectedQuality === '사용불가'">
                  <th class="bg-warning-soft text-warning">불량/AS
                    상세 사유</th>
                  <td class="bg-highlight">
                    <input v-model="defectDetail" type="text"
                      class="field w-full"
                      placeholder="파손 및 불량 부위를 상세히 적어주세요." />
                  </td>
                </tr>
                <tr v-if="inspectedQuality === 'AS진행중' || inspectedQuality === '사용불가'">
                  <th class="bg-warning-soft text-warning">처리 담당자
                  </th>
                  <td class="bg-highlight">
                    <input v-model="managerName" type="text"
                      class="field w-[150px]"
                      placeholder="담당 엔지니어명" />
                  </td>
                </tr>
                <tr>
                  <th>다음 물류 상태
                  </th>
                  <td class="font-bold text-primary">
                    {{ inspectedQuality === 'AS진행중' ? 'AS진행중' : (inspectedQuality === '사용불가' ? '불량폐기' : '재고보유') }}
                  </td>
                </tr>
              </tbody>
            </table>
            <button
              class="btn btn-primary btn-lg"
              @click="completeReturnReceiving">입고 및 품질 상태 확정</button>
          </div>
        </div>
      </div>
      <div
        class="panel flex-1 justify-center items-center"
        v-else>
        <div class="text-muted font-bold text-heading">좌측에서 회수(반품/AS) 처리할 내역을 선택해 주십시오.</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated, nextTick } from 'vue'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import { useAuthStore } from '../../stores/auth'
import { apiErrorMessage } from '../../utils/apiError'
import { playBeep } from '../../utils/beep'

const store = useInventoryStore()
const toast = useToastStore()

const returnOrders = ref([])
const selectedReturn = ref(null)
const scanSerialVal = ref('')
const scanInputRef = ref(null)
const isScanned = ref(false)
const inspectedQuality = ref('양품A급')

const defectDetail = ref('')
const managerName = ref('시스템관리자')

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === '관리자')

const RETURN_REASONS = ['단순변심', '전원불량', '액정파손', '기타']
const isReturnFormOpen = ref(false)
const isSaving = ref(false)
const returnForm = ref({ customer: '', reason: RETURN_REASONS[0], serial: null })
const shippedSerials = computed(() => store.serials.filter(s => s.status === '출고완료'))

const loadReturns = async () => {
  const data = await store.fetchReturns('회수대기')
  returnOrders.value = data.reverse().map(order => ({
    id: order.id,
    returnNo: order.return_no,
    customer: order.customer,
    reason: order.reason,
    expectedSerial: order.serial_number,
    status: order.status
  }))
  if (selectedReturn.value) selectedReturn.value = returnOrders.value.find(o => o.id === selectedReturn.value.id) || null
}

const openReturnForm = async () => {
  await store.fetchSerials()
  if (shippedSerials.value.length === 0) return toast.addToast('출고 완료된 시리얼이 없어 반품을 등록할 수 없습니다.', 'error')
  returnForm.value = { customer: '', reason: RETURN_REASONS[0], serial: null }
  isReturnFormOpen.value = true
}

const submitReturn = async () => {
  isSaving.value = true
  try {
    const created = await store.createReturn(returnForm.value)
    toast.addToast(`반품 ${created.return_no} 등록 완료`, 'success')
    isReturnFormOpen.value = false
    await loadReturns()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '반품 등록 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const statusColor = (status) => {
  if (status === '회수대기') return 'text-danger'
  if (status === '회수완료') return 'text-success'
  return ''
}

const handleReturnScan = async () => {
  if (!scanSerialVal.value || !selectedReturn.value) return
  if (scanSerialVal.value !== selectedReturn.value.expectedSerial) {
    playBeep('error')
    toast.addToast(`❌ [오회수] 예정된 시리얼(${selectedReturn.value.expectedSerial})과 불일치!`, 'error', 5000)
    scanSerialVal.value = ''
    await nextTick(); if (scanInputRef.value) scanInputRef.value.focus();
    return
  }

  playBeep('success')
  isScanned.value = true
  toast.addToast('✅ 정상 기기 회수 확인', 'success')

  defectDetail.value = ''

  if (selectedReturn.value.reason === '단순변심') inspectedQuality.value = '양품A급'
  else if (selectedReturn.value.reason === '전원불량') inspectedQuality.value = 'AS진행중'
  else if (selectedReturn.value.reason === '액정파손') inspectedQuality.value = '사용불가'
}

const completeReturnReceiving = async () => {
  let nextStatus = '재고보유'
  if (inspectedQuality.value === 'AS진행중') nextStatus = 'AS진행중'
  if (inspectedQuality.value === '사용불가') nextStatus = '불량폐기'

  let extraMsg = ''
  if (nextStatus !== '재고보유') {
    extraMsg = `\n사유: ${defectDetail.value || '미입력'} (담당: ${managerName.value})`
  }

  try {
    // AS진행중은 물류 상태라 품질 등급으로 보내지 않습니다.
    const quality = inspectedQuality.value === 'AS진행중' ? null : inspectedQuality.value
    const detail = nextStatus !== '재고보유' ? `${defectDetail.value || '미입력'} / 담당: ${managerName.value}` : ''
    await store.completeReturn(selectedReturn.value.id, nextStatus, quality, detail)
  } catch (err) {
    playBeep('error')
    return toast.addToast(apiErrorMessage(err, '회수 처리 중 오류가 발생했습니다.'), 'error', 5000)
  }

  toast.addToast(`📦 [${inspectedQuality.value}] 최종 입고 및 상태 변경 완료!${extraMsg}`, 'info')

  isScanned.value = false
  scanSerialVal.value = ''
  selectedReturn.value = null
  await loadReturns()
}


onActivated(() => { store.fetchSerials(); loadReturns() })
</script>
<!-- CSS 삭제됨 -->