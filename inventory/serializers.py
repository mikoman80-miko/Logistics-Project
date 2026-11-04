from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db.models import Q
from django.utils import timezone
import re

from . import carrier
from .models import Item, ItemSerial, InventoryLog, WarehouseLocation, Category, Supplier, PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem, SalesOrderSerial, ReturnOrder, CarrierEvent

def next_document_number(model, field, prefix):
    # PO-20261031-0001 형식의 일자별 일련번호를 만듭니다. 동시에 등록해도 겹치지 않도록 잠급니다.
    day_prefix = f"{prefix}-{timezone.localdate():%Y%m%d}-"
    last = model.objects.select_for_update().filter(**{f'{field}__startswith': day_prefix}).order_by(f'-{field}').first()
    number = int(getattr(last, field).rsplit('-', 1)[1]) + 1 if last else 1
    return f"{day_prefix}{number:04d}"

def user_display(user):
    return (user.get_full_name() or user.username) if user else ''

CARRIER_FIELDS = ['waybill_no', 'carrier_status', 'carrier_error']


def validate_shipping(attrs, required):
    """연락처와 우편번호 형식을 확인합니다. required이면 택배 요청에 필요한 칸을 모두 받습니다."""
    for key in ('contact_name', 'contact_phone', 'zipcode', 'address', 'address_detail'):
        if key in attrs:
            attrs[key] = (attrs[key] or '').strip()
    phone, zipcode = attrs.get('contact_phone'), attrs.get('zipcode')
    if phone and not re.fullmatch(r'0\d{1,2}-?\d{3,4}-?\d{4}', phone):
        raise serializers.ValidationError({'contact_phone': '연락처 형식이 올바르지 않습니다. 예: 010-1234-5678'})
    if zipcode and not re.fullmatch(r'\d{5}', zipcode):
        raise serializers.ValidationError({'zipcode': '우편번호는 숫자 5자리입니다.'})
    if required:
        missing = [label for key, label in (('contact_name', '이름'), ('contact_phone', '연락처'), ('zipcode', '우편번호'), ('address', '주소')) if not attrs.get(key)]
        if missing:
            raise serializers.ValidationError({'address': f'택배 발송에 필요한 {", ".join(missing)}을(를) 입력해주세요.'})
    return attrs


class CarrierEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarrierEvent
        fields = ['status', 'location', 'occurred_at']


class CarrierInfoMixin(serializers.Serializer):
    carrier_events = CarrierEventSerializer(many=True, read_only=True)
    tracking_url = serializers.SerializerMethodField()
    carrier_name = serializers.SerializerMethodField()

    def get_tracking_url(self, obj):
        return carrier.tracking_url(obj.waybill_no)

    def get_carrier_name(self, obj):
        return carrier.CARRIER_NAME if obj.waybill_no else ''


def validate_unique_lines(lines):
    if not lines:
        raise serializers.ValidationError('품목을 1개 이상 입력해주세요.')
    ids = [line['item'].id for line in lines]
    if len(ids) != len(set(ids)):
        raise serializers.ValidationError('같은 품목이 중복되었습니다. 한 줄로 합쳐주세요.')
    return lines

class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    # 화면의 메뉴 표시에 쓸 권한을 서버 계정 정보로 알려줍니다.
    def validate(self, attrs):
        data = super().validate(attrs)
        data['role'] = '관리자' if self.user.is_staff else '현장작업자'
        return data

class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = '__all__'

    def get_subcategories(self, obj):
        serializer = self.__class__(obj.subcategories.all(), many=True)
        return serializer.data

class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    location_name = serializers.ReadOnlyField(source='location.full_code')
    location_barcode = serializers.ReadOnlyField(source='location.barcode')
    quantity = serializers.IntegerField(min_value=0, required=False)
    safety_stock = serializers.IntegerField(min_value=0, required=False)
    in_stock_serials = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = '__all__'
        read_only_fields = ['is_active']

    def get_in_stock_serials(self, obj):
        # 목록 조회에서는 미리 센 값을 쓰고, 등록·수정 응답에서는 직접 셉니다.
        count = getattr(obj, 'in_stock_serials', None)
        return count if count is not None else obj.serials.filter(status='재고보유').count()

    def validate(self, attrs):
        # 등록 시 따로 정하지 않으면 상품만 시리얼 관리, 구성품/부자재/사은품은 관리하지 않습니다.
        if not self.instance and 'serial_tracked' not in self.initial_data:
            attrs['serial_tracked'] = attrs.get('item_type', '상품') == '상품'
        return attrs

# 🌟 NEW: 신규 모델 Serializer 추가
class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(is_active=True))
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    serial_tracked = serializers.BooleanField(source='item.serial_tracked', read_only=True)
    location_name = serializers.ReadOnlyField(source='item.location.full_code')
    location_barcode = serializers.ReadOnlyField(source='item.location.barcode')
    order_quantity = serializers.IntegerField(min_value=1)
    received_serials = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderItem
        exclude = ['po']
        read_only_fields = ['received_quantity']

    def get_received_serials(self, obj):
        # 이 발주로 입고되어 아직 창고에 있는 시리얼 (입고 취소 대상)
        return [s.serial_number for s in obj.received_serials.all() if s.status == '재고보유']

