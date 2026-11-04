import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import TodayView from '../views/TodayView.vue'
import StockAuditView from '../views/inventory/StockAuditView.vue'
import PickingView from '../views/outbound/PickingView.vue'
import SerialTrackingView from '../views/inventory/SerialTrackingView.vue'
import ReturnReceivingView from '../views/inbound/ReturnReceivingView.vue'
import LocationMasterView from '../views/master/LocationMasterView.vue'
import ItemMasterView from '../views/master/ItemMasterView.vue'
import SupplierView from '../views/master/SupplierView.vue'
import UserManageView from '../views/master/UserManageView.vue'
import PurchaseOrderView from '../views/inbound/PurchaseOrderView.vue'
import WorkHomeView from '../views/work/WorkHomeView.vue'
import WorkInboundView from '../views/work/WorkInboundView.vue'
import WorkOutboundView from '../views/work/WorkOutboundView.vue'
import WorkReturnView from '../views/work/WorkReturnView.vue'
import WorkTodayView from '../views/work/WorkTodayView.vue'
import WorkPickingView from '../views/work/WorkPickingView.vue'

const isAdmin = () => localStorage.getItem('user_role') === '관리자'
const homePath = () => (isAdmin() ? '/today' : '/work')
const adminPage = (title) => ({ requiresAuth: true, role: 'admin', title })
const workPage = { requiresAuth: true, work: true }

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', redirect: homePath },

    // 현장 작업 화면 (큰 글씨, 스캔 중심)
    { path: '/work', name: 'work', component: WorkHomeView, meta: workPage },
    { path: '/work/inbound', name: 'work-inbound', component: WorkInboundView, meta: workPage },
    { path: '/work/outbound', name: 'work-outbound', component: WorkOutboundView, meta: workPage },
    { path: '/work/return', name: 'work-return', component: WorkReturnView, meta: workPage },
    { path: '/work/today', name: 'work-today', component: WorkTodayView, meta: workPage },
    { path: '/work/picking', name: 'work-picking', component: WorkPickingView, meta: workPage },

    // 관리 화면
    { path: '/today', name: 'today', component: TodayView, meta: adminPage('오늘 할 일') },
    { path: '/purchase-order', name: 'purchase-order', component: PurchaseOrderView, meta: adminPage('발주 관리') },
    { path: '/orders', name: 'orders', component: PickingView, meta: adminPage('주문 관리') },
    { path: '/returns', name: 'returns', component: ReturnReceivingView, meta: adminPage('반품 관리') },
    { path: '/stock', name: 'stock', component: HomeView, meta: adminPage('재고 현황') },
    { path: '/audit', name: 'audit', component: StockAuditView, meta: adminPage('재고 조사') },
    { path: '/serials', name: 'serials', component: SerialTrackingView, meta: adminPage('시리얼 조회') },
    { path: '/ledger', name: 'ledger', component: () => import('../views/inventory/StockLedgerView.vue'), meta: adminPage('입출고 장부') },
    { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: adminPage('입출고 통계') },
    { path: '/daily-close', name: 'daily-close', component: () => import('../views/inventory/DailyCloseView.vue'), meta: adminPage('일일 마감') },
    { path: '/workers', name: 'workers', component: () => import('../views/inventory/WorkerReportView.vue'), meta: adminPage('작업자 실적') },
    { path: '/items', name: 'items', component: ItemMasterView, meta: adminPage('상품') },
    { path: '/locations', name: 'locations', component: LocationMasterView, meta: adminPage('보관 위치') },
    { path: '/suppliers', name: 'suppliers', component: SupplierView, meta: adminPage('거래처') },
    { path: '/users', name: 'users', component: UserManageView, meta: adminPage('사용자') },

    // 예전 주소
    { path: '/picking', redirect: '/orders' },
    { path: '/receiving', redirect: '/returns' },
    { path: '/:pathMatch(.*)*', redirect: homePath },
  ]
})

router.beforeEach((to) => {
  const isAuthenticated = !!localStorage.getItem('access_token')

  if (to.meta.requiresAuth && !isAuthenticated) return '/login'
  if (to.name === 'login' && isAuthenticated) return homePath()
  if (to.meta.role === 'admin' && !isAdmin()) return '/work'
})

export default router
