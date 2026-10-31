<template>
  <WorkLayout title="현장 작업" :show-home="false">
    <div class="grid grid-cols-3 gap-8 h-full">
      <button v-for="(menu, index) in menus" :key="menu.path" class="work-card" @click="router.push(menu.path)">
        <span class="text-3xl text-muted">{{ index + 1 }}번 키</span>
        <span class="text-[80px] font-bold leading-tight">{{ menu.title }}</span>
        <span class="text-4xl">대기 <strong class="text-primary text-6xl">{{ menu.count() }}</strong>건</span>
      </button>
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
  const menu = menus[Number(event.key) - 1]
  if (menu) router.push(menu.path)
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  today.value = (await axios.get('/api/inventory/today/')).data
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>
