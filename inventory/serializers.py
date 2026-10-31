from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
from .models import Item, ItemSerial, InventoryLog, WarehouseLocation, Category, Supplier, PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem, ReturnOrder

def next_document_number(model, field, prefix):
    # PO-20261031-0001 형식의 일자별 일련번호를 만듭니다. 동시에 등록해도 겹치지 않도록 잠급니다.
    day_prefix = f"{prefix}-{timezone.localdate():%Y%m%d}-"
    last = model.objects.select_for_update().filter(**{f'{field}__startswith': day_prefix}).order_by(f'-{field}').first()
    number = int(getattr(last, field).rsplit('-', 1)[1]) + 1 if last else 1
    return f"{day_prefix}{number:04d}"

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
    quantity = serializers.IntegerField(min_value=0, required=False)
    safety_stock = serializers.IntegerField(min_value=0, required=False)

    class Meta:
        model = Item
        fields = '__all__'
        read_only_fields = ['is_active']

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
    order_quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = PurchaseOrderItem
        exclude = ['po']
        read_only_fields = ['received_quantity']

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

class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True)

    class Meta:
        model = SalesOrder
        fields = '__all__'
        read_only_fields = ['order_no', 'status', 'created_by', 'created_at', 'completed_at']

    def validate_items(self, lines):
        return validate_unique_lines(lines)

    def create(self, validated_data):
        lines = validated_data.pop('items')
        order = SalesOrder.objects.create(order_no=next_document_number(SalesOrder, 'order_no', 'ORD'), **validated_data)
        SalesOrderItem.objects.bulk_create([SalesOrderItem(order=order, **line) for line in lines])
        return order

class ReturnOrderSerializer(serializers.ModelSerializer):
    serial_number = serializers.CharField(source='serial.serial_number', read_only=True)
    item_sku = serializers.CharField(source='serial.item.sku', read_only=True)
    item_name = serializers.CharField(source='serial.item.name', read_only=True)

    class Meta:
        model = ReturnOrder
        fields = '__all__'
        read_only_fields = ['return_no', 'status', 'created_by', 'created_at', 'completed_at']

    def validate_serial(self, serial):
        if serial.status != '출고완료':
            raise serializers.ValidationError(f'출고완료 상태의 시리얼만 반품 등록할 수 있습니다. (현재: {serial.status})')
        if serial.returns.filter(status='회수대기').exists():
            raise serializers.ValidationError('이미 회수 대기 중인 시리얼입니다.')
        return serial

    def create(self, validated_data):
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

    class Meta:
        model = InventoryLog
        fields = '__all__'

    def get_action_display(self, obj):
        return self.ACTION_NAMES.get(obj.action, obj.action)
      
class WarehouseLocationSerializer(serializers.ModelSerializer):
    full_code = serializers.ReadOnlyField()

    class Meta:
        model = WarehouseLocation
        fields = '__all__'