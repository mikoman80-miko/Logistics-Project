import { createRouter, createWebHistory } from 'vue-router'
// 화면은 처음 열 때 불러옵니다. (현장 PC가 관리 화면 코드까지 미리 받지 않게) 로그인 화면만 바로 씁니다.
const HomeView = () => import('../views/HomeView.vue')
const DashboardView = () => import('../views/DashboardView.vue')
import LoginView from '../views/LoginView.vue'
const TodayView = () => import('../views/TodayView.vue')
const StockAuditView = () => import('../views/inventory/StockAuditView.vue')
const PickingView = () => import('../views/outbound/PickingView.vue')
const SerialTrackingView = () => import('../views/inventory/SerialTrackingView.vue')
const ReturnReceivingView = () => import('../views/inbound/ReturnReceivingView.vue')
const LocationMasterView = () => import('../views/master/LocationMasterView.vue')
const ItemMasterView = () => import('../views/master/ItemMasterView.vue')
const SupplierView = () => import('../views/master/SupplierView.vue')
const UserManageView = () => import('../views/master/UserManageView.vue')
const PurchaseOrderView = () => import('../views/inbound/PurchaseOrderView.vue')
const WorkHomeView = () => import('../views/work/WorkHomeView.vue')
const WorkInboundView = () => import('../views/work/WorkInboundView.vue')
const WorkOutboundView = () => import('../views/work/WorkOutboundView.vue')
const WorkReturnView = () => import('../views/work/WorkReturnView.vue')
const WorkTodayView = () => import('../views/work/WorkTodayView.vue')
const WorkPickingView = () => import('../views/work/WorkPickingView.vue')
const WorkReplenishView = () => import('../views/work/WorkReplenishView.vue')

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
    { path: '/work/replenish', name: 'work-replenish', component: WorkReplenishView, meta: workPage },

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
    { path: '/receipt-issues', name: 'receipt-issues', component: () => import('../views/inbound/ReceiptIssueReportView.vue'), meta: adminPage('입고 검수 차이') },
    { path: '/analysis', name: 'analysis', component: () => import('../views/inventory/AnalysisView.vue'), meta: adminPage('재고·반품 분석') },
    { path: '/workers', name: 'workers', component: () => import('../views/inventory/WorkerReportView.vue'), meta: adminPage('작업자 실적') },
    { path: '/items', name: 'items', component: ItemMasterView, meta: adminPage('상품') },
    { path: '/locations', name: 'locations', component: LocationMasterView, meta: adminPage('보관 위치') },
    { path: '/suppliers', name: 'suppliers', component: SupplierView, meta: adminPage('거래처') },
    { path: '/users', name: 'users', component: UserManageView, meta: adminPage('사용자') },
    { path: '/changes', name: 'changes', component: () => import('../views/master/ChangeHistoryView.vue'), meta: adminPage('변경 이력') },

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
