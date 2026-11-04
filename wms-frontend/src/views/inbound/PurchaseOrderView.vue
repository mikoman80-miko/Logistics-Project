<template>
  <div class="flex flex-col h-full">
    <ReorderSuggestModal v-if="suggestOpen" @close="suggestOpen = false" @created="fetchPOs()" />
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

    <div v-if="cancelForm" class="modal-overlay" @click.self="cancelForm = null">
      <form class="modal w-[450px]" @submit.prevent="submitCancel">
        <div class="modal-header">입고 취소</div>
        <div class="modal-content flex flex-col gap-2.5">
          <div class="alert alert-warning m-0">[{{ cancelForm.line.item_sku }}] {{ cancelForm.line.item_name }} · 입고 {{ cancelForm.line.received_quantity }}개<br />취소한 수량만큼 재고가 줄고, 발주서의 입고 수량도 줄어듭니다.</div>
          <label v-if="cancelForm.line.serial_tracked" class="field-label">취소할 시리얼
            <select v-model="cancelForm.serial_number" class="field w-full mt-1" required>
              <option value="" disabled>시리얼 선택</option>
              <option v-for="sn in cancelForm.line.received_serials" :key="sn" :value="sn">{{ sn }}</option>
            </select>
            <span v-if="cancelForm.line.received_serials.length === 0" class="block mt-1 font-normal text-danger">취소할 수 있는 시리얼이 없습니다. 이미 출고되었거나 상태가 바뀌었습니다.</span>
          </label>
          <label v-else class="field-label">취소할 수량
            <input v-model.number="cancelForm.quantity" type="number" min="1" :max="cancelForm.line.received_quantity" class="field field-num w-[120px] mt-1 block" required />
          </label>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-danger btn-lg" :disabled="isSaving">입고 취소</button>
          <button type="button" class="btn btn-lg" @click="cancelForm = null">닫기</button>
        </div>
      </form>
    </div>

    <div class="page-split">
      <div class="panel w-full md:w-[500px] shrink-0">
        <div class="panel-header">
          <span class="panel-title">발주서 목록</span>
          <div class="flex gap-1">
            <select v-model="statusFilter" class="field field-sm">
              <option value="">전체</option>
              <option value="발주대기">발주 대기</option>
              <option value="입고중">입고중</option>
              <option value="입고완료">입고 완료</option>
              <option value="취소됨">취소됨</option>
            </select>
            <button class="btn btn-sm" @click="suggestOpen = true">발주 제안</button>
            <button class="btn btn-primary btn-sm" @click="openForm">발주 등록</button>
            <button class="btn btn-sm" @click="fetchPOs()">새로고침</button>
          </div>
        </div>
        <ListFilter :model="filter" placeholder="발주번호, 거래처, 상품" @apply="fetchPOs(1)" />
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
                <td colspan="3">{{ filter.q || filter.start_date || filter.end_date || statusFilter ? '조건에 맞는 발주서가 없습니다.' : '발주서가 없습니다. [발주 등록]을 눌러 추가하세요.' }}</td>
              </tr>
              <tr v-for="po in poList" :key="po.id" class="is-clickable" :class="{ 'is-selected': selected?.id === po.id }" @click="selected = po">
                <td class="text-center text-primary font-bold">{{ po.po_number }}</td>
                <td class="truncate">{{ po.supplier_name || '미지정' }}</td>
                <td class="text-center font-bold" :class="statusClass(po.status)">{{ po.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pager :count="poCount" :page="page" @change="fetchPOs" />
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
                <th width="90">검수 차이</th>
                <th width="90">관리</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="item in selected.items" :key="item.id">
              <tr :class="{ 'row-success': item.remaining <= 0 }">
                <td class="text-center font-mono">{{ item.item_sku }}</td>
                <td class="truncate">{{ item.item_name }}</td>
                <td class="text-center">{{ item.serial_tracked ? '관리' : '-' }}</td>
                <td class="text-right font-bold">{{ item.order_quantity }}</td>
                <td class="text-right font-bold text-primary">{{ item.received_quantity }}</td>
                <td class="text-right" :class="item.issues.length ? 'font-bold text-warning' : 'text-muted'">{{ item.issues.length ? `${item.issues.length}건` : '-' }}</td>
                <td class="text-center">
                  <button v-if="item.received_quantity > 0" class="btn btn-sm btn-danger" @click="openCancel(item)">입고 취소</button>
                </td>
              </tr>
              <tr v-for="issue in item.issues" :key="`issue-${issue.id}`" class="row-warning">
                <td colspan="5" class="text-caption">
                  └ <b>{{ issue.kind }} {{ issue.quantity }}개</b>{{ issue.note ? ` · ${issue.note}` : '' }}
                  <span class="text-muted"> · {{ issue.user }} · {{ issue.created_at.slice(0, 16).replace('T', ' ') }}</span>
                </td>
                <td colspan="2" class="text-center"><button class="btn btn-sm" :disabled="selected.status === '취소됨'" @click="cancelIssue(issue)">기록 지우기</button></td>
              </tr>
              </template>
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
import { computed, onActivated, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore'
import { useInventoryStore } from '../../stores/inventory'
import OrderLinesEditor from '../../components/OrderLinesEditor.vue'
import ListFilter from '../../components/ListFilter.vue'
import Pager from '../../components/Pager.vue'
import ReorderSuggestModal from '../../components/ReorderSuggestModal.vue'
import { useDialogStore } from '../../stores/dialogStore'
import { apiErrorMessage } from '../../utils/apiError'

const router = useRouter()
const route = useRoute()
const suggestOpen = ref(false)
const toast = useToastStore()
const store = useInventoryStore()
const dialog = useDialogStore()

const poList = ref([])
const statusFilter = ref('')
const filter = ref({ q: '', start_date: '', end_date: '' })
const selected = ref(null)
const isFormOpen = ref(false)
const isSaving = ref(false)
const suppliers = ref([])
const form = ref({ supplier: null, expected_date: '', items: [] })
const activeSuppliers = computed(() => suppliers.value.filter(s => s.is_active))

const statusClass = (status) => ({ 입고완료: 'text-success', 입고중: 'text-primary', 발주대기: 'text-warning' }[status] || 'text-muted')

// 발주서는 50건씩 나눠 불러옵니다.
const page = ref(1)
const poCount = ref(0)
const fetchPOs = async (toPage = page.value) => {
  const data = await store.fetchPage('/api/inventory/purchase-orders/', { status: statusFilter.value, ...filter.value }, toPage)
  if (!data.results.length && toPage > 1) return fetchPOs(toPage - 1)
  poList.value = data.results
  poCount.value = data.count
  page.value = toPage
  if (selected.value) selected.value = poList.value.find(p => p.id === selected.value.id) || null
}

const openForm = async () => {
  await store.fetchItems()
  suppliers.value = (await axios.get('/api/inventory/suppliers/')).data
  form.value = { supplier: null, expected_date: '', items: [{ item: null, quantity: 1 }] }
  isFormOpen.value = true
}

const addSupplier = async () => {
  const name = await dialog.prompt('신규 거래처 이름을 입력하세요.', { title: '신규 거래처', okText: '등록', maxlength: 100 })
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

const cancelForm = ref(null)
const cancelIssue = async (issue) => {
  const message = issue.kind === '초과' ? '이 기록을 지웁니다.' : `기록을 지우면 ${issue.quantity}개를 다시 받을 수 있게 됩니다.`
  if (!(await dialog.confirm(`[${issue.kind} ${issue.quantity}개] ${message}`, { title: '검수 차이 기록 지우기', okText: '지우기' }))) return
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${selected.value.id}/cancel_issue/`, { issue: issue.id })
    toast.addToast(res.data.message, 'success')
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '기록을 지우지 못했습니다.'), 'error', 5000)
  }
}

const openCancel = (line) => {
  cancelForm.value = { line, serial_number: '', quantity: 1 }
}

const submitCancel = async () => {
  const { line, serial_number, quantity } = cancelForm.value
  const body = line.serial_tracked ? { sku: line.item_sku, serial_number } : { sku: line.item_sku, quantity }
  isSaving.value = true
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${selected.value.id}/cancel_receipt/`, body)
    toast.addToast(res.data.message, 'success')
    cancelForm.value = null
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '입고 취소 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const cancelPO = async () => {
  if (!(await dialog.confirm(`[${selected.value.po_number}] 발주서를 취소하시겠습니까?`, { danger: true, okText: '발주 취소', cancelText: '닫기' }))) return
  try {
    const res = await axios.post(`/api/inventory/purchase-orders/${selected.value.id}/cancel/`)
    toast.addToast(res.data.message, 'info')
    selected.value = null
    await fetchPOs()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주서 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

watch(statusFilter, () => fetchPOs(1))

// 오늘 할 일의 재고 부족 카드에서 /purchase-order?suggest=1 로 들어오면 발주 제안을 엽니다.
// 다른 화면에서 /purchase-order?q=발주번호 로 들어오면 그 발주서를 찾아 엽니다.
onActivated(async () => {
  const { suggest, q } = route.query
  if (suggest || q) router.replace({ query: {} })
  if (suggest) suggestOpen.value = true
  if (q) {
    filter.value = { q, start_date: '', end_date: '' }
    statusFilter.value = ''
  }
  await fetchPOs(q ? 1 : page.value)
  if (q && poList.value.length === 1) selected.value = poList.value[0]
})
</script>
