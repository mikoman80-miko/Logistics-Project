from django.conf import settings
from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    description = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        if self.parent:
            return f"{self.parent} > {self.name}"
        return self.name

class WarehouseLocation(models.Model):
    zone = models.CharField(max_length=50)
    rack = models.CharField(max_length=50)
    tier = models.IntegerField(default=1)
    cell = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=200, blank=True, null=True)

    @property
    def full_code(self):
        if self.cell:
            return f"{self.zone}-{self.rack}-{self.tier}단-{self.cell}"
        return f"{self.zone}-{self.rack}-{self.tier}단"

    @property
    def barcode(self):
        # 위치 코드에는 한글(단, 동)이 들어갈 수 있어 바코드에는 번호를 씁니다.
        return f'LOC{self.id:05d}' if self.id else ''

    def __str__(self):
        return self.full_code

class Item(models.Model):
    TYPE_CHOICES = [
        ('상품', '상품'),
        ('구성품', '구성품'),
        ('부자재', '부자재'),
        ('사은품', '사은품'),
    ]
    sku = models.CharField(max_length=100, unique=True)
    item_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='상품')
    serial_tracked = models.BooleanField(default=True) # 켜면 입출고 때 시리얼을 스캔합니다. 상품별로 언제든 바꿀 수 있습니다.
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    quantity = models.IntegerField(default=0)
    location = models.ForeignKey(WarehouseLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    
    # 🌟 NEW: 재고 분석 및 알림을 위한 필드 추가
    safety_stock = models.IntegerField(default=5) # 안전 재고 (이하로 떨어지면 슬랙 알림)
    abc_grade = models.CharField(max_length=10, blank=True, null=True) # A, B, C 등급 (장기 체화 분석용)
    is_active = models.BooleanField(default=True) # 삭제해도 이력을 남기기 위해 사용 중지로 처리
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name='item_quantity_not_negative'),
        ]

    def __str__(self):
        return f"[{self.sku}] {self.name}"

# 🌟 NEW: 거래처(공급사) 모델
class Supplier(models.Model):
    name = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=50, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

# 🌟 NEW: 정규 발주서(PO) 모델
class PurchaseOrder(models.Model):
    po_number = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='purchase_orders')
    
    STATUS_CHOICES = [
        ('발주대기', '발주대기'),
        ('입고중', '입고중'),
        ('입고완료', '입고완료'),
        ('취소됨', '취소됨')
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='발주대기')
    order_date = models.DateField(auto_now_add=True)
    expected_date = models.DateField(blank=True, null=True)
    
    def __str__(self):
        return self.po_number

# 🌟 NEW: 발주서 상세 품목 모델
class PurchaseOrderItem(models.Model):
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    order_quantity = models.IntegerField(default=0)
    received_quantity = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['po', 'item'], name='unique_po_item'),
        ]

    def __str__(self):
        return f"{self.po.po_number} - {self.item.name}"

class ShippingInfo(models.Model):
    # 택배 연동에 쓰는 주소와 운송장. 주문에서는 수령인, 반품에서는 회수할 고객입니다.
    contact_name = models.CharField(max_length=50, blank=True, default='')
    contact_phone = models.CharField(max_length=20, blank=True, default='')
    zipcode = models.CharField(max_length=10, blank=True, default='')
    address = models.CharField(max_length=200, blank=True, default='')
    address_detail = models.CharField(max_length=100, blank=True, default='')
    waybill_no = models.CharField(max_length=30, blank=True, default='', db_index=True)
    carrier_status = models.CharField(max_length=20, blank=True, default='')  # 택배사가 알려준 최근 상태
    carrier_error = models.CharField(max_length=200, blank=True, default='')  # 택배사 요청 실패 사유

    class Meta:
        abstract = True

    @property
    def has_address(self):
        return bool(self.contact_name and self.contact_phone and self.zipcode and self.address)


