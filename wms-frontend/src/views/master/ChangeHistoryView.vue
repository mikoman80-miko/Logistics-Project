<template>
  <div class="page">
    <div class="panel flex-1 min-h-0">
      <div class="panel-header">
        <div class="flex items-center gap-1">
          <span class="panel-title mr-2">기준정보 변경 이력</span>
          <button v-for="tab in targets" :key="tab" class="tab" :class="{ 'is-active': target === tab }" @click="target = tab; load(1)">{{ tab || '전체' }}</button>
        </div>
        <span class="text-muted">총 {{ count }}건</span>
      </div>
      <ListFilter :model="filter" placeholder="대상(상품코드, 위치, 이름) 또는 처리자" @apply="load(1)" />
      <div class="flex-1 overflow-y-auto">
        <table class="data-table data-table-sm">
          <thead>
            <tr><th width="150">일시</th><th width="70">구분</th><th width="220">대상</th><th width="110">작업</th><th>바뀐 내용</th><th width="110">처리자</th></tr>
          </thead>
          <tbody>
            <tr v-if="rows.length === 0" class="empty-row"><td colspan="6">기록이 없습니다.</td></tr>
            <tr v-for="row in rows" :key="row.id">
              <td class="text-center whitespace-nowrap">{{ row.timestamp.slice(0, 16).replace('T', ' ') }}</td>
              <td class="text-center">{{ row.target }}</td>
              <td class="truncate" :title="row.label">{{ row.label }}</td>
              <td class="text-center font-bold" :class="actionClass(row.action)">{{ row.action }}</td>
              <td>
                <span v-if="!Object.keys(row.changes).length" class="text-muted">-</span>
                <span v-for="(pair, field) in row.changes" :key="field" class="inline-block mr-3">
                  <b>{{ field }}</b>
                  <template v-if="row.action === '등록' || row.action === '재등록'"> {{ pair[1] }}</template>
                  <template v-else> <span class="text-muted line-through">{{ pair[0] || '(없음)' }}</span> → <span class="text-primary">{{ pair[1] || '(없음)' }}</span></template>
                </span>
              </td>
              <td class="text-center">{{ row.user || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="toolbar px-2.5 py-1.5 border-t border-line">
        <button class="btn btn-sm" :disabled="page <= 1" @click="load(page - 1)">이전</button>
        <span>{{ page }} / {{ pages }}</span>
        <button class="btn btn-sm" :disabled="page >= pages" @click="load(page + 1)">다음</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import axios from 'axios'
import ListFilter from '../../components/ListFilter.vue'
import { apiErrorMessage } from '../../utils/apiError'
import { useToastStore } from '../../stores/toastStore'

const PAGE_SIZE = 50
const toast = useToastStore()
const targets = ['', '상품', '위치', '거래처', '카테고리', '사용자']
const target = ref('')
const filter = ref({ q: '', start_date: '', end_date: '' })
const rows = ref([])
const count = ref(0)
const page = ref(1)
const pages = computed(() => Math.max(1, Math.ceil(count.value / PAGE_SIZE)))

const actionClass = (action) => ({ 삭제: 'text-danger', '사용 중지': 'text-danger', 등록: 'text-success', 재등록: 'text-success' }[action] || '')

const load = async (to = page.value) => {
  try {
    const params = { page: to, page_size: PAGE_SIZE, ...filter.value, ...(target.value ? { target: target.value } : {}) }
    const data = (await axios.get('/api/inventory/changes/', { params })).data
    rows.value = data.results
    count.value = data.count
    page.value = to
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '변경 이력을 불러오지 못했습니다.'), 'error')
  }
}

onActivated(() => load())
</script>
