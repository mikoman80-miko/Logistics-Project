from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db.models import Q
from django.utils import timezone
import re

from . import carrier, due
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


def stock_rows(item):
    # 재고가 있는 위치 목록 (수량 많은 순, 기본 위치 먼저). 미리 불러온 stocks를 씁니다.
    rows = [st for st in item.stocks.all() if st.quantity > 0]
    rows.sort(key=lambda st: (st.location_id != item.location_id, -st.quantity))
    return [{'location': st.location_id, 'location_name': st.location.full_code, 'barcode': st.location.barcode, 'quantity': st.quantity} for st in rows]


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
    stocks = serializers.SerializerMethodField()
    unassigned = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = '__all__'
        read_only_fields = ['is_active']

    def get_stocks(self, obj):
        return stock_rows(obj)

    def get_unassigned(self, obj):
        # 위치에 기록되지 않은 재고 (예전 데이터나 기본 위치가 없는 상품)
        return max(0, obj.quantity - sum(st.quantity for st in obj.stocks.all()))

    def get_in_stock_serials(self, obj):
        # 목록 조회에서는 미리 센 값을 쓰고, 등록·수정 응답에서는 직접 셉니다.
        count = getattr(obj, 'in_stock_serials', None)
        return count if count is not None else obj.serials.filter(status='재고보유').count()

    def validate(self, attrs):
        # 등록 시 따로 정하지 않으면 상품만 시리얼 관리, 구성품/부자재/사은품은 관리하지 않습니다.
        if not self.instance and 'serial_tracked' not in self.initial_data:
            attrs['serial_tracked'] = attrs.get('item_type', '상품') == '상품'
        pick_min = attrs.get('pick_min', getattr(self.instance, 'pick_min', 0))
        pick_max = attrs.get('pick_max', getattr(self.instance, 'pick_max', 0))
        if pick_min and pick_max <= pick_min:
            raise serializers.ValidationError({'pick_max': '보충 최대 수량은 최소 수량보다 커야 합니다.'})
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
    stock_locations = serializers.SerializerMethodField()
    current_quantity = serializers.IntegerField(source='item.quantity', read_only=True)
    serial_tracked = serializers.BooleanField(source='item.serial_tracked', read_only=True)
    quantity = serializers.IntegerField(min_value=1)
    scanned_serials = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrderItem
        exclude = ['order']
        read_only_fields = ['picked_quantity']

    def get_stock_locations(self, obj):
        # 현장 출고 안내: 이 상품이 실제로 있는 위치들 (첫 번째로 안내합니다)
        return stock_rows(obj.item)

    def get_scanned_serials(self, obj):
        return [pick.serial.serial_number for pick in obj.picked_serials.all()]

