<template>
  <div class="page">
    <div class="panel flex-1">
      <div
        class="panel-header">
        <span class="panel-title">정기 재고 실사 (Inventory Audit)</span>
        <div>
          <button
            class="btn"
            @click="fetchData">🔄 새로고침</button>
          <button
            class="btn btn-success ml-1.5"
            @click="applyAudit" :disabled="auditList.length === 0">
            실사 결과 일괄 반영
          </button>
        </div>
      </div>

      <div class="panel-body">
        <div class="alert alert-info">
          ※ 전산 상의 재고와 실제 창고 재고(실물 재고)를 대조합니다. 실물 재고 칸에 숫자를 입력하면 오차가 자동 계산됩니다.
        </div>

        <table class="data-table data-table-sm">
          <thead>
            <tr>
              <th
               
                width="120">보관 구역</th>
              <th
               
                width="150">상품코드</th>
              <th
               >
                상품명</th>
              <th
               
                width="100">전산 재고 (A)</th>
              <th
               
                width="120">실물 재고 (B)</th>
              <th
               
                width="100">오차 (B - A)</th>
              <th
               
                width="100">상태</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="auditList.length === 0">
              <td colspan="7" class="text-center">조회된 상품이 없습니다.</td>
            </tr>
            <tr v-for="item in auditList" :key="item.id" :class="{ 'row-danger': item.difference !== 0 }"
             >
              <td
                class="text-center whitespace-nowrap overflow-hidden text-ellipsis">
                {{ item.location || '미지정' }}</td>
              <td class="text-center font-mono">{{ item.sku }}</td>
              <td
                class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">
                {{ item.name }}</td>
              <td class="text-right font-bold">{{ item.systemQty }}</td>
              <td class="text-center">
                <input type="number" v-model.number="item.physicalQty"
                  class="field field-num w-[80px]"
                  @input="calculateDiff(item)" />
              </td>
              <td class="text-right font-bold"
                :class="item.difference > 0 ? 'text-primary' : (item.difference < 0 ? 'text-danger' : '')">
                {{ item.difference > 0 ? '+' : '' }}{{ item.difference }}
              </td>
              <td class="text-center font-bold"
                :class="item.difference !== 0 ? 'text-danger' : 'text-success'">
                {{ item.difference === 0 ? '일치' : '불일치' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useInventoryStore } from '../../stores/inventory'

const store = useInventoryStore()
const auditList = ref([])

const fetchData = async () => {
  await store.fetchItems()
  auditList.value = store.items.map(item => ({
    id: item.id,
    sku: item.sku,
    name: item.name,
    location: item.location_name,
    systemQty: item.quantity,
    physicalQty: item.quantity,
    difference: 0
  }))
}

const calculateDiff = (item) => {
  if (item.physicalQty === '' || isNaN(item.physicalQty)) item.physicalQty = 0
  item.difference = item.physicalQty - item.systemQty
}

const applyAudit = async () => {
  const discrepancies = auditList.value.filter(item => item.difference !== 0)
  if (discrepancies.length === 0) {
    alert('모든 재고가 전산과 일치합니다. 반영할 내역이 없습니다.')
    return
  }
  if (!confirm(`총 ${discrepancies.length}건의 불일치 항목이 발견되었습니다.\n실물 재고 기준으로 전산 재고를 강제 조정하시겠습니까?`)) return

  let success = 0
  for (const item of discrepancies) {
    try {
      await store.updateQuantity(item.id, item.physicalQty, true)
      success++
    } catch (e) {
      console.error(`[${item.sku}] 조정 실패`, e)
    }
  }

  alert(`재고 조정 완료 (총 ${success}건 반영)`)
  await fetchData()
}

onMounted(() => { fetchData() })
</script>
<!-- CSS 삭제됨 -->