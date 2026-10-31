<template>
  <div class="flex flex-col h-full">
    <div v-if="isFormOpen" class="modal-overlay">
      <form class="modal w-[640px]" @submit.prevent="submitPO">
        <div class="modal-header">발주서 등록</div>
        <div class="modal-content">
          <div v-if="store.items.length === 0" class="alert alert-warning">등록된 상품이 없습니다. 기본 설정 → 상품에서 먼저 등록하세요.</div>
          <div class="toolbar mb-2.5">
            <label class="field-label">거래처</label>
            <select v-model="form.supplier" class="field w-[200px]" required>
              <option :value="null" disabled>거래처 선택</option>
              <option v-for="supplier in activeSuppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
            </select>
            <button type="button" class="btn" @click="addSupplier">신규 거래처</button>
            <label class="field-label ml-2.5">입고 예정일</label>
            <input v-model="form.expected_date" type="date" class="field" />
          </div>
          <OrderLinesEditor :lines="form.items" :items="store.items" />
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">등록</button>
          <button type="button" class="btn btn-lg" @click="isFormOpen = false">닫기</button>
        </div>
      </form>
    </div>

    <div class="page-split">
      <div class="panel w-full md:w-[420px] shrink-0">
        <div class="panel-header">
          <span class="panel-title">발주서 목록</span>
          <div class="flex gap-1">
            <button class="btn btn-primary btn-sm" @click="openForm">발주 등록</button>
            <button class="btn btn-sm" @click="fetchPOs">새로고침</button>
          </div>
        </div>
        <div class="panel-body-flush">
          <table class="data-table">
            <thead>
              <tr>
                <th width="170">발주번호</th>
                <th>거래처</th>
                <th width="80">상태</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="poList.length === 0" class="empty-row">
                <td colspan="3">발주서가 없습니다. [발주 등록]을 눌러 추가하세요.</td>
              </tr>
              <tr v-for="po in poList" :key="po.id" class="is-clickable" :class="{ 'is-selected': selected?.id === po.id }" @click="selected = po">
                <td class="text-center text-primary font-bold">{{ po.po_number }}</td>
                <td class="truncate">{{ po.supplier_name || '미지정' }}</td>
                <td class="text-center font-bold" :class="statusClass(po.status)">{{ po.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="selected" class="panel flex-1">
        <div class="panel-header">
          <span class="panel-title">[{{ selected.po_number }}] {{ selected.supplier_name }} (입고 예정일: {{ selected.expected_date || '미정' }})</span>
          <div class="flex gap-1">
            <button v-if="selected.status === '발주대기' || selected.status === '입고중'" class="btn btn-success btn-sm" @click="router.push('/work/inbound')">현장 화면에서 입고</button>
            <button v-if="selected.status === '발주대기'" class="btn btn-danger btn-sm" @click="cancelPO">발주 취소</button>
          </div>
        </div>
        <div class="panel-body">
          <table class="data-table">
            <thead>
              <tr>
                <th width="150">상품코드</th>
                <th>상품명</th>
                <th width="80">시리얼</th>
                <th width="90">발주 수량</th>
                <th width="90">입고 수량</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in selected.items" :key="item.id" :class="{ 'row-success': item.received_quantity >= item.order_quantity }">
                <td class="text-center font-mono">{{ item.item_sku }}</td>
                <td class="truncate">{{ item.item_name }}</td>
                <td class="text-center">{{ item.serial_tracked ? '관리' : '-' }}</td>
                <td class="text-right font-bold">{{ item.order_quantity }}</td>
                <td class="text-right font-bold text-primary">{{ item.received_quantity }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="panel flex-1 justify-center items-center">
        <div class="text-muted font-bold text-heading">왼쪽에서 발주서를 선택하면 품목이 보입니다.</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore'
import { useInventoryStore } from '../../stores/inventory'
import OrderLinesEditor from '../../components/OrderLinesEditor.vue'
import { apiErrorMessage } from '../../utils/apiError'

const router = useRouter()
const toast = useToastStore()
const store = useInventoryStore()

const poList = ref([])
const selected = ref(null)
const isFormOpen = ref(false)
const isSaving = ref(false)
const suppliers = ref([])
const form = ref({ supplier: null, expected_date: '', items: [] })
const activeSuppliers = computed(() => suppliers.value.filter(s => s.is_active))

const statusClass = (status) => ({ 입고완료: 'text-success', 입고중: 'text-primary', 발주대기: 'text-warning' }[status] || 'text-muted')

const fetchPOs = async () => {
  const res = await axios.get('/api/inventory/purchase-orders/')
  poList.value = res.data
  if (selected.value) selected.value = poList.value.find(p => p.id === selected.value.id) || null
}

const openForm = async () => {
  await store.fetchItems()
  suppliers.value = (await axios.get('/api/inventory/suppliers/')).data
  form.value = { supplier: null, expected_date: '', items: [{ item: null, quantity: 1 }] }
  isFormOpen.value = true
}

const addSupplier = async () => {
  const name = prompt('신규 거래처 이름을 입력하세요.')?.trim()
  if (!name) return
  try {
    const res = await axios.post('/api/inventory/suppliers/', { name })
    suppliers.value.push(res.data)
    form.value.supplier = res.data.id
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '거래처 등록 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const submitPO = async () => {
  isSaving.value = true
  try {
    const body = {
      supplier: form.value.supplier,
      expected_date: form.value.expected_date || null,
      items: form.value.items.map(line => ({ item: line.item, order_quantity: line.quantity }))
    }
    const res = await axios.post('/api/inventory/purchase-orders/', body)
    toast.addToast(`발주서 ${res.data.po_number} 등록 완료`, 'success')
    isFormOpen.value = false
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주서 등록 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const cancelPO = async () => {
  if (!confirm(`[${selected.value.po_number}] 발주서를 취소하시겠습니까?`)) return
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${selected.value.id}/cancel/`)
    toast.addToast(res.data.message, 'info')
    selected.value = null
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주서 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

onActivated(fetchPOs)
</script>
