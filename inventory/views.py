import csv
import logging
import math
import secrets
from collections import Counter
import re
from datetime import datetime, time, timedelta
from time import sleep
from io import StringIO

import requests # 🌟 NEW: 슬랙/디스코드 웹훅 알림용 모듈
from django.conf import settings
from django.contrib.auth.models import User, update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Count, DateField, DateTimeField, F, Func, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from . import audit, carrier, due, stock
from .audit import AuditMixin
from .carrier import CarrierError
from .models import DailyClose, MasterChange, WorkerBadge, Item, ItemSerial, ItemStock, InventoryLog, WarehouseLocation, Category, Supplier, PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem, SalesOrderSerial, ReturnOrder, CarrierEvent
from .serializers import next_document_number, user_display, UserSerializer, ItemSerializer, ItemSerialSerializer, InventoryLogSerializer, WarehouseLocationSerializer, CategorySerializer, SupplierSerializer, PurchaseOrderSerializer, SalesOrderSerializer, ReturnOrderSerializer

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


# ---------- 택배 연동 ----------
SHIPPING_FIELDS = ['contact_name', 'contact_phone', 'zipcode', 'address', 'address_detail']
SHIPPING_LABELS = {'contact_name': '받는 분', 'contact_phone': '연락처', 'zipcode': '우편번호', 'address': '주소', 'address_detail': '상세주소'}


def save_carrier_event(record, event):
    """택배사가 알려준 단계를 저장합니다. 이미 받은 알림이면 False."""
    occurred_at = carrier.parse_time(event.get('occurred_at'))
    if not event.get('event_id') or not event.get('status') or not occurred_at:
        return False
    owner = {'sales_order': record} if isinstance(record, SalesOrder) else {'return_order': record}
    _, created = CarrierEvent.objects.get_or_create(event_id=str(event['event_id'])[:64], defaults={
        **owner, 'waybill_no': record.waybill_no, 'status': str(event['status'])[:20],
        'location': str(event.get('location') or '')[:100], 'occurred_at': occurred_at})
    return created


def apply_carrier_data(record, data):
    """택배사 응답(단계 이력)을 반영합니다. 알림이 늦게 와도 가장 최근 단계를 상태로 씁니다."""
    for event in data.get('events', []):
        save_carrier_event(record, event)
    latest = record.carrier_events.order_by('-occurred_at', '-id').first()
    record.carrier_status = latest.status if latest else data.get('status', record.carrier_status)
    record.carrier_error = ''
    record.save(update_fields=['carrier_status', 'carrier_error'])
    if isinstance(record, SalesOrder):
        SalesOrder.objects.filter(bundle_parent=record).update(carrier_status=record.carrier_status, carrier_error='')


def request_carrier(record, create):
    """운송장(배송) 또는 회수 요청을 보냅니다. 실패해도 등록은 유지하고 사유를 남깁니다."""
    if not carrier.enabled() or record.waybill_no:
        return
    if not record.has_address:
        record.carrier_error = '주소가 없어 택배사에 요청하지 않았습니다.'
        record.save(update_fields=['carrier_error'])
        return
    try:
        data = create(record)
    except CarrierError as exc:
        record.carrier_error = str(exc)[:200]
        record.save(update_fields=['carrier_error'])
        return
    record.waybill_no = data['waybill_no']
    record.save(update_fields=['waybill_no'])
    apply_carrier_data(record, data)


def cancel_carrier(record, pickup):
    """등록을 취소할 때 택배 요청도 취소합니다. 이미 기사가 가져갔으면 오류 문구를 반환합니다."""
    if not carrier.enabled() or not record.waybill_no or record.carrier_status == '취소':
        return None
    try:
        apply_carrier_data(record, carrier.cancel(record.waybill_no, pickup=pickup))
    except CarrierError as exc:
        return f'택배사 취소 실패: {exc}'
    return None


def split_backorder(order, user):
    """부분 출고 준비: 스캔하지 못한 수량을 새 주문으로 옮기고, 원래 주문은 스캔한 수량만 남깁니다. (새 주문, 오류 문구)"""
    if order.bundle_parent_id or order.bundle_members.exists():
        return None, '묶음배송 주문은 부분 출고할 수 없습니다. 묶음을 해제한 뒤 진행하세요.'
    lines = list(order.items.select_for_update())
    if not any(line.picked_quantity > 0 for line in lines):
        return None, '스캔한 품목이 없습니다. 하나 이상 스캔한 뒤 부분 출고하세요.'
    short = [line for line in lines if line.picked_quantity < line.quantity]
    if not short:
        return None, None  # 모두 스캔했으면 보통 출고와 같습니다.

    backorder = SalesOrder.objects.create(
        order_no=next_document_number(SalesOrder, 'order_no', 'ORD'), customer=order.customer, split_from=order, created_by=user, is_urgent=order.is_urgent,
        note=f'{order.order_no}의 남은 수량' + (f' / {order.note}' if order.note else ''),
        **{key: getattr(order, key) for key in SHIPPING_FIELDS})
    SalesOrderItem.objects.bulk_create([SalesOrderItem(order=backorder, item_id=line.item_id, quantity=line.quantity - line.picked_quantity) for line in short])
    for line in short:
        if line.picked_quantity == 0:
            line.delete()
        else:
            line.quantity = line.picked_quantity
            line.save(update_fields=['quantity'])
    return backorder, None


def bundle_shipped(master):
    # 묶음(대표 + 묶인 주문) 중 취소되지 않은 주문이 모두 출고되었는지
    statuses = SalesOrder.objects.filter(Q(pk=master.pk) | Q(bundle_parent=master)).exclude(status='취소됨').values_list('status', flat=True)
    return all(value == '출고완료' for value in statuses)