class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.filter(is_active=True))
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = PurchaseOrderItemSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = '__all__'
        read_only_fields = ['po_number', 'status', 'order_date']

    def validate_items(self, lines):
        return validate_unique_lines(lines)

    def create(self, validated_data):
        lines = validated_data.pop('items')
        po = PurchaseOrder.objects.create(po_number=next_document_number(PurchaseOrder, 'po_number', 'PO'), **validated_data)
        PurchaseOrderItem.objects.bulk_create([PurchaseOrderItem(po=po, **line) for line in lines])
        return po

class SalesOrderItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(is_active=True))
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    location_name = serializers.ReadOnlyField(source='item.location.full_code')
    location_barcode = serializers.ReadOnlyField(source='item.location.barcode')
    current_quantity = serializers.IntegerField(source='item.quantity', read_only=True)
    serial_tracked = serializers.BooleanField(source='item.serial_tracked', read_only=True)
    quantity = serializers.IntegerField(min_value=1)
    scanned_serials = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrderItem
        exclude = ['order']
        read_only_fields = ['picked_quantity']

    def get_scanned_serials(self, obj):
        return [pick.serial.serial_number for pick in obj.picked_serials.all()]

class SalesOrderSerializer(CarrierInfoMixin, serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True)

    class Meta:
        model = SalesOrder
        fields = '__all__'
        read_only_fields = ['order_no', 'status', 'created_by', 'created_at', 'completed_at', *CARRIER_FIELDS]

    def validate(self, attrs):
        # 택배 연동을 쓰면 새 주문은 배송지가 있어야 운송장을 발급할 수 있습니다.
        return validate_shipping(attrs, required=not self.instance and carrier.enabled())

    def validate_items(self, lines):
        return validate_unique_lines(lines)

    def create(self, validated_data):
        lines = validated_data.pop('items')
        order = SalesOrder.objects.create(order_no=next_document_number(SalesOrder, 'order_no', 'ORD'), **validated_data)
        SalesOrderItem.objects.bulk_create([SalesOrderItem(order=order, **line) for line in lines])
        return order

class ReturnOrderSerializer(CarrierInfoMixin, serializers.ModelSerializer):
    serial_number = serializers.CharField(source='serial.serial_number', read_only=True)
    item_sku = serializers.CharField(source='serial.item.sku', read_only=True)
    item_name = serializers.CharField(source='serial.item.name', read_only=True)

    class Meta:
        model = ReturnOrder
        fields = '__all__'
        read_only_fields = ['return_no', 'status', 'created_by', 'created_at', 'completed_at', *CARRIER_FIELDS]

    def validate(self, attrs):
        return validate_shipping(attrs, required=False)

    def validate_serial(self, serial):
        if serial.status != '출고완료':
            raise serializers.ValidationError(f'출고완료 상태의 시리얼만 반품 등록할 수 있습니다. (현재: {serial.status})')
        if serial.returns.filter(status='회수대기').exists():
            raise serializers.ValidationError('이미 회수 대기 중인 시리얼입니다.')
        return serial

    def create(self, validated_data):
        # 회수지를 비워 두면 그 기기를 출고한 주문의 배송지에서 회수합니다.
        if not validated_data.get('address'):
            pick = (SalesOrderSerial.objects.filter(serial=validated_data['serial'], line__order__status='출고완료')
                    .select_related('line__order').order_by('-line__order__completed_at').first())
            if pick:
                order = pick.line.order
                for key in ('contact_name', 'contact_phone', 'zipcode', 'address', 'address_detail'):
                    validated_data[key] = validated_data.get(key) or getattr(order, key)
        return ReturnOrder.objects.create(return_no=next_document_number(ReturnOrder, 'return_no', 'RTN'), **validated_data)

class ItemSerialSerializer(serializers.ModelSerializer):
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = ItemSerial
        fields = '__all__'

class InventoryLogSerializer(serializers.ModelSerializer):
    ACTION_NAMES = {'IN': '입고', 'OUT': '출고', 'NEW': '신규등록', 'TRANSFER': '위치이동', 'DISABLE': '사용중지'}

    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    action_display = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = InventoryLog
        fields = '__all__'

    def get_action_display(self, obj):
        return self.ACTION_NAMES.get(obj.action, obj.action)

    def get_user_name(self, obj):
        return user_display(obj.user)
      
class WarehouseLocationSerializer(serializers.ModelSerializer):
    full_code = serializers.ReadOnlyField()
    barcode = serializers.ReadOnlyField()

    class Meta:
        model = WarehouseLocation
        fields = '__all__'

    def validate(self, attrs):
        # 같은 코드의 보관 위치가 두 개 생기지 않게 합니다. (수정할 때는 자기 자신 제외)
        get = lambda field: attrs.get(field, getattr(self.instance, field, None))
        zone, rack, tier = (get('zone') or '').strip(), (get('rack') or '').strip(), get('tier')
        cell = (get('cell') or '').strip()
        attrs.update({'zone': zone, 'rack': rack, 'cell': cell or None})
        same = WarehouseLocation.objects.filter(zone=zone, rack=rack, tier=tier).filter(Q(cell=cell) if cell else Q(cell__isnull=True) | Q(cell=''))
        if self.instance:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise serializers.ValidationError({'error': f'이미 등록된 보관 위치입니다: {same.first().full_code}'})
        return attrs