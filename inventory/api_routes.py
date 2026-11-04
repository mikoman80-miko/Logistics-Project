from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ItemViewSet, 
    WorkerReportAPIView,
    InventoryLogViewSet, 
    ItemSerialViewSet, 
    WarehouseLocationViewSet, 
    CategoryViewSet, 
    SupplierViewSet, # 🌟 NEW
    PurchaseOrderViewSet, # 🌟 NEW
    SalesOrderViewSet,
    ReturnOrderViewSet,
    InventoryLedgerAPIView, 
    DashboardAPIView,
    TodayAPIView,
    UserViewSet,
)

router = DefaultRouter()
router.register(r'items', ItemViewSet)
router.register(r'logs', InventoryLogViewSet)
router.register(r'serials', ItemSerialViewSet)
router.register(r'locations', WarehouseLocationViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'suppliers', SupplierViewSet) # 🌟 NEW: 거래처 주소
router.register(r'purchase-orders', PurchaseOrderViewSet) # 🌟 NEW: 발주서 주소
router.register(r'orders', SalesOrderViewSet)
router.register(r'returns', ReturnOrderViewSet)
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('ledger/', InventoryLedgerAPIView.as_view(), name='inventory-ledger'),
    path('dashboard/', DashboardAPIView.as_view(), name='dashboard-stats'),
    path('today/', TodayAPIView.as_view(), name='today-summary'),
    path('reports/workers/', WorkerReportAPIView.as_view(), name='worker-report'),
]