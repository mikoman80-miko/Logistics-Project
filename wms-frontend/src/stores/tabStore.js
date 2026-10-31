import { ref } from 'vue'
import { defineStore } from 'pinia'
import router from '../router'

export const useTabStore = defineStore('tab', () => {
  const openTabs = ref([
    { title: '입출고 대시보드', path: '/dashboard', name: 'dashboard' }
  ])
  
  // 💡 새로고침 시 무조건 '/dashboard'로 가는 현상 방지
  const activeTabPath = ref(window.location.pathname)

  const addTab = (route) => {
    const isExist = openTabs.value.find(tab => tab.path === route.path)
    if (!isExist) {
      openTabs.value.push({
        title: route.meta.title || route.name,
        path: route.path,
        name: route.name
      })
    }
    activeTabPath.value = route.path
    // 💡 여기서 router.push(route.path) 삭제 (라우터 충돌 및 화면 튕김 방지)
  }

  // 권한별 기본 화면 (작업자는 대시보드에 접근할 수 없습니다)
  const homeTab = () => (localStorage.getItem('user_role') === '관리자'
    ? { title: '입출고 통계 조회', path: '/dashboard', name: 'dashboard' }
    : { title: '피킹 및 출고 검수', path: '/picking', name: 'picking' })

  // 탭 닫기 로직
  const removeTab = (targetPath) => {
    const tabs = openTabs.value
    let activePath = activeTabPath.value

    if (activePath === targetPath) {
      tabs.forEach((tab, index) => {
        if (tab.path === targetPath) {
          const nextTab = tabs[index + 1] || tabs[index - 1]
          if (nextTab) {
            activePath = nextTab.path
          } else {
            // 탭이 다 닫히면 대시보드로 강제 이동
            activePath = homeTab().path
          }
        }
      })
    }

    activeTabPath.value = activePath
    openTabs.value = tabs.filter(tab => tab.path !== targetPath)
    
    // 탭이 모두 닫힌 경우 대시보드 탭 재생성
    if (openTabs.value.length === 0) {
      openTabs.value.push(homeTab())
    }
    
    router.push(activeTabPath.value)
  }

  // 탭 직접 클릭 시 활성화
  const setActiveTab = (path) => {
    activeTabPath.value = path
    router.push(path)
  }

  // 모든 탭 닫기
  const closeAllTabs = () => {
    const home = homeTab()
    openTabs.value = [home]
    activeTabPath.value = home.path
    router.push(home.path)
  }

  return { openTabs, activeTabPath, addTab, removeTab, setActiveTab, closeAllTabs }
})