def update_shipping_address(record, serializer_class, data):
    # 주소만 부분 수정합니다. 형식 검사는 각 시리얼라이저 규칙을 따릅니다.
    fields = {key: data[key] for key in SHIPPING_FIELDS if key in data}
    if fields:
        serializer = serializer_class(record, data=fields, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()


class PageOnRequest(PageNumberPagination):
    """page를 보낸 요청만 나눠서 돌려줍니다. ({count, results}) 현장 화면처럼 전체 목록(배열)을 쓰는 곳은 그대로 둡니다."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if 'page' not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


def filter_documents(queryset, params, date_field, search_fields, date_only=False):
    """발주·주문·반품 목록 공통 조건: 상태(쉼표로 여러 개), 검색어(q), 등록일 기간(start_date ~ end_date)."""
    statuses = [s for s in (params.get('status') or '').split(',') if s]
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    keyword = (params.get('q') or '').strip()
    if keyword:
        condition = Q()
        for field in search_fields:
            condition |= Q(**{f'{field}__icontains': keyword})
        queryset = queryset.filter(condition).distinct()
    start, end = parse_date_param(params.get('start_date')), parse_date_param(params.get('end_date'))
    if start and end and start > end:
        raise ValidationError({'error': '시작일이 종료일보다 늦습니다.'})
    if start:
        queryset = queryset.filter(**{f'{date_field}__gte': start if date_only else day_start(start)})
    if end:
        queryset = queryset.filter(**({f'{date_field}__lte': end} if date_only else {f'{date_field}__lt': day_start(end + timedelta(days=1))}))
    return queryset


def address_key(record):
    # 묶음배송 비교용: 공백과 전화번호 구분 기호를 무시합니다.
    clean = lambda value: ' '.join((value or '').split())
    return (clean(record.contact_name), re.sub(r'\D', '', record.contact_phone or ''), clean(record.zipcode),
            clean(record.address), clean(record.address_detail))


def update_order(order, changes, lines=None):
    """출고대기 주문을 고칩니다. 배송지가 바뀌면 기존 송장을 취소하고 새로 발급합니다. (오류 문구, 메시지)를 돌려줍니다."""
    old_address = [getattr(order, key) for key in SHIPPING_FIELDS]
    for key, value in changes.items():
        setattr(order, key, value)
    address_changed = old_address != [getattr(order, key) for key in SHIPPING_FIELDS]
    if carrier.enabled() and not order.has_address:
        return '택배 발송에 필요한 이름, 연락처, 우편번호, 주소를 모두 입력해주세요.', ''
    if address_changed and (order.bundle_parent_id or order.bundle_members.exists()):
        return '묶음배송 주문입니다. 묶음을 해제한 뒤 배송지를 바꿔 주세요.', ''

    if address_changed and order.waybill_no:
        error = cancel_carrier(order, pickup=False)
        if error:
            return f'{error} 배송지를 바꾸려면 기존 송장을 먼저 취소해야 합니다.', ''
        order.carrier_events.all().delete()  # 취소한 송장의 이력은 새 송장과 섞이지 않게 지웁니다.
        order.waybill_no, order.carrier_status = '', ''
    order.save()
    if lines is not None:
        order.items.all().delete()
        SalesOrderItem.objects.bulk_create([SalesOrderItem(order=order, **line) for line in lines])
    if not order.bundle_parent_id:
        request_carrier(order, carrier.create_shipment)

    message = f'주문 {order.order_no} 수정 완료'
    if address_changed and order.waybill_no:
        message += f' (새 운송장 {order.waybill_no})'
    elif order.carrier_error:
        message += f'. 운송장 발급 실패: {order.carrier_error}'
    return None, message


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
    """안전 재고 이하로 처음 내려갈 때 한 번만 알립니다. 다시 안전 재고 위로 채워지면(Item.save) 다음에 또 알립니다."""
    if item.quantity > item.safety_stock or item.low_stock_alerted:
        return
    incoming = (PurchaseOrderItem.objects.filter(item=item, po__status__in=['발주대기', '입고중'])
                .aggregate(n=Coalesce(Sum(F('order_quantity') - F('received_quantity')), 0))['n'])
    plan = f'입고 예정 {incoming}개' if incoming > 0 else '진행 중인 발주 없음 → 발주 관리의 [발주 제안]에서 발주하세요'
    send_webhook_alert(f"[재고 부족] {item.name}({item.sku}) 재고 {item.quantity}개 ≤ 안전 재고 {item.safety_stock}개 · {plan}")
    Item.objects.filter(pk=item.pk).update(low_stock_alerted=True)
    item.low_stock_alerted = True


def change_serial_status(serial, new_status, quality=None, description='', user=None, work='조정', reference=''):
    """시리얼 상태를 바꾸고, 재고보유 여부가 달라지면 재고 수량과 이력도 함께 맞춥니다. 실패 시 오류 문구를 반환합니다."""
    item = Item.objects.select_for_update().get(pk=serial.item_id)
    was_in_stock = serial.status == IN_STOCK
    is_in_stock = new_status == IN_STOCK

    if was_in_stock and not is_in_stock:
        if item.quantity < 1:
            return f'[{item.sku}] 재고가 0개라 상태를 변경할 수 없습니다.'
        item.quantity -= 1
        item.save(update_fields=['quantity'])
        stock.remove(item, 1, prefer=serial.location)
        serial.location = None  # 선반에서 빠진 기기
        InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-1, description=description[:200], user=user, work=work, reference=reference)
        alert_if_low_stock(item)
    elif is_in_stock and not was_in_stock:
        item.quantity += 1
        item.save(update_fields=['quantity'])
        serial.location = stock.add(item, 1)  # 기본 위치로 되돌립니다.
        InventoryLog.objects.create(item=item, action='IN', quantity_changed=1, description=description[:200], user=user, work=work, reference=reference)

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


class CategoryViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Category.objects.filter(parent__isnull=True).order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRole]


class ItemViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Item.objects.select_related('category', 'location').prefetch_related('stocks__location').filter(is_active=True).annotate(
        in_stock_serials=Count('serials', filter=Q(serials__status=IN_STOCK)))
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

    @action(detail=False, methods=['post'])
    def audit_scan(self, request):
        """스캔 재고 조사: 한 보관 위치에서 스캔한 바코드를 전산과 대조합니다. apply가 참이면 결과를 반영합니다.
        수량 상품은 스캔한 개수로 수량을 맞추고, 시리얼 상품은 찾지 못한 기기를 분실 처리합니다(mark_missing)."""
        location = WarehouseLocation.objects.filter(pk=to_int(request.data.get('location'))).first()
        if not location:
            return error_response('조사할 보관 위치를 고르세요.')
        codes = [clean_code(code) for code in (request.data.get('codes') or []) if clean_code(code)]
        if not isinstance(request.data.get('codes'), list) or len(codes) > 5000:
            return error_response('스캔한 바코드 목록이 올바르지 않습니다. (한 번에 5,000개까지)')
        apply, mark_missing = request.data.get('apply') is True, request.data.get('mark_missing') is True

        items_by_sku = {item.sku: item for item in Item.objects.filter(is_active=True, sku__in=set(codes))}
        serials_by_no = {s.serial_number: s for s in ItemSerial.objects.select_related('item').filter(serial_number__in=set(codes))}
        counted, seen_serials, unknown, warnings = Counter(), {}, [], []
        for code in codes:
            if code in serials_by_no:
                serial = serials_by_no[code]
                if code in seen_serials:
                    continue  # 같은 기기를 두 번 스캔해도 한 번만 셉니다.
                seen_serials[code] = serial
                counted[serial.item_id] += 1
            elif code in items_by_sku:
                item = items_by_sku[code]
                if item.serial_tracked:
                    warnings.append(f'[{code}] 시리얼 관리 상품은 상품코드가 아니라 기기의 시리얼을 스캔하세요.')
                else:
                    counted[item.id] += 1
            else:
                unknown.append(code)

        # 이 위치에 재고가 있거나 기본 위치인 상품, 그리고 스캔한 상품을 대조합니다.
        here = Q(location=location) | Q(serials__location=location, serials__status=IN_STOCK) | Q(stocks__location=location, stocks__quantity__gt=0)
        item_ids = set(Item.objects.filter(here, is_active=True).values_list('id', flat=True)) | set(counted)
        rows = []
        for item in Item.objects.select_for_update().filter(pk__in=item_ids).select_related('location').order_by('sku'):
            row = {'item': item.id, 'sku': item.sku, 'name': item.name, 'serial_tracked': item.serial_tracked,
                   'system': stock.at(item, location), 'counted': counted[item.id], 'missing': [], 'unexpected': [], 'moved': [],
                   'location_name': item.location.full_code if item.location else '',
                   # 이 위치에 기록이 없던 수량 상품: 반영하면 이 위치 재고로 더해집니다.
                   'new_here': not item.serial_tracked and item.location_id != location.id and not stock.at(item, location)}
            if item.serial_tracked:
                in_stock = list(item.serials.filter(status=IN_STOCK).select_related('location').order_by('serial_number'))
                here_serials = [s for s in in_stock if s.location_id == location.id]
                scanned = {no: s for no, s in seen_serials.items() if s.item_id == item.id}
                row['system'] = len(here_serials)
                row['missing'] = [s.serial_number for s in here_serials if s.serial_number not in scanned]
                row['unexpected'] = [f'{no} ({s.status})' for no, s in scanned.items() if s.status != IN_STOCK]
                row['moved'] = [f'{no} ({s.location.full_code if s.location else "위치 미지정"})' for no, s in scanned.items()
                                if s.status == IN_STOCK and s.location_id != location.id]
            rows.append(row)

        applied = []
        if apply:
            note = f'스캔 재고 조사 ({location.full_code})'
            for row in rows:
                item = Item.objects.select_for_update().get(pk=row['item'])
                if not item.serial_tracked:
                    # 위치를 모르던(미지정) 재고를 여기서 찾은 것이면 총재고는 그대로 두고 이 위치로 옮깁니다.
                    unknown_before = stock.unassigned(item)
                    located = stock.set_at(item, location, row['counted'])
                    diff = located - min(max(located, 0), unknown_before)
                    if located:
                        item.quantity = max(0, item.quantity + diff)
                        item.save(update_fields=['quantity'])
                        if diff:
                            InventoryLog.objects.create(item=item, action='IN' if diff > 0 else 'OUT', quantity_changed=diff, description=note, user=request.user, work='조정')
                        if diff < 0:
                            alert_if_low_stock(item)
                        applied.append(f'[{item.sku}] 이 위치 {located:+d}' + (f', 총재고 {diff:+d}' if diff != located else ''))
                    continue
                # 다른 위치로 기록된 기기가 여기 있으면 위치를 바로잡습니다.
                for no, serial in seen_serials.items():
                    if serial.item_id == item.id and serial.status == IN_STOCK and serial.location_id != location.id:
                        stock.relocate_one(item, serial.location, location)
                        ItemSerial.objects.filter(pk=serial.pk).update(location=location)
                        applied.append(f'[{no}] 위치 정정')
                if mark_missing:
                    for serial in ItemSerial.objects.select_for_update().filter(item=item, serial_number__in=row['missing'], status=IN_STOCK):
                        error = change_serial_status(serial, '분실', None, f'{note}: 분실 {serial.serial_number}', request.user)
                        if error:
                            return error_response(error)
                        applied.append(f'[{serial.serial_number}] 분실 처리')
        # 반영했거나 전부 일치하면 이 위치의 조사를 마친 것으로 기록합니다. (순환 조사 목록에서 빠짐)
        matched = not unknown and all(row['counted'] == row['system'] and not row['missing'] and not row['unexpected'] for row in rows)
        if apply or (matched and codes):
            WarehouseLocation.objects.filter(pk=location.pk).update(last_counted_at=timezone.now())
        return Response({'location': location.full_code, 'rows': rows, 'unknown': unknown, 'warnings': warnings, 'applied': applied,
                         'counted': bool(apply or (matched and codes))})

    @action(detail=True, methods=['post'])
    def transfer_location(self, request, pk=None):
        item = self.get_object()
        new_location_id = to_int(request.data.get('new_location_id'))
        if new_location_id is None:
            return error_response('이동할 보관 위치를 선택해주세요.')
        new_location = WarehouseLocation.objects.filter(id=new_location_id).first()
        if not new_location:
            return error_response('존재하지 않는 보관 위치입니다.', status.HTTP_404_NOT_FOUND)

        item = Item.objects.select_for_update().get(pk=item.pk)
        old_location = item.location
        before = audit.snapshot(item)
        moved = stock.at(item, old_location) if old_location else stock.unassigned(item)
        if moved:
            stock.move(item, moved, old_location, new_location)
        item.serials.filter(status=IN_STOCK, location=old_location).update(location=new_location)
        item.location = new_location
        item.save(update_fields=['location'])
        audit.record(request.user, item, '수정', before)
        old_location_str = old_location.full_code if old_location else '미지정'
        InventoryLog.objects.create(item=item, action='TRANSFER', quantity_changed=0, description=f"보관 위치 이동: [{old_location_str}] ➔ [{new_location.full_code}] {moved}개", user=request.user, work='이동')
        return Response({'message': '보관 위치 이동 완료', 'location': new_location.full_code})

    @action(detail=True, methods=['post'])
    def move_stock(self, request, pk=None):
        """위치 간 재고 이동. 수량 상품은 수량으로, 시리얼 상품은 옮길 시리얼 번호로 옮깁니다. from이 비어 있으면 '위치 미지정' 재고에서 옮깁니다."""
        item = Item.objects.select_for_update().get(pk=self.get_object().pk)
        target = WarehouseLocation.objects.filter(pk=to_int(request.data.get('to')), is_active=True).first()
        return self._move(request, item, target, '재고 이동')

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def replenishment(self, request):
        # 기본 위치(꺼내는 자리)를 채워야 하는 상품 목록. 현장 [위치 보충] 화면에서 씁니다.
        return Response(replenishment_tasks())

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def replenish(self, request, pk=None):
        # 현장작업자도 할 수 있는 이동: 다른 위치의 재고를 이 상품의 기본 위치로만 옮깁니다.
        item = Item.objects.select_for_update().get(pk=self.get_object().pk)
        if not item.location_id:
            return error_response(f'[{item.sku}] 기본 위치가 없어 보충할 수 없습니다.')
        if not request.data.get('from'):
            return error_response('가져올 위치를 고르세요.')
        return self._move(request, item, item.location, '위치 보충')

    def _move(self, request, item, target, label):
        source = WarehouseLocation.objects.filter(pk=to_int(request.data.get('from'))).first() if request.data.get('from') else None
        if not target:
            return error_response('옮길 보관 위치를 고르세요.')
        if source == target:
            return error_response('같은 위치로는 옮길 수 없습니다.')
        if item.serial_tracked:
            numbers = [clean_code(n) for n in (request.data.get('serials') or []) if clean_code(n)]
            if not numbers:
                return error_response('옮길 기기의 시리얼을 입력하세요.')
            serials = list(item.serials.select_for_update().filter(serial_number__in=numbers, status=IN_STOCK, location=source))
            missing = sorted(set(numbers) - {s.serial_number for s in serials})
            if missing:
                where = source.full_code if source else '위치 미지정'
                return error_response(f'{where}에 있는 재고보유 기기가 아닙니다: {", ".join(missing)}')
            quantity = len(serials)
        else:
            quantity = to_int(request.data.get('quantity'))
            if not quantity or quantity < 1:
                return error_response('옮길 수량을 입력하세요.')
            serials = []
        error = stock.move(item, quantity, source, target)
        if error:
            return error_response(error)
        ItemSerial.objects.filter(id__in=[s.id for s in serials]).update(location=target)
        where = source.full_code if source else '미지정'
        InventoryLog.objects.create(item=item, action='TRANSFER', quantity_changed=0, user=request.user, work='이동',
                                    description=f'{label}: [{where}] ➔ [{target.full_code}] {quantity}개' + (f' ({", ".join(s.serial_number for s in serials)})'[:120] if serials else ''))
        return Response({'message': f'[{item.sku}] {quantity}개를 {target.full_code}로 옮겼습니다.', 'item': self.get_serializer(item).data})

    def create(self, request, *args, **kwargs):
        # 사용 중지된 SKU를 다시 등록하면 기존 상품과 이력을 이어서 사용합니다.
        stopped = Item.objects.select_for_update().filter(sku=clean_code(request.data.get('sku')), is_active=False).first()
        if not stopped:
            return super().create(request, *args, **kwargs)
        serializer = self.get_serializer(stopped, data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(is_active=True)
        ItemStock.objects.filter(item=item).delete()  # 다시 등록한 수량으로 새로 시작합니다.
        stock.add(item, item.quantity)
        InventoryLog.objects.create(item=item, action='NEW', quantity_changed=item.quantity, description='사용 중지 상품 재등록', user=request.user)
        audit.record(request.user, item, '재등록')
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
        InventoryLog.objects.create(item=item, action='DISABLE', quantity_changed=0, description='상품 삭제(사용 중지)', user=self.request.user)

    def perform_create(self, serializer):
        item = serializer.save()
        stock.add(item, item.quantity)
        InventoryLog.objects.create(item=item, action='NEW', quantity_changed=item.quantity, user=self.request.user)

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
        new_quantity = serializer.validated_data.get('quantity', old_quantity)
        if new_tracked and new_quantity < old_quantity:
            # 창고에 있다고 기록된 시리얼보다 수량이 적어지면 둘이 어긋나므로 막습니다.
            in_stock = old.serials.filter(status=IN_STOCK).count()
            if new_quantity < in_stock:
                raise ValidationError({'error': f'[{old.sku}] 재고보유 시리얼이 {in_stock}개라 수량을 {in_stock}개 미만으로 줄일 수 없습니다. 없어진 기기는 시리얼 조회에서 상태를 바꿔 주세요.'})
        item = serializer.save()
        quantity_diff = item.quantity - old_quantity
        if quantity_diff > 0:
            stock.add(item, quantity_diff)
        elif quantity_diff < 0:
            stock.remove(item, -quantity_diff)

        if quantity_diff != 0:
            action_type = 'IN' if quantity_diff > 0 else 'OUT'
            description = ""
            if 'physicalQty' in self.request.data: # 실사 조정일 경우
                description = "월말 재고 실사 조정"
                send_webhook_alert(f"재고 오차 조정 발생: {item.name} ({quantity_diff}개)")
            InventoryLog.objects.create(item=item, action=action_type, quantity_changed=quantity_diff, description=description, user=self.request.user, work='조정')

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
        stock.add(item, change) if change > 0 else stock.remove(item, -change)
        InventoryLog.objects.create(item=item, action='IN' if change > 0 else 'OUT', quantity_changed=change, user=request.user, work='조정')
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
                    ItemSerial.objects.create(item=item, serial_number=serial_number, status=IN_STOCK, location=item.location)
            except IntegrityError:
                return error_response('이미 창고에 등록된 시리얼 번호입니다.')
            item.quantity += 1
            item.save(update_fields=['quantity'])
            stock.add(item, 1)
            InventoryLog.objects.create(item=item, action='IN', quantity_changed=1, description=f'시리얼 직접 입고 S/N {serial_number}', user=request.user, work='조정')
            return Response({'message': f'S/N [{serial_number}] 입고 완료'})

        serial_obj = ItemSerial.objects.select_for_update().filter(serial_number=serial_number, item=item, status=IN_STOCK).first()
        if not serial_obj or item.quantity < 1:
            return error_response('재고가 없거나 이미 출고되었습니다.')
        stock.remove(item, 1, prefer=serial_obj.location)
        serial_obj.status, serial_obj.location = '출고완료', None
        serial_obj.save()
        item.quantity -= 1
        item.save(update_fields=['quantity'])
        InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-1, description=f'시리얼 직접 출고 S/N {serial_number}', user=request.user, work='조정')

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
                InventoryLog.objects.create(item=item, action='NEW', quantity_changed=qty, user=request.user)
                success_count += 1
        except csv.Error:
            transaction.set_rollback(True)
            return error_response('CSV 형식이 올바르지 않습니다.')

        message = f'총 {success_count}건 등록 완료'
        if skipped_count:
            message += f' (중복 또는 오류 {skipped_count}건 제외)'
        return Response({'message': message}, status=status.HTTP_200_OK)


# 🌟 NEW: 공급사(거래처) API
class SupplierViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all().order_by('name')
    serializer_class = SupplierSerializer
    permission_classes = [IsAdminRole]


# 🌟 NEW: 발주서(PO) API 및 검수 입고 로직
class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__item__location', 'items__received_serials').order_by('-order_date', '-id')
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAdminRole]
    pagination_class = PageOnRequest
    # 입고 이력과 어긋나지 않도록 등록 후에는 수정, 삭제 대신 취소만 허용합니다.
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return filter_documents(super().get_queryset(), self.request.query_params, 'order_date',
                                ['po_number', 'supplier__name', 'items__item__sku', 'items__item__name'], date_only=True)

    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def suggestions(self, request):
        """발주 제안: (안전 재고 + 하루 평균 출고량 × 조달 기간) − (현재 재고 + 들어올 수량)이 0보다 큰 상품.
        하루 평균은 최근 30일 출고량으로 계산하고, 거래처는 그 상품을 마지막으로 발주한 곳을 씁니다."""
        lead_days = settings.REORDER_LEAD_DAYS
        since = timezone.now() - timedelta(days=30)
        items = Item.objects.filter(is_active=True).annotate(
            usage=Coalesce(Sum('logs__quantity_changed', filter=Q(logs__action='OUT', logs__timestamp__gte=since)), 0),
        )
        incoming = dict(PurchaseOrderItem.objects.filter(po__status__in=['발주대기', '입고중'])
                        .values('item').annotate(total=Sum(F('order_quantity') - F('received_quantity'))).values_list('item', 'total'))
        last_supplier = {}
        for line in (PurchaseOrderItem.objects.filter(po__supplier__is_active=True).exclude(po__status='취소됨')
                     .select_related('po__supplier').order_by('item_id', '-po__order_date', '-po_id')):
            last_supplier.setdefault(line.item_id, line.po.supplier)

        rows = []
        for item in items:
            usage = abs(item.usage)
            target = item.safety_stock + math.ceil(usage / 30 * lead_days)
            coming = incoming.get(item.id) or 0
            suggested = target - item.quantity - coming
            if suggested <= 0:
                continue
            supplier = last_supplier.get(item.id)
            rows.append({
                'item': item.id, 'sku': item.sku, 'name': item.name, 'quantity': item.quantity,
                'safety_stock': item.safety_stock, 'incoming': coming, 'usage_30d': usage, 'suggested': suggested,
                'supplier': supplier.id if supplier else None, 'supplier_name': supplier.name if supplier else '',
            })
        rows.sort(key=lambda row: (row['supplier_name'] or '힣', row['quantity'] - row['safety_stock']))
        return Response({'lead_days': lead_days, 'rows': rows})

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
        # 현장에서 위치 라벨을 스캔해 다른 위치에 넣을 수 있습니다. 정하지 않으면 상품의 기본 위치입니다.
        target = None
        if request.data.get('location'):
            target = WarehouseLocation.objects.filter(pk=to_int(request.data.get('location')), is_active=True).first()
            if not target:
                return error_response('넣을 보관 위치를 찾을 수 없습니다.')
        target = target or master_item.location

        if serial_number:
            ItemSerial.objects.create(item=master_item, serial_number=serial_number, status=IN_STOCK, po_item=po_item, location=target)

        po_item.received_quantity += receive_qty
        po_item.save(update_fields=['received_quantity'])

        # 실제 마스터 재고 증가
        master_item.quantity += receive_qty
        master_item.save(update_fields=['quantity'])
        stock.add(master_item, receive_qty, target)
        description = f"발주번호 {po.po_number} 정상 입고" + (f" S/N {serial_number}" if serial_number else '') + (f" → {target.full_code}" if target else '')
        InventoryLog.objects.create(item=master_item, action='IN', quantity_changed=receive_qty, description=description[:200], user=request.user, work='입고', reference=po.po_number)

        # 모든 품목 입고 완료 체크
        all_received = all(i.received_quantity >= i.order_quantity for i in po.items.all())
        po.status = '입고완료' if all_received else '입고중'
        po.save(update_fields=['status'])

        fresh = self.get_queryset().get(pk=po.pk)
        return Response({'message': f'발주 품목 [{sku}] 정상 입고 처리 완료', 'status': po.status, 'po': self.get_serializer(fresh).data})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel_receipt(self, request, pk=None):
        # 잘못 스캔한 입고를 되돌립니다. 시리얼 관리 상품은 시리얼 1개씩, 그 외는 수량으로 취소합니다.
        sku = clean_code(request.data.get('sku'))
        serial_number = clean_code(request.data.get('serial_number'))
        cancel_qty = to_int(request.data.get('quantity', 1))
        if not sku or cancel_qty is None or cancel_qty < 1:
            return error_response('취소할 상품(SKU)과 수량을 확인해주세요.')

        po = PurchaseOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if po.status == '취소됨':
            return error_response('취소된 발주서입니다.')
        po_item = po.items.select_for_update().filter(item__sku=sku).first()
        if not po_item:
            return error_response('해당 발주서에 존재하지 않는 상품(SKU)입니다.')
        if cancel_qty > po_item.received_quantity:
            return error_response(f'입고된 수량보다 많이 취소할 수 없습니다. (입고 {po_item.received_quantity}개)')

        item = Item.objects.select_for_update().get(pk=po_item.item_id)
        serial = None
        if item.serial_tracked:
            if not serial_number:
                return error_response('시리얼 관리 상품입니다. 취소할 시리얼을 스캔해주세요.')
            if cancel_qty != 1:
                return error_response('시리얼 관리 상품은 1개씩 취소해주세요.')
            serial = ItemSerial.objects.select_for_update().filter(serial_number=serial_number, item=item).first()
            # 이 기능 이전에 입고된 시리얼은 발주 연결이 없어 입고 기록으로 확인합니다.
            from_this_po = serial and (serial.po_item_id == po_item.id or (
                serial.po_item_id is None and InventoryLog.objects.filter(item=item, description=f'발주번호 {po.po_number} 정상 입고 S/N {serial_number}').exists()))
            if not from_this_po:
                return error_response(f'[{serial_number}] 이 발주서로 입고된 시리얼이 아닙니다.')
            if serial.status != IN_STOCK:
                return error_response(f'[{serial_number}] {serial.status} 상태라 입고를 취소할 수 없습니다.')
            if serial.order_picks.exists():
                return error_response(f'[{serial_number}] 출고 주문에 스캔된 시리얼입니다. 주문 화면에서 다시 스캔으로 지운 뒤 취소해주세요.')
        elif serial_number:
            return error_response('시리얼을 관리하지 않는 상품입니다. 수량으로 취소해주세요.')

        if item.quantity < cancel_qty:
            return error_response(f'재고가 부족해 취소할 수 없습니다. 이미 출고되었는지 확인해주세요. (현재 {item.quantity}개)')

        stock.remove(item, cancel_qty, prefer=serial.location if serial else None)
        if serial:
            serial.delete()
        po_item.received_quantity -= cancel_qty
        po_item.save(update_fields=['received_quantity'])
        item.quantity -= cancel_qty
        item.save(update_fields=['quantity'])
        description = f'발주번호 {po.po_number} 입고 취소' + (f' S/N {serial_number}' if serial else '')
        InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-cancel_qty, description=description[:200], user=request.user, work='입고취소', reference=po.po_number)
        alert_if_low_stock(item)

        po.status = '입고중' if any(line.received_quantity > 0 for line in po.items.all()) else '발주대기'
        po.save(update_fields=['status'])

        fresh = self.get_queryset().get(pk=po.pk)
        return Response({'message': f'[{item.name}] {cancel_qty}개 입고 취소 완료', 'status': po.status, 'po': self.get_serializer(fresh).data})

class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.select_related('bundle_parent').prefetch_related(
        'items__item__location', 'items__item__stocks__location', 'items__picked_serials__serial', 'carrier_events', 'bundle_members', 'bundle_parent__bundle_members', 'bundle_parent__carrier_events'
    ).order_by('-created_at', '-id')
    serializer_class = SalesOrderSerializer
    permission_classes = [IsAdminRole]
    pagination_class = PageOnRequest
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = filter_documents(super().get_queryset(), self.request.query_params, 'created_at',
                                    ['order_no', 'customer', 'contact_name', 'waybill_no', 'items__item__sku', 'items__item__name'])
        if self.request.query_params.get('item'):  # 이 상품이 들어 있는 주문 (반품 등록에서 원래 주문 고르기)
            queryset = queryset.filter(items__item_id=to_int(self.request.query_params['item'])).distinct()
        return queryset

    def perform_create(self, serializer):
        order = serializer.save(created_by=self.request.user)
        request_carrier(order, carrier.create_shipment)

    def _order_response(self, order, message=''):
        return Response({'message': message, 'order': self.get_serializer(self.get_queryset().get(pk=order.pk)).data})

    @action(detail=True, methods=['post'])
    def edit(self, request, pk=None):
        # 출고대기 주문의 고객, 비고, 배송지, 품목을 고칩니다. 배송지가 바뀌면 운송장을 새로 발급합니다.
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 수정할 수 없습니다.')
        if 'items' in request.data and order.items.filter(picked_quantity__gt=0).exists():
            return error_response('스캔을 시작한 주문은 품목을 바꿀 수 없습니다. 현장 화면에서 [다시 스캔]으로 지운 뒤 수정해 주세요.')

        serializer = self.get_serializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        lines = changes.pop('items', None)
        if lines is not None and any('item' not in line or 'quantity' not in line for line in lines):
            return error_response('품목마다 상품과 수량을 입력해주세요.')
        error, message = update_order(order, changes, lines)
        if error:
            return error_response(error)
        return self._order_response(order, message)

    @action(detail=True, methods=['post'])
    def urgent(self, request, pk=None):
        # 긴급 표시를 켜고 끕니다. 묶음배송이면 같은 상자의 주문도 함께 바꿉니다.
        order = self.get_object()
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 바꿀 수 없습니다.')
        value = request.data.get('urgent') in (True, 'true', '1', 1)
        master = order.bundle_parent or order
        SalesOrder.objects.filter(Q(pk=master.pk) | Q(bundle_parent=master)).update(is_urgent=value)
        order.refresh_from_db()
        return self._order_response(order, f"주문 {order.order_no} 긴급 {'지정' if value else '해제'}")

    @action(detail=False, methods=['post'])
    def import_addresses(self, request):
        """엑셀로 고친 배송지를 한 번에 반영합니다. apply가 아니면 미리보기만 합니다.
        rows: [{order_no, contact_name, contact_phone, zipcode, address, address_detail}]"""
        rows = request.data.get('rows')
        if not isinstance(rows, list) or not rows:
            return error_response('반영할 행이 없습니다. 양식의 첫 줄(제목)을 지우지 말고 올려 주세요.')
        if len(rows) > 1000:
            return error_response('한 번에 1,000행까지 올릴 수 있습니다.')
        apply = request.data.get('apply') is True
        results = []
        for index, row in enumerate(rows, start=2):  # 엑셀의 2번째 줄부터 데이터
            row = row if isinstance(row, dict) else {}
            order_no = str(row.get('order_no') or '').strip()
            result = {'row': index, 'order_no': order_no, 'status': 'error', 'message': '', 'changes': []}
            results.append(result)
            order = SalesOrder.objects.select_for_update().filter(order_no=order_no).first() if order_no else None
            if not order:
                result['message'] = '없는 주문번호입니다.'
                continue
            if order.status != '출고대기':
                result['message'] = f'{order.status} 상태라 바꿀 수 없습니다.'
                continue
            data = {key: str(row.get(key) or '').strip() for key in SHIPPING_FIELDS}
            serializer = SalesOrderSerializer(order, data=data, partial=True)
            if not serializer.is_valid():
                result['message'] = next(iter(serializer.errors.values()))[0]
                continue
            changes = {key: value for key, value in serializer.validated_data.items() if getattr(order, key) != value}
            result['changes'] = [f'{SHIPPING_LABELS[key]}: {getattr(order, key) or "(없음)"} → {value or "(없음)"}' for key, value in changes.items()]
            if not changes:
                result.update(status='unchanged', message='바뀐 내용 없음')
                continue
            result['status'] = 'ok'
            if apply:
                error, message = update_order(order, changes)
                result.update(status='error' if error else 'saved', message=error or message)
        counts = {key: sum(r['status'] == key for r in results) for key in ('ok', 'saved', 'unchanged', 'error')}
        return Response({'applied': apply, 'counts': counts, 'rows': results})

    @action(detail=False, methods=['post'])
    def bundle(self, request):
        # 받는 분과 배송지가 같은 출고대기 주문을 운송장 하나로 묶습니다. 가장 먼저 등록한 주문이 대표입니다.
        ids = request.data.get('ids')
        if not isinstance(ids, list) or len({to_int(i) for i in ids}) < 2 or any(to_int(i) is None for i in ids):
            return error_response('묶을 주문을 2건 이상 선택해주세요.')
        if not carrier.enabled():
            return error_response('택배 연동이 설정되지 않았습니다.')
        ids = {to_int(i) for i in ids}
        orders = list(SalesOrder.objects.select_for_update().filter(pk__in=ids).order_by('created_at', 'id'))
        if len(orders) != len(ids):
            return error_response('없는 주문이 포함되어 있습니다.')
        for order in orders:
            if order.status != '출고대기':
                return error_response(f'[{order.order_no}] {order.status} 상태라 묶을 수 없습니다.')
            if order.bundle_parent_id or order.bundle_members.exists():
                return error_response(f'[{order.order_no}] 이미 묶음배송인 주문입니다.')
            if not order.has_address:
                return error_response(f'[{order.order_no}] 배송지가 없습니다.')
            if order.carrier_status not in ('', '접수'):
                return error_response(f'[{order.order_no}] 이미 택배 {order.carrier_status} 단계입니다.')
        if len({address_key(order) for order in orders}) > 1:
            return error_response('받는 분, 연락처, 배송지가 모두 같은 주문만 묶을 수 있습니다.')

        master, members = orders[0], orders[1:]
        request_carrier(master, carrier.create_shipment)
        if not master.waybill_no:
            return error_response(master.carrier_error or '대표 주문의 운송장을 발급하지 못했습니다.')
        skipped = []
        for member in members:
            # 택배사 취소가 실패한 주문은 따로 보내고 나머지만 묶습니다. (이미 취소한 송장을 되돌릴 수 없으므로)
            error = cancel_carrier(member, pickup=False) if member.waybill_no else None
            if error:
                skipped.append(f'{member.order_no}({error})')
                continue
            member.carrier_events.all().delete()
            member.bundle_parent = master
            member.waybill_no, member.carrier_status, member.carrier_error = master.waybill_no, master.carrier_status, ''
            member.save(update_fields=['bundle_parent', 'waybill_no', 'carrier_status', 'carrier_error'])
        bundled = len(members) - len(skipped) + 1
        message = f'{bundled}건을 운송장 {master.waybill_no} 하나로 묶었습니다.'
        if skipped:
            message += f' 묶지 못한 주문: {", ".join(skipped)}'
        return self._order_response(master, message)

    @action(detail=True, methods=['post'])
    def unbundle(self, request, pk=None):
        # 묶음을 풀고, 대표 주문을 뺀 나머지 주문에 운송장을 새로 발급합니다.
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        master = order.bundle_parent or order
        members = list(master.bundle_members.select_for_update())
        if not members:
            return error_response('묶음배송이 아닌 주문입니다.')
        if any(o.status == '출고완료' for o in [master, *members]):
            return error_response('이미 출고한 주문이 있어 묶음을 풀 수 없습니다.')
        failed = []
        for member in members:
            member.bundle_parent = None
            member.waybill_no, member.carrier_status, member.carrier_error = '', '', ''
            member.save(update_fields=['bundle_parent', 'waybill_no', 'carrier_status', 'carrier_error'])
            request_carrier(member, carrier.create_shipment)
            if not member.waybill_no:
                failed.append(member.order_no)
        message = f'묶음을 풀었습니다. {len(members)}건에 운송장을 새로 발급했습니다.'
        if failed:
            message = f'묶음을 풀었습니다. 운송장 발급 실패: {", ".join(failed)} (주문을 열어 다시 발급하세요)'
        return self._order_response(order, message)

    @action(detail=True, methods=['post'])
    def issue_waybill(self, request, pk=None):
        # 운송장 발급을 다시 시도합니다. 주소를 함께 보내면 고친 뒤 발급합니다.
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if not carrier.enabled():
            return error_response('택배 연동이 설정되지 않았습니다.')
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 운송장을 발급할 수 없습니다.')
        if order.waybill_no:
            return error_response(f'이미 운송장이 발급되었습니다. ({order.waybill_no})')
        if order.bundle_parent_id:
            return error_response('묶음배송 주문은 대표 주문의 운송장을 씁니다.')
        update_shipping_address(order, SalesOrderSerializer, request.data)
        request_carrier(order, carrier.create_shipment)
        if not order.waybill_no:
            return error_response(order.carrier_error or '운송장을 발급하지 못했습니다.')
        return self._order_response(order, f'운송장 {order.waybill_no} 발급 완료')

    @action(detail=True, methods=['post'])
    def track(self, request, pk=None):
        # 택배사에서 최신 배송 단계를 가져옵니다. 출고했는데 집하 요청이 실패했었다면 다시 보냅니다.
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        master = order.bundle_parent or order
        if not carrier.enabled() or not master.waybill_no:
            return error_response('운송장이 없는 주문입니다.')
        try:
            if master.carrier_error.startswith('집하 요청 실패') and bundle_shipped(master):
                carrier.request_collection(master.waybill_no)
            apply_carrier_data(master, carrier.track(master.waybill_no))
        except CarrierError as exc:
            return error_response(str(exc))
        return self._order_response(order, f'배송 상태: {master.carrier_status}')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 취소할 수 없습니다.')
        if order.bundle_members.exists():
            return error_response('묶음배송의 대표 주문입니다. [묶음 해제] 후 취소해 주세요.')
        if order.bundle_parent_id:  # 대표 주문의 송장은 그대로 두고 이 주문만 묶음에서 뺍니다.
            order.bundle_parent = None
            order.waybill_no, order.carrier_status, order.carrier_error = '', '', ''
            order.save(update_fields=['bundle_parent', 'waybill_no', 'carrier_status', 'carrier_error'])
        error = cancel_carrier(order, pickup=False)
        if error:
            return error_response(error)
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
        # partial이면 스캔한 만큼만 출고하고, 남은 수량은 같은 배송지의 새 주문으로 등록합니다.
        order = SalesOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if order.status != '출고대기':
            return error_response(f'{order.status} 상태의 주문은 출고할 수 없습니다.')
        backorder = None
        if request.data.get('partial') is True:
            backorder, error = split_backorder(order, request.user)
            if error:
                return error_response(error)

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
            picked = [pick.serial for pick in line.picked_serials.all()]
            for serial in picked:  # 시리얼은 그 기기가 있던 위치에서 뺍니다.
                stock.remove(item, 1, prefer=serial.location)
            stock.remove(item, line.quantity - len(picked))
            ItemSerial.objects.filter(id__in=[s.id for s in picked]).update(status='출고완료', location=None, updated_at=timezone.now())
            InventoryLog.objects.create(item=item, action='OUT', quantity_changed=-line.quantity, description=f'주문번호 {order.order_no} 출고', user=request.user, work='출고', reference=order.order_no)
            alert_if_low_stock(item)

        order.status = '출고완료'
        order.completed_at = timezone.now()
        order.save(update_fields=['status', 'completed_at'])

        # 재고는 이미 차감되었으므로, 집하 요청이 실패해도 출고는 유지하고 관리자가 [배송 조회]로 다시 보냅니다.
        message = f'출고 완료 (총 {len(lines)}종 재고 차감)'
        if backorder:
            request_carrier(backorder, carrier.create_shipment)
            message = f'부분 출고 완료. 남은 수량은 주문 {backorder.order_no}로 등록했습니다.'
        master = order.bundle_parent or order
        if carrier.enabled() and master.waybill_no:
            if bundle_shipped(master):
                try:
                    carrier.request_collection(master.waybill_no)
                except CarrierError as exc:
                    master.carrier_error = f'집하 요청 실패: {exc}'[:200]
                    master.save(update_fields=['carrier_error'])
            else:
                message += '. 묶음배송의 나머지 주문을 모두 출고하면 집하를 요청합니다.'
        return Response({'message': message, 'status': order.status, 'waybill_no': order.waybill_no})

class ReturnOrderViewSet(viewsets.ModelViewSet):
    queryset = ReturnOrder.objects.select_related('serial', 'item', 'sales_order').prefetch_related('carrier_events').order_by('-created_at', '-id')
    serializer_class = ReturnOrderSerializer
    permission_classes = [IsAdminRole]
    pagination_class = PageOnRequest
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return filter_documents(super().get_queryset(), self.request.query_params, 'created_at',
                                ['return_no', 'customer', 'contact_name', 'waybill_no', 'serial__serial_number', 'item__sku', 'item__name'])

    def perform_create(self, serializer):
        return_order = serializer.save(created_by=self.request.user)
        request_carrier(return_order, carrier.create_pickup)

    def _return_response(self, return_order, message=''):
        return Response({'message': message, 'return': self.get_serializer(self.get_queryset().get(pk=return_order.pk)).data})

    @action(detail=True, methods=['post'])
    def request_pickup(self, request, pk=None):
        # 회수 요청을 다시 보냅니다. 주소를 함께 보내면 고친 뒤 요청합니다.
        return_order = ReturnOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if not carrier.enabled():
            return error_response('택배 연동이 설정되지 않았습니다.')
        if return_order.status != '회수대기':
            return error_response(f'{return_order.status} 상태의 반품은 회수 요청할 수 없습니다.')
        if return_order.waybill_no:
            return error_response(f'이미 회수 요청이 접수되었습니다. ({return_order.waybill_no})')
        update_shipping_address(return_order, ReturnOrderSerializer, request.data)
        request_carrier(return_order, carrier.create_pickup)
        if not return_order.waybill_no:
            return error_response(return_order.carrier_error or '회수 요청을 보내지 못했습니다.')
        return self._return_response(return_order, f'회수 운송장 {return_order.waybill_no} 접수 완료')

    @action(detail=True, methods=['post'])
    def track(self, request, pk=None):
        return_order = ReturnOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if not carrier.enabled() or not return_order.waybill_no:
            return error_response('회수 운송장이 없는 반품입니다.')
        try:
            apply_carrier_data(return_order, carrier.track(return_order.waybill_no))
        except CarrierError as exc:
            return error_response(str(exc))
        return self._return_response(return_order, f'회수 상태: {return_order.carrier_status}')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return_order = ReturnOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if return_order.status != '회수대기':
            return error_response(f'{return_order.status} 상태의 반품은 취소할 수 없습니다.')
        error = cancel_carrier(return_order, pickup=True)
        if error:
            return error_response(error)
        return_order.status = '취소됨'
        return_order.save(update_fields=['status'])
        return Response({'message': f'반품 {return_order.return_no} 취소 완료', 'status': return_order.status})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def complete(self, request, pk=None):
        new_status = request.data.get('status')
        quality = request.data.get('quality') or None
        detail = clean_code(request.data.get('detail'))
        label = clean_code(request.data.get('label'))[:50]

        return_order = ReturnOrder.objects.select_for_update().get(pk=self.get_object().pk)
        if return_order.status != '회수대기':
            return error_response(f'{return_order.status} 상태의 반품은 처리할 수 없습니다.')
        if not return_order.serial_id:
            return self._complete_quantity(request, return_order, request.data.get('result'), label, detail)

        if new_status not in (IN_STOCK, 'AS진행중', '불량폐기'):
            return error_response('올바르지 않은 회수 처리 상태입니다.')
        if quality and quality not in SERIAL_QUALITIES:
            return error_response('올바르지 않은 품질 등급입니다.')

        serial = ItemSerial.objects.select_for_update().get(pk=return_order.serial_id)
        if serial.status != '출고완료':
            return error_response(f'출고완료 상태의 시리얼만 회수할 수 있습니다. (현재: {serial.status})')

        description = f'반품 {return_order.return_no} 회수: {serial.serial_number}' + (f' ({detail})' if detail else '')
        error = change_serial_status(serial, new_status, quality, description, request.user, work='반품', reference=return_order.return_no)
        if error:
            return error_response(error)
        if new_status != IN_STOCK:  # 재고로 돌아오지 않는 회수(AS·폐기)도 실적에 남도록 기록합니다.
            InventoryLog.objects.create(item=serial.item, action='RETURN', quantity_changed=0, description=f'{description} → {new_status}'[:200],
                                        user=request.user, work='반품', reference=return_order.return_no)

        return_order.status, return_order.result = '회수완료', label
        return_order.completed_at = timezone.now()
        return_order.save(update_fields=['status', 'result', 'completed_at'])
        return Response({'message': f'S/N [{serial.serial_number}] 회수 처리 완료', 'status': serial.status})

    def _complete_quantity(self, request, return_order, result, label, detail):
        # 시리얼 없는 상품: 재고로 되돌리거나(restock) 폐기(dispose)합니다.
        if result not in ('restock', 'dispose'):
            return error_response('회수 결과를 고르세요. (재고로 되돌림 또는 폐기)')
        item = Item.objects.select_for_update().get(pk=return_order.item_id)
        description = f'반품 {return_order.return_no} 회수 {return_order.quantity}개' + (f' ({detail})' if detail else '')
        if result == 'restock':
            item.quantity += return_order.quantity
            item.save(update_fields=['quantity'])
            stock.add(item, return_order.quantity)
            InventoryLog.objects.create(item=item, action='IN', quantity_changed=return_order.quantity, description=description[:200], user=request.user,
                                        work='반품', reference=return_order.return_no)
        else:  # 폐기해도 회수 작업은 한 것이므로 수량 0으로 기록합니다.
            InventoryLog.objects.create(item=item, action='RETURN', quantity_changed=0, description=f'{description} → 폐기'[:200], user=request.user,
                                        work='반품', reference=return_order.return_no)
        return_order.status, return_order.result = '회수완료', label or ('재고로 되돌림' if result == 'restock' else '폐기')
        return_order.completed_at = timezone.now()
        return_order.save(update_fields=['status', 'result', 'completed_at'])
        return Response({'message': f'[{item.name}] {return_order.quantity}개 회수 처리 완료 ({return_order.result})', 'status': return_order.status})


class LogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class MasterChangeViewSet(viewsets.ReadOnlyModelViewSet):
    """기준정보 변경 이력. ?target=상품&q=검색어&start_date&end_date&object_id="""
    queryset = MasterChange.objects.select_related('user')
    permission_classes = [IsAdminUser]
    pagination_class = LogPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get('target'):
            queryset = queryset.filter(target=params['target'])
        if params.get('object_id'):
            queryset = queryset.filter(object_id=to_int(params['object_id']))
        if params.get('q'):
            queryset = queryset.filter(Q(label__icontains=params['q']) | Q(user__username__icontains=params['q']) | Q(user__first_name__icontains=params['q']))
        start, end = parse_date_param(params.get('start_date')), parse_date_param(params.get('end_date'))
        if start:
            queryset = queryset.filter(timestamp__gte=day_start(start))
        if end:
            queryset = queryset.filter(timestamp__lt=day_start(end + timedelta(days=1)))
        return queryset

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        rows = [{'id': c.id, 'timestamp': timezone.localtime(c.timestamp).isoformat(), 'target': c.target, 'object_id': c.object_id,
                 'label': c.label, 'action': c.action, 'changes': c.changes, 'user': user_display(c.user) if c.user else ''} for c in page]
        return self.get_paginated_response(rows)


class InventoryLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InventoryLog.objects.select_related('item', 'user').order_by('-timestamp', '-id')
    serializer_class = InventoryLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LogPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get('mine') == '1':
            queryset = queryset.filter(user=self.request.user)

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
            yield writer.writerow(['발생일시', '구분', 'SKU', '상품명', '변동수량', '처리자', '비고'])
            for log in self.get_queryset().iterator(chunk_size=1000):
                yield writer.writerow([
                    timezone.localtime(log.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                    action_names.get(log.action, log.action),
                    csv_safe(log.item.sku),
                    csv_safe(log.item.name),
                    log.quantity_changed,
                    csv_safe(user_display(log.user)),
                    csv_safe(log.description),
                ])

        response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="inventory_logs.csv"'
        return response


class ItemSerialViewSet(viewsets.ModelViewSet):
    queryset = ItemSerial.objects.select_related('item', 'location').order_by('-updated_at', '-id')
    serializer_class = ItemSerialSerializer
    permission_classes = [IsAdminRole]
    pagination_class = PageOnRequest

    def get_queryset(self):
        # 시리얼은 기기 수만큼 늘어나므로 서버에서 거릅니다. ?q=시리얼·상품코드·상품명 &status= &quality= &item=
        queryset = super().get_queryset()
        if self.action != 'list':
            return queryset
        params = self.request.query_params
        statuses = [s for s in (params.get('status') or '').split(',') if s]
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        if params.get('quality'):
            queryset = queryset.filter(quality=params['quality'])
        if params.get('item'):
            queryset = queryset.filter(item_id=to_int(params['item']))
        keyword = (params.get('q') or '').strip()
        if keyword:
            queryset = queryset.filter(Q(serial_number__icontains=keyword) | Q(item__sku__icontains=keyword) | Q(item__name__icontains=keyword))
        return queryset

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        # 기기 한 대가 언제 들어와서 어느 주문으로 나갔고, 반품으로 어떻게 돌아왔는지 시간순으로 모읍니다.
        serial = self.get_object()
        sn = serial.serial_number
        mentions = re.compile(rf'(?<![0-9A-Za-z_-]){re.escape(sn)}(?![0-9A-Za-z_-])')
        events = []

        def add(when, kind, title, detail='', user=None, waybill='', carrier_status=''):
            events.append({'time': when, 'kind': kind, 'title': title, 'detail': detail, 'user': user_display(user),
                           'waybill_no': waybill, 'carrier_status': carrier_status, 'tracking_url': carrier.tracking_url(waybill)})

        logs = [log for log in InventoryLog.objects.filter(item=serial.item, description__contains=sn).select_related('user')
                if mentions.search(log.description or '') and not log.description.startswith('반품 ')]
        if not any(log.action == 'IN' for log in logs):
            source = f'발주 {serial.po_item.po.po_number}' if serial.po_item_id else ''
            add(serial.created_at, 'in', '시리얼 등록', source)
        for log in logs:
            add(log.timestamp, 'in' if log.quantity_changed > 0 else 'out' if log.quantity_changed < 0 else 'etc',
                InventoryLogSerializer.ACTION_NAMES.get(log.action, log.action), log.description, log.user)

        for pick in serial.order_picks.select_related('line__order__created_by'):
            order = pick.line.order
            detail = f'주문 {order.order_no} · {order.customer}'
            if order.status == '출고완료':
                add(order.completed_at, 'out', '주문 출고', detail, None, order.waybill_no, order.carrier_status)
            else:
                add(None, 'etc', f'출고 스캔됨 ({order.status})', detail, None, order.waybill_no, order.carrier_status)

        for ret in serial.returns.select_related('created_by'):
            add(ret.created_at, 'return', '반품 등록', f'반품 {ret.return_no} · {ret.customer} · {ret.reason}', ret.created_by, ret.waybill_no, ret.carrier_status)
            if ret.status == '회수완료':
                add(ret.completed_at, 'return', '반품 회수 완료', f'반품 {ret.return_no}')
            elif ret.status == '취소됨':
                add(None, 'etc', '반품 취소', f'반품 {ret.return_no}')

        # 시각이 없는 진행 중 항목은 맨 뒤에 둡니다.
        events.sort(key=lambda e: (e['time'] is None, e['time'] or serial.created_at))
        return Response({'serial': self.get_serializer(serial).data, 'events': events})

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
            error = change_serial_status(serial, new_status or serial.status, new_quality, f'시리얼 상태 변경: {serial.serial_number}', request.user)
            if error:
                transaction.set_rollback(True)
                return error_response(error)
        return Response({'message': f'{len(serials)}건 변경 완료', 'count': len(serials)})


class WarehouseLocationViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = WarehouseLocation.objects.all().order_by('zone', 'rack', 'tier')
    serializer_class = WarehouseLocationSerializer
    permission_classes = [IsAdminRole]

    @action(detail=False, methods=['get'])
    def cycle_count(self, request):
        return Response(cycle_count_plan())

    def perform_destroy(self, instance):
        # 지우면 상품의 위치가 조용히 비워지므로, 보관 중인 상품이 있으면 막습니다.
        count = instance.items.filter(is_active=True).count()
        if count:
            raise ValidationError({'error': f'상품 {count}개의 기본 위치라 삭제할 수 없습니다. 상품의 위치를 바꾼 뒤 삭제해 주세요.'})
        if instance.stocks.filter(quantity__gt=0).exists() or instance.serials.filter(status=IN_STOCK).exists():
            raise ValidationError({'error': '이 위치에 재고가 남아 있어 삭제할 수 없습니다. 재고를 다른 위치로 옮긴 뒤 삭제해 주세요.'})
        instance.stocks.all().delete()
        instance.delete()


STALLED_HOURS = 24  # 출고 후 이 시간이 지나도 배송완료가 아니면 확인이 필요합니다.


def cycle_count_plan():
    """순환 재고 조사: 오늘 조사할 위치. 재고가 있는 위치 가운데 오래 조사하지 않은 곳,
    최근 30일 동안 입출고가 많은 상품이 있는 곳을 먼저 고릅니다. 오늘 이미 조사한 곳은 done에 들어갑니다."""
    now = timezone.now()
    today_start = day_start(timezone.localdate())
    since = now - timedelta(days=30)
    movement = dict(InventoryLog.objects.filter(timestamp__gte=since).exclude(work='').values('item_id').annotate(n=Count('id')).values_list('item_id', 'n'))
    stocked = {}
    for row in ItemStock.objects.filter(quantity__gt=0, location__is_active=True, item__is_active=True).values('location_id', 'item_id'):
        stocked.setdefault(row['location_id'], set()).add(row['item_id'])
    locations = WarehouseLocation.objects.filter(pk__in=stocked)
    busy = sorted(sum(movement.get(i, 0) for i in items) for items in stocked.values())
    busy_line = busy[len(busy) // 2] if busy else 0  # 중간값보다 많이 움직이면 "자주 움직임"

    done, candidates = [], []
    for loc in locations:
        moves = sum(movement.get(i, 0) for i in stocked[loc.id])
        days = (now - loc.last_counted_at).days if loc.last_counted_at else None
        row = {'id': loc.id, 'full_code': loc.full_code, 'barcode': loc.barcode, 'items': len(stocked[loc.id]), 'moves_30d': moves,
               'busy': moves > busy_line, 'days_since': days,
               'last_counted_at': timezone.localtime(loc.last_counted_at).isoformat() if loc.last_counted_at else None}
        if loc.last_counted_at and loc.last_counted_at >= today_start:
            done.append(row)
            continue
        # 한 번도 안 했거나 목표 주기를 넘긴 곳이 먼저, 자주 움직이는 곳은 두 배 빨리 돌아옵니다.
        age = days if days is not None else 10 ** 6
        row['overdue'] = days is None or days >= settings.CYCLE_COUNT_DAYS
        row['score'] = age * (2 if row['busy'] else 1)
        candidates.append(row)
    candidates.sort(key=lambda r: (-r['score'], r['full_code']))
    todo = candidates[:max(0, settings.CYCLE_COUNT_DAILY - len(done))]
    return {
        'daily': settings.CYCLE_COUNT_DAILY, 'cycle_days': settings.CYCLE_COUNT_DAYS,
        'todo': todo, 'done': sorted(done, key=lambda r: r['full_code']),
        'overdue': sum(1 for r in candidates if r['overdue']), 'stocked_locations': len(stocked),
    }


def replenishment_tasks():
    """기본 위치의 재고가 보충 최소 이하인 상품과, 어느 위치에서 몇 개를 가져오면 되는지.
    다른 위치에 재고가 없으면 sources가 비어 있습니다. (발주가 필요)"""
    items = (Item.objects.filter(is_active=True, pick_min__gt=0, location__isnull=False)
             .select_related('location').prefetch_related('stocks__location'))
    tasks = []
    for item in items:
        here = next((st.quantity for st in item.stocks.all() if st.location_id == item.location_id), 0)
        if here > item.pick_min:
            continue
        need = item.pick_max - here
        others = sorted((st for st in item.stocks.all() if st.location_id != item.location_id and st.quantity > 0), key=lambda st: -st.quantity)
        sources = []
        for st in others:
            if need - sum(src['take'] for src in sources) <= 0:
                break
            take = min(st.quantity, need - sum(src['take'] for src in sources))
            serials = []
            if item.serial_tracked:
                serials = list(item.serials.filter(status=IN_STOCK, location_id=st.location_id).order_by('serial_number').values_list('serial_number', flat=True)[:take])
                take = len(serials)
            if take:
                sources.append({'location': st.location_id, 'location_name': st.location.full_code, 'barcode': st.location.barcode,
                                'quantity': st.quantity, 'take': take, 'serials': serials})
        tasks.append({
            'item': item.id, 'sku': item.sku, 'name': item.name, 'serial_tracked': item.serial_tracked,
            'target': item.location_id, 'target_name': item.location.full_code, 'target_barcode': item.location.barcode,
            'here': here, 'pick_min': item.pick_min, 'pick_max': item.pick_max, 'need': need, 'sources': sources,
        })
    # 채울 수 있는 것 먼저, 꺼내는 자리가 빈 것 먼저
    return sorted(tasks, key=lambda t: (not t['sources'], t['here'], t['target_name']))


def overdue_purchase_orders(limit=10):
    """입고 예정일이 지났는데 아직 다 받지 못한 발주 (오늘 할 일, 슬랙 알림에서 함께 씀)"""
    today = timezone.localdate()
    pos = (PurchaseOrder.objects.filter(status__in=['발주대기', '입고중'], expected_date__lt=today)
           .select_related('supplier').order_by('expected_date', 'id'))
    items = [{'id': po.id, 'po_number': po.po_number, 'supplier': po.supplier.name if po.supplier else '',
              'expected_date': po.expected_date, 'days': (today - po.expected_date).days, 'status': po.status} for po in pos[:limit]]
    return {'count': pos.count(), 'items': items}


def carrier_issues(limit=10):
    """택배 연동에서 사람이 확인해야 할 주문·반품: 요청 실패, 운송장 없음, 오래 멈춘 배송"""
    if not carrier.enabled():
        return {'count': 0, 'items': []}
    stalled_before = timezone.now() - timedelta(hours=STALLED_HOURS)
    orders = SalesOrder.objects.filter(
        Q(status='출고대기', waybill_no='')
        | Q(status__in=['출고대기', '출고완료']) & ~Q(carrier_error='')
        | Q(status='출고완료', completed_at__lt=stalled_before) & ~Q(waybill_no='') & ~Q(carrier_status__in=['배송완료', '취소'])
    ).filter(bundle_parent__isnull=True).order_by('-created_at')
    returns = ReturnOrder.objects.filter(status='회수대기').filter(Q(waybill_no='') | ~Q(carrier_error='')).order_by('-created_at')

    def order_reason(order):
        if order.carrier_error:
            return order.carrier_error
        if not order.waybill_no:
            return '운송장 미발급'
        hours = int((timezone.now() - order.completed_at).total_seconds() // 3600)
        return f'출고 후 {hours}시간째 {order.carrier_status or "상태 미확인"}'

    items = [{'kind': 'order', 'number': o.order_no, 'customer': o.customer, 'reason': order_reason(o)} for o in orders[:limit]]
    items += [{'kind': 'return', 'number': r.return_no, 'customer': r.customer, 'reason': r.carrier_error or '회수 요청 안 됨'}
              for r in returns[:max(0, limit - len(items))]]
    return {'count': orders.count() + returns.count(), 'items': items}


class TodayAPIView(APIView):
    # 첫 화면에 보여줄 오늘 할 일과 처음 설정 진행 상태
    permission_classes = [IsAuthenticated]

    def get(self, request):
        low_stock = Item.objects.filter(is_active=True, quantity__lte=F('safety_stock')).count()
        plan = cycle_count_plan()
        return Response({
            'carrier_issues': carrier_issues(),
            'overdue_purchase_orders': overdue_purchase_orders(),
            'orders': SalesOrder.objects.filter(status='출고대기').count(),
            'orders_due': due.summary(SalesOrder.objects.filter(status='출고대기').only('status', 'created_at', 'is_urgent')),
            'purchase_orders': PurchaseOrder.objects.filter(status__in=['발주대기', '입고중']).count(),
            'returns': ReturnOrder.objects.filter(status='회수대기').count(),
            'low_stock': low_stock,
            'replenish': len(replenishment_tasks()),
            'cycle_count': {'todo': len(plan['todo']), 'done': len(plan['done'])},
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
        zone_totals = ItemStock.objects.filter(item__is_active=True, location__is_active=True).values('location__zone').annotate(total=Sum('quantity'))
        for row in zone_totals:
            occupancy_dict[row['location__zone']] = row['total'] or 0
        occupancy_data = [{'zone': k, 'quantity': v} for k, v in occupancy_dict.items()]

        today_start = day_start(timezone.localdate())
        today_count = InventoryLog.objects.filter(timestamp__gte=today_start).count()
        top_moving = InventoryLog.objects.filter(timestamp__gte=thirty_days_ago).values('item__sku', 'item__name').annotate(movements=Count('id')).order_by('-movements')[:5]
        top_moving_data = [{'sku': row['item__sku'], 'name': row['item__name'], 'movements': row['movements']} for row in top_moving]

        return Response({'trend': trend_data, 'occupancy': occupancy_data, 'today_count': today_count, 'top_moving': top_moving_data}, status=status.HTTP_200_OK)


REPORT_MAX_DAYS = 93


WORKS = [name for name, _ in InventoryLog.WORK_CHOICES]


def worker_stats(start, end):
    """기간(날짜 start~end) 동안 작업자별·일자별 작업 실적.
    건수는 문서(발주·주문·반품) 수, 문서가 없는 작업(이동·조정)은 처리한 줄 수입니다."""
    logs = (InventoryLog.objects.filter(timestamp__gte=day_start(start), timestamp__lt=day_start(end + timedelta(days=1)))
            .exclude(work='').values('user_id', 'work', 'reference', 'quantity_changed', 'timestamp', 'description'))
    users = {u.id: u for u in User.objects.filter(id__in={row['user_id'] for row in logs if row['user_id']})}
    return_quantities = dict(ReturnOrder.objects.filter(return_no__in={row['reference'] for row in logs if row['work'] == '반품'})
                             .values_list('return_no', 'quantity'))

    def blank():
        return {work: {'count': 0, 'lines': 0, 'quantity': 0} for work in WORKS}

    workers, daily, refs = {}, {}, set()
    for row in logs:
        uid = row['user_id']
        if uid not in workers:
            user = users.get(uid)
            workers[uid] = {'user_id': uid, 'username': user.username if user else '', 'name': user_display(user) if user else '(기록 없음)',
                            'is_staff': bool(user and user.is_staff), 'works': blank(), 'lines': 0, 'first': None, 'last': None}
        worker, work = workers[uid], row['work']
        cell = worker['works'][work]
        cell['lines'] += 1
        worker['lines'] += 1
        # 문서 번호가 있으면 문서 단위로 한 번만 셉니다.
        key = (uid, work, row['reference'])
        if not row['reference'] or key not in refs:
            refs.add(key)
            cell['count'] += 1
            if work == '반품':
                cell['quantity'] += return_quantities.get(row['reference'], 1)
        if work != '반품':
            cell['quantity'] += abs(row['quantity_changed']) or moved_quantity(row['description'])
        stamp = timezone.localtime(row['timestamp'])
        worker['first'] = min(worker['first'] or stamp, stamp)
        worker['last'] = max(worker['last'] or stamp, stamp)
        day = daily.setdefault((stamp.date(), uid), {'date': stamp.date().isoformat(), 'user_id': uid, 'name': worker['name'],
                                                    'works': {w: 0 for w in WORKS}, 'lines': 0})
        day['works'][work] += 1
        day['lines'] += 1

    rows = sorted(workers.values(), key=lambda w: (-w['lines'], w['name']))
    for worker in rows:
        worker['first'] = worker['first'] and worker['first'].isoformat()
        worker['last'] = worker['last'] and worker['last'].isoformat()
    return rows, sorted(daily.values(), key=lambda d: (d['date'], d['name']))


class WorkerReportAPIView(APIView):
    """작업자별 실적: 기간 안에 누가 어떤 작업을 얼마나 했는지 셉니다."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        end = parse_date_param(request.query_params.get('end_date')) or timezone.localdate()
        start = parse_date_param(request.query_params.get('start_date')) or end - timedelta(days=6)
        if start > end:
            return error_response('시작일이 종료일보다 늦습니다.')
        if (end - start).days >= REPORT_MAX_DAYS:
            return error_response(f'기간은 최대 {REPORT_MAX_DAYS}일까지 조회할 수 있습니다.')
        workers, daily = worker_stats(start, end)
        return Response({'start_date': start.isoformat(), 'end_date': end.isoformat(), 'works': WORKS, 'workers': workers, 'daily': daily})


def daily_summary(day):
    """일일 마감 요약. 처리 실적은 그날 기록으로, 남은 일(backlog)은 계산하는 지금 기준으로 셉니다."""
    start, end = day_start(day), day_start(day + timedelta(days=1))
    logs = InventoryLog.objects.filter(timestamp__gte=start, timestamp__lt=end)

    def work(name):
        rows = logs.filter(work=name)
        return {
            'documents': rows.exclude(reference='').values('reference').distinct().count() + rows.filter(reference='').count(),
            'lines': rows.count(),
            'quantity': abs(rows.aggregate(total=Coalesce(Sum('quantity_changed'), 0))['total']),
        }

    returned = ReturnOrder.objects.filter(status='회수완료', completed_at__gte=start, completed_at__lt=end)
    adjust = logs.filter(work='조정').aggregate(plus=Coalesce(Sum('quantity_changed', filter=Q(quantity_changed__gt=0)), 0),
                                              minus=Coalesce(Sum('quantity_changed', filter=Q(quantity_changed__lt=0)), 0))
    pending_orders = SalesOrder.objects.filter(status='출고대기')
    low_stock = Item.objects.filter(is_active=True, quantity__lte=F('safety_stock')).order_by('quantity', 'sku')
    workers, _ = worker_stats(day, day)
    return {
        'inbound': work('입고'),
        'inbound_cancel': work('입고취소'),
        'outbound': work('출고'),
        'returns': {
            'documents': returned.count(),
            'quantity': returned.aggregate(total=Coalesce(Sum('quantity'), 0))['total'],
            'results': [{'result': row['result'] or '(기록 없음)', 'count': row['n']}
                        for row in returned.values('result').annotate(n=Count('id')).order_by('-n')],
        },
        'moves': logs.filter(work='이동').count(),
        'adjust': {'lines': logs.filter(work='조정').count(), 'plus': adjust['plus'], 'minus': abs(adjust['minus'])},
        'received': {
            'orders': SalesOrder.objects.filter(created_at__gte=start, created_at__lt=end).count(),
            'returns': ReturnOrder.objects.filter(created_at__gte=start, created_at__lt=end).count(),
            'purchase_orders': PurchaseOrder.objects.filter(order_date=day).count(),
        },
        'backlog': {
            'orders': pending_orders.count(),
            'orders_carried': pending_orders.filter(created_at__lt=start).count(),  # 그날 이전에 들어와 아직 못 나간 주문
            'orders_due': due.summary(pending_orders.only('status', 'created_at', 'is_urgent')),
            'pending_orders': [{'order_no': o.order_no, 'customer': o.customer, 'created_at': timezone.localtime(o.created_at).isoformat()}
                               for o in pending_orders.order_by('created_at')[:20]],
            'returns': ReturnOrder.objects.filter(status='회수대기').count(),
            'purchase_orders': PurchaseOrder.objects.filter(status__in=['발주대기', '입고중']).count(),
            'overdue_purchase_orders': overdue_purchase_orders()['count'],
            'carrier_issues': carrier_issues(limit=20),
            'low_stock': {'count': low_stock.count(),
                          'items': [{'sku': i.sku, 'name': i.name, 'quantity': i.quantity, 'safety_stock': i.safety_stock} for i in low_stock[:20]]},
        },
        'workers': [{'name': w['name'], 'username': w['username'], 'lines': w['lines'],
                     'works': {k: v['count'] for k, v in w['works'].items() if v['count']}} for w in workers],
        'calculated_at': timezone.localtime().isoformat(),
    }


def close_message(day, summary, user, note):
    s, b = summary, summary['backlog']
    lines = [
        f'[일일 마감] {day.isoformat()} ({user_display(user)})',
        f"입고 {s['inbound']['documents']}건 {s['inbound']['quantity']}개 · 출고 {s['outbound']['documents']}건 {s['outbound']['quantity']}개 · 반품 회수 {s['returns']['documents']}건",
        f"남은 일: 출고대기 {b['orders']}건(이월 {b['orders_carried']}) · 회수대기 {b['returns']}건 · 입고 지연 {b['overdue_purchase_orders']}건"
        f" · 택배 확인 {b['carrier_issues']['count']}건 · 재고 부족 {b['low_stock']['count']}종",
    ]
    if note:
        lines.append(f'메모: {note}')
    return '\n'.join(lines)


def close_payload(record):
    return {'date': record.date.isoformat(), 'note': record.note, 'closed_by': user_display(record.closed_by) if record.closed_by else '',
            'closed_at': timezone.localtime(record.closed_at).isoformat()}


class DailyCloseAPIView(APIView):
    """GET ?date=: 그날 요약 (마감했으면 마감 때 저장한 내용) / POST {date, note}: 마감 (다시 마감하면 새로 계산해 덮어씀)"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        day = parse_date_param(request.query_params.get('date')) or timezone.localdate()
        record = DailyClose.objects.filter(date=day).select_related('closed_by').first()
        history = [{**close_payload(r), 'outbound': r.summary['outbound']['documents'], 'backlog_orders': r.summary['backlog']['orders']}
                   for r in DailyClose.objects.select_related('closed_by')[:14]]
        return Response({
            'date': day.isoformat(), 'today': timezone.localdate().isoformat(),
            'closed': close_payload(record) if record else None,
            'summary': record.summary if record else daily_summary(day),
            'history': history,
        })

    def post(self, request):
        day = parse_date_param(request.data.get('date')) or timezone.localdate()
        if day > timezone.localdate():
            return error_response('앞으로 올 날짜는 마감할 수 없습니다.')
        note = clean_code(request.data.get('note'))[:200]
        summary = daily_summary(day)
        record, created = DailyClose.objects.update_or_create(date=day, defaults={'summary': summary, 'note': note, 'closed_by': request.user})
        send_webhook_alert(close_message(day, summary, request.user, note))
        return Response({'message': f"{day.isoformat()} {'마감' if created else '다시 마감'} 완료", 'closed': close_payload(record), 'summary': summary})


MOVED_PATTERN = re.compile(r'\] (\d+)개')


def moved_quantity(description):
    # 위치 이동 기록은 재고 수량이 바뀌지 않아(0) 설명의 "… N개"에서 옮긴 개수를 읽습니다.
    match = MOVED_PATTERN.search(description or '')
    return int(match.group(1)) if match else 0


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class CarrierWebhookView(APIView):
    # 택배사가 배송·회수 단계가 바뀔 때마다 호출합니다. 로그인 대신 HMAC 서명으로 확인합니다.
    # WMS가 송장을 취소하는 도중에 그 취소 알림이 바로 들어오면 DB 잠금이 엇갈릴 수 있어, 잠깐 뒤 다시 시도합니다.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not carrier.verify_signature(request.body, request.headers.get('X-Carrier-Signature', '')):
            return Response({'result': 'ERROR', 'message': '서명이 올바르지 않습니다.'}, status=status.HTTP_401_UNAUTHORIZED)
        event = request.data if isinstance(request.data, dict) else {}
        for attempt in range(3):
            try:
                with transaction.atomic():
                    return self.apply(event)
            except OperationalError as exc:
                if exc.args and exc.args[0] in (1213, 1205):  # 교착 상태, 잠금 대기 시간 초과
                    sleep(0.2 * (attempt + 1))
                    continue
                raise
        # 택배사는 5xx 응답이면 나중에 다시 보냅니다.
        return Response({'result': 'ERROR', 'message': '잠시 후 다시 보내 주세요.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def apply(self, event):
        waybill_no = str(event.get('waybill_no') or '')
        record = None
        if waybill_no:
            record = (SalesOrder.objects.select_for_update().filter(waybill_no=waybill_no, bundle_parent__isnull=True).first()
                      or ReturnOrder.objects.select_for_update().filter(waybill_no=waybill_no).first())
        if not record:
            return Response({'result': 'ERROR', 'message': '없는 운송장입니다.'}, status=status.HTTP_404_NOT_FOUND)
        if save_carrier_event(record, event):
            apply_carrier_data(record, {})
        return Response({'result': 'OK'})


class PasswordChangeView(APIView):
    # 로그인한 사람이 자기 비밀번호를 바꿉니다. 현재 비밀번호 추측을 막기 위해 로그인과 같은 횟수 제한을 둡니다.
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        current = str(request.data.get('current_password') or '')
        new = str(request.data.get('new_password') or '')
        user = request.user
        if not user.check_password(current):
            return error_response('현재 비밀번호가 맞지 않습니다.')
        if current == new:
            return error_response('새 비밀번호가 현재 비밀번호와 같습니다.')
        try:
            validate_password(new, user)
        except DjangoValidationError as exc:
            return error_response(' '.join(exc.messages))
        user.set_password(new)
        user.save(update_fields=['password'])
        return Response({'message': '비밀번호를 바꿨습니다. 다음 로그인부터 새 비밀번호를 쓰세요.'})


class UserViewSet(AuditMixin, viewsets.ModelViewSet):
    """관리자가 계정을 만들고 권한·사용 여부를 바꿉니다. 이력을 지키기 위해 삭제 대신 사용 중지합니다."""
    queryset = User.objects.order_by('-is_active', 'username')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def perform_update(self, serializer):
        user = serializer.instance
        if user.is_superuser and not self.request.user.is_superuser:
            raise ValidationError({'error': '최고 관리자 계정은 바꿀 수 없습니다.'})
        if user == self.request.user and (serializer.validated_data.get('is_active') is False or serializer.validated_data.get('is_staff') is False):
            raise ValidationError({'error': '자기 계정의 권한을 내리거나 사용 중지할 수 없습니다. 다른 관리자에게 요청하세요.'})
        serializer.save()

    @action(detail=True, methods=['post'])
    def issue_badge(self, request, pk=None):
        # 사원증 코드를 새로 만듭니다. 다시 발급하면 예전 사원증은 쓸 수 없습니다. 관리자 계정은 비밀번호로만 로그인합니다.
        user = self.get_object()
        if user.is_staff:
            return error_response('관리자 계정은 사원증으로 로그인할 수 없습니다. 현장작업자 계정에 발급하세요.')
        code = 'EMP-' + ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
        WorkerBadge.objects.update_or_create(user=user, defaults={'code': code})
        audit.record(request.user, user, '사원증 발급', after={})
        return Response({'message': f'[{user.username}] 사원증을 발급했습니다. 예전 사원증은 더 이상 쓸 수 없습니다.',
                         'code': code, 'username': user.username, 'name': user.first_name})

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        # 잊어버린 비밀번호를 관리자가 새로 정해 줍니다. 받은 사람은 로그인 후 직접 바꾸게 안내합니다.
        user = self.get_object()
        if user.is_superuser and not request.user.is_superuser:
            return error_response('최고 관리자 계정은 바꿀 수 없습니다.')
        password = str(request.data.get('password') or '')
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return error_response(' '.join(exc.messages))
        user.set_password(password)
        user.save(update_fields=['password'])
        audit.record(request.user, user, '비밀번호 초기화', after={})
        return Response({'message': f'[{user.username}] 비밀번호를 초기화했습니다. 로그인 후 직접 바꾸도록 안내하세요.'})


class BadgeLoginView(APIView):
    """사원증 바코드로 로그인합니다. 현장작업자 계정만 되며, 비밀번호 로그인과 같은 횟수 제한을 둡니다."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        code = clean_code(request.data.get('code'))
        badge = WorkerBadge.objects.select_related('user').filter(code=code).first() if code else None
        user = badge.user if badge else None
        if not user or not user.is_active or user.is_staff:
            return error_response('등록되지 않았거나 쓸 수 없는 사원증입니다.', status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        update_last_login(None, user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'role': '현장작업자',
                         'username': user.username, 'name': user.first_name})
