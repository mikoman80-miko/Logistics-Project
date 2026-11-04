<template>
  <div class="page">
    <SerialHistoryModal v-if="historySerial" :serial-id="historySerial.id" :serial-number="historySerial.serial_number" @close="historySerial = null" />
    <!-- 상단 컨트롤 영역 -->
    <div class="panel p-1.5 print:hidden">
      <table class="form-table">
        <colgroup>
          <col width="100px">
          <col width="200px">
          <col width="100px">
          <col width="150px">
          <col width="100px">
          <col width="150px">
          <col width="*">
        </colgroup>
        <tbody>
          <tr>
            <th>시리얼 또는 상품코드</th>
            <td><input v-model="searchQuery" type="text"
                class="field w-full"
                placeholder="시리얼 번호 검색" /></td>
            <th>물류 상태</th>
            <td>
              <select v-model="filterStatus"
                class="field w-full">
                <option value="ALL">전체 상태</option>
                <option value="입고대기">입고대기</option>
                <option value="재고보유">재고보유</option>
                <option value="출고완료">출고완료</option>
                <option value="AS진행중">AS진행중</option>
                <option value="불량폐기">불량폐기</option>
                <option value="분실">분실</option>
              </select>
            </td>
            <th>품질 등급</th>
            <td>
              <select v-model="filterQuality"
                class="field w-full">
                <option value="ALL">전체 등급</option>
                <option value="신규상품">신규상품</option>
                <option value="양품A급">양품A급</option>
                <option value="양품B급">양품B급</option>
                <option value="사용불가">사용불가</option>
              </select>
            </td>
            <td class="text-right">
              <button
                class="btn btn-primary"
                @click="fetchData()">새로고침</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 데이터 그리드 영역 -->
    <div
      class="panel flex-1 overflow-hidden print:hidden">
      <div class="panel-header">
        <div class="flex items-center">
          <label class="text-body flex items-center cursor-pointer"><input type="checkbox" :checked="isAllSelected"
              @change="toggleSelectAll" class="mr-1" /> 페이지 전체선택</label>
          <span v-if="selectedIds.length > 0" class="text-danger font-bold ml-1.5 text-body">[{{ selectedIds.length
          }}건 선택]</span>

          <span class="text-line mx-2.5 font-bold" v-if="selectedIds.length > 0">|</span>
          <span v-if="selectedIds.length > 0" class="font-bold mr-1.5 text-body">선택 항목 일괄 변경:</span>

          <select v-if="selectedIds.length > 0" v-model="batchStatus"
            class="field">
            <option value="">-- 상태 변경 --</option>
            <option value="재고보유">재고보유</option>
            <option value="AS진행중">AS진행중</option>
            <option value="불량폐기">불량폐기</option>
          </select>

          <select v-if="selectedIds.length > 0" v-model="batchQuality"
            class="field ml-1.5">
            <option value="">-- 품질 변경 --</option>
            <option value="양품A급">양품A급</option>
            <option value="양품B급">양품B급</option>
            <option value="사용불가">사용불가</option>
          </select>

          <button v-if="selectedIds.length > 0"
            class="btn btn-success ml-1.5"
            @click="applyBatchUpdate">적용</button>
        </div>
        <div class="text-body">
          <span class="total-count">총 <strong>{{ serialCount.toLocaleString() }}</strong> 건</span>
        </div>
      </div>

      <div class="panel-body-flush">
        <table class="data-table data-table-sm">
          <thead>
            <tr>
              <th
               
                width="30"><input type="checkbox" :checked="isAllSelected" @change="toggleSelectAll" /></th>
              <th
               
                width="150">시리얼 번호 (S/N)</th>
              <th
               
                width="120">상품코드</th>
              <th
               >
                상품명</th>
              <th
               
                width="100">물류 상태</th>
              <th width="110">위치</th>
              <th
               
                width="100">품질 등급</th>
              <th
               
                width="150">최근 업데이트 일시</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="paginatedSerials.length === 0">
              <td colspan="8" class="text-center">조회된 시리얼 데이터가 없습니다.</td>
            </tr>
            <tr v-for="serial in paginatedSerials" :key="serial.id" class="is-clickable" :class="rowClass(serial)"
              title="누르면 이력을 봅니다" @click="historySerial = serial">
              <td class="text-center" @click.stop><input type="checkbox"
                  :value="serial.id" v-model="selectedIds" /></td>
              <td class="text-center font-mono font-bold">{{
                serial.serial_number }}</td>
              <td class="text-center font-mono text-primary">{{
                serial.item_sku }}</td>
              <td
                class="whitespace-nowrap overflow-hidden text-ellipsis">
                {{ serial.item_name }}</td>
              <td class="text-center font-bold"
                :class="statusColor(serial.status)">{{ serial.status }}</td>
              <td class="text-center font-mono">{{ serial.location_name || '-' }}</td>
              <td class="text-center font-bold"
                :class="qualityColor(serial.quality)">{{ serial.quality }}</td>
              <td class="text-center">{{ new
                Date(serial.updated_at).toLocaleString('ko-KR') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="p-2 text-center border-t border-line-strong bg-[#f9f9f9]">
        <button
          class="btn"
          @click="changePage(currentPage - 1)" :disabled="currentPage === 1">이전</button>
        <span class="inline-block w-[60px] font-bold text-body">{{ currentPage }} / {{ totalPages }}</span>
        <button
          class="btn"
          @click="changePage(currentPage + 1)" :disabled="currentPage === totalPages">다음</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated, watch } from 'vue'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import { apiErrorMessage } from '../../utils/apiError'
import { useDialogStore } from '../../stores/dialogStore'
import SerialHistoryModal from '../../components/SerialHistoryModal.vue'

const store = useInventoryStore()
const historySerial = ref(null)
const toast = useToastStore()
const dialog = useDialogStore()
const searchQuery = ref('')
const filterStatus = ref('ALL')
const filterQuality = ref('ALL')
const currentPage = ref(1)
const itemsPerPage = ref(30)

const selectedIds = ref([])
const batchStatus = ref('')
const batchQuality = ref('')

// 시리얼은 기기 수만큼 늘어나므로 검색·필터·페이지 나누기를 서버에서 합니다.
const paginatedSerials = ref([])
const serialCount = ref(0)
const fetchData = async (page = currentPage.value) => {
  const params = {
    q: searchQuery.value.trim(),
    status: filterStatus.value === 'ALL' ? '' : filterStatus.value,
    quality: filterQuality.value === 'ALL' ? '' : filterQuality.value,
  }
  const data = await store.fetchPage('/api/inventory/serials/', params, page, itemsPerPage.value)
  if (!data.results.length && page > 1) return fetchData(page - 1)
  paginatedSerials.value = data.results
  serialCount.value = data.count
  currentPage.value = page
}

let searchTimer
watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => fetchData(1), 300)  // 입력이 멈추면 검색
})
watch([filterStatus, filterQuality], () => fetchData(1))

