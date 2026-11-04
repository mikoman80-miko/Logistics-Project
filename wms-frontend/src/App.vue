<template>
  <template v-if="!authStore.isAuthenticated || route.meta.work"><router-view /></template>

  <div v-else class="flex w-screen h-screen overflow-hidden bg-surface-app text-ink text-body font-sans">
    <!-- 좁은 화면에서는 메뉴 버튼으로 여닫습니다. -->
    <div v-if="menuOpen" class="md:hidden fixed inset-0 z-[1090] bg-black/40" @click="menuOpen = false"></div>
    <aside class="md:flex md:static w-[230px] bg-[#f8f9fa] border-r border-line-strong flex-col shrink-0 print:hidden"
      :class="menuOpen ? 'flex fixed inset-y-0 left-0 z-[1100] shadow-lg' : 'hidden'">
      <div class="bg-surface-nav text-white p-3 border-b-2 border-primary text-center">
        <h2 class="m-0 text-heading font-bold">WMS 시스템</h2>
      </div>
      <div class="p-2.5 bg-[#e4e5e6] border-b border-line leading-[1.6]">
        접속자: <strong>{{ authStore.user?.name }}</strong><br />
        권한: {{ authStore.user?.role }}
        <button @click="handleLogout"
          class="btn btn-link btn-sm ml-1.5">로그아웃</button>
      </div>

      <div class="p-2 border-b border-line">
        <button class="btn btn-success btn-block" @click="router.push('/work')">현장 작업 화면 열기</button>
      </div>

      <ul class="list-none p-0 m-0 overflow-y-auto">
        <template v-for="group in menuGroups" :key="group.title">
          <li class="menu-group">{{ group.title }}</li>
          <li v-for="menu in group.menus" :key="menu.path">
            <a href="#" class="menu-link" :class="{ 'is-active': tabStore.activeTabPath === menu.path }"
              @click.prevent="openMenu(menu.path)">{{ menu.title }}</a>
          </li>
        </template>
      </ul>
    </aside>

    <main class="flex-1 flex flex-col min-w-0 md:min-w-[800px] bg-white overflow-hidden">
      <header class="bg-surface-head h-[44px] border-b border-line-strong flex flex-col shrink-0 print:hidden">
        <div class="flex h-full justify-between items-end gap-1 px-2.5 pl-[5px]">
          <button class="btn btn-sm mb-1 md:hidden" aria-label="메뉴 열기" @click="menuOpen = true">☰ 메뉴</button>
          <div
            class="flex gap-0.5 overflow-x-auto overflow-y-hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <div v-for="tab in tabStore.openTabs" :key="tab.path"
              class="tab" :class="{ 'is-active': tabStore.activeTabPath === tab.path }"
              @click="tabStore.setActiveTab(tab.path)">
              <span class="text-body mr-2 flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{{ tab.title
              }}</span>
              <button
                class="bg-transparent border-none text-[10px] text-[#777] cursor-pointer p-0.5 rounded-full w-4 h-4 flex justify-center items-center hover:bg-[#ffcccc] hover:text-danger"
                @click.stop="tabStore.removeTab(tab.path)">✖</button>
            </div>
          </div>
          <button
            class="btn btn-sm mb-1"
            @click="tabStore.closeAllTabs">전체 닫기</button>
        </div>
      </header>

      <div class="p-2.5 flex-1 overflow-auto bg-surface-app print:p-0 print:overflow-visible print:bg-white">
        <router-view v-slot="{ Component, route }">
          <keep-alive>
            <component :is="Component" :key="route.path" />
          </keep-alive>
        </router-view>
      </div>
    </main>

  </div>

  <AppDialog />

  <div class="fixed bottom-[30px] right-[30px] z-[9999] flex flex-col gap-2.5 pointer-events-none print:hidden">
    <transition-group enter-active-class="transition-all duration-300 ease-[cubic-bezier(0.68,-0.55,0.265,1.55)]"
      leave-active-class="transition-all duration-300 ease-[cubic-bezier(0.68,-0.55,0.265,1.55)]"
      enter-from-class="opacity-0 translate-x-full" leave-to-class="opacity-0 translate-y-5">

      <div v-for="toast in toastStore.toasts" :key="toast.id"
        class="min-w-[250px] px-5 py-[15px] text-white text-heading font-bold rounded shadow-[0_4px_15px_rgba(0,0,0,0.3)] pointer-events-auto flex items-center gap-2.5"
        :class="{ 'bg-success border-l-[6px] border-success-dark': toast.type === 'success', 'bg-danger border-l-[6px] border-danger-dark': toast.type === 'error', 'bg-primary border-l-[6px] border-primary-dark': toast.type === 'info' || !toast.type }">
        {{ toast.message }}
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useTabStore } from './stores/tabStore'
import { useToastStore } from './stores/toastStore'
import AppDialog from './components/AppDialog.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const tabStore = useTabStore()
const toastStore = useToastStore()

watch(() => [route.path, route.meta.title], ([newPath]) => {
  if (newPath !== '/login' && route.meta.title) {
    tabStore.addTab({ path: newPath, name: route.name, meta: { title: route.meta.title } })
  }
}, { immediate: true })

const menuGroups = [
  { title: '시작', menus: [{ title: '오늘 할 일', path: '/today' }] },
  { title: '입고', menus: [{ title: '발주 관리', path: '/purchase-order' }] },
  { title: '출고', menus: [{ title: '주문 관리', path: '/orders' }] },
  { title: '반품', menus: [{ title: '반품 관리', path: '/returns' }] },
  { title: '재고', menus: [
    { title: '재고 현황', path: '/stock' },
    { title: '재고 조사', path: '/audit' },
    { title: '시리얼 조회', path: '/serials' },
  ] },
  { title: '보고서', menus: [
    { title: '입출고 장부', path: '/ledger' },
    { title: '입출고 통계', path: '/dashboard' },
  ] },
  { title: '기본 설정', menus: [
    { title: '상품', path: '/items' },
    { title: '보관 위치', path: '/locations' },
    { title: '거래처', path: '/suppliers' },
  ] },
]

const menuOpen = ref(false)
const openMenu = (path) => { router.push(path) }
watch(() => route.path, () => { menuOpen.value = false })

const handleLogout = () => {
  authStore.logout()
}

// 세션 만료로 로그아웃되어도 이전 사용자의 탭이 남지 않게 합니다.
watch(() => authStore.isAuthenticated, (loggedIn) => {
  if (!loggedIn) tabStore.openTabs = []
})
</script>