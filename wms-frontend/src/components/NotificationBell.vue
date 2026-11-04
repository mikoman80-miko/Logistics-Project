<template>
  <!-- 화면 안 알림: 재고 부족, 택배 장애, 서버 오류, 입고 지연, 일일 마감 등. 1분마다 새로 확인합니다. -->
  <div ref="rootRef" class="relative mb-1">
    <button class="btn btn-sm" :class="{ 'btn-danger': unread > 0 }" :aria-label="`알림 ${unread}건`" @click="toggle">
      🔔 알림<b v-if="unread"> {{ unread > 99 ? '99+' : unread }}</b>
    </button>
    <div v-if="open" class="absolute right-0 top-[calc(100%+4px)] z-[1200] w-[460px] max-h-[70vh] overflow-y-auto bg-white border border-line-strong shadow-lg">
      <div class="panel-header"><span class="panel-title">알림</span><span class="text-muted">최근 30건 · 90일 보관</span></div>
      <div v-if="!items.length" class="p-4 text-center text-muted">알림이 없습니다.</div>
      <button v-for="item in items" :key="item.id" class="block w-full text-left px-3 py-2 border-b border-line hover:bg-primary-soft"
        :class="{ 'bg-[#fff8e6]': item.unread, 'cursor-default': !item.link }" @click="openItem(item)">
        <div class="flex justify-between gap-2 text-caption">
          <b :class="kindClass(item.kind)">{{ item.kind }}</b>
          <span class="text-muted">{{ item.created_at.slice(5, 16).replace('T', ' ') }}<span v-if="item.unread" class="ml-1 text-danger font-bold">새 알림</span></span>
        </div>
        <div class="mt-0.5 whitespace-pre-line break-keep">{{ item.message }}</div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const rootRef = ref(null)
const open = ref(false)
const unread = ref(0)
const items = ref([])
let timer

const kindClass = (kind) => (['서버 오류', '택배', '재고 부족'].includes(kind) ? 'text-danger' : kind === '일일 마감' ? 'text-success' : 'text-warning')

const load = async () => {
  try {
    const data = (await axios.get('/api/inventory/notifications/')).data
    unread.value = data.unread
    items.value = data.items
  } catch {
    // 알림을 못 불러와도 화면 사용에는 지장이 없게 조용히 넘어갑니다.
  }
}

// 열면 지금까지 온 알림을 읽은 것으로 표시합니다. (목록의 '새 알림' 표시는 닫을 때까지 남겨 둡니다)
const toggle = async () => {
  open.value = !open.value
  if (!open.value) return load()
  await load()
  if (unread.value) {
    await axios.post('/api/inventory/notifications/')
    unread.value = 0
  }
}

const openItem = (item) => {
  if (!item.link) return
  open.value = false
  router.push(item.link)
  load()
}

const onClickOutside = (event) => {
  if (open.value && !rootRef.value?.contains(event.target)) {
    open.value = false
    load()
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 60000)
  document.addEventListener('click', onClickOutside)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('click', onClickOutside)
})
</script>
