<template>
  <div class="modal-overlay">
    <div class="modal w-[700px]">
      <div class="modal-header">CSV 일괄 업로드 사전 검증</div>
      <div class="modal-content h-[400px] p-0">
        <table class="data-table">
          <thead>
            <tr>
              <th width="80">상태</th><th width="150">SKU 코드</th>
              <th>상품명</th><th width="80">수량</th><th width="100">보관 구역</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in parsedData" :key="index" :class="{ 'row-danger': !row.isValid }">
              <td class="text-center font-bold" :class="row.isValid ? 'text-primary' : 'text-danger'">
                {{ row.isValid ? '정상' : '오류' }}
              </td>
              <td class="text-center font-mono">{{ row.sku }}</td>
              <td class="truncate">{{ row.name }}</td>
              <td class="text-right" :class="{ 'text-danger': isNaN(row.quantity) }">{{ row.quantity }}</td>
              <td class="text-center">{{ row.location }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="modal-footer justify-between items-center px-[15px] py-2.5">
        <div class="text-left">
          <strong class="text-danger" v-if="errorCount > 0">※ 필수값(SKU/상품명/수량) 누락, 등록되지 않은 구역 등 오류 {{ errorCount }}건이 발견되었습니다.</strong>
          <strong class="text-primary" v-else>※ 모든 데이터가 정상입니다. (총 {{ parsedData.length }}건)</strong>
        </div>
        <div>
          <button class="btn btn-primary mr-1" @click="confirmUpload" :disabled="errorCount > 0 || parsedData.length === 0">[최종 등록]</button>
          <button class="btn" @click="$emit('close')">[취소]</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps(['file'])
const emit = defineEmits(['close', 'success'])

const parsedData = ref([])
const errorCount = ref(0)

// 엑셀에서 저장한 CSV는 UTF-8(BOM) 또는 CP949입니다.
const decodeCsv = (buffer) => {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer).replace(/^\uFEFF/, '')
  } catch {
    return new TextDecoder('euc-kr').decode(buffer)
  }
}

onMounted(async () => {
  const locationIds = {}
  try {
    const res = await axios.get('/api/inventory/locations/')
    res.data.forEach((loc) => { locationIds[loc.full_code] = loc.id })
  } catch (e) {
    console.error('구역 목록 조회 실패', e)
  }

  const reader = new FileReader()
  reader.onload = (e) => {
    const rows = decodeCsv(e.target.result).split('\n')
    for (let i = 1; i < rows.length; i++) {
      const rowText = rows[i].trim()
      if (!rowText) continue
      
      const cols = rowText.split(',')
      const sku = cols[0] ? cols[0].trim() : ''
      const name = cols[1] ? cols[1].trim() : ''
      const quantity = parseInt(cols[2])
      const location = cols[3] ? cols[3].trim() : ''
      
      // 검증 로직: SKU, 상품명이 있고 수량이 숫자여야 함
      const locationId = location ? locationIds[location] : null
      const isValid = sku !== '' && name !== '' && !isNaN(quantity) && quantity >= 0 && locationId !== undefined
      if (!isValid) errorCount.value++
      
      parsedData.value.push({ sku, name, quantity: isNaN(quantity) ? '숫자오류' : quantity, location, locationId, isValid })
    }
  }
  reader.readAsArrayBuffer(props.file)
})

const confirmUpload = async () => {
  let successCount = 0; let failCount = 0;
  for (const row of parsedData.value) {
    if (!row.isValid) continue;
    try {
      await axios.post('/api/inventory/items/', {
        sku: row.sku, name: row.name, quantity: row.quantity, location: row.locationId
      })
      successCount++
    } catch (e) { failCount++ }
  }
  alert(`등록 완료 (성공: ${successCount}건, 실패(중복등): ${failCount}건)`)
  emit('success')
}
</script>
