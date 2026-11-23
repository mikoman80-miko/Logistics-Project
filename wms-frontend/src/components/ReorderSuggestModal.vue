<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal w-[980px]">
      <div class="modal-header">발주 제안</div>
      <div class="modal-content flex flex-col gap-3">
        <div class="alert alert-info m-0">
          제안 수량 = (안전 재고 + 최근 30일 하루 평균 출고량 × 조달 {{ leadDays }}일) − (현재 재고 + 발주 중인 수량).
          거래처는 그 상품을 마지막으로 발주한 곳입니다. 수량을 고친 뒤 거래처별로 발주서를 만드세요.
        </div>
        <div v-if="loading" class="text-center text-muted p-6">계산 중...</div>
        <div v-else-if="groups.length === 0" class="alert alert-success m-0">지금 발주가 필요한 상품이 없습니다.</div>

        <div v-for="group in groups" :key="group.key" class="border border-line">
          <div class="flex items-center gap-2 px-2.5 py-1.5 bg-surface-head border-b border-line">
            <span class="font-bold">{{ group.name || '거래처 미지정' }}</span>
            <span class="text-muted">{{ group.rows.filter(r => r.checked).length }}개 상품</span>
            <span class="flex-1"></span>
            <select v-model="group.supplier" class="field field-sm w-[200px]">
              <option :value="null" disabled>거래처 선택</option>
              <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <button class="btn btn-sm btn-primary" :disabled="isSaving || !group.supplier || !group.rows.some(r => r.checked && r.order > 0)" @click="createPO(group)">
              발주서 만들기
            </button>
          </div>
          <table class="data-table data-table-sm">
            <thead>
              <tr>
                <th width="34"></th><th width="120">상품코드</th><th>상품명</th>
                <th width="70">현재</th><th width="70">안전</th><th width="80">발주 중</th><th width="90">30일 출고</th><th width="100">발주 수량</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in group.rows" :key="row.item" :class="{ 'row-muted': !row.checked }">
                <td class="text-center"><input v-model="row.checked" type="checkbox" :aria-label="`${row.sku} 포함`" /></td>
                <td class="text-center font-mono">{{ row.sku }}</td>
                <td class="truncate">{{ row.name }}</td>
                <td class="text-right font-bold" :class="row.quantity <= row.safety_stock ? 'text-danger' : ''">{{ row.quantity }}</td>
                <td class="text-right">{{ row.safety_stock }}</td>
                <td class="text-right">{{ row.incoming }}</td>
                <td class="text-right">{{ row.usage_30d }}</td>
                <td><input v-model.number="row.order" type="number" min="1" class="field field-sm field-num w-full" :disabled="!row.checked" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-lg" @click="$emit('close')">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../stores/toastStore'
import { apiErrorMessage } from '../utils/apiError'

const emit = defineEmits(['close', 'created'])
const toast = useToastStore()
const groups = ref([])
const suppliers = ref([])
const leadDays = ref(7)
const loading = ref(true)
const isSaving = ref(false)

const load = async () => {
  const [suggest, supplierList] = await Promise.all([
    axios.get('/api/inventory/purchase-orders/suggestions/'),
    axios.get('/api/inventory/suppliers/'),
  ])
  suppliers.value = supplierList.data.filter(s => s.is_active)
  leadDays.value = suggest.data.lead_days
  const byKey = new Map()
  for (const row of suggest.data.rows) {
    const key = row.supplier ?? 'none'
    if (!byKey.has(key)) byKey.set(key, { key, name: row.supplier_name, supplier: row.supplier, rows: [] })
    byKey.get(key).rows.push({ ...row, checked: true, order: row.suggested })
  }
  groups.value = [...byKey.values()]
}

const createPO = async (group) => {
  const lines = group.rows.filter(r => r.checked && r.order > 0)
  isSaving.value = true
  try {
    const res = await axios.post('/api/inventory/purchase-orders/', {
      supplier: group.supplier, expected_date: null, items: lines.map(r => ({ item: r.item, order_quantity: r.order })),
    })
    toast.addToast(`발주서 ${res.data.po_number} 등록 완료 (${lines.length}개 상품)`, 'success')
    group.rows = group.rows.filter(r => !lines.includes(r))
    groups.value = groups.value.filter(g => g.rows.length > 0)
    emit('created')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주서를 만들지 못했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  try {
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '발주 제안을 불러오지 못했습니다.'), 'error', 5000)
  } finally {
    loading.value = false
  }
})
</script>
