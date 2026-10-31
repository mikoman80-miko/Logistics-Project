import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import StockAuditView from '../views/inventory/StockAuditView.vue'
import PickingView from '../views/outbound/PickingView.vue'
import SerialTrackingView from '../views/inventory/SerialTrackingView.vue'
import ReturnReceivingView from '../views/inbound/ReturnReceivingView.vue'
import LocationMasterView from '../views/master/LocationMasterView.vue'
import ItemMasterView from '../views/master/ItemMasterView.vue'
// 🌟 NEW: 발주/입고 컴포넌트 추가
import PurchaseOrderView from '../views/inbound/PurchaseOrderView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', name: 'home', component: HomeView, meta: { requiresAuth: true, title: '재고/출납 관리', role: 'admin' } },
    { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true, title: '입출고 통계 조회', role: 'admin' } },
    { path: '/audit', name: 'audit', component: StockAuditView, meta: { requiresAuth: true, title: '월말 재고 실사', role: 'admin' } },
    { path: '/serials', name: 'serials', component: SerialTrackingView, meta: { requiresAuth: true, title: '시리얼/품질 상태 관리', role: 'admin' } },
    { path: '/locations', name: 'locations', component: LocationMasterView, meta: { requiresAuth: true, title: '창고 구역/랙 관리', role: 'admin' } },
    { path: '/items', name: 'items', component: ItemMasterView, meta: { requiresAuth: true, title: '상품/카테고리 관리', role: 'admin' } },
    { path: '/ledger', name: 'ledger', component: () => import('../views/inventory/StockLedgerView.vue'), meta: { requiresAuth: true, title: '재고수불부', role: 'admin' } },
    
    { path: '/picking', name: 'picking', component: PickingView, meta: { requiresAuth: true, title: '피킹 및 출고 검수' } },
    { path: '/receiving', name: 'receiving', component: ReturnReceivingView, meta: { requiresAuth: true, title: '반품/AS 입고 검수' } },
    // 🌟 NEW: 정규 발주 입고 라우터 추가 (작업자 공용)
    { path: '/purchase-order', name: 'purchase-order', component: PurchaseOrderView, meta: { requiresAuth: true, title: '정규 발주 및 입고' } },
  ]
})

router.beforeEach((to, from) => {
  const isAuthenticated = !!localStorage.getItem('access_token')
  const userRole = localStorage.getItem('user_role') || '현장작업자'

  if (to.meta.requiresAuth && !isAuthenticated) return '/login'
  if (to.name === 'login' && isAuthenticated) return userRole === '관리자' ? '/dashboard' : '/picking'
  
  if (to.meta.role === 'admin' && userRole !== '관리자') {
    alert('해당 메뉴는 관리자만 접근할 수 있습니다.')
    return '/picking' 
  }
})

export default router