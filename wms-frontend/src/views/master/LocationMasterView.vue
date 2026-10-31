<template>
  <div class="page">
    <!-- 등록 패널 -->
    <div class="panel p-1.5 print:hidden">
      <div class="modal-header mb-1.5">신규 구역 및 랙(Location) 등록</div>
      <form @submit.prevent="handleAddLocation" class="flex items-center gap-1.5 text-body p-1">
        구역명(Zone): <input v-model="form.zone" type="text"
          class="field w-[120px]"
          placeholder="예: A동, 냉장" required />
        랙 번호(Rack): <input v-model="form.rack" type="text"
          class="field w-[100px]"
          placeholder="예: R-01" required />
        단(Tier): <input v-model.number="form.tier" type="number"
          class="field field-num w-[60px]"
          required />
        셀 번호(Cell): <input v-model="form.cell" type="text"
          class="field w-[80px]"
          placeholder="선택사항" />
        비고: <input v-model="form.description" type="text"
          class="field w-[200px]"
          placeholder="설명 입력" />
        <button type="submit"
          class="btn btn-success ml-2.5">로케이션
          등록</button>
      </form>
    </div>

    <!-- 목록 패널 -->
    <div
      class="panel flex-1 overflow-hidden print:hidden">
      <div class="panel-header">
        <span class="panel-title text-ink">창고 공간 구조 마스터 목록</span>
        <span class="text-body">총 <strong>{{ locations.length }}</strong> 개 구역 등록됨</span>
      </div>

      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th
               
                width="150">전체 로케이션 코드</th>
              <th
               
                width="100">구역 (Zone)</th>
              <th
               
                width="100">랙 (Rack)</th>
              <th
               
                width="80">단 (Tier)</th>
              <th
               
                width="100">셀 (Cell)</th>
              <th
               >
                비고 설명</th>
              <th
               
                width="100">관리 도구</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="locations.length === 0">
              <td colspan="7" class="text-center">등록된 로케이션이 없습니다.</td>
            </tr>
            <tr v-for="loc in locations" :key="loc.id">
              <td class="text-center font-mono font-bold text-primary truncate">{{
                loc.full_code }}</td>
              <td class="text-center font-bold">{{ loc.zone }}</td>
              <td class="text-center font-mono">{{ loc.rack }}</td>
              <td class="text-center">{{ loc.tier }}단</td>
              <td class="text-center font-mono">{{ loc.cell || '-' }}</td>
              <td class="truncate">{{ loc.description || '-' }}</td>
              <td class="text-center">
                <button
                  class="btn btn-link"
                  @click="handleDelete(loc.id)">[삭제]</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onActivated } from 'vue'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore' // 🌟 NEW: 토스트 임포트 추가

const locations = ref([])
const form = ref({ zone: '', rack: '', tier: 1, cell: '', description: '' })
const toast = useToastStore() // 🌟 NEW: 토스트 스토어 선언

const fetchLocations = async () => {
  try {
    const res = await axios.get('/api/inventory/locations/')
    locations.value = res.data
  } catch (e) {
    console.error('로케이션 조회 실패', e)
  }
}

const handleAddLocation = async () => {
  try {
    await axios.post('/api/inventory/locations/', form.value)
    form.value = { zone: '', rack: '', tier: 1, cell: '', description: '' }
    await fetchLocations()
    toast.addToast('로케이션이 성공적으로 등록되었습니다.', 'success') // 🌟 기존 alert 교체
  } catch (e) {
    toast.addToast('등록 중 오류가 발생했습니다.', 'error') // 🌟 기존 alert 교체
  }
}

const handleDelete = async (id) => {
  if (!confirm('해당 로케이션을 삭제하시겠습니까?')) return
  try {
    await axios.delete(`/api/inventory/locations/${id}/`)
    await fetchLocations()
    toast.addToast('삭제되었습니다.', 'success') // 🌟 NEW: 성공 피드백 추가
  } catch (e) {
    toast.addToast('삭제 실패', 'error') // 🌟 기존 alert 교체
  }
}

onActivated(() => { fetchLocations() })
</script>
<!-- 🚨 기존의 <style scoped> 는 완벽히 제거되었습니다! 🚨 -->