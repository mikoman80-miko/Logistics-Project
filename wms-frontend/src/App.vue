<template>
  <template v-if="!authStore.isAuthenticated"><router-view /></template>

  <div v-else class="flex w-screen h-screen overflow-hidden bg-surface-app text-ink text-body font-sans">
    <aside class="hidden md:flex w-[200px] bg-[#f8f9fa] border-r border-line-strong flex-col shrink-0 print:hidden">
      <div class="bg-surface-nav text-white p-3 border-b-2 border-primary text-center">
        <h2 class="m-0 text-heading font-bold">WMS 시스템</h2>
      </div>
      <div class="p-2.5 bg-[#e4e5e6] border-b border-line leading-[1.6]">
        접속자: <strong>{{ authStore.user?.name }}</strong><br />
        권한: {{ authStore.user?.role }}
        <button @click="handleLogout"
          class="btn btn-link btn-sm ml-1.5">[로그아웃]</button>
      </div>

      <ul class="list-none p-0 m-0">
        <template v-if="authStore.user?.role === '관리자'">
          <li class="menu-group">기준정보 관리</li>
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/locations' }"
              @click.prevent="openMenu('/locations')">- 창고 구역/랙 관리</a></li>
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/items' }"
              @click.prevent="openMenu('/items')">- 상품/카테고리 관리</a></li>
        </template>

        <li class="menu-group">물류 작업 관리</li>
        <template v-if="authStore.user?.role === '관리자'">
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/' }"
              @click.prevent="openMenu('/')">- 재고/출납 관리</a></li>
        </template>

        <!-- 🌟 NEW: 발주 메뉴 추가 -->
        <li><a href="#"
            class="menu-link"
            :class="{ 'is-active': tabStore.activeTabPath === '/purchase-order' }"
            @click.prevent="openMenu('/purchase-order')">- 정규 발주 및 입고</a></li>
        <li><a href="#"
            class="menu-link"
            :class="{ 'is-active': tabStore.activeTabPath === '/receiving' }"
            @click.prevent="openMenu('/receiving')">- 반품/AS 입고 검수</a></li>
        <li><a href="#"
            class="menu-link"
            :class="{ 'is-active': tabStore.activeTabPath === '/picking' }"
            @click.prevent="openMenu('/picking')">- 피킹 및 출고 검수</a></li>

        <template v-if="authStore.user?.role === '관리자'">
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/audit' }"
              @click.prevent="openMenu('/audit')">- 월말 재고 실사</a></li>
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/serials' }"
              @click.prevent="openMenu('/serials')">- 시리얼/품질 상태 관리</a></li>
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/ledger' }"
              @click.prevent="openMenu('/ledger')">- 재고수불부</a></li>
          <li><a href="#"
              class="menu-link"
              :class="{ 'is-active': tabStore.activeTabPath === '/dashboard' }"
              @click.prevent="openMenu('/dashboard')">- 입출고 통계 조회</a></li>
        </template>
      </ul>
    </aside>

    <main class="flex-1 flex flex-col min-w-0 md:min-w-[800px] bg-white overflow-hidden">
      <header class="bg-surface-head h-[35px] border-b border-line-strong flex flex-col shrink-0 print:hidden">
        <div class="flex h-full justify-between items-end px-2.5 pl-[5px]">
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
  </div>
</template>

<script setup>
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useTabStore } from './stores/tabStore'
import { useToastStore } from './stores/toastStore'

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

const openMenu = (path) => { router.push(path) }

const handleLogout = () => {
  authStore.logout()
}

// 세션 만료로 로그아웃되어도 이전 사용자의 탭이 남지 않게 합니다.
watch(() => authStore.isAuthenticated, (loggedIn) => {
  if (!loggedIn) tabStore.openTabs = []
})
</script>