class SalesOrderSerializer(CarrierInfoMixin, serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True)
    carrier_events = serializers.SerializerMethodField()
    bundle_orders = serializers.SerializerMethodField()
    split_from_no = serializers.CharField(source='split_from.order_no', read_only=True, default='')
    due_at = serializers.SerializerMethodField()
    due_status = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrder
        fields = '__all__'
        read_only_fields = ['order_no', 'status', 'created_by', 'created_at', 'completed_at', 'bundle_parent', 'split_from', *CARRIER_FIELDS]

    def get_carrier_events(self, obj):
        # 묶인 주문은 대표 주문의 배송 이력을 보여줍니다.
        return CarrierEventSerializer((obj.bundle_parent or obj).carrier_events.all(), many=True).data

    def get_due_at(self, obj):
        return timezone.localtime(due.due_at(obj.created_at)).isoformat() if obj.created_at else None

    def get_due_status(self, obj):
        return due.due_status(obj) if obj.created_at else ''

    def get_bundle_orders(self, obj):
        # 같은 상자로 나가는 주문번호 (대표 주문이 먼저). 묶음이 아니면 빈 목록
        master = obj.bundle_parent or obj
        members = list(master.bundle_members.all())
        return [master.order_no, *[m.order_no for m in members]] if members else []

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
    serial_number = serializers.CharField(source='serial.serial_number', read_only=True, default='')
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(is_active=True), required=False)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    serial_tracked = serializers.BooleanField(source='item.serial_tracked', read_only=True)
    order_no = serializers.CharField(source='sales_order.order_no', read_only=True, default='')
    quantity = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        model = ReturnOrder
        fields = '__all__'
        read_only_fields = ['return_no', 'status', 'result', 'created_by', 'created_at', 'completed_at', *CARRIER_FIELDS]

    def validate(self, attrs):
        attrs = validate_shipping(attrs, required=False)
        if self.instance:
            return attrs
        serial, item, order = attrs.get('serial'), attrs.get('item'), attrs.get('sales_order')
        if serial:
            # 시리얼 반품: 상품과 수량은 시리얼에서 정합니다.
            attrs.update(item=serial.item, quantity=1)
            return attrs
        if not item:
            raise serializers.ValidationError({'item': '반품할 시리얼 또는 상품을 선택해주세요.'})
        if item.serial_tracked:
            raise serializers.ValidationError({'item': '시리얼 관리 상품은 시리얼을 골라 반품 등록해주세요.'})
        quantity = attrs.setdefault('quantity', 1)
        if order:
            # 원래 주문을 고르면 그 주문에서 나간 수량까지만 반품할 수 있습니다.
            if order.status != '출고완료':
                raise serializers.ValidationError({'sales_order': '출고완료된 주문만 고를 수 있습니다.'})
            line = order.items.filter(item=item).first()
            if not line:
                raise serializers.ValidationError({'sales_order': f'이 주문에는 [{item.sku}] 상품이 없습니다.'})
            returned = sum(order.returns.filter(item=item).exclude(status='취소됨').values_list('quantity', flat=True))
            if quantity > line.quantity - returned:
                raise serializers.ValidationError({'quantity': f'이 주문에서 더 반품할 수 있는 수량은 {line.quantity - returned}개입니다.'})
        return attrs

    def validate_serial(self, serial):
        if serial.status != '출고완료':
            raise serializers.ValidationError(f'출고완료 상태의 시리얼만 반품 등록할 수 있습니다. (현재: {serial.status})')
        if serial.returns.filter(status='회수대기').exists():
            raise serializers.ValidationError('이미 회수 대기 중인 시리얼입니다.')
        return serial

    def create(self, validated_data):
        # 회수지를 비워 두면 원래 출고한 주문의 배송지에서 회수합니다. (시리얼은 그 기기를 출고한 주문)
        if validated_data.get('serial') and not validated_data.get('sales_order'):
            pick = (SalesOrderSerial.objects.filter(serial=validated_data['serial'], line__order__status='출고완료')
                    .select_related('line__order').order_by('-line__order__completed_at').first())
            if pick:
                validated_data['sales_order'] = pick.line.order
        order = validated_data.get('sales_order')
        if order and not validated_data.get('address'):
            for key in ('contact_name', 'contact_phone', 'zipcode', 'address', 'address_detail'):
                validated_data[key] = validated_data.get(key) or getattr(order, key)
        return ReturnOrder.objects.create(return_no=next_document_number(ReturnOrder, 'return_no', 'RTN'), **validated_data)

class ItemSerialSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.full_code', read_only=True, default='')
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = ItemSerial
        fields = '__all__'

class InventoryLogSerializer(serializers.ModelSerializer):
    ACTION_NAMES = {'IN': '입고', 'OUT': '출고', 'NEW': '신규등록', 'TRANSFER': '위치이동', 'DISABLE': '사용중지', 'RETURN': '반품회수'}

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

class UserSerializer(serializers.ModelSerializer):
    # 사용자 관리 화면용. role은 '관리자'(is_staff) 또는 '현장작업자'입니다.
    role = serializers.ChoiceField(choices=['관리자', '현장작업자'], required=False)
    password = serializers.CharField(write_only=True, required=False)
    name = serializers.CharField(source='first_name', required=False, allow_blank=True, max_length=150)
    has_badge = serializers.SerializerMethodField()

    def get_has_badge(self, obj):
        return hasattr(obj, 'badge')

    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'role', 'is_active', 'is_superuser', 'last_login', 'date_joined', 'password', 'has_badge']
        read_only_fields = ['is_superuser', 'last_login', 'date_joined']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['role'] = '관리자' if instance.is_staff else '현장작업자'
        return data

    def validate_username(self, value):
        if self.instance and value != self.instance.username:
            raise serializers.ValidationError('사원번호는 바꿀 수 없습니다.')
        return value

    def validate(self, attrs):
        if 'role' in attrs:
            attrs['is_staff'] = attrs.pop('role') == '관리자'
        if not self.instance:
            password = attrs.get('password') or ''
            if not password:
                raise serializers.ValidationError({'password': '첫 비밀번호를 입력해주세요.'})
            try:
                validate_password(password, User(username=attrs.get('username', ''), first_name=attrs.get('first_name', '')))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop('password', None)  # 비밀번호는 reset_password로만 바꿉니다.
        return super().update(instance, validated_data)
