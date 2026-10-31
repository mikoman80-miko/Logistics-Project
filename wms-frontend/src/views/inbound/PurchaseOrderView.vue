<template>
  <div class="flex flex-col h-full">
    <div v-if="isPoFormOpen" class="modal-overlay">
      <form class="modal w-[640px]" @submit.prevent="submitPO">
        <div class="modal-header">발주서 등록</div>
        <div class="modal-content">
          <div class="toolbar mb-2.5">
            <label class="field-label">거래처</label>
            <select v-model="poForm.supplier" class="field w-[200px]" required>
              <option :value="null" disabled>거래처 선택</option>
              <option v-for="supplier in activeSuppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
            </select>
            <button type="button" class="btn" @click="addSupplier">신규 거래처</button>
            <label class="field-label ml-2.5">입고 예정일</label>
            <input v-model="poForm.expected_date" type="date" class="field" />
          </div>
          <OrderLinesEditor :lines="poForm.items" :items="store.items" />
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">등록</button>
          <button type="button" class="btn btn-lg" @click="isPoFormOpen = false">닫기</button>
        </div>
      </form>
    </div>
    <div class="page-split">

      <!-- 좌측: 발주서(PO) 목록 -->
      <div
        class="panel w-full md:w-[350px] shrink-0">
        <div
          class="panel-header">
          <span class="panel-title">발주서(PO) 목록</span>
          <div class="flex gap-1">
            <button v-if="isAdmin" class="btn btn-primary btn-sm" @click="openPoForm">발주 등록</button>
            <button class="btn btn-sm" @click="fetchPOs">새로고침</button>
          </div>
        </div>
        <div class="panel-body-flush">
          <table class="data-table">
            <thead>
              <tr>
                <th
                  width="100">발주번호</th>
                <th>거래처</th>
                <th width="80">
                  상태</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="poList.length === 0">
                <td colspan="3" class="text-center text-gray-500 font-bold">진행 중인 발주 내역이 없습니다.
                </td>
              </tr>
              <tr v-for="po in poList" :key="po.id" class="is-clickable"
                :class="{ 'is-selected': selectedPO?.id === po.id }" @click="selectPO(po)">
                <td class="text-center text-primary font-bold">{{ po.po_number }}
                </td>
                <td class="truncate">{{ po.supplier_name || '미지정' }}</td>
                <td class="text-center font-bold"
                  :class="po.status === '입고완료' ? 'text-success' : 'text-danger'">{{ po.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 우측: 신규 상품 정규 입고 스캔 -->
      <div class="panel flex-1"
        v-if="selectedPO">
        <div
          class="panel-header panel-title">
          <span>[{{ selectedPO.po_number }}] 정규 입고 스캔 처리</span>
          <button v-if="isAdmin && selectedPO.status === '발주대기'" class="btn btn-danger btn-sm" @click="cancelPO">발주 취소</button>
        </div>
        <div class="panel-body">
          <div class="alert alert-info">
            ※ 납품된 상품의 바코드를 스캔하여 발주 수량과 대조 후 입고를 확정합니다.
          </div>

          <div class="scan-box">
            <form @submit.prevent="handleScan" class="flex flex-col md:flex-row gap-2.5 md:items-center">
              <strong class="text-body whitespace-nowrap">상품 바코드 스캔:</strong>
              <input ref="scanInputRef" v-model="scanInput" type="text"
                class="field field-scan w-full md:w-[300px]"
                placeholder="SKU 스캔 후 Enter" autofocus :disabled="selectedPO.status === '입고완료'" />
              <button type="submit"
                class="btn btn-success btn-lg"
                :disabled="selectedPO.status === '입고완료'">입고 스캔</button>
            </form>
          </div>

          <table class="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>상품명</th>
                <th width="80">발주수량</th>
                <th class="text-primary"
                  width="80">입고수량</th>
                <th width="80">상태</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in selectedPO.items" :key="item.id"
                :class="{ 'row-success': item.received_quantity >= item.order_quantity }">
                <td class="text-center font-mono">{{ item.item_sku }}</td>
                <td class="truncate">{{ item.item_name }}</td>
                <td class="text-right font-bold">{{ item.order_quantity }}</td>
                <td class="text-right font-bold text-primary">{{
                  item.received_quantity }}</td>
                <td class="text-center font-bold"
                  :class="item.received_quantity >= item.order_quantity ? 'text-success' : 'text-danger'">
                  {{ item.received_quantity >= item.order_quantity ? '완료' : '대기' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div
        class="panel flex-1 justify-center items-center text-muted font-bold text-heading"
        v-else>
        좌측에서 입고 처리할 발주서를 선택해주세요.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated, nextTick } from 'vue'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore'
import { useAuthStore } from '../../stores/auth'
import { useInventoryStore } from '../../stores/inventory'
import OrderLinesEditor from '../../components/OrderLinesEditor.vue'
import { apiErrorMessage } from '../../utils/apiError'

const toast = useToastStore()
const store = useInventoryStore()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === '관리자')

const isPoFormOpen = ref(false)
const isSaving = ref(false)
const suppliers = ref([])
const poForm = ref({ supplier: null, expected_date: '', items: [] })
const activeSuppliers = computed(() => suppliers.value.filter(s => s.is_active))
const poList = ref([])
const selectedPO = ref(null)
const scanInput = ref('')
const scanInputRef = ref(null)

const fetchPOs = async () => {
  try {
    const res = await axios.get('/api/inventory/purchase-orders/')
    poList.value = res.data
    // 새로고침 시 선택된 PO 갱신
    if (selectedPO.value) {
      selectedPO.value = poList.value.find(p => p.id === selectedPO.value.id)
    }
  } catch (e) { console.error('발주서 로드 실패', e) }
}

const openPoForm = async () => {
  await store.fetchItems()
  const res = await axios.get('/api/inventory/suppliers/')
  suppliers.value = res.data
  poForm.value = { supplier: null, expected_date: '', items: [{ item: null, quantity: 1 }] }
  isPoFormOpen.value = true
}

const addSupplier = async () => {
  const name = prompt('신규 거래처 이름을 입력하세요.')?.trim()
  if (!name) return
  try {
    const res = await axios.post('/api/inventory/suppliers/', { name })
    suppliers.value.push(res.data)
    poForm.value.supplier = res.data.id
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '거래처 등록 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const submitPO = async () => {
  isSaving.value = true
  try {
    const body = {
      supplier: poForm.value.supplier,
      expected_date: poForm.value.expected_date || null,
      items: poForm.value.items.map(line => ({ item: line.item, order_quantity: line.quantity }))
    }
    const res = await axios.post('/api/inventory/purchase-orders/', body)
    toast.addToast(`발주서 ${res.data.po_number} 등록 완료`, 'success')
    isPoFormOpen.value = false
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주서 등록 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const cancelPO = async () => {
  if (!confirm(`[${selectedPO.value.po_number}] 발주서를 취소하시겠습니까?`)) return
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${selectedPO.value.id}/cancel/`)
    toast.addToast(res.data.message, 'info')
    selectedPO.value = null
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주서 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const selectPO = (po) => {
  selectedPO.value = po
  scanInput.value = ''
  nextTick(() => { scanInputRef.value?.focus() })
}

const handleScan = async () => {
  if (!scanInput.value || !selectedPO.value) return

  // 현재 PO에 있는 품목인지 먼저 프론트에서 체크
  const targetItem = selectedPO.value.items.find(i => i.item_sku === scanInput.value)
  if (!targetItem) {
    toast.addToast(`해당 발주서에 존재하지 않는 상품(SKU: ${scanInput.value}) 입니다.`, 'error')
    scanInput.value = ''; await nextTick(); scanInputRef.value?.focus()
    return
  }

  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${selectedPO.value.id}/receive_inbound/`, {
      sku: scanInput.value,
      quantity: 1
    })
    toast.addToast(res.data.message, 'success', 1500)
    await fetchPOs() // 성공 후 리스트 갱신
  } catch (err) {
    toast.addToast(err.response?.data?.error || '입고 처리 중 오류가 발생했습니다.', 'error')
  } finally {
    scanInput.value = ''
    await nextTick()
    scanInputRef.value?.focus()
  }
}

onActivated(() => fetchPOs())
</script>