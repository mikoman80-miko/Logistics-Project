from django.contrib import admin
from .models import (
    Category, 
    WarehouseLocation, 
    Item, 
    ItemSerial, 
    InventoryLog, 
    Supplier, 
    PurchaseOrder, 
    PurchaseOrderItem
)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'description')
    search_fields = ('name',)

@admin.register(WarehouseLocation)
class WarehouseLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_code', 'zone', 'rack', 'tier', 'cell', 'is_active')
    list_filter = ('zone', 'is_active')

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'sku', 'name', 'quantity', 'safety_stock', 'abc_grade', 'location')
    search_fields = ('sku', 'name')
    list_filter = ('abc_grade',)

@admin.register(ItemSerial)
class ItemSerialAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'serial_number', 'status', 'quality', 'location', 'updated_at')
    search_fields = ('serial_number', 'item__sku', 'item__name')
    list_filter = ('status', 'quality')

@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'action', 'quantity_changed', 'timestamp')
    list_filter = ('action', 'timestamp')

# 🌟 NEW: 공급사(거래처) 및 발주서 관리자 등록
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'contact_person', 'phone', 'email', 'is_active')
    search_fields = ('name',)

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'po_number', 'supplier', 'status', 'order_date', 'expected_date')
    list_filter = ('status', 'order_date')
    search_fields = ('po_number',)

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'po', 'item', 'order_quantity', 'received_quantity')
    search_fields = ('po__po_number', 'item__sku', 'item__name')