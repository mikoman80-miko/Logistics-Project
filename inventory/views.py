import csv
import logging
from datetime import datetime, time, timedelta
from io import StringIO

import requests # 🌟 NEW: 슬랙/디스코드 웹훅 알림용 모듈
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, DateField, DateTimeField, F, Func, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Item, ItemSerial, InventoryLog, WarehouseLocation, Category, Supplier, PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem, SalesOrderSerial, ReturnOrder
from .serializers import ItemSerializer, ItemSerialSerializer, InventoryLogSerializer, WarehouseLocationSerializer, CategorySerializer, SupplierSerializer, PurchaseOrderSerializer, SalesOrderSerializer, ReturnOrderSerializer

logger = logging.getLogger(__name__)

MAX_CSV_SIZE = 5 * 1024 * 1024
MAX_CODE_LENGTH = 100
SERIAL_STATUSES = {value for value, _ in ItemSerial.STATUS_CHOICES}
SERIAL_QUALITIES = {value for value, _ in ItemSerial.QUALITY_CHOICES}
IN_STOCK = '재고보유'
ITEM_TYPES = {value for value, _ in Item.TYPE_CHOICES}


# 🌟 NEW: 슬랙/디스코드 웹훅 전송 헬퍼 함수
def send_webhook_alert(message):
    # 재고 변경이 저장된 뒤에만 보내고, 주소가 없으면 보내지 않습니다.
    if not settings.ALERT_WEBHOOK_URL:
        return

    def post():
        try:
            requests.post(settings.ALERT_WEBHOOK_URL, json={"text": f"🚨 [WMS 긴급 알림] {message}"}, timeout=2)
        except requests.RequestException:
            logger.exception('Webhook 전송 실패')

    transaction.on_commit(post)


def error_response(message, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({'error': message}, status=http_status)


def to_int(value):
    # 숫자 또는 숫자 문자열만 정수로 인정합니다. (True, 1.5, 'abc'는 None)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def clean_code(value):
    return value.strip() if isinstance(value, str) else ''


def alert_if_low_stock(item):
    if item.quantity <= item.safety_stock:
        send_webhook_alert(f"재고 부족 경고! {item.name}의 현재 재고가 {item.quantity}개로 안전 재고({item.safety_stock}개) 이하입니다. 긴급 발주가 필요합니다.")


def change_serial_status(serial, new_status, quality=None, description=''):
    """시리얼 상태를 바꾸고, 재고보유 여부가 달라지면 재고 수량과 이력도 함께 맞춥니다. 실패 시 오류 문구를 반환합니다."""
    item = Item.objects.select_for_update().get(pk=serial.item_id)
    was_in_stock = serial.status == IN_STOCK
    is_in_stock = new_status == IN_STOCK

    if was_in_stock and not is_in_stock:
        if item.quantity < 1:
            return f'[{item.sku}] 재고가 0개라 상태를 변경할 수 없습니다.'
        item.quantity -= 1
        item.save(update_fields=['quantity'])
        InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-1, description=description[:200])
        alert_if_low_stock(item)
    elif is_in_stock and not was_in_stock:
        item.quantity += 1
        item.save(update_fields=['quantity'])
        InventoryLog.objects.create(item=item, action='IN', quantity_changed=1, description=description[:200])

    serial.status = new_status
    if quality:
        serial.quality = quality
    serial.save()
    return None


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def parse_date_param(value):
    if not value:
        return None
    try:
        parsed = parse_date(value)
    except ValueError:
        parsed = None
    if not parsed:
        raise ValidationError({'error': '날짜 형식이 올바르지 않습니다.'})
    return parsed


def csv_safe(value):
    # 엑셀이 수식으로 실행할 수 있는 글자는 앞에 작은따옴표를 붙입니다.
    text = '' if value is None else str(value)
    return f"'{text}" if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


class IsAdminRole(BasePermission):
    # 조회는 로그인 사용자 모두, 변경은 관리자 계정(is_staff)만 허용합니다.
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        return request.user.is_staff


class InventoryLedgerAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        category_id = request.GET.get('category')

        try:
            start_date = parse_date(start_date_str) if start_date_str else None
            end_date = parse_date(end_date_str) if end_date_str else None
        except ValueError:
            return error_response('날짜 형식이 올바르지 않습니다.')
        if (start_date_str and not start_date) or (end_date_str and not end_date):
            return error_response('날짜 형식이 올바르지 않습니다.')

        items = Item.objects.select_related('category', 'location')
        if category_id:
            if to_int(category_id) is None:
                return error_response('카테고리 값이 올바르지 않습니다.')
            items = items.filter(category_id=to_int(category_id))

        # 날짜 경계는 한국 시간 자정 기준입니다.
        period = Q()
        opening = Q(pk__isnull=True)
        if start_date:
            start_at = day_start(start_date)
            period &= Q(logs__timestamp__gte=start_at)
            opening = Q(logs__timestamp__lt=start_at)
        if end_date:
            end_before = day_start(end_date + timedelta(days=1))
            period &= Q(logs__timestamp__lt=end_before)

        items = items.annotate(
            opening_qty=Coalesce(Sum('logs__quantity_changed', filter=opening), 0),
            inbound_qty=Coalesce(Sum('logs__quantity_changed', filter=period & Q(logs__quantity_changed__gt=0)), 0),
            outbound_qty=Coalesce(Sum('logs__quantity_changed', filter=period & Q(logs__quantity_changed__lt=0)), 0),
        )

        ledger_data = []
        for item in items:
            outbound_qty = abs(item.outbound_qty)
            ledger_data.append({
                'sku': item.sku,
                'name': item.name,
                'category_name': item.category.name if item.category else '미분류',
                'location': item.location.full_code if item.location else '미지정',
                'opening_qty': item.opening_qty,
                'inbound_qty': item.inbound_qty,
                'outbound_qty': outbound_qty,
                'closing_qty': item.opening_qty + item.inbound_qty - outbound_qty,
                'current_qty': item.quantity
            })

        return Response(ledger_data, status=status.HTTP_200_OK)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(parent__isnull=True).order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRole]


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.select_related('category', 'location').filter(is_active=True)
    serializer_class = ItemSerializer
    permission_classes = [IsAdminRole]

    # 🌟 NEW: 재고 ABC 자동 분석 엔진 (최근 30일 출고량 기준)
    @action(detail=False, methods=['post'])
    def analyze_abc(self, request):
        thirty_days_ago = timezone.now() - timedelta(days=30)
        items = list(Item.objects.filter(is_active=True).annotate(
            usage=Coalesce(Sum('logs__quantity_changed', filter=Q(logs__action='OUT', logs__timestamp__gte=thirty_days_ago)), 0)
        ))
        for item in items:
            item.usage = abs(item.usage)
        total_outbound = sum(item.usage for item in items)

        # 출고량 기준 내림차순 정렬
        items.sort(key=lambda x: x.usage, reverse=True)

        cumulative = 0
        for item in items:
            if total_outbound == 0:
                item.abc_grade = 'C'
                continue
            cumulative += item.usage
            percent = cumulative / total_outbound
            if percent <= 0.7:
                item.abc_grade = 'A' # 상위 70% 매출 점유
            elif percent <= 0.9:
                item.abc_grade = 'B' # 중위 20%
            else:
                item.abc_grade = 'C' # 하위 10% (장기 체화 의심)
        Item.objects.bulk_update(items, ['abc_grade'])

        return Response({'message': 'ABC 재고 분석 및 등급 갱신이 완료되었습니다.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def transfer_location(self, request, pk=None):
        item = self.get_object()
        new_location_id = to_int(request.data.get('new_location_id'))
        if new_location_id is None:
            return error_response('이동할 목표 로케이션 ID를 입력해주세요.')
        new_location = WarehouseLocation.objects.filter(id=new_location_id).first()
        if not new_location:
            return error_response('존재하지 않는 로케이션 구역입니다.', status.HTTP_404_NOT_FOUND)

        old_location_str = item.location.full_code if item.location else '미지정'
        item.location = new_location
        item.save(update_fields=['location'])
        InventoryLog.objects.create(item=item, action='TRANSFER', quantity_changed=0, description=f"로케이션 이동: [{old_location_str}] ➔ [{new_location.full_code}]")
        return Response({'message': '로케이션 변경 완료', 'location': new_location.full_code})

    def create(self, request, *args, **kwargs):
        # 사용 중지된 SKU를 다시 등록하면 기존 상품과 이력을 이어서 사용합니다.
        stopped = Item.objects.select_for_update().filter(sku=clean_code(request.data.get('sku')), is_active=False).first()
        if not stopped:
            return super().create(request, *args, **kwargs)
        serializer = self.get_serializer(stopped, data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(is_active=True)
        InventoryLog.objects.create(item=item, action='NEW', quantity_changed=item.quantity, description='사용 중지 상품 재등록')
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # 입출고 이력을 보존하기 위해 실제로 지우지 않고 사용 중지합니다.
        item = Item.objects.select_for_update().get(pk=instance.pk)
        if item.quantity > 0:
            raise ValidationError({'error': f'재고가 {item.quantity}개 남아 있어 삭제할 수 없습니다. 재고를 0으로 만든 뒤 삭제해 주세요.'})
        if SalesOrderItem.objects.filter(item=item, order__status='출고대기').exists() or item.purchaseorderitem_set.filter(po__status__in=['발주대기', '입고중']).exists():
            raise ValidationError({'error': '진행 중인 주문 또는 발주서에 포함된 상품은 삭제할 수 없습니다.'})
        item.is_active = False
        item.save(update_fields=['is_active'])
        InventoryLog.objects.create(item=item, action='DISABLE', quantity_changed=0, description='상품 삭제(사용 중지)')

    def perform_create(self, serializer):
        item = serializer.save()
        InventoryLog.objects.create(item=item, action='NEW', quantity_changed=item.quantity)

    def perform_update(self, serializer):
        # 동시에 수정해도 수량 변화가 어긋나지 않도록 행을 잠급니다.
        old = Item.objects.select_for_update().get(pk=serializer.instance.pk)
        old_quantity = old.quantity
        new_tracked = serializer.validated_data.get('serial_tracked', old.serial_tracked)
        if new_tracked != old.serial_tracked:
            in_progress = (
                SalesOrderItem.objects.filter(item=old, order__status='출고대기').exists()
                or PurchaseOrderItem.objects.filter(item=old, po__status__in=['발주대기', '입고중']).exists()
            )
            if in_progress:
                raise ValidationError({'error': '진행 중인 주문 또는 발주서에 포함된 상품은 시리얼 관리 설정을 바꿀 수 없습니다.'})
        item = serializer.save()
        quantity_diff = item.quantity - old_quantity

        if quantity_diff != 0:
            action_type = 'IN' if quantity_diff > 0 else 'OUT'
            description = ""
            if 'physicalQty' in self.request.data: # 실사 조정일 경우
                description = "월말 재고 실사 조정"
                send_webhook_alert(f"재고 오차 조정 발생: {item.name} ({quantity_diff}개)")
            InventoryLog.objects.create(item=item, action=action_type, quantity_changed=quantity_diff, description=description)

            # 🌟 NEW: 안전 재고 이하로 떨어졌을 때 웹훅 알림 발송
            if quantity_diff < 0:
                alert_if_low_stock(item)

    @action(detail=True, methods=['post'])
    def adjust_stock(self, request, pk=None):
        # 화면에 표시된 옛 수량이 아니라 증감량을 받아, 최신 수량 기준으로 계산합니다.
        change = to_int(request.data.get('change'))
        if not change:
            return error_response('변경 수량을 정수로 입력해주세요.')
        item = self.get_object()
        item = Item.objects.select_for_update().get(pk=item.pk)
        if item.serial_tracked:
            return error_response('시리얼 관리 상품은 바코드 스캔이나 재고 조사로만 수량을 바꿀 수 있습니다.')
        if item.quantity + change < 0:
            return error_response(f'재고가 부족합니다. (현재 {item.quantity}개)')
        item.quantity += change
        item.save(update_fields=['quantity'])
        InventoryLog.objects.create(item=item, action='IN' if change > 0 else 'OUT', quantity_changed=change)
        if change < 0:
            alert_if_low_stock(item)
        return Response(self.get_serializer(item).data)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def scan_serial(self, request):
        sku = clean_code(request.data.get('sku'))
        serial_number = clean_code(request.data.get('serial_number'))
        scan_type = request.data.get('type')

        if not sku or not serial_number or len(serial_number) > MAX_CODE_LENGTH:
            return error_response('상품코드(SKU)와 시리얼 번호를 확인해주세요.')
        if scan_type not in ('in', 'out'):
            return error_response('스캔 구분은 입고 또는 출고여야 합니다.')

        item = Item.objects.select_for_update().filter(sku=sku, is_active=True).first()
        if not item:
            return error_response('등록되지 않은 상품코드(SKU)입니다.', status.HTTP_404_NOT_FOUND)
        if not item.serial_tracked:
            return error_response('시리얼을 관리하지 않는 상품입니다.')

        if scan_type == 'in':
            if ItemSerial.objects.filter(serial_number=serial_number).exists():
                return error_response('이미 창고에 등록된 시리얼 번호입니다.')
            try:
                with transaction.atomic():
                    ItemSerial.objects.create(item=item, serial_number=serial_number, status=IN_STOCK)
            except IntegrityError:
                return error_response('이미 창고에 등록된 시리얼 번호입니다.')
            item.quantity += 1
            item.save(update_fields=['quantity'])
            InventoryLog.objects.create(item=item, action='IN', quantity_changed=1)
            return Response({'message': f'S/N [{serial_number}] 입고 완료'})

        serial_obj = ItemSerial.objects.select_for_update().filter(serial_number=serial_number, item=item, status=IN_STOCK).first()
        if not serial_obj or item.quantity < 1:
            return error_response('재고가 없거나 이미 출고되었습니다.')
        serial_obj.status = '출고완료'
        serial_obj.save()
        item.quantity -= 1
        item.save(update_fields=['quantity'])
        InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-1)

        # 🌟 NEW: 출고 후 안전 재고 체크
        alert_if_low_stock(item)

        return Response({'message': f'S/N [{serial_number}] 출고 완료'})

    @action(detail=False, methods=['post'])
    def upload_csv(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return error_response('CSV 파일을 선택해주세요.')
        if file_obj.size > MAX_CSV_SIZE:
            return error_response('CSV 파일은 5MB 이하만 업로드할 수 있습니다.')

        raw = file_obj.read()
        try:
            # 엑셀에서 저장한 CSV는 UTF-8(BOM) 또는 CP949입니다.
            file_data = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                file_data = raw.decode('cp949')
            except UnicodeDecodeError:
                return error_response('CSV 파일 인코딩을 읽을 수 없습니다. UTF-8로 저장해 주세요.')

        reader = csv.DictReader(StringIO(file_data))
        if not reader.fieldnames or 'SKU' not in reader.fieldnames:
            return error_response('CSV 첫 줄에 SKU, 상품명, 초기수량 항목이 필요합니다.')

        success_count = 0
        skipped_count = 0
        try:
            for row in reader:
                sku = (row.get('SKU') or '').strip()
                name = (row.get('상품명') or '').strip()
                qty = to_int(row.get('초기수량') or '0')
                item_type = (row.get('구분') or '상품').strip()
                valid = item_type in ITEM_TYPES and sku and len(sku) <= MAX_CODE_LENGTH and name and len(name) <= 200 and qty is not None and qty >= 0
                if not valid or Item.objects.filter(sku=sku).exists():
                    skipped_count += 1
                    continue
                item = Item.objects.create(sku=sku, name=name, quantity=qty, item_type=item_type, serial_tracked=item_type == '상품')
                InventoryLog.objects.create(item=item, action='NEW', quantity_changed=qty)
                success_count += 1
        except csv.Error:
            transaction.set_rollback(True)
            return error_response('CSV 형식이 올바르지 않습니다.')

        message = f'총 {success_count}건 등록 완료'
        if skipped_count:
            message += f' (중복 또는 오류 {skipped_count}건 제외)'
        return Response({'message': message}, status=status.HTTP_200_OK)


# 🌟 NEW: 공급사(거래처) API
class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all().order_by('name')
    serializer_class = SupplierSerializer
    permission_classes = [IsAdminRole]


# 🌟 NEW: 발주서(PO) API 및 검수 입고 로직
class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__item').order_by('-order_date')
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAdminRole]
    # 입고 이력과 어긋나지 않도록 등록 후에는 수정, 삭제 대신 취소만 허용합니다.
    http_method_names = ['get', 'post', 'head', 'options']

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        po = PurchaseOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if po.status != '발주대기':
            return error_response(f'{po.status} 상태의 발주서는 취소할 수 없습니다.')
        po.status = '취소됨'
        po.save(update_fields=['status'])
        return Response({'message': f'발주서 {po.po_number} 취소 완료', 'status': po.status})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def receive_inbound(self, request, pk=None):
        sku = clean_code(request.data.get('sku'))
        serial_number = clean_code(request.data.get('serial_number'))
        receive_qty = to_int(request.data.get('quantity', 1))
        if not sku or receive_qty is None or receive_qty < 1:
            return error_response('입고할 상품(SKU)과 수량을 확인해주세요.')

        po = PurchaseOrder.objects.select_for_update().filter(pk=self.get_object().pk).first()
        if po.status in ('입고완료', '취소됨'):
            return error_response(f'{po.status} 상태의 발주서는 입고 처리할 수 없습니다.')

        po_item = po.items.select_for_update().filter(item__sku=sku).first()
        if not po_item:
            return error_response('해당 발주서에 존재하지 않는 상품(SKU)입니다.')

        master_item = Item.objects.select_for_update().get(pk=po_item.item_id)
        if master_item.serial_tracked:
            if not serial_number:
                return error_response('시리얼 관리 상품입니다. 시리얼을 스캔해주세요.')
            if receive_qty != 1:
                return error_response('시리얼 관리 상품은 1개씩 스캔해주세요.')
            if len(serial_number) > MAX_CODE_LENGTH or Item.objects.filter(sku=serial_number).exists():
                return error_response(f'[{serial_number}] 시리얼 번호가 아니라 상품코드입니다. 기기의 시리얼을 스캔해주세요.')
            if ItemSerial.objects.filter(serial_number=serial_number).exists():
                return error_response(f'[{serial_number}] 이미 등록된 시리얼 번호입니다.')
        elif serial_number:
            return error_response('시리얼을 관리하지 않는 상품입니다. 상품코드만 스캔해주세요.')

        remaining = po_item.order_quantity - po_item.received_quantity
        if receive_qty > remaining:
            return error_response(f'발주 수량을 초과합니다. (남은 수량 {remaining}개)')

        if serial_number:
            ItemSerial.objects.create(item=master_item, serial_number=serial_number, status=IN_STOCK)

        po_item.received_quantity += receive_qty
        po_item.save(update_fields=['received_quantity'])

        # 실제 마스터 재고 증가
        master_item.quantity += receive_qty
        master_item.save(update_fields=['quantity'])
        description = f"발주번호 {po.po_number} 정상 입고" + (f" S/N {serial_number}" if serial_number else '')
        InventoryLog.objects.create(item=master_item, action='IN', quantity_changed=receive_qty, description=description[:200])

        # 모든 품목 입고 완료 체크
        all_received = all(i.received_quantity >= i.order_quantity for i in po.items.all())
        po.status = '입고완료' if all_received else '입고중'
        po.save(update_fields=['status'])

        fresh = self.get_queryset().get(pk=po.pk)
        return Response({'message': f'발주 품목 [{sku}] 정상 입고 처리 완료', 'status': po.status, 'po': self.get_serializer(fresh).data})

class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.prefetch_related('items__item__location', 'items__picked_serials__serial').order_by('-created_at', '-id')
    serializer_class = SalesOrderSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        order_status = self.request.query_params.get('status')
        return queryset.filter(status=order_status) if order_status else queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 취소할 수 없습니다.')
        SalesOrderSerial.objects.filter(line__order=order).delete()
        order.status = '취소됨'
        order.save(update_fields=['status'])
        return Response({'message': f'주문 {order.order_no} 취소 완료', 'status': order.status})

    def _scan_result(self, order, message, **extra):
        fresh = self.get_queryset().get(pk=order.pk)
        return Response({'message': message, 'order': self.get_serializer(fresh).data, **extra})

    def _pick_serial(self, order, line, serial):
        if not line.item.serial_tracked:
            return error_response(f'[{line.item.sku}] 시리얼을 관리하지 않는 상품입니다. 상품코드를 스캔해주세요.')
        if serial.status != IN_STOCK:
            return error_response(f'[{serial.serial_number}] 출고할 수 없는 시리얼입니다. (현재: {serial.status})')
        if SalesOrderSerial.objects.filter(serial=serial, line__order__status='출고대기').exists():
            return error_response(f'[{serial.serial_number}] 이미 스캔한 시리얼입니다.')
        if line.picked_quantity >= line.quantity:
            return error_response(f'[{line.item.sku}] 지시 수량({line.quantity}개)을 모두 스캔했습니다.')
        SalesOrderSerial.objects.create(line=line, serial=serial)
        line.picked_quantity += 1
        line.save(update_fields=['picked_quantity'])
        return self._scan_result(order, f'{line.item.name} S/N {serial.serial_number} 확인')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def scan(self, request, pk=None):
        # 스캔 결과를 서버에 저장해, 새로고침하거나 다른 PC에서 이어서 작업해도 어긋나지 않습니다.
        code = clean_code(request.data.get('code'))
        current_sku = clean_code(request.data.get('sku'))
        quantity = to_int(request.data.get('quantity', 1))
        if not code or len(code) > MAX_CODE_LENGTH or quantity is None or quantity < 1:
            return error_response('바코드 또는 수량을 확인해주세요.')

        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 스캔할 수 없습니다.')
        lines = list(order.items.select_related('item').select_for_update())
        by_sku = {line.item.sku: line for line in lines}
        by_item = {line.item_id: line for line in lines}

        if code in by_sku:
            line = by_sku[code]
            if line.item.serial_tracked:
                return self._scan_result(order, f'{line.item.name}: 시리얼을 스캔해주세요.', need_serial=True, sku=code)
            if line.picked_quantity + quantity > line.quantity:
                return error_response(f'[{code}] 지시 수량을 초과합니다. (남은 수량 {line.quantity - line.picked_quantity}개)')
            if line.picked_quantity + quantity > line.item.quantity:
                return error_response(f'[{code}] 재고가 부족합니다. (현재 {line.item.quantity}개)')
            line.picked_quantity += quantity
            line.save(update_fields=['picked_quantity'])
            return self._scan_result(order, f'{line.item.name} {quantity}개 확인')

        serial = ItemSerial.objects.select_for_update().filter(serial_number=code).first()
        if serial:
            line = by_item.get(serial.item_id)
            if not line:
                return error_response(f'[{code}] 이 주문에 없는 상품의 시리얼입니다.')
            return self._pick_serial(order, line, serial)

        line = by_sku.get(current_sku)
        if not line:
            if Item.objects.filter(sku=code).exists():
                return error_response(f'[{code}] 이 주문에 없는 상품입니다. 오출고에 주의해주세요.')
            return error_response(f'[{code}] 등록되지 않은 바코드입니다. 상품코드를 먼저 스캔해주세요.')
        if Item.objects.filter(sku=code).exists():
            return error_response(f'[{code}] 시리얼이 아니라 다른 상품의 상품코드입니다.')
        if not line.item.serial_tracked:
            return error_response(f'[{line.item.sku}] 시리얼을 관리하지 않는 상품입니다.')

        # 시리얼 관리 전에 들어온 재고는 시리얼이 없으므로, 그 수량 안에서만 출고할 때 등록합니다.
        registered = line.item.serials.filter(status=IN_STOCK).count()
        if line.item.quantity <= registered:
            return error_response(f'[{code}] 재고에 등록되지 않은 시리얼입니다.')
        serial = ItemSerial.objects.create(item=line.item, serial_number=code, status=IN_STOCK)
        return self._pick_serial(order, line, serial)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def reset_line(self, request, pk=None):
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 변경할 수 없습니다.')
        line = order.items.select_for_update().filter(pk=to_int(request.data.get('line'))).first()
        if not line:
            return error_response('주문 품목을 찾을 수 없습니다.')
        line.picked_serials.all().delete()
        line.picked_quantity = 0
        line.save(update_fields=['picked_quantity'])
        return self._scan_result(order, '해당 품목의 스캔을 지웠습니다. 다시 스캔해주세요.')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def complete(self, request, pk=None):
        # 주문 하나를 한 번에 출고합니다. 하나라도 부족하면 전체를 처리하지 않습니다.
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 출고할 수 없습니다.')

        lines = list(order.items.prefetch_related('picked_serials__serial'))
        items = {i.id: i for i in Item.objects.select_for_update().filter(id__in=[line.item_id for line in lines]).order_by('id')}
        for line in lines:
            item = items[line.item_id]
            if line.picked_quantity < line.quantity:
                return error_response(f'[{item.sku}] 스캔이 끝나지 않았습니다. ({line.picked_quantity}/{line.quantity})')
            if item.quantity < line.quantity:
                return error_response(f'[{item.sku}] 재고가 부족합니다. (현재 {item.quantity}개, 요청 {line.quantity}개)')

        for line in lines:
            item = items[line.item_id]
            item.quantity -= line.quantity
            item.save(update_fields=['quantity'])
            serial_ids = [pick.serial_id for pick in line.picked_serials.all()]
            ItemSerial.objects.filter(id__in=serial_ids).update(status='출고완료', updated_at=timezone.now())
            InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-line.quantity, description=f'주문번호 {order.order_no} 출고')
            alert_if_low_stock(item)

        order.status = '출고완료'
        order.completed_at = timezone.now()
        order.save(update_fields=['status', 'completed_at'])
        return Response({'message': f'출고 완료 (총 {len(lines)}종 재고 차감)', 'status': order.status})

class ReturnOrderViewSet(viewsets.ModelViewSet):
    queryset = ReturnOrder.objects.select_related('serial__item').order_by('-created_at', '-id')
    serializer_class = ReturnOrderSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        return_status = self.request.query_params.get('status')
        return queryset.filter(status=return_status) if return_status else queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return_order = ReturnOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if return_order.status != '회수대기':
            return error_response(f'{return_order.status} 상태의 반품은 취소할 수 없습니다.')
        return_order.status = '취소됨'
        return_order.save(update_fields=['status'])
        return Response({'message': f'반품 {return_order.return_no} 취소 완료', 'status': return_order.status})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def complete(self, request, pk=None):
        new_status = request.data.get('status')
        quality = request.data.get('quality') or None
        detail = clean_code(request.data.get('detail'))

        if new_status not in (IN_STOCK, 'AS진행중', '불량폐기'):
            return error_response('올바르지 않은 회수 처리 상태입니다.')
        if quality and quality not in SERIAL_QUALITIES:
            return error_response('올바르지 않은 품질 등급입니다.')

        return_order = ReturnOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if return_order.status != '회수대기':
            return error_response(f'{return_order.status} 상태의 반품은 처리할 수 없습니다.')
        serial = ItemSerial.objects.select_for_update().get(pk=return_order.serial_id)
        if serial.status != '출고완료':
            return error_response(f'출고완료 상태의 시리얼만 회수할 수 있습니다. (현재: {serial.status})')

        description = f'반품 {return_order.return_no} 회수: {serial.serial_number}' + (f' ({detail})' if detail else '')
        error = change_serial_status(serial, new_status, quality, description)
        if error:
            return error_response(error)

        return_order.status = '회수완료'
        return_order.completed_at = timezone.now()
        return_order.save(update_fields=['status', 'completed_at'])
        return Response({'message': f'S/N [{serial.serial_number}] 회수 처리 완료', 'status': serial.status})


class LogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class InventoryLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InventoryLog.objects.select_related('item').order_by('-timestamp', '-id')
    serializer_class = InventoryLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LogPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        item_id = params.get('item')
        if item_id:
            if to_int(item_id) is None:
                raise ValidationError({'error': '상품 값이 올바르지 않습니다.'})
            queryset = queryset.filter(item_id=to_int(item_id))
        if params.get('action'):
            queryset = queryset.filter(action=params['action'])
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(item__sku__icontains=search) | Q(item__name__icontains=search))

        start_date = parse_date_param(params.get('start_date'))
        end_date = parse_date_param(params.get('end_date'))
        if start_date:
            queryset = queryset.filter(timestamp__gte=day_start(start_date))
        if end_date:
            queryset = queryset.filter(timestamp__lt=day_start(end_date + timedelta(days=1)))
        return queryset

    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def export(self, request):
        # 조건에 맞는 전체 이력을 메모리에 올리지 않고 조금씩 내려보냅니다.
        class Echo:
            def write(self, value):
                return value

        writer = csv.writer(Echo())
        action_names = InventoryLogSerializer.ACTION_NAMES

        def rows():
            yield '\ufeff'
            yield writer.writerow(['발생일시', '구분', 'SKU', '상품명', '변동수량', '비고'])
            for log in self.get_queryset().iterator(chunk_size=1000):
                yield writer.writerow([
                    timezone.localtime(log.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                    action_names.get(log.action, log.action),
                    csv_safe(log.item.sku),
                    csv_safe(log.item.name),
                    log.quantity_changed,
                    csv_safe(log.description),
                ])

        response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="inventory_logs.csv"'
        return response


class ItemSerialViewSet(viewsets.ModelViewSet):
    queryset = ItemSerial.objects.select_related('item').order_by('-updated_at')
    serializer_class = ItemSerialSerializer
    permission_classes = [IsAdminRole]

    @action(detail=False, methods=['patch'])
    def batch_update(self, request):
        ids = request.data.get('ids')
        new_status = request.data.get('status') or None
        new_quality = request.data.get('quality') or None

        if not isinstance(ids, list) or not ids or any(to_int(i) is None for i in ids):
            return error_response('변경할 시리얼을 선택해주세요.')
        if not new_status and not new_quality:
            return error_response('변경할 상태나 품질을 선택해주세요.')
        if new_status and new_status not in SERIAL_STATUSES:
            return error_response('올바르지 않은 물류 상태입니다.')
        if new_quality and new_quality not in SERIAL_QUALITIES:
            return error_response('올바르지 않은 품질 등급입니다.')

        serials = list(ItemSerial.objects.select_for_update().filter(id__in=[to_int(i) for i in ids]))
        for serial in serials:
            error = change_serial_status(serial, new_status or serial.status, new_quality, f'시리얼 상태 변경: {serial.serial_number}')
            if error:
                transaction.set_rollback(True)
                return error_response(error)
        return Response({'message': f'{len(serials)}건 변경 완료', 'count': len(serials)})


class WarehouseLocationViewSet(viewsets.ModelViewSet):
    queryset = WarehouseLocation.objects.all().order_by('zone', 'rack', 'tier')
    serializer_class = WarehouseLocationSerializer
    permission_classes = [IsAdminRole]


class TodayAPIView(APIView):
    # 첫 화면에 보여줄 오늘 할 일과 처음 설정 진행 상태
    permission_classes = [IsAuthenticated]

    def get(self, request):
        low_stock = Item.objects.filter(is_active=True, quantity__lte=F('safety_stock')).count()
        return Response({
            'orders': SalesOrder.objects.filter(status='출고대기').count(),
            'purchase_orders': PurchaseOrder.objects.filter(status__in=['발주대기', '입고중']).count(),
            'returns': ReturnOrder.objects.filter(status='회수대기').count(),
            'low_stock': low_stock,
            'setup': {
                'locations': WarehouseLocation.objects.exists(),
                'items': Item.objects.filter(is_active=True).exists(),
                'suppliers': Supplier.objects.exists(),
            },
        })


class DashboardAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # 일자는 한국 시간 기준으로 DB에서 묶습니다. (이력이 많아도 전체 행을 읽지 않습니다)
        offset = timezone.localtime().strftime('%z')
        local_day = Func(
            Func(F('timestamp'), Value('+00:00'), Value(f'{offset[:3]}:{offset[3:]}'), function='CONVERT_TZ', output_field=DateTimeField()),
            function='DATE', output_field=DateField(),
        )
        daily_logs = (
            InventoryLog.objects.filter(timestamp__gte=thirty_days_ago)
            .annotate(day=local_day).values('day')
            .annotate(
                inbound=Sum('quantity_changed', filter=Q(quantity_changed__gt=0)),
                outbound=Sum('quantity_changed', filter=Q(quantity_changed__lt=0)),
            ).order_by('day')
        )
        trend_data = [{'date': row['day'].strftime('%Y-%m-%d'), 'inbound': row['inbound'] or 0, 'outbound': abs(row['outbound'] or 0)} for row in daily_logs]

        occupancy_dict = {zone: 0 for zone in WarehouseLocation.objects.filter(is_active=True).values_list('zone', flat=True)}
        zone_totals = Item.objects.filter(is_active=True, location__is_active=True).values('location__zone').annotate(total=Sum('quantity'))
        for row in zone_totals:
            occupancy_dict[row['location__zone']] = row['total'] or 0
        occupancy_data = [{'zone': k, 'quantity': v} for k, v in occupancy_dict.items()]

        today_start = day_start(timezone.localdate())
        today_count = InventoryLog.objects.filter(timestamp__gte=today_start).count()
        top_moving = InventoryLog.objects.filter(timestamp__gte=thirty_days_ago).values('item__sku', 'item__name').annotate(movements=Count('id')).order_by('-movements')[:5]
        top_moving_data = [{'sku': row['item__sku'], 'name': row['item__name'], 'movements': row['movements']} for row in top_moving]

        return Response({'trend': trend_data, 'occupancy': occupancy_data, 'today_count': today_count, 'top_moving': top_moving_data}, status=status.HTTP_200_OK)
