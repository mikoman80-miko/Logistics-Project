<template>
  <WorkLayout title="위치 보충">
    <!-- 1. 보충할 상품 고르기 -->
    <div v-if="!step" class="flex flex-col gap-4 h-full min-h-0">
      <div class="text-4xl font-bold">꺼내는 자리가 비어 가는 상품입니다. 누르면 채우러 갑니다.</div>
      <div v-if="!isLoading && tasks.length === 0" class="work-empty">지금 채울 자리가 없습니다.</div>
      <div class="flex flex-col gap-3 overflow-y-auto min-h-0">
        <button v-for="task in tasks" :key="task.item" class="work-row work-row-due" :disabled="!task.sources.length" :class="{ 'opacity-60': !task.sources.length }" @click="choose(task)">
          <span class="font-bold truncate">{{ task.name }}</span>
          <span class="text-2xl">📍 {{ task.target_name }} <b :class="task.here ? 'text-warning' : 'text-danger'">{{ task.here }}개</b> <span class="text-muted">(최소 {{ task.pick_min }})</span></span>
          <span class="text-2xl font-bold text-primary">+{{ task.sources.reduce((s, src) => s + src.take, 0) }}개</span>
          <span class="text-2xl" :class="task.sources.length ? 'text-muted' : 'text-danger font-bold'">{{ task.sources.length ? `${task.sources.map(s => s.location_name).join(', ')}에서` : '다른 위치에 재고 없음 · 발주 필요' }}</span>
        </button>
      </div>
    </div>

    <!-- 2. 꺼내서 채우기 -->
    <div v-else class="grid grid-cols-[2fr_1fr] gap-6 h-full">
      <section class="flex flex-col gap-5 min-h-0">
        <div class="work-task">
          <template v-if="phase === 'pick'">
            <div class="text-4xl text-muted">1단계 · 보관 위치에서 꺼내기</div>
            <div class="text-[64px] font-bold text-warning leading-tight">📍 {{ step.source.location_name }}
              <span v-if="sourceChecked" class="text-success text-4xl align-middle">✔ 위치 확인</span>
            </div>
          </template>
          <template v-else>
            <div class="text-4xl text-muted">2단계 · 꺼내는 자리에 채우기</div>
            <div class="text-[64px] font-bold text-success leading-tight">📍 {{ step.task.target_name }}</div>
          </template>
          <div class="text-[52px] font-bold leading-tight">{{ step.task.name }}</div>
          <div class="text-4xl font-mono">{{ step.task.sku }}</div>
          <div class="text-[72px] font-bold leading-tight"><span class="text-primary">{{ count }}</span> / {{ step.source.take }}개</div>
          <div v-if="step.task.serial_tracked && phase === 'pick'" class="text-2xl text-muted">이 위치의 기기 예: {{ step.source.serials.join(', ') }}</div>
        </div>
        <div class="text-4xl font-bold text-center">{{ prompt }}</div>
        <ScanBox :paused="qtyOpen || isSaving" @scan="onScan" />
        <div class="grid grid-cols-2 gap-4">
          <template v-if="phase === 'pick'">
            <button v-if="!step.task.serial_tracked" class="work-btn" @click="qtyOpen = true">수량 직접 입력</button>
            <button class="work-btn work-btn-primary" :disabled="count === 0" @click="phase = 'put'">꺼낸 만큼 채우러 가기 ({{ count }}개)</button>
          </template>
          <template v-else>
            <button class="work-btn" :disabled="count >= step.source.take" @click="phase = 'pick'">더 꺼내기</button>
            <button class="work-btn work-btn-success" :disabled="isSaving" @click="submit">라벨 없이 채움 완료</button>
          </template>
        </div>
      </section>

      <aside class="flex flex-col gap-3 min-h-0">
        <div class="work-line">
          <div class="text-2xl text-muted">꺼내는 자리 지금</div>
          <div class="text-4xl font-bold">{{ step.task.here }}개 → {{ step.task.here + count }}개</div>
          <div class="text-2xl text-muted">최소 {{ step.task.pick_min }} · 최대 {{ step.task.pick_max }}</div>
        </div>
        <div v-if="serials.length" class="work-line overflow-y-auto">
          <div class="text-2xl text-muted">스캔한 기기</div>
          <div v-for="no in serials" :key="no" class="text-2xl font-mono">{{ no }}</div>
        </div>
        <button class="work-btn mt-auto" @click="cancel">그만두기</button>
      </aside>
    </div>

    <QuantityDialog v-if="qtyOpen" :name="step.task.name" label="꺼낸 수량" :remaining="step.source.take - count"
      @confirm="(n) => { count += n; qtyOpen = false; afterCount() }" @close="qtyOpen = false" />
  </WorkLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'
import ScanBox from '../../components/work/ScanBox.vue'
import QuantityDialog from '../../components/work/QuantityDialog.vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { isLocationCode } from '../../composables/useLocationCheck'
import { useDialogStore } from '../../stores/dialogStore'
import { apiErrorMessage } from '../../utils/apiError'

// 보관 위치에서 꺼내(1단계) 기본 위치에 넣고 그 선반 라벨을 스캔하면(2단계) 재고 위치가 옮겨집니다.
const { ok, fail } = useWorkFeedback()
const dialog = useDialogStore()
const tasks = ref([])
const isLoading = ref(true)
const step = ref(null)  // { task, source }
const phase = ref('pick')
const count = ref(0)
const serials = ref([])
const sourceChecked = ref(false)
const qtyOpen = ref(false)
const isSaving = ref(false)

const prompt = computed(() => {
  if (phase.value === 'put') return '채운 선반의 위치 라벨을 스캔하면 완료됩니다'
  return step.value.task.serial_tracked ? '꺼낸 기기의 시리얼을 스캔하세요' : '꺼낸 상품의 바코드를 개수만큼 스캔하세요'
})

const load = async () => {
  isLoading.value = true
  tasks.value = (await axios.get('/api/inventory/items/replenishment/')).data
  isLoading.value = false
}

const choose = (task) => {
  step.value = { task, source: task.sources[0] }
  phase.value = 'pick'
  count.value = 0
  serials.value = []
  sourceChecked.value = false
}

const afterCount = () => {
  if (count.value >= step.value.source.take) phase.value = 'put'
}

const onScan = (code) => {
  const { task, source } = step.value
  if (isLocationCode(code)) {
    if (code === source.barcode && phase.value === 'pick') {
      sourceChecked.value = true
      return ok(`위치 확인: ${source.location_name}`)
    }
    if (code === task.target_barcode) {
      if (count.value === 0) return fail(`먼저 ${source.location_name}에서 꺼내 스캔하세요.`)
      return submit()
    }
    return fail(phase.value === 'pick' ? `다른 위치입니다. ${source.location_name}에서 꺼냅니다.` : `다른 위치입니다. ${task.target_name}에 채웁니다.`)
  }
  if (phase.value === 'put') return fail(`${task.target_name}의 위치 라벨을 스캔하세요.`)
  if (count.value >= source.take) return fail(`필요한 ${source.take}개를 이미 꺼냈습니다. 채우러 가세요.`)
  if (task.serial_tracked) {
    if (code === task.sku) return fail('시리얼 관리 상품입니다. 기기의 시리얼 바코드를 스캔하세요.')
    if (serials.value.includes(code)) return fail(`[${code}] 이미 스캔한 기기입니다.`)
    serials.value.push(code)
  } else if (code !== task.sku) {
    return fail(`[${code}] 다른 상품입니다. ${task.name}(${task.sku})을 꺼내세요.`)
  }
  count.value += 1
  ok(`${task.name} ${count.value}/${source.take}`)
  afterCount()
}

const submit = async () => {
  const { task, source } = step.value
  isSaving.value = true
  try {
    const body = { from: source.location, ...(task.serial_tracked ? { serials: serials.value } : { quantity: count.value }) }
    const res = await axios.post(`/api/inventory/items/${task.item}/replenish/`, body)
    ok(res.data.message)
    step.value = null
    await load()
  } catch (err) {
    fail(apiErrorMessage(err, '보충하지 못했습니다.'))
  } finally {
    isSaving.value = false
  }
}

const cancel = async () => {
  if (count.value && !(await dialog.confirm('꺼낸 물건은 원래 위치에 되돌려 놓으세요. 기록은 바뀌지 않습니다.', { title: '그만두기', okText: '그만두기', large: true, focusCancel: true }))) return
  step.value = null
}

onMounted(load)
</script>