class SalesOrder(ShippingInfo):
    STATUS_CHOICES = [
        ('출고대기', '출고대기'),
        ('출고완료', '출고완료'),
        ('취소됨', '취소됨')
    ]
    order_no = models.CharField(max_length=50, unique=True)
    customer = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='출고대기', db_index=True)
    note = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # 묶음배송: 같은 곳으로 가는 주문을 대표 주문의 운송장 하나로 보냅니다.
    bundle_parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='bundle_members')

    def __str__(self):
        return self.order_no

class SalesOrderItem(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    picked_quantity = models.IntegerField(default=0) # 스캔으로 확인한 수량

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['order', 'item'], name='unique_order_item'),
        ]

    def __str__(self):
        return f"{self.order.order_no} - {self.item.name}"

class ItemSerial(models.Model):
    item = models.ForeignKey(Item, related_name='serials', on_delete=models.PROTECT)
    serial_number = models.CharField(max_length=100, unique=True)
    lot_number = models.CharField(max_length=100, blank=True, null=True)
    
    STATUS_CHOICES = [
        ('입고대기', '입고대기'),
        ('재고보유', '재고보유'),
        ('출고완료', '출고완료'),
        ('AS진행중', 'AS진행중'),
        ('불량폐기', '불량폐기')
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='재고보유')
    
    QUALITY_CHOICES = [
        ('신규상품', '신규상품'),
        ('양품A급', '양품A급'),
        ('양품B급', '양품B급'),
        ('사용불가', '사용불가')
    ]
    quality = models.CharField(max_length=20, choices=QUALITY_CHOICES, default='신규상품')
    location = models.ForeignKey(WarehouseLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='serials')
    # 발주 입고로 들어온 시리얼이면 그 발주 품목. 입고 취소 때 어느 발주로 들어왔는지 확인합니다.
    po_item = models.ForeignKey('PurchaseOrderItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_serials')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.item.name} - S/N: {self.serial_number}"

class SalesOrderSerial(models.Model):
    # 출고 스캔으로 주문 품목에 묶인 시리얼
    line = models.ForeignKey(SalesOrderItem, on_delete=models.CASCADE, related_name='picked_serials')
    serial = models.ForeignKey(ItemSerial, on_delete=models.PROTECT, related_name='order_picks')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['line', 'serial'], name='unique_line_serial'),
        ]

class ReturnOrder(ShippingInfo):
    STATUS_CHOICES = [
        ('회수대기', '회수대기'),
        ('회수완료', '회수완료'),
        ('취소됨', '취소됨')
    ]
    return_no = models.CharField(max_length=50, unique=True)
    customer = models.CharField(max_length=100)
    reason = models.CharField(max_length=100)
    serial = models.ForeignKey(ItemSerial, on_delete=models.PROTECT, related_name='returns')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='회수대기', db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.return_no

class InventoryLog(models.Model):
    item = models.ForeignKey(Item, related_name='logs', on_delete=models.PROTECT)
    action = models.CharField(max_length=10)
    quantity_changed = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=200, blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+') # 처리자

    class Meta:
        indexes = [
            models.Index(fields=['-timestamp'], name='log_time_idx'),
            models.Index(fields=['item', '-timestamp'], name='log_item_time_idx'),
            models.Index(fields=['action', '-timestamp'], name='log_action_time_idx'),
        ]

class CarrierEvent(models.Model):
    # 택배사에서 받은 배송·회수 단계 이력. 같은 알림이 두 번 와도 한 번만 저장합니다.
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, null=True, blank=True, related_name='carrier_events')
    return_order = models.ForeignKey(ReturnOrder, on_delete=models.CASCADE, null=True, blank=True, related_name='carrier_events')
    event_id = models.CharField(max_length=64, unique=True)
    waybill_no = models.CharField(max_length=30)
    status = models.CharField(max_length=20)
    location = models.CharField(max_length=100, blank=True, default='')
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ['occurred_at', 'id']
