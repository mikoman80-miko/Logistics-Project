<template>
  <div class="page">
    <div class="panel flex-1">
      <div
        class="panel-header">
        <div class="flex items-center gap-1">
          <span class="panel-title mr-2">재고 조사</span>
          <button class="tab" :class="{ 'is-active': mode === 'scan' }" @click="mode = 'scan'">스캔 조사</button>
          <button class="tab" :class="{ 'is-active': mode === 'count' }" @click="mode = 'count'">수량 입력 조사</button>
        </div>
        <div v-if="mode === 'count'">
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

      <div v-if="mode === 'scan'" class="panel-body">
        <div class="alert alert-info">※ 위치를 고르고 그 선반의 물건을 하나씩 스캔한 뒤 [대조하기]를 누릅니다. 시리얼 상품은 기기의 시리얼을, 수량 상품은 상품코드를 개수만큼 스캔합니다.</div>
        <div class="panel mb-2.5">
          <div class="panel-header">
            <span class="panel-title">오늘의 순환 조사 ({{ plan.done.length }} / {{ plan.done.length + plan.todo.length }}곳 완료)</span>
            <span class="text-muted">하루 {{ plan.daily }}곳 · 모든 위치를 {{ plan.cycle_days }}일에 한 번 · 주기 넘긴 위치 {{ plan.overdue }}곳</span>
          </div>
          <div class="panel-body flex flex-wrap gap-1.5">
            <span v-if="!plan.todo.length && !plan.done.length" class="text-muted">재고가 있는 위치가 없습니다.</span>
            <button v-for="loc in plan.todo" :key="loc.id" class="btn" :title="`상품 ${loc.items}종 · 최근 30일 입출고 ${loc.moves_30d}건`" @click="scanPanel.selectLocation(loc.id)">
              <b>{{ loc.full_code }}</b>
              <span class="ml-1 text-caption" :class="loc.overdue ? 'text-danger' : 'text-muted'">{{ loc.days_since === null ? '조사 기록 없음' : `${loc.days_since}일 전` }}</span>
              <span v-if="loc.busy" class="ml-1 text-caption text-warning">자주 움직임</span>
            </button>
            <span v-for="loc in plan.done" :key="loc.id" class="btn cursor-default text-success">✔ {{ loc.full_code }}</span>
          </div>
        </div>
        <ScanAuditPanel ref="scanPanel" @applied="afterCount" @counted="loadPlan" />
      </div>

      <div v-else class="panel-body">
        <div class="alert alert-info">
          ※ 전산 재고와 실제 창고 재고(실물 재고)를 대조합니다. 실물 재고 칸에 숫자를 입력하면 오차가 자동 계산됩니다.<br />
          ※ 시리얼 관리 상품은 재고보유 시리얼 수보다 적게 입력할 수 없습니다. 없어진 기기는 시리얼 조회에서 상태를 바꿔 주세요.
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
                {{ item.name }}
                <span v-if="item.serialTracked" class="block font-normal text-caption text-muted">재고보유 시리얼 {{ item.minQty }}개</span></td>
              <td class="text-right font-bold">{{ item.systemQty }}</td>
              <td class="text-center">
                <input type="number" v-model.number="item.physicalQty" :min="item.minQty"
                  class="field field-num w-[80px]"
                  @input="calculateDiff(item)" />
              </td>
              <td class="text-right font-bold"
                :class="item.difference > 0 ? 'text-primary' : (item.difference < 0 ? 'text-danger' : '')">
                {{ item.difference > 0 ? '+' : '' }}{{ item.difference }}
              </td>
              <td class="text-center font-bold"
                :class="item.difference !== 0 ? 'text-danger' : 'text-success'">
                {{ statusText(item) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onActivated, onMounted } from 'vue'
import axios from 'axios'
import { useInventoryStore } from '../../stores/inventory'
import { apiErrorMessage } from '../../utils/apiError'
import { useToastStore } from '../../stores/toastStore'
import { useDialogStore } from '../../stores/dialogStore'
import ScanAuditPanel from '../../components/ScanAuditPanel.vue'

const store = useInventoryStore()
const mode = ref('scan')
const toast = useToastStore()
const dialog = useDialogStore()
const auditList = ref([])
const scanPanel = ref(null)
const plan = ref({ daily: 0, cycle_days: 0, todo: [], done: [], overdue: 0 })

const loadPlan = async () => {
  plan.value = (await axios.get('/api/inventory/locations/cycle_count/')).data
}
const afterCount = () => {
  fetchData()
  loadPlan()
}

const fetchData = async () => {
  await store.fetchItems()
  auditList.value = store.items.map(item => ({
    id: item.id,
    sku: item.sku,
    name: item.name,
    location: item.location_name,
    systemQty: item.quantity,
    physicalQty: item.quantity,
    difference: 0,
    serialTracked: item.serial_tracked,
    minQty: item.serial_tracked ? (item.in_stock_serials || 0) : 0,
  }))
}

const statusText = (item) => {
  if (item.physicalQty < item.minQty) return '시리얼 확인'
  return item.difference === 0 ? '일치' : '불일치'
}

const calculateDiff = (item) => {
  if (item.physicalQty === '' || isNaN(item.physicalQty)) item.physicalQty = 0
  item.difference = item.physicalQty - item.systemQty
}

const applyAudit = async () => {
  const discrepancies = auditList.value.filter(item => item.difference !== 0)
  if (discrepancies.length === 0) {
    toast.addToast('모든 재고가 전산과 일치합니다. 반영할 내역이 없습니다.', 'info')
    return
  }
  if (!(await dialog.confirm(`불일치 ${discrepancies.length}건을 실물 재고 기준으로 조정합니다.\n전산 재고가 바뀌고 입출고 기록이 남습니다.`, { title: '실사 결과 반영', okText: '반영' }))) return

  let success = 0
  const failures = []
  for (const item of discrepancies) {
    try {
      await store.updateQuantity(item.id, item.physicalQty, true)
      success++
    } catch (e) {
      failures.push(apiErrorMessage(e, `[${item.sku}] 조정 중 오류가 발생했습니다.`))
    }
  }

  const summary = `재고 조정 완료 (총 ${success}건 반영)`
  if (failures.length) await dialog.alert(`${summary}\n\n반영하지 못한 ${failures.length}건:\n${failures.join('\n')}`, { title: '일부 반영 실패' })
  else toast.addToast(summary, 'success')
  await fetchData()
}

onMounted(() => { fetchData() })
onActivated(loadPlan)  // 다른 탭에서 조사하고 돌아와도 최신 목록
</script>
<!-- CSS 삭제됨 -->