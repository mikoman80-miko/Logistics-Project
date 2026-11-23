<template>
  <WorkLayout title="반품 회수">
    <div class="grid grid-cols-[2fr_1fr] gap-6 h-full">
      <section class="flex flex-col gap-5 min-h-0">
        <template v-if="!target">
          <div class="work-task justify-center items-center flex-1 text-[56px] font-bold text-muted">
            회수한 기기의 시리얼이나 상품 바코드를 스캔하세요
          </div>
          <ScanBox :paused="loading" :placeholder="loading ? '회수 대기 목록을 불러오는 중...' : undefined" @scan="onScan" />
        </template>

        <template v-else>
          <div class="work-task">
            <div class="text-[52px] font-bold leading-tight">{{ target.item_name }}</div>
            <div v-if="target.serial_number" class="text-4xl font-mono">S/N {{ target.serial_number }}</div>
            <div v-else class="text-4xl"><b class="text-primary">{{ target.quantity }}개</b> · {{ target.return_no }} · {{ target.customer }}</div>
            <div class="text-4xl">반품 사유: <strong class="text-warning">{{ target.reason }}</strong></div>
          </div>
          <div class="text-4xl font-bold text-center">{{ target.serial_number ? '기기 상태를 고르세요' : '회수 결과를 고르세요' }}</div>
          <div class="grid grid-cols-2 gap-4 flex-1">
            <button v-for="result in (target.serial_number ? RESULTS : QUANTITY_RESULTS)" :key="result.label" class="work-btn h-auto! text-4xl!" :class="result.style" :disabled="isSaving" @click="complete(result)">
              {{ result.label }}
              <span class="block text-2xl font-normal mt-2">{{ result.desc }}</span>
            </button>
          </div>
          <button class="work-btn" @click="target = null">취소하고 다시 스캔</button>
        </template>
      </section>

      <aside class="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <div class="text-3xl font-bold">회수 대기 {{ returns.length }}건</div>
        <div v-if="returns.length === 0" class="work-empty">회수 대기 중인 반품이 없습니다.</div>
        <div v-for="row in returns" :key="row.id" class="work-line">
          <div class="font-bold truncate">{{ row.item_name }}</div>
          <div class="mt-1 text-xl text-muted font-mono truncate">{{ row.serial_number || `${row.item_sku} · ${row.quantity}개` }}</div>
          <div class="text-xl text-muted">{{ row.customer }} · {{ row.reason }}</div>
          <div v-if="row.carrier_status" class="text-xl font-bold" :class="row.carrier_status === '회수완료' ? 'text-success' : 'text-primary'">
            택배 {{ row.carrier_status === '회수완료' ? '회수완료 (창고 도착)' : row.carrier_status }}
          </div>
        </div>
      </aside>
    </div>
  </WorkLayout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'
import ScanBox from '../../components/work/ScanBox.vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { useAuthStore } from '../../stores/auth'
import { apiErrorMessage } from '../../utils/apiError'

const RESULTS = [
  { label: '정상 (A급)', desc: '재고로 되돌립니다', status: '재고보유', quality: '양품A급', style: 'work-btn-success' },
  { label: '사용감 (B급)', desc: '재고로 되돌립니다', status: '재고보유', quality: '양품B급', style: 'work-btn-primary' },
  { label: 'AS 필요', desc: '재고에 넣지 않습니다', status: 'AS진행중', quality: null, style: 'work-btn-warning' },
  { label: '폐기', desc: '재고에 넣지 않습니다', status: '불량폐기', quality: '사용불가', style: 'work-btn-danger' },
]

// 시리얼 없는 상품의 반품 결과
const QUANTITY_RESULTS = [
  { label: '재고로 되돌림', desc: '수량만큼 재고에 더합니다', result: 'restock', style: 'work-btn-success' },
  { label: '폐기', desc: '재고에 넣지 않습니다', result: 'dispose', style: 'work-btn-danger' },
]

const { ok, fail } = useWorkFeedback()
const authStore = useAuthStore()
const returns = ref([])
const loading = ref(true)  // 목록을 다 불러오기 전에 스캔하면 '목록에 없음'으로 잘못 처리되므로 잠급니다.
const target = ref(null)
const isSaving = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/inventory/returns/', { params: { status: '회수대기' } })
    returns.value = res.data.reverse()
  } finally {
    loading.value = false
  }
}

const onScan = (code) => {
  // 시리얼이 맞으면 그 기기, 아니면 상품 바코드로 가장 먼저 등록한 수량 반품을 찾습니다.
  const found = returns.value.find(row => row.serial_number === code)
    || returns.value.find(row => !row.serial_number && row.item_sku === code)  // 목록은 오래된 순
  if (!found) {
    fail(`[${code}] 회수 대기 목록에 없는 시리얼 또는 상품입니다.`)
    return
  }
  ok('회수 대상 확인')
  target.value = found
}

const complete = async (result) => {
  isSaving.value = true
  try {
    const detail = `${result.label} / 담당: ${authStore.user?.name}`
    const body = target.value.serial_number
      ? { status: result.status, quality: result.quality, detail, label: result.label }
      : { result: result.result, detail, label: result.label }
    await axios.post(`/api/inventory/returns/${target.value.id}/complete/`, body)
    ok(`${target.value.serial_number || `${target.value.item_name} ${target.value.quantity}개`} 회수 완료: ${result.label}`)
    target.value = null
    await load()
  } catch (err) {
    fail(apiErrorMessage(err, '회수 처리 중 오류가 발생했습니다.'))
  } finally {
    isSaving.value = false
  }
}

// 상태 선택은 클릭으로만 받습니다. 바코드의 숫자가 키 입력으로 처리되는 사고를 막기 위해서입니다.
onMounted(load)
</script>