const totalPages = computed(() => Math.ceil(serialCount.value / itemsPerPage.value) || 1)
const changePage = (page) => { if (page >= 1 && page <= totalPages.value) fetchData(page) }

const isAllSelected = computed(() => paginatedSerials.value.length > 0 && paginatedSerials.value.every(s => selectedIds.value.includes(s.id)))
const toggleSelectAll = (event) => {
  const pageIds = paginatedSerials.value.map(s => s.id)
  if (event.target.checked) selectedIds.value = [...new Set([...selectedIds.value, ...pageIds])]
  else selectedIds.value = selectedIds.value.filter(id => !pageIds.includes(id))
}

const applyBatchUpdate = async () => {
  if (!batchStatus.value && !batchQuality.value) return toast.addToast('변경할 상태나 품질을 선택해 주세요.', 'error')
  if (!(await dialog.confirm(`선택한 ${selectedIds.value.length}개 시리얼의 상태를 일괄 변경하시겠습니까?`, { okText: '변경' }))) return

  try {
    await store.batchUpdateSerials(selectedIds.value, batchStatus.value, batchQuality.value)
  } catch (err) {
    return toast.addToast(apiErrorMessage(err, '일괄 변경 중 오류가 발생했습니다.'), 'error', 5000)
  }
  selectedIds.value = []
  batchStatus.value = ''
  batchQuality.value = ''
  toast.addToast('일괄 변경을 완료했습니다.', 'success')
  await fetchData()
}

const rowClass = (serial) => {
  if (serial.status === '불량폐기' || serial.status === '분실') return 'row-muted'
  if (serial.status === 'AS진행중') return 'row-warning'
  return ''
}
const statusColor = (status) => {
  const colors = { '재고보유': 'text-success', '출고완료': 'text-primary', 'AS진행중': 'text-warning', '불량폐기': 'text-danger', '분실': 'text-danger' }
  return colors[status] || ''
}
const qualityColor = (quality) => {
  const colors = { '신규상품': 'text-primary', '양품A급': 'text-success', '양품B급': 'text-warning', '사용불가': 'text-danger' }
  return colors[quality] || ''
}

onActivated(() => { fetchData() })
</script>
<!-- CSS 삭제됨 -->