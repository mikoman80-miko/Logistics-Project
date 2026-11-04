<template>
  <WorkLayout title="현장 작업" :show-home="false">
    <div class="flex flex-col gap-6 h-full">
    <div class="grid grid-cols-3 gap-8 flex-1 min-h-0">
      <button v-for="(menu, index) in menus" :key="menu.path" class="work-card" @click="router.push(menu.path)">
        <span class="text-3xl text-muted">{{ index + 1 }}번 키</span>
        <span class="text-[80px] font-bold leading-tight">{{ menu.title }}</span>
        <span class="text-4xl">대기 <strong class="text-primary text-6xl">{{ menu.count() }}</strong>건</span>
      </button>
    </div>
    <button class="work-btn shrink-0" @click="router.push('/work/today')">4번 키 · 오늘 내 작업 보기</button>
    </div>
  </WorkLayout>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import WorkLayout from '../../components/work/WorkLayout.vue'

const router = useRouter()
const today = ref({})

const menus = [
  { title: '입고', path: '/work/inbound', count: () => today.value.purchase_orders ?? '-' },
  { title: '출고', path: '/work/outbound', count: () => today.value.orders ?? '-' },
  { title: '반품 회수', path: '/work/return', count: () => today.value.returns ?? '-' },
]

const onKeydown = (event) => {
  // 비밀번호 칸 등에 숫자를 입력할 때는 이동하지 않습니다.
  if (event.target.closest?.('input, textarea, select, .modal-overlay')) return
  if (event.key === '4') return router.push('/work/today')
  const menu = menus[Number(event.key) - 1]
  if (menu) router.push(menu.path)
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  today.value = (await axios.get('/api/inventory/today/')).data
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>
