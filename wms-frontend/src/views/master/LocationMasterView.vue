<template>
  <div class="page">
    <!-- 등록 패널 -->
    <div class="panel print:hidden">
      <div class="panel-header"><span class="panel-title">보관 위치 등록</span></div>
      <form @submit.prevent="handleAddLocation" class="flex flex-wrap items-center gap-1.5 text-body p-2.5">
        구역(Zone): <input v-model="form.zone" type="text"
          class="field w-[120px]"
          placeholder="예: A동, 냉장" required />
        랙(Rack): <input v-model="form.rack" type="text"
          class="field w-[100px]"
          placeholder="예: R-01" required />
        단(Tier): <input v-model.number="form.tier" type="number" min="1"
          class="field field-num w-[60px]"
          required />
        셀(Cell): <input v-model="form.cell" type="text"
          class="field w-[80px]"
          placeholder="선택사항" />
        비고: <input v-model="form.description" type="text"
          class="field w-[200px]"
          placeholder="설명 입력" />
        <button type="submit"
          class="btn btn-success ml-2.5">보관 위치
          등록</button>
      </form>
    </div>

    <!-- 목록 패널 -->
    <div
      class="panel flex-1 overflow-hidden print:hidden">
      <div class="panel-header">
        <span class="panel-title text-ink">보관 위치 목록</span>
        <div class="flex items-center gap-2">
          <span class="text-body">총 <strong>{{ locations.length }}</strong>곳</span>
          <button class="btn btn-sm" :disabled="locations.length === 0" @click="labelLocations = locations">전체 라벨 인쇄</button>
        </div>
      </div>

      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th width="150">보관 위치 코드</th>
              <th width="100">바코드</th>
              <th width="100">구역 (Zone)</th>
              <th width="100">랙 (Rack)</th>
              <th width="80">단 (Tier)</th>
              <th width="100">셀 (Cell)</th>
              <th>비고</th>
              <th width="180">관리</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="locations.length === 0" class="empty-row">
              <td colspan="8">등록된 보관 위치가 없습니다. 위에서 보관 위치를 등록하세요.</td>
            </tr>
            <tr v-for="loc in locations" :key="loc.id">
              <td class="text-center font-mono font-bold text-primary truncate">{{
                loc.full_code }}</td>
              <td class="text-center font-mono text-caption">{{ loc.barcode }}</td>
              <td class="text-center font-bold">{{ loc.zone }}</td>
              <td class="text-center font-mono">{{ loc.rack }}</td>
              <td class="text-center">{{ loc.tier }}단</td>
              <td class="text-center font-mono">{{ loc.cell || '-' }}</td>
              <td class="truncate">{{ loc.description || '-' }}</td>
              <td class="text-center">
                <button class="btn btn-sm" @click="labelLocations = [loc]">라벨</button>
                <button class="btn btn-sm ml-1" @click="openEdit(loc)">수정</button>
                <button class="btn btn-sm btn-danger ml-1" @click="handleDelete(loc)">삭제</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <LocationLabelModal v-if="labelLocations" :locations="labelLocations" @close="labelLocations = null" />

    <div v-if="editForm" class="modal-overlay" @click.self="editForm = null">
      <form class="modal w-[450px]" @submit.prevent="submitEdit">
        <div class="modal-header">보관 위치 수정</div>
        <div class="modal-content flex flex-col gap-2.5">
          <div class="alert alert-info m-0">코드를 바꾸면 이 위치에 있는 상품의 표시 위치도 함께 바뀝니다.</div>
          <div class="grid grid-cols-2 gap-2.5">
            <label class="field-label">구역(Zone)
              <input v-model="editForm.zone" class="field w-full mt-1" required />
            </label>
            <label class="field-label">랙(Rack)
              <input v-model="editForm.rack" class="field w-full mt-1" required />
            </label>
            <label class="field-label">단(Tier)
              <input v-model.number="editForm.tier" type="number" min="1" class="field field-num w-full mt-1" required />
            </label>
            <label class="field-label">셀(Cell)
              <input v-model="editForm.cell" class="field w-full mt-1" placeholder="선택사항" />
            </label>
          </div>
          <label class="field-label">비고
            <input v-model="editForm.description" class="field w-full mt-1" maxlength="200" />
          </label>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg">저장</button>
          <button type="button" class="btn btn-lg" @click="editForm = null">취소</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onActivated } from 'vue'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore'
import { apiErrorMessage } from '../../utils/apiError'
import { useDialogStore } from '../../stores/dialogStore'
import LocationLabelModal from '../../components/LocationLabelModal.vue'

const locations = ref([])
const emptyForm = () => ({ zone: '', rack: '', tier: 1, cell: '', description: '' })
const form = ref(emptyForm())
const editForm = ref(null)
const labelLocations = ref(null)
const toast = useToastStore()
const dialog = useDialogStore()

const fetchLocations = async () => {
  try {
    const res = await axios.get('/api/inventory/locations/')
    locations.value = res.data
  } catch (e) {
    toast.addToast(apiErrorMessage(e, '보관 위치를 불러오지 못했습니다.'), 'error')
  }
}

const handleAddLocation = async () => {
  try {
    await axios.post('/api/inventory/locations/', form.value)
    form.value = emptyForm()
    await fetchLocations()
    toast.addToast('보관 위치를 등록했습니다.', 'success')
  } catch (e) {
    toast.addToast(apiErrorMessage(e, '등록 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const openEdit = (loc) => {
  const { id, zone, rack, tier, cell, description } = loc
  editForm.value = { id, zone, rack, tier, cell: cell || '', description: description || '' }
}

const submitEdit = async () => {
  const { id, ...change } = editForm.value
  try {
    await axios.patch(`/api/inventory/locations/${id}/`, change)
    editForm.value = null
    await fetchLocations()
    toast.addToast('보관 위치를 수정했습니다.', 'success')
  } catch (e) {
    toast.addToast(apiErrorMessage(e, '수정 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const handleDelete = async (loc) => {
  if (!(await dialog.confirm(`[${loc.full_code}] 보관 위치를 삭제하시겠습니까?`, { danger: true, okText: '삭제' }))) return
  try {
    await axios.delete(`/api/inventory/locations/${loc.id}/`)
    await fetchLocations()
    toast.addToast('삭제되었습니다.', 'success')
  } catch (e) {
    toast.addToast(apiErrorMessage(e, '삭제 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

onActivated(() => { fetchLocations() })
</script>
