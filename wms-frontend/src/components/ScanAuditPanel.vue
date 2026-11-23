<template>
  <!-- 스캔 재고 조사: 보관 위치를 고르고 선반의 물건을 스캔하면 전산과 대조합니다. -->
  <div class="flex flex-col gap-2.5">
    <div class="toolbar">
      <label class="field-label">조사할 위치</label>
      <select v-model="locationId" class="field w-[200px]" @change="reset">
        <option :value="null" disabled>보관 위치 선택</option>
        <option v-for="loc in locations" :key="loc.id" :value="loc.id">{{ loc.full_code }}</option>
      </select>
      <form class="flex gap-1.5 flex-1" @submit.prevent="addScan">
        <input ref="scanRef" v-model="code" class="field field-scan flex-1" :disabled="!locationId"
          :placeholder="locationId ? '시리얼 또는 상품코드를 스캔하세요 (Enter)' : '먼저 위치를 고르세요'" autocomplete="off" spellcheck="false" />
      </form>
      <button class="btn" :disabled="codes.length === 0" @click="codes.pop(); result = null">마지막 스캔 지우기</button>
      <button class="btn" :disabled="codes.length === 0" @click="reset">처음부터</button>
      <button class="btn btn-primary" :disabled="!locationId || isBusy" @click="check(false)">대조하기</button>
    </div>
    <div class="text-muted">스캔 {{ codes.length }}건<span v-if="codes.length">: 최근 {{ codes.slice(-6).reverse().join(', ') }}</span></div>

    <template v-if="result">
      <div v-if="result.counted && !result.applied.length" class="alert alert-success m-0">✔ 모두 일치합니다. {{ result.location }} 조사 완료로 기록했습니다.</div>
      <div v-for="message in result.warnings" :key="message" class="alert alert-warning m-0">{{ message }}</div>
      <div v-if="result.unknown.length" class="alert alert-danger m-0">등록되지 않은 바코드: {{ result.unknown.join(', ') }}</div>
      <table class="data-table data-table-sm">
        <thead>
          <tr><th width="130">상품코드</th><th>상품명</th><th width="80">전산</th><th width="80">스캔</th><th width="80">차이</th><th>확인할 내용</th></tr>
        </thead>
        <tbody>
          <tr v-if="result.rows.length === 0" class="empty-row"><td colspan="6">이 위치에 등록된 상품이 없고, 스캔한 상품도 없습니다.</td></tr>
          <tr v-for="row in result.rows" :key="row.item" :class="rowClass(row)">
            <td class="text-center font-mono">{{ row.sku }}</td>
            <td class="truncate">{{ row.name }} <span v-if="row.serial_tracked" class="text-caption text-muted">(시리얼)</span></td>
            <td class="text-right font-bold">{{ row.system }}</td>
            <td class="text-right font-bold">{{ row.counted }}</td>
            <td class="text-right font-bold" :class="row.counted - row.system < 0 ? 'text-danger' : row.counted - row.system > 0 ? 'text-primary' : 'text-success'">
              {{ row.counted - row.system > 0 ? '+' : '' }}{{ row.counted - row.system }}
            </td>
            <td>
              <div v-if="row.other_location" class="text-warning">다른 위치({{ row.location_name || '미지정' }}) 상품입니다. 반영하지 않습니다.</div>
              <div v-if="row.missing.length" class="text-danger">못 찾은 기기: {{ row.missing.join(', ') }}</div>
              <div v-if="row.unexpected.length" class="text-warning">전산 상태가 다른 기기: {{ row.unexpected.join(', ') }}</div>
              <div v-if="isMatch(row)" class="text-success">일치</div>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="toolbar">
        <label class="flex items-center gap-1"><input v-model="markMissing" type="checkbox" /> 못 찾은 기기를 분실 처리 (재고에서 뺍니다)</label>
        <span class="flex-1"></span>
        <button class="btn btn-success" :disabled="isBusy || !hasChanges" @click="apply">조사 결과 반영</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../stores/toastStore'
import { useDialogStore } from '../stores/dialogStore'
import { apiErrorMessage } from '../utils/apiError'
import { playBeep } from '../utils/beep'

const emit = defineEmits(['applied', 'counted'])
const toast = useToastStore()
const dialog = useDialogStore()
const locations = ref([])
const locationId = ref(null)
const code = ref('')
const codes = ref([])
const result = ref(null)
const markMissing = ref(true)
const isBusy = ref(false)
const scanRef = ref(null)

const isMatch = (row) => !row.other_location && row.counted === row.system && !row.missing.length && !row.unexpected.length
const rowClass = (row) => (row.other_location ? 'row-warning' : isMatch(row) ? '' : 'row-danger')
const hasChanges = computed(() => result.value?.rows.some(row => !row.other_location &&
  ((!row.serial_tracked && row.counted !== row.system) || (row.serial_tracked && markMissing.value && row.missing.length))))

const addScan = () => {
  const value = code.value.trim()
  code.value = ''
  if (!value) return
  if (/[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(value)) {
    playBeep('error')
    return toast.addToast('한글로 입력되었습니다. [한/영] 키로 영문으로 바꾼 뒤 다시 스캔하세요.', 'error', 5000)
  }
  codes.value.push(value)
  result.value = null
  playBeep('success')
}

const reset = () => {
  codes.value = []
  result.value = null
  nextTick(() => scanRef.value?.focus())
}

const send = async (apply) => (await axios.post('/api/inventory/items/audit_scan/', {
  location: locationId.value, codes: codes.value, apply, mark_missing: markMissing.value,
})).data

const check = async () => {
  isBusy.value = true
  try {
    result.value = await send(false)
    if (result.value.counted) emit('counted')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '대조 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isBusy.value = false
  }
}

const apply = async () => {
  if (!(await dialog.confirm(`${result.value.location} 조사 결과를 반영합니다.\n수량 상품은 스캔한 개수로 바뀌고${markMissing.value ? ', 못 찾은 기기는 분실 처리됩니다' : ''}.`, { title: '조사 결과 반영', okText: '반영' }))) return
  isBusy.value = true
  try {
    const data = await send(true)
    toast.addToast(data.applied.length ? `반영 완료: ${data.applied.join(', ')}` : '바꿀 내용이 없었습니다.', 'success', 7000)
    reset()
    emit('applied')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '반영 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isBusy.value = false
  }
}

// 순환 조사 목록에서 위치를 고르면 여기로 넘어옵니다.
const selectLocation = (id) => {
  locationId.value = id
  reset()
}
defineExpose({ selectLocation })

onMounted(async () => {
  locations.value = (await axios.get('/api/inventory/locations/')).data
})
</script>
