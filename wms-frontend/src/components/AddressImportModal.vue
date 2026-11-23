<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal w-[900px]">
      <div class="modal-header">배송지 일괄 등록</div>
      <div class="modal-content flex flex-col gap-2.5">
        <ol class="m-0 pl-5 leading-[1.8]">
          <li>출고대기 주문의 현재 배송지가 담긴 양식을 내려받습니다. <button class="btn btn-sm ml-1" @click="downloadTemplate">양식 내려받기</button></li>
          <li>엑셀에서 받는 분, 연락처, 우편번호, 주소, 상세주소를 고칩니다. 주문번호와 첫 줄 제목은 바꾸지 마세요.</li>
          <li>고친 파일을 올리면 바뀌는 내용을 먼저 보여줍니다. 확인한 뒤 [저장]을 누릅니다.
            <label class="btn btn-sm btn-primary ml-1 cursor-pointer">파일 선택
              <input type="file" :accept="EXCEL_ACCEPT" class="hidden" @change="pickFile" />
            </label>
            <span v-if="fileName" class="ml-1.5 text-muted">{{ fileName }}</span>
          </li>
        </ol>
        <div class="alert alert-info m-0">배송지를 바꾼 주문은 기존 송장을 취소하고 새 운송장을 발급합니다. 묶음배송 주문은 묶음을 해제한 뒤 바꿀 수 있습니다.</div>

        <template v-if="result">
          <div class="flex gap-3 font-bold">
            <span v-if="result.applied" class="text-success">저장 {{ result.counts.saved }}건</span>
            <span v-else class="text-primary">반영할 내용 {{ result.counts.ok }}건</span>
            <span class="text-muted">변경 없음 {{ result.counts.unchanged }}건</span>
            <span :class="result.counts.error ? 'text-danger' : 'text-muted'">오류 {{ result.counts.error }}건</span>
          </div>
          <div class="max-h-[360px] overflow-y-auto border border-line">
            <table class="data-table data-table-sm">
              <thead><tr><th width="50">줄</th><th width="170">주문번호</th><th width="90">결과</th><th>내용</th></tr></thead>
              <tbody>
                <tr v-for="row in result.rows" :key="row.row" :class="{ 'row-danger': row.status === 'error', 'row-success': row.status === 'saved', 'row-muted': row.status === 'unchanged' }">
                  <td class="text-center">{{ row.row }}</td>
                  <td class="text-center font-mono">{{ row.order_no || '-' }}</td>
                  <td class="text-center font-bold">{{ STATUS[row.status] }}</td>
                  <td>
                    <div v-for="change in row.changes" :key="change">{{ change }}</div>
                    <div v-if="row.message && row.status !== 'ok'" :class="{ 'text-danger': row.status === 'error' }">{{ row.message }}</div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
      <div class="modal-footer">
        <button v-if="result && !result.applied" class="btn btn-primary btn-lg" :disabled="isSaving || result.counts.ok === 0" @click="send(true)">
          저장 ({{ result.counts.ok }}건)
        </button>
        <button class="btn btn-lg" @click="$emit('close')">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../stores/toastStore'
import { apiErrorMessage } from '../utils/apiError'
import { EXCEL_ACCEPT, downloadXlsx, readSheetObjects } from '../utils/excel'

const emit = defineEmits(['close', 'saved'])
const toast = useToastStore()
const STATUS = { ok: '반영 예정', saved: '저장', unchanged: '변경 없음', error: '오류' }
const COLUMNS = [['주문번호', 'order_no'], ['고객', null], ['받는 분', 'contact_name'], ['연락처', 'contact_phone'], ['우편번호', 'zipcode'], ['주소', 'address'], ['상세주소', 'address_detail']]
const rows = ref([])
const result = ref(null)
const fileName = ref('')
const isSaving = ref(false)

const downloadTemplate = async () => {
  const orders = (await axios.get('/api/inventory/orders/', { params: { status: '출고대기' } })).data
  if (orders.length === 0) return toast.addToast('출고대기 주문이 없습니다.', 'info')
  downloadXlsx(`배송지일괄등록_${new Date().toLocaleDateString('sv-SE')}`, '배송지', COLUMNS.map(([label]) => label),
    orders.map(order => [order.order_no, order.customer, order.contact_name, order.contact_phone, order.zipcode, order.address, order.address_detail]))
}

// 엑셀이 숫자로 바꾸며 지운 앞자리 0을 되살립니다. (06236 → 6236, 010... → 10...)
const fixZipcode = (value) => (/^\d{4}$/.test(value) ? `0${value}` : value)
const fixPhone = (value) => (/^[1-9]\d{8,9}$/.test(value) ? `0${value}` : value)

const pickFile = async (event) => {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  fileName.value = file.name
  result.value = null
  try {
    const sheet = await readSheetObjects(file)
    if (sheet.length === 0 || !('주문번호' in sheet[0])) {
      return toast.addToast('첫 줄에 "주문번호" 제목이 없습니다. 내려받은 양식을 그대로 써 주세요.', 'error', 6000)
    }
    rows.value = sheet.map(line => {
      const row = Object.fromEntries(COLUMNS.filter(([, key]) => key).map(([label, key]) => [key, String(line[label] ?? '').trim()]))
      return { ...row, zipcode: fixZipcode(row.zipcode), contact_phone: fixPhone(row.contact_phone) }
    })
    await send(false)
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '파일을 읽지 못했습니다. xlsx 또는 csv 파일인지 확인하세요.'), 'error', 6000)
  }
}

const send = async (apply) => {
  isSaving.value = true
  try {
    result.value = (await axios.post('/api/inventory/orders/import_addresses/', { rows: rows.value, apply })).data
    if (apply) {
      const { saved, error } = result.value.counts
      toast.addToast(`배송지 ${saved}건 저장${error ? `, ${error}건 오류` : ''}`, error ? 'error' : 'success', 6000)
      emit('saved')
    }
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '배송지 일괄 등록 중 오류가 발생했습니다.'), 'error', 6000)
  } finally {
    isSaving.value = false
  }
}
</script>
