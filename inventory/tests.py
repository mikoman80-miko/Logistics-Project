from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import InventoryLog, Item, ItemSerial, ItemStock, PurchaseOrder, PurchaseOrderItem, ReturnOrder, SalesOrder, SalesOrderItem, Supplier, WarehouseLocation

ITEMS = '/api/inventory/items/'
SERIALS = '/api/inventory/serials/'
POS = '/api/inventory/purchase-orders/'
ORDERS = '/api/inventory/orders/'
RETURNS = '/api/inventory/returns/'
LOGS = '/api/inventory/logs/'


# 개발 PC의 .env에 택배사 주소가 있어도, 기본 테스트는 택배 연동 없이 실행합니다.
@override_settings(CARRIER_API_URL='')
class BaseCase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('boss', password='pw-strong-1', is_staff=True)
        self.worker = User.objects.create_user('worker', password='pw-strong-2')
        self.item = Item.objects.create(sku='A-1', name='상품A', quantity=5, item_type='부자재', serial_tracked=False)
        self.other = Item.objects.create(sku='B-1', name='상품B', quantity=1, item_type='부자재', serial_tracked=False)


class AuthTests(BaseCase):
    def test_anonymous_is_rejected(self):
        for url in (ITEMS, SERIALS, POS, '/api/inventory/logs/', '/api/inventory/ledger/', '/api/inventory/dashboard/'):
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_login_returns_role_from_account(self):
        res = self.client.post('/api/token/', {'username': 'boss', 'password': 'pw-strong-1'})
        self.assertEqual(res.data['role'], '관리자')
        res = self.client.post('/api/token/', {'username': 'worker', 'password': 'pw-strong-2'})
        self.assertEqual(res.data['role'], '현장작업자')
        self.worker.refresh_from_db()
        self.assertIsNotNone(self.worker.last_login)  # 사용자 관리 화면의 마지막 로그인

    def test_token_refresh(self):
        res = self.client.post('/api/token/', {'username': 'boss', 'password': 'pw-strong-1'})
        res = self.client.post('/api/token/refresh/', {'refresh': res.data['refresh']})
        self.assertEqual(res.status_code, 200)

    def test_any_staff_account_is_admin(self):
        # 사용자 이름이 admin이 아니어도 관리자 계정이면 변경할 수 있어야 합니다.
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(f'{ITEMS}{self.item.id}/', {'name': '변경'}).status_code, 200)

    def test_worker_cannot_change_master_data(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(ITEMS).status_code, 200)
        self.assertEqual(self.client.patch(f'{ITEMS}{self.item.id}/', {'quantity': 999}).status_code, 403)
        self.assertEqual(self.client.delete(f'{ITEMS}{self.item.id}/').status_code, 403)
        self.assertEqual(self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': 5}).status_code, 403)
        self.assertEqual(self.client.post(POS, {'po_number': 'X'}).status_code, 403)
        self.assertEqual(self.client.get('/api/inventory/ledger/').status_code, 403)


class StockTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.worker)

    def test_adjust_stock_cannot_go_negative(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': -6}).status_code, 400)
        res = self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': -5})
        self.assertEqual(res.data['quantity'], 0)

    def test_negative_quantity_rejected(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(f'{ITEMS}{self.item.id}/', {'quantity': -1}).status_code, 400)
        self.assertEqual(self.client.post(ITEMS, {'sku': 'N', 'name': 'n', 'quantity': -1}).status_code, 400)

    def test_database_blocks_negative_quantity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Item.objects.filter(pk=self.item.pk).update(quantity=-1)

    def test_audit_log_description(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(f'{ITEMS}{self.item.id}/', {'quantity': 4, 'physicalQty': 4}, format='json')
        self.assertEqual(InventoryLog.objects.get(item=self.item).description, '월말 재고 실사 조정')


class ScanTests(BaseCase):
    def setUp(self):
        super().setUp()
        Item.objects.filter(pk=self.item.pk).update(serial_tracked=True)
        self.client.force_authenticate(self.worker)

    def scan(self, **data):
        return self.client.post(f'{ITEMS}scan_serial/', data, format='json')

    def test_invalid_type_is_400_not_500(self):
        self.assertEqual(self.scan(sku='A-1', serial_number='S1', type='zzz').status_code, 400)

    def test_missing_serial_is_400(self):
        self.assertEqual(self.scan(sku='A-1', type='in').status_code, 400)

    def test_in_and_out(self):
        self.assertEqual(self.scan(sku='A-1', serial_number='S1', type='in').status_code, 200)
        self.assertEqual(self.scan(sku='A-1', serial_number='S1', type='in').status_code, 400)
        self.assertEqual(self.scan(sku='A-1', serial_number='S1', type='out').status_code, 200)
        self.assertEqual(self.scan(sku='A-1', serial_number='S1', type='out').status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)


class PurchaseOrderTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.po = PurchaseOrder.objects.create(po_number='PO-1')
        self.line = PurchaseOrderItem.objects.create(po=self.po, item=self.item, order_quantity=2)
        self.client.force_authenticate(self.worker)

    def receive(self, **data):
        return self.client.post(f'{POS}{self.po.id}/receive_inbound/', data, format='json')

    def test_receive_until_complete(self):
        self.assertEqual(self.receive(sku='A-1', quantity=1).data['status'], '입고중')
        self.assertEqual(self.receive(sku='A-1', quantity=1).data['status'], '입고완료')
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)

    def test_rejects_invalid_and_over_receipt(self):
        for qty in (-1, 0, 'abc', 3):
            self.assertEqual(self.receive(sku='A-1', quantity=qty).status_code, 400, qty)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

    def test_completed_po_is_closed(self):
        self.receive(sku='A-1', quantity=2)
        self.assertEqual(self.receive(sku='A-1', quantity=1).status_code, 400)


class SerialTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.serial = ItemSerial.objects.create(item=self.item, serial_number='S1', status='재고보유')

    def test_batch_update_syncs_stock(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(f'{SERIALS}batch_update/', {'ids': [self.serial.id], 'status': 'AS진행중', 'quality': '양품B급'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.serial.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual((self.serial.status, self.serial.quality, self.item.quantity), ('AS진행중', '양품B급', 4))

    def test_batch_update_rejects_bad_values(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(f'{SERIALS}batch_update/', {'ids': [self.serial.id], 'status': '없는상태'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_batch_update_is_admin_only(self):
        self.client.force_authenticate(self.worker)
        res = self.client.patch(f'{SERIALS}batch_update/', {'ids': [self.serial.id], 'status': 'AS진행중'}, format='json')
        self.assertEqual(res.status_code, 403)


class CsvTests(BaseCase):
    def upload(self, content, name='a.csv'):
        self.client.force_authenticate(self.admin)
        return self.client.post(f'{ITEMS}upload_csv/', {'file': SimpleUploadedFile(name, content)}, format='multipart')

    def test_excel_utf8_bom_and_cp949(self):
        for sku, encoding in (('C-1', 'utf-8-sig'), ('C-2', 'cp949')):
            res = self.upload(f'SKU,상품명,초기수량\n{sku},이름,3\n'.encode(encoding))
            self.assertEqual(res.status_code, 200, encoding)
            self.assertEqual(Item.objects.get(sku=sku).name, '이름')

    def test_skips_invalid_rows(self):
        res = self.upload('SKU,상품명,초기수량\nD-1,이름,-5\nD-2,이름,abc\nA-1,중복,1\nD-3,정상,1\n'.encode())
        self.assertIn('1건', res.data['message'])
        self.assertIn('3건', res.data['message'])

    def test_missing_header(self):
        self.assertEqual(self.upload('a,b\n1,2\n'.encode()).status_code, 400)

    def test_size_limit(self):
        self.assertEqual(self.upload(b'x' * (5 * 1024 * 1024 + 1)).status_code, 400)


class ReportTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def log_at(self, y, m, d, h, qty):
        log = InventoryLog.objects.create(item=self.item, action='IN' if qty > 0 else 'OUT', quantity_changed=qty)
        InventoryLog.objects.filter(pk=log.pk).update(timestamp=timezone.make_aware(datetime(y, m, d, h)))

    def test_ledger_uses_korean_day_boundary(self):
        self.log_at(2026, 10, 1, 8, 10)  # 한국 시간 10월 1일 오전 8시 (UTC로는 9월 30일)
        self.log_at(2026, 9, 30, 23, 1)
        self.log_at(2026, 10, 1, 9, -4)
        res = self.client.get('/api/inventory/ledger/', {'start_date': '2026-10-01', 'end_date': '2026-10-01'})
        row = next(r for r in res.data if r['sku'] == 'A-1')
        self.assertEqual((row['opening_qty'], row['inbound_qty'], row['outbound_qty'], row['closing_qty']), (1, 10, 4, 7))

    def test_ledger_bad_params(self):
        for params in ({'start_date': '2026-13-45'}, {'start_date': 'abc'}, {'category': 'abc'}):
            self.assertEqual(self.client.get('/api/inventory/ledger/', params).status_code, 400, params)

    def test_dashboard(self):
        loc = WarehouseLocation.objects.create(zone='A', rack='1')
        Item.objects.filter(pk=self.item.pk).update(location=loc)
        ItemStock.objects.create(item=self.item, location=loc, quantity=5)
        InventoryLog.objects.create(item=self.item, action='IN', quantity_changed=3)
        res = self.client.get('/api/inventory/dashboard/')
        self.assertEqual(res.data['trend'][0]['inbound'], 3)
        self.assertEqual(res.data['occupancy'], [{'zone': 'A', 'quantity': 5}])

    def test_dashboard_trend_uses_korean_day(self):
        now = timezone.localtime().replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(days=1)
        previous_night = now - timedelta(hours=9)  # 전날 밤 23시
        for moment, qty in ((now, 7), (previous_night, 2), (now, -3)):
            log = InventoryLog.objects.create(item=self.item, action='IN' if qty > 0 else 'OUT', quantity_changed=qty)
            InventoryLog.objects.filter(pk=log.pk).update(timestamp=moment)
        rows = {r['date']: r for r in self.client.get('/api/inventory/dashboard/').data['trend']}
        self.assertEqual(rows[now.strftime('%Y-%m-%d')], {'date': now.strftime('%Y-%m-%d'), 'inbound': 7, 'outbound': 3})
        self.assertEqual(rows[previous_night.strftime('%Y-%m-%d')]['inbound'], 2)

    def test_abc_analysis(self):
        InventoryLog.objects.create(item=self.item, action='OUT', quantity_changed=-9)
        InventoryLog.objects.create(item=self.other, action='OUT', quantity_changed=-1)
        self.assertEqual(self.client.post(f'{ITEMS}analyze_abc/').status_code, 200)
        self.item.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.other.abc_grade, 'C')


class WebhookTests(BaseCase):
    @patch('inventory.views.requests.post')
    def test_no_webhook_without_url(self, post):
        self.client.force_authenticate(self.admin)
        with self.settings(ALERT_WEBHOOK_URL=''), self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': -5})
        post.assert_not_called()

    @patch('inventory.views.requests.post')
    def test_webhook_sent_after_commit(self, post):
        self.client.force_authenticate(self.admin)
        with self.settings(ALERT_WEBHOOK_URL='https://example.test/hook'), self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': -5})
        post.assert_called_once()


class SalesOrderTests(BaseCase):
    def make_order(self, *lines):
        self.client.force_authenticate(self.admin)
        return self.client.post(ORDERS, {'customer': '고객사', 'items': list(lines)}, format='json')

    def line(self, item, quantity):
        return {'item': item.id, 'quantity': quantity}

    def test_create_assigns_number_and_creator(self):
        res = self.make_order(self.line(self.item, 2))
        self.assertEqual(res.status_code, 201)
        self.assertRegex(res.data['order_no'], r'^ORD-\d{8}-0001$')
        self.assertEqual(res.data['status'], '출고대기')
        self.assertEqual(SalesOrder.objects.get().created_by, self.admin)
        self.assertRegex(self.make_order(self.line(self.item, 1)).data['order_no'], r'-0002$')

    def test_create_validation(self):
        for lines in ([], [self.line(self.item, 0)], [self.line(self.item, 1), self.line(self.item, 2)], [{'item': 99999, 'quantity': 1}]):
            self.assertEqual(self.make_order(*lines).status_code, 400, lines)
        self.assertFalse(SalesOrder.objects.exists())

    def test_worker_cannot_create_or_cancel_but_can_complete(self):
        order_id = self.make_order(self.line(self.item, 2)).data['id']
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.post(ORDERS, {'customer': 'x', 'items': [self.line(self.item, 1)]}, format='json').status_code, 403)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/cancel/').status_code, 403)
        self.assertEqual(self.client.get(ORDERS).status_code, 200)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/complete/').status_code, 400)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/scan/', {'code': 'A-1', 'quantity': 2}, format='json').status_code, 200)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/complete/').status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/complete/').status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_complete_is_all_or_nothing(self):
        Item.objects.filter(pk=self.other.pk).update(quantity=9)
        order_id = self.make_order(self.line(self.item, 2), self.line(self.other, 9)).data['id']
        self.client.post(f'{ORDERS}{order_id}/scan/', {'code': 'A-1', 'quantity': 2}, format='json')
        self.client.post(f'{ORDERS}{order_id}/scan/', {'code': 'B-1', 'quantity': 9}, format='json')
        Item.objects.filter(pk=self.other.pk).update(quantity=1)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/complete/').status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)
        self.assertFalse(InventoryLog.objects.exists())
        self.assertEqual(SalesOrder.objects.get().status, '출고대기')

    def test_cancelled_order_cannot_ship(self):
        order_id = self.make_order(self.line(self.item, 1)).data['id']
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/cancel/').status_code, 200)
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/complete/').status_code, 400)

    def test_status_filter_and_no_edit(self):
        order_id = self.make_order(self.line(self.item, 1)).data['id']
        self.assertEqual(len(self.client.get(ORDERS, {'status': '출고대기'}).data), 1)
        self.assertEqual(len(self.client.get(ORDERS, {'status': '출고완료'}).data), 0)
        self.assertEqual(self.client.delete(f'{ORDERS}{order_id}/').status_code, 405)


class PurchaseOrderCreateTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.supplier = Supplier.objects.create(name='공급사')
        self.client.force_authenticate(self.admin)

    def make(self, lines, supplier=None):
        return self.client.post(POS, {'supplier': supplier or self.supplier.id, 'items': lines}, format='json')

    def test_create_then_receive(self):
        res = self.make([{'item': self.item.id, 'order_quantity': 3}])
        self.assertEqual(res.status_code, 201)
        self.assertRegex(res.data['po_number'], r'^PO-\d{8}-0001$')
        self.assertEqual(res.data['items'][0]['item_sku'], 'A-1')
        self.client.force_authenticate(self.worker)
        res = self.client.post(f"{POS}{res.data['id']}/receive_inbound/", {'sku': 'A-1', 'quantity': 3}, format='json')
        self.assertEqual(res.data['status'], '입고완료')

    def test_create_validation(self):
        for lines in ([], [{'item': self.item.id, 'order_quantity': 0}], [{'item': self.item.id, 'order_quantity': 1}, {'item': self.item.id, 'order_quantity': 1}]):
            self.assertEqual(self.make(lines).status_code, 400, lines)
        self.assertEqual(self.make([{'item': self.item.id, 'order_quantity': 1}], supplier=99999).status_code, 400)

    def test_cannot_set_received_quantity_on_create(self):
        res = self.make([{'item': self.item.id, 'order_quantity': 3, 'received_quantity': 3}])
        self.assertEqual(res.data['items'][0]['received_quantity'], 0)

    def test_cancel_only_before_receiving(self):
        po_id = self.make([{'item': self.item.id, 'order_quantity': 2}]).data['id']
        self.client.post(f'{POS}{po_id}/receive_inbound/', {'sku': 'A-1', 'quantity': 1}, format='json')
        self.assertEqual(self.client.post(f'{POS}{po_id}/cancel/').status_code, 400)
        po_id = self.make([{'item': self.item.id, 'order_quantity': 2}]).data['id']
        self.assertEqual(self.client.post(f'{POS}{po_id}/cancel/').status_code, 200)
        self.assertEqual(self.client.post(f'{POS}{po_id}/receive_inbound/', {'sku': 'A-1', 'quantity': 1}, format='json').status_code, 400)


class ReturnOrderTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.serial = ItemSerial.objects.create(item=self.item, serial_number='S1', status='출고완료')
        self.client.force_authenticate(self.admin)

    def make(self):
        return self.client.post(RETURNS, {'customer': '고객', 'reason': '단순변심', 'serial': self.serial.id}, format='json')

    def test_create_rules(self):
        res = self.make()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['serial_number'], 'S1')
        self.assertEqual(self.make().status_code, 400)
        ItemSerial.objects.filter(pk=self.serial.pk).update(status='재고보유')
        ReturnOrder.objects.all().delete()
        self.assertEqual(self.make().status_code, 400)

    def test_complete_restocks_once(self):
        return_id = self.make().data['id']
        self.client.force_authenticate(self.worker)
        url = f'{RETURNS}{return_id}/complete/'
        self.assertEqual(self.client.post(url, {'status': '재고보유', 'quality': '양품A급'}, format='json').status_code, 200)
        self.item.refresh_from_db()
        self.serial.refresh_from_db()
        self.assertEqual((self.item.quantity, self.serial.status, self.serial.quality), (6, '재고보유', '양품A급'))
        self.assertEqual(self.client.post(url, {'status': '재고보유'}, format='json').status_code, 400)

    def test_defective_does_not_restock(self):
        return_id = self.make().data['id']
        self.client.post(f'{RETURNS}{return_id}/complete/', {'status': '불량폐기', 'quality': '사용불가', 'detail': '파손'}, format='json')
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)
        self.assertEqual(ReturnOrder.objects.get().status, '회수완료')

    def test_worker_cannot_register(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.make().status_code, 403)


class LogQueryTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        InventoryLog.objects.bulk_create([
            InventoryLog(item=self.item if i % 2 else self.other, action='IN' if i % 3 else 'OUT', quantity_changed=1 if i % 3 else -1)
            for i in range(120)
        ])

    def test_paginated_by_default(self):
        res = self.client.get(LOGS)
        self.assertEqual((res.data['count'], len(res.data['results'])), (120, 50))
        self.assertIsNotNone(res.data['next'])
        self.assertEqual(len(self.client.get(LOGS, {'page_size': 9999}).data['results']), 120)

    def test_query_count_does_not_grow_with_rows(self):
        # 저장점 2개 + 건수 1개 + 목록 1개. 행 수와 상품 수에 따라 늘어나지 않아야 합니다.
        with self.assertNumQueries(4):
            self.client.get(LOGS)

    def test_filters(self):
        self.assertEqual(self.client.get(LOGS, {'item': self.item.id}).data['count'], 60)
        self.assertEqual(self.client.get(LOGS, {'action': 'OUT'}).data['count'], 40)
        self.assertEqual(self.client.get(LOGS, {'search': 'B-1'}).data['count'], 60)
        self.assertEqual(self.client.get(LOGS, {'search': '상품A'}).data['count'], 60)
        self.assertEqual(self.client.get(LOGS, {'start_date': '2000-01-01', 'end_date': '2000-01-02'}).data['count'], 0)

    def test_bad_params(self):
        self.assertEqual(self.client.get(LOGS, {'start_date': 'abc'}).status_code, 400)
        self.assertEqual(self.client.get(LOGS, {'item': 'abc'}).status_code, 400)

    def test_export_all_rows_and_blocks_formula(self):
        evil = Item.objects.create(sku='=cmd', name='@evil', quantity=0)
        InventoryLog.objects.create(item=evil, action='NEW', quantity_changed=0)
        res = self.client.get(f'{LOGS}export/')
        text = b''.join(res.streaming_content).decode('utf-8-sig')
        self.assertEqual(len(text.strip().splitlines()), 122)
        self.assertIn("'=cmd", text)
        self.assertIn("'@evil", text)

    def test_export_is_admin_only(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(f'{LOGS}export/').status_code, 403)

    def test_dashboard_summary(self):
        res = self.client.get('/api/inventory/dashboard/')
        self.assertEqual(res.data['today_count'], 120)
        self.assertEqual(res.data['top_moving'][0]['movements'], 60)


class ItemDeleteTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_stock_blocks_delete(self):
        self.assertEqual(self.client.delete(f'{ITEMS}{self.item.id}/').status_code, 400)
        self.assertTrue(Item.objects.get(pk=self.item.pk).is_active)

    def test_delete_keeps_history(self):
        Item.objects.filter(pk=self.item.pk).update(quantity=0)
        InventoryLog.objects.create(item=self.item, action='IN', quantity_changed=1)
        self.assertEqual(self.client.delete(f'{ITEMS}{self.item.id}/').status_code, 204)
        self.assertEqual(InventoryLog.objects.filter(item=self.item).count(), 2)
        self.assertEqual([i['sku'] for i in self.client.get(ITEMS).data], ['B-1'])

    def test_open_order_blocks_delete(self):
        Item.objects.filter(pk=self.item.pk).update(quantity=0)
        order = SalesOrder.objects.create(order_no='O', customer='c')
        SalesOrderItem.objects.create(order=order, item=self.item, quantity=1)
        self.assertEqual(self.client.delete(f'{ITEMS}{self.item.id}/').status_code, 400)

    def test_reregister_stopped_sku(self):
        Item.objects.filter(pk=self.item.pk).update(quantity=0, is_active=False)
        res = self.client.post(ITEMS, {'sku': 'A-1', 'name': '다시', 'quantity': 3})
        self.assertEqual(res.status_code, 201)
        self.item.refresh_from_db()
        self.assertEqual((self.item.is_active, self.item.name, self.item.quantity), (True, '다시', 3))


class SerialRuleTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_type_decides_default_tracking_and_can_change_later(self):
        res = self.client.post(ITEMS, {'sku': 'P', 'name': '상품', 'item_type': '상품'})
        self.assertTrue(res.data['serial_tracked'])
        res = self.client.post(ITEMS, {'sku': 'G', 'name': '사은품', 'item_type': '사은품'})
        self.assertFalse(res.data['serial_tracked'])
        res = self.client.patch(f"{ITEMS}{res.data['id']}/", {'serial_tracked': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['serial_tracked'])
        res = self.client.post(ITEMS, {'sku': 'X', 'name': '예외', 'item_type': '구성품', 'serial_tracked': True})
        self.assertTrue(res.data['serial_tracked'])

    def test_cannot_change_tracking_during_open_order(self):
        order = SalesOrder.objects.create(order_no='O', customer='c')
        SalesOrderItem.objects.create(order=order, item=self.item, quantity=1)
        self.assertEqual(self.client.patch(f'{ITEMS}{self.item.id}/', {'serial_tracked': True}).status_code, 400)
        self.assertEqual(self.client.patch(f'{ITEMS}{self.item.id}/', {'name': '변경'}).status_code, 200)

    def test_tracked_item_blocks_manual_adjust(self):
        Item.objects.filter(pk=self.item.pk).update(serial_tracked=True)
        self.assertEqual(self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': 1}).status_code, 400)

    def test_csv_type_column(self):
        content = 'SKU,상품명,초기수량,구분\nC-1,스티커,3,사은품\nC-2,본품,1,\nC-3,오류,1,없는구분\n'.encode('utf-8-sig')
        res = self.client.post(f'{ITEMS}upload_csv/', {'file': SimpleUploadedFile('a.csv', content)}, format='multipart')
        self.assertIn('2건', res.data['message'])
        self.assertFalse(Item.objects.get(sku='C-1').serial_tracked)
        self.assertTrue(Item.objects.get(sku='C-2').serial_tracked)


class OrderScanTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=2)
        self.s1 = ItemSerial.objects.create(item=self.product, serial_number='SN1')
        self.s2 = ItemSerial.objects.create(item=self.product, serial_number='SN2')
        self.client.force_authenticate(self.admin)
        res = self.client.post(ORDERS, {'customer': 'c', 'items': [{'item': self.product.id, 'quantity': 1}, {'item': self.item.id, 'quantity': 2}]}, format='json')
        self.order = res.data['id']
        self.client.force_authenticate(self.worker)

    def scan(self, code, **extra):
        return self.client.post(f'{ORDERS}{self.order}/scan/', {'code': code, **extra}, format='json')

    def done(self):
        return self.client.post(f'{ORDERS}{self.order}/complete/')

    def test_full_flow_ships_serial_and_stock(self):
        res = self.scan('P-1')
        self.assertTrue(res.data['need_serial'])
        self.assertEqual(self.done().status_code, 400)
        self.assertEqual(self.scan('SN1').status_code, 200)
        self.assertEqual(self.scan('A-1').status_code, 200)
        self.assertEqual(self.scan('A-1').status_code, 200)
        self.assertEqual(self.done().status_code, 200)
        self.s1.refresh_from_db()
        self.s2.refresh_from_db()
        self.product.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual((self.s1.status, self.s2.status), ('출고완료', '재고보유'))
        self.assertEqual((self.product.quantity, self.item.quantity), (1, 3))

    def test_rejects_wrong_codes(self):
        self.assertEqual(self.scan('B-1').status_code, 400)
        self.assertEqual(self.scan('NOPE').status_code, 400)
        other_item = Item.objects.create(sku='Z', name='z', quantity=1)
        ItemSerial.objects.create(item=other_item, serial_number='ZS')
        self.assertEqual(self.scan('ZS').status_code, 400)
        self.assertEqual(self.scan('B-1', sku='P-1').status_code, 400)

    def test_rejects_over_scan_and_duplicate(self):
        self.assertEqual(self.scan('SN1').status_code, 200)
        self.assertEqual(self.scan('SN1').status_code, 400)
        self.assertEqual(self.scan('SN2').status_code, 400)
        self.assertEqual(self.scan('A-1', quantity=3).status_code, 400)
        self.assertEqual(self.scan('A-1', quantity=2).status_code, 200)
        self.assertEqual(self.scan('A-1').status_code, 400)

    def test_shipped_serial_rejected(self):
        ItemSerial.objects.filter(pk=self.s1.pk).update(status='출고완료')
        self.assertEqual(self.scan('SN1').status_code, 400)

    def test_serial_reserved_by_other_open_order(self):
        self.scan('SN1')
        self.client.force_authenticate(self.admin)
        other = self.client.post(ORDERS, {'customer': 'c', 'items': [{'item': self.product.id, 'quantity': 1}]}, format='json').data['id']
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.post(f'{ORDERS}{other}/scan/', {'code': 'SN1'}, format='json').status_code, 400)

    def test_unregistered_serial_only_for_stock_without_serial(self):
        # 재고 2개, 시리얼 2개면 모르는 시리얼은 거부합니다.
        self.assertEqual(self.scan('NEW-SN', sku='P-1').status_code, 400)
        # 시리얼 없는 재고가 생기면 출고하면서 등록합니다.
        Item.objects.filter(pk=self.product.pk).update(quantity=3)
        self.assertEqual(self.scan('NEW-SN', sku='P-1').status_code, 200)
        self.assertEqual(ItemSerial.objects.get(serial_number='NEW-SN').item, self.product)

    def test_reset_line(self):
        res = self.scan('SN1')
        line = next(l for l in res.data['order']['items'] if l['item_sku'] == 'P-1')
        self.assertEqual(line['scanned_serials'], ['SN1'])
        res = self.client.post(f'{ORDERS}{self.order}/reset_line/', {'line': line['id']}, format='json')
        line = next(l for l in res.data['order']['items'] if l['item_sku'] == 'P-1')
        self.assertEqual((line['picked_quantity'], line['scanned_serials']), (0, []))
        self.assertEqual(self.scan('SN1').status_code, 200)

    def test_cancel_releases_serial(self):
        self.scan('SN1')
        self.client.force_authenticate(self.admin)
        self.client.post(f'{ORDERS}{self.order}/cancel/')
        other = self.client.post(ORDERS, {'customer': 'c', 'items': [{'item': self.product.id, 'quantity': 1}]}, format='json').data['id']
        self.assertEqual(self.client.post(f'{ORDERS}{other}/scan/', {'code': 'SN1'}, format='json').status_code, 200)


class InboundSerialTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=0)
        self.po = PurchaseOrder.objects.create(po_number='PO-1')
        PurchaseOrderItem.objects.create(po=self.po, item=self.product, order_quantity=2)
        PurchaseOrderItem.objects.create(po=self.po, item=self.item, order_quantity=3)
        self.client.force_authenticate(self.worker)

    def receive(self, **data):
        return self.client.post(f'{POS}{self.po.id}/receive_inbound/', data, format='json')

    def test_tracked_requires_serial(self):
        self.assertEqual(self.receive(sku='P-1').status_code, 400)
        self.assertEqual(self.receive(sku='P-1', serial_number='SN1', quantity=2).status_code, 400)
        self.assertEqual(self.receive(sku='P-1', serial_number='A-1').status_code, 400)
        self.assertEqual(self.receive(sku='P-1', serial_number='SN1').status_code, 200)
        self.assertEqual(self.receive(sku='P-1', serial_number='SN1').status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 1)
        self.assertEqual(ItemSerial.objects.get(serial_number='SN1').status, '재고보유')

    def test_over_receipt_does_not_create_serial(self):
        self.receive(sku='P-1', serial_number='SN1')
        self.receive(sku='P-1', serial_number='SN2')
        self.assertEqual(self.receive(sku='A-1', serial_number='X').status_code, 400)
        self.assertEqual(self.receive(sku='P-1', serial_number='SN3').status_code, 400)
        self.assertFalse(ItemSerial.objects.filter(serial_number='SN3').exists())

    def test_untracked_takes_quantity(self):
        res = self.receive(sku='A-1', quantity=3)
        self.assertEqual(res.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)
        self.assertEqual(res.data['po']['status'], '입고중')


class TodayTests(BaseCase):
    def test_counts_and_setup(self):
        self.client.force_authenticate(self.worker)
        SalesOrder.objects.create(order_no='O', customer='c')
        PurchaseOrder.objects.create(po_number='P')
        res = self.client.get('/api/inventory/today/')
        self.assertEqual((res.data['orders'], res.data['purchase_orders'], res.data['returns'], res.data['low_stock']), (1, 1, 0, 2))
        self.assertEqual(res.data['setup'], {'locations': False, 'items': True, 'suppliers': False})


class MasterDataEditTests(BaseCase):
    LOCATIONS = '/api/inventory/locations/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_edit_item_keeps_stock_and_sets_safety_stock(self):
        res = self.client.patch(f'{ITEMS}{self.item.id}/', {'name': '새이름', 'safety_stock': 2}, format='json')
        self.assertEqual(res.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual((self.item.name, self.item.safety_stock, self.item.quantity), ('새이름', 2, 5))
        self.assertFalse(InventoryLog.objects.filter(item=self.item).exists())
        self.assertEqual(self.client.patch(f'{ITEMS}{self.item.id}/', {'safety_stock': -1}, format='json').status_code, 400)

    def test_edit_supplier(self):
        supplier = Supplier.objects.create(name='옛거래처')
        res = self.client.patch(f'/api/inventory/suppliers/{supplier.id}/', {'name': '새거래처', 'email': 'a@example.com'}, format='json')
        self.assertEqual(res.status_code, 200)
        supplier.refresh_from_db()
        self.assertEqual((supplier.name, supplier.email), ('새거래처', 'a@example.com'))

    def test_location_code_must_be_unique(self):
        self.assertEqual(self.client.post(self.LOCATIONS, {'zone': 'A', 'rack': 'R1', 'tier': 1}).status_code, 201)
        res = self.client.post(self.LOCATIONS, {'zone': ' A ', 'rack': 'R1', 'tier': 1, 'cell': ''})
        self.assertEqual(res.status_code, 400)
        self.assertIn('A-R1-1단', res.data['error'][0])
        self.assertEqual(self.client.post(self.LOCATIONS, {'zone': 'A', 'rack': 'R1', 'tier': 1, 'cell': 'C1'}).status_code, 201)

    def test_edit_location_allows_itself_but_not_duplicate(self):
        a = WarehouseLocation.objects.create(zone='A', rack='R1', tier=1)
        WarehouseLocation.objects.create(zone='A', rack='R1', tier=2)
        self.assertEqual(self.client.patch(f'{self.LOCATIONS}{a.id}/', {'description': '메모'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'{self.LOCATIONS}{a.id}/', {'tier': 2}, format='json').status_code, 400)

    def test_location_with_stock_cannot_be_deleted(self):
        loc = WarehouseLocation.objects.create(zone='A', rack='R1', tier=1)
        Item.objects.filter(pk=self.item.pk).update(location=loc)
        self.assertEqual(self.client.delete(f'{self.LOCATIONS}{loc.id}/').status_code, 400)
        Item.objects.filter(pk=self.item.pk).update(location=None)
        self.assertEqual(self.client.delete(f'{self.LOCATIONS}{loc.id}/').status_code, 204)


class ReceiptCancelTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=0)
        self.po = PurchaseOrder.objects.create(po_number='PO-1')
        PurchaseOrderItem.objects.create(po=self.po, item=self.product, order_quantity=1)
        PurchaseOrderItem.objects.create(po=self.po, item=self.item, order_quantity=3)
        self.client.force_authenticate(self.worker)

    def receive(self, **data):
        return self.client.post(f'{POS}{self.po.id}/receive_inbound/', data, format='json')

    def cancel(self, **data):
        return self.client.post(f'{POS}{self.po.id}/cancel_receipt/', data, format='json')

    def test_worker_cancels_serial_receipt_even_after_po_completed(self):
        self.receive(sku='P-1', serial_number='SN1')
        self.receive(sku='A-1', quantity=3)
        self.assertEqual(PurchaseOrder.objects.get(pk=self.po.pk).status, '입고완료')
        res = self.cancel(sku='P-1', serial_number='SN1')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], '입고중')
        self.assertFalse(ItemSerial.objects.filter(serial_number='SN1').exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)
        log = InventoryLog.objects.filter(item=self.product).latest('id')
        self.assertEqual((log.quantity_changed, log.user, log.description), (-1, self.worker, '발주번호 PO-1 입고 취소 S/N SN1'))
        # 같은 시리얼을 다시 입고할 수 있습니다.
        self.assertEqual(self.receive(sku='P-1', serial_number='SN1').status_code, 200)

    def test_quantity_cancel_returns_po_to_waiting(self):
        self.receive(sku='A-1', quantity=2)
        self.assertEqual(self.cancel(sku='A-1', quantity=3).status_code, 400)
        res = self.cancel(sku='A-1', quantity=2)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], '발주대기')
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

    def test_rejects_serial_from_elsewhere_or_already_shipped(self):
        ItemSerial.objects.create(item=self.product, serial_number='OTHER')
        self.receive(sku='P-1', serial_number='SN1')
        self.assertEqual(self.cancel(sku='P-1', serial_number='OTHER').status_code, 400)
        ItemSerial.objects.filter(serial_number='SN1').update(status='출고완료')
        self.assertEqual(self.cancel(sku='P-1', serial_number='SN1').status_code, 400)
        self.assertEqual(self.cancel(sku='P-1').status_code, 400)

    def test_legacy_serial_found_by_receipt_log(self):
        self.receive(sku='P-1', serial_number='SN1')
        ItemSerial.objects.filter(serial_number='SN1').update(po_item=None)
        self.assertEqual(self.cancel(sku='P-1', serial_number='SN1').status_code, 200)

    def test_cannot_cancel_more_than_stock(self):
        self.receive(sku='A-1', quantity=3)
        Item.objects.filter(pk=self.item.pk).update(quantity=1)
        self.assertEqual(self.cancel(sku='A-1', quantity=2).status_code, 400)

    def test_po_lists_received_serials(self):
        self.receive(sku='P-1', serial_number='SN1')
        self.client.force_authenticate(self.admin)
        line = next(l for l in self.client.get(f'{POS}{self.po.id}/').data['items'] if l['item_sku'] == 'P-1')
        self.assertEqual(line['received_serials'], ['SN1'])


class LogUserAndSerialAuditTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=3)
        ItemSerial.objects.create(item=self.product, serial_number='SN1')
        ItemSerial.objects.create(item=self.product, serial_number='SN2')

    def test_log_records_user(self):
        self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': 1}, format='json')
        self.assertEqual(self.client.get(LOGS).data['results'][0]['user_name'], 'boss')

    def test_audit_cannot_drop_below_in_stock_serials(self):
        url = f'{ITEMS}{self.product.id}/'
        self.assertEqual(self.client.get(url).data['in_stock_serials'], 2)
        self.assertEqual(self.client.patch(url, {'quantity': 1, 'physicalQty': 1}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'quantity': 2, 'physicalQty': 2}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'quantity': 4, 'physicalQty': 4}, format='json').status_code, 200)


class DocumentFilterTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        supplier = Supplier.objects.create(name='미래전자')
        self.po_old = PurchaseOrder.objects.create(po_number='PO-OLD', supplier=supplier)
        PurchaseOrder.objects.filter(pk=self.po_old.pk).update(order_date=timezone.localdate() - timedelta(days=40))
        self.po_new = PurchaseOrder.objects.create(po_number='PO-NEW')
        PurchaseOrderItem.objects.create(po=self.po_new, item=self.item, order_quantity=1)
        self.order = SalesOrder.objects.create(order_no='ORD-1', customer='가온유통', waybill_no='581111111111')
        SalesOrderItem.objects.create(order=self.order, item=self.other, quantity=1)
        SalesOrder.objects.create(order_no='ORD-2', customer='나래상사', status='출고완료')

    def numbers(self, url, **params):
        res = self.client.get(url, params)
        self.assertEqual(res.status_code, 200, res.data)
        return sorted(row.get('po_number') or row.get('order_no') for row in res.data)

    def test_search_by_number_partner_and_item(self):
        self.assertEqual(self.numbers(POS, q='미래'), ['PO-OLD'])
        self.assertEqual(self.numbers(POS, q='상품A'), ['PO-NEW'])
        self.assertEqual(self.numbers(ORDERS, q='5811111'), ['ORD-1'])
        self.assertEqual(self.numbers(ORDERS, q='B-1'), ['ORD-1'])
        self.assertEqual(self.numbers(ORDERS, q='나래'), ['ORD-2'])
        self.assertEqual(self.numbers(ORDERS, q='나래', status='출고대기'), [])

    def test_date_range(self):
        today = timezone.localdate().isoformat()
        self.assertEqual(self.numbers(POS, start_date=today), ['PO-NEW'])
        self.assertEqual(self.numbers(POS, end_date=(timezone.localdate() - timedelta(days=30)).isoformat()), ['PO-OLD'])
        self.assertEqual(self.numbers(ORDERS, start_date=today, end_date=today), ['ORD-1', 'ORD-2'])
        self.assertEqual(self.client.get(ORDERS, {'start_date': '2026-12-01', 'end_date': '2026-11-01'}).status_code, 400)
        self.assertEqual(self.client.get(ORDERS, {'start_date': 'bad'}).status_code, 400)


class OrderEditTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.order = SalesOrder.objects.create(order_no='ORD-1', customer='고객')
        self.line = SalesOrderItem.objects.create(order=self.order, item=self.item, quantity=1)

    def edit(self, **data):
        return self.client.post(f'{ORDERS}{self.order.id}/edit/', data, format='json')

    def test_edit_fields_and_lines(self):
        res = self.edit(customer='새고객', note='메모', items=[{'item': self.other.id, 'quantity': 2}])
        self.assertEqual(res.status_code, 200, res.data)
        self.order.refresh_from_db()
        self.assertEqual((self.order.customer, self.order.note), ('새고객', '메모'))
        self.assertEqual([(l.item_id, l.quantity) for l in self.order.items.all()], [(self.other.id, 2)])
        self.assertEqual(self.edit(items=[{'item': self.other.id}]).status_code, 400)
        self.assertEqual(self.edit(items=[]).status_code, 400)

    def test_scanned_or_shipped_order_is_locked(self):
        SalesOrderItem.objects.filter(pk=self.line.pk).update(picked_quantity=1)
        self.assertEqual(self.edit(items=[{'item': self.other.id, 'quantity': 1}]).status_code, 400)
        self.assertEqual(self.edit(note='메모만').status_code, 200)
        SalesOrder.objects.filter(pk=self.order.pk).update(status='출고완료')
        self.assertEqual(self.edit(note='x').status_code, 400)

    def test_worker_cannot_edit(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.edit(note='x').status_code, 403)


class SerialHistoryAndLocationBarcodeTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.loc = WarehouseLocation.objects.create(zone='A', rack='R1', tier=1)
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=0, location=self.loc)

    def test_location_barcode_in_lists(self):
        self.assertEqual(self.client.get('/api/inventory/locations/').data[0]['barcode'], f'LOC{self.loc.id:05d}')
        po = PurchaseOrder.objects.create(po_number='PO-1')
        PurchaseOrderItem.objects.create(po=po, item=self.product, order_quantity=1)
        self.assertEqual(self.client.get(f'{POS}{po.id}/').data['items'][0]['location_barcode'], f'LOC{self.loc.id:05d}')
        order = SalesOrder.objects.create(order_no='ORD-1', customer='c')
        SalesOrderItem.objects.create(order=order, item=self.item, quantity=1)
        self.assertIsNone(self.client.get(f'{ORDERS}{order.id}/').data['items'][0].get('location_barcode'))

    def test_serial_history_follows_the_device(self):
        po = PurchaseOrder.objects.create(po_number='PO-1')
        PurchaseOrderItem.objects.create(po=po, item=self.product, order_quantity=1)
        self.client.post(f'{POS}{po.id}/receive_inbound/', {'sku': 'P-1', 'serial_number': 'SN1'}, format='json')
        # 이름이 겹치는 다른 시리얼의 기록은 섞이지 않습니다.
        InventoryLog.objects.create(item=self.product, action='IN', quantity_changed=1, description='발주번호 X 정상 입고 S/N SN10')
        order_id = self.client.post(ORDERS, {'customer': '고객', 'items': [{'item': self.product.id, 'quantity': 1}]}, format='json').data['id']
        self.client.post(f'{ORDERS}{order_id}/scan/', {'code': 'SN1'}, format='json')
        self.assertEqual(self.client.post(f'{ORDERS}{order_id}/complete/').status_code, 200)
        serial = ItemSerial.objects.get(serial_number='SN1')
        ret_id = self.client.post(RETURNS, {'customer': '고객', 'reason': '전원불량', 'serial': serial.id}, format='json').data['id']
        self.client.post(f'{RETURNS}{ret_id}/complete/', {'status': '재고보유', 'quality': '양품A급'}, format='json')

        res = self.client.get(f'{SERIALS}{serial.id}/history/')
        self.assertEqual(res.status_code, 200)
        titles = [e['title'] for e in res.data['events']]
        self.assertEqual(titles, ['입고', '주문 출고', '반품 등록', '반품 회수 완료'])
        self.assertIn('PO-1', res.data['events'][0]['detail'])
        self.assertEqual(res.data['events'][0]['user'], 'boss')

    def test_direct_scan_is_recorded_with_serial(self):
        self.client.post(f'{ITEMS}scan_serial/', {'sku': 'P-1', 'serial_number': 'SN9', 'type': 'in'}, format='json')
        serial = ItemSerial.objects.get(serial_number='SN9')
        self.assertEqual([e['detail'] for e in self.client.get(f'{SERIALS}{serial.id}/history/').data['events']], ['시리얼 직접 입고 S/N SN9'])


class AccountAndMyWorkTests(BaseCase):
    URL = '/api/account/password/'

    def test_change_password(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.post(self.URL, {'current_password': 'wrong', 'new_password': 'Better-pass-77'}).status_code, 400)
        self.assertEqual(self.client.post(self.URL, {'current_password': 'pw-strong-2', 'new_password': '1234'}).status_code, 400)
        res = self.client.post(self.URL, {'current_password': 'pw-strong-2', 'new_password': 'Better-pass-77'})
        self.assertEqual(res.status_code, 200, res.data)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password('Better-pass-77'))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.URL, {}).status_code, 401)

    def test_mine_filter_shows_only_my_logs(self):
        InventoryLog.objects.create(item=self.item, action='IN', quantity_changed=1, user=self.worker)
        InventoryLog.objects.create(item=self.item, action='OUT', quantity_changed=-1, user=self.admin)
        self.client.force_authenticate(self.worker)
        rows = self.client.get(LOGS, {'mine': '1'}).data['results']
        self.assertEqual([r['user_name'] for r in rows], ['worker'])


class AddressImportTests(BaseCase):
    URL = '/api/inventory/orders/import_addresses/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.order = SalesOrder.objects.create(order_no='ORD-1', customer='c', contact_name='김수령', contact_phone='010-1111-2222', zipcode='06236', address='옛 주소')
        SalesOrder.objects.create(order_no='ORD-2', customer='c', status='출고완료')

    def rows(self):
        base = {'contact_name': '김수령', 'contact_phone': '010-1111-2222', 'zipcode': '06236', 'address_detail': ''}
        return [
            {'order_no': 'ORD-1', **base, 'address': '새 주소'},
            {'order_no': 'ORD-2', **base, 'address': '아무 주소'},
            {'order_no': 'ORD-X', **base, 'address': '아무 주소'},
            {'order_no': 'ORD-1', **base, 'zipcode': '12', 'address': '새 주소'},
        ]

    def test_preview_then_apply(self):
        res = self.client.post(self.URL, {'rows': self.rows()}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([r['status'] for r in res.data['rows']], ['ok', 'error', 'error', 'error'])
        self.assertIn('주소: 옛 주소 → 새 주소', res.data['rows'][0]['changes'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.address, '옛 주소')  # 미리보기는 저장하지 않습니다.

        res = self.client.post(self.URL, {'rows': self.rows()[:1], 'apply': True}, format='json')
        self.assertEqual(res.data['counts']['saved'], 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.address, '새 주소')
        res = self.client.post(self.URL, {'rows': self.rows()[:1]}, format='json')
        self.assertEqual(res.data['rows'][0]['status'], 'unchanged')

    def test_rejects_empty_and_worker(self):
        self.assertEqual(self.client.post(self.URL, {'rows': []}, format='json').status_code, 400)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.post(self.URL, {'rows': self.rows()}, format='json').status_code, 403)


class ReorderSuggestionTests(BaseCase):
    URL = '/api/inventory/purchase-orders/suggestions/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_suggests_shortfall_with_usage_incoming_and_last_supplier(self):
        # 상품A: 재고 5, 안전 재고 5, 최근 30일 출고 30개(하루 1개) → 목표 5 + 7 = 12, 발주 중 2개 → 제안 5개
        Item.objects.filter(pk=self.item.pk).update(safety_stock=5)
        InventoryLog.objects.create(item=self.item, action='OUT', quantity_changed=-30)
        old = InventoryLog.objects.create(item=self.item, action='OUT', quantity_changed=-100)
        InventoryLog.objects.filter(pk=old.pk).update(timestamp=timezone.now() - timedelta(days=40))  # 30일 밖은 제외
        supplier = Supplier.objects.create(name='미래전자')
        po = PurchaseOrder.objects.create(po_number='PO-1', supplier=supplier, status='입고중')
        PurchaseOrderItem.objects.create(po=po, item=self.item, order_quantity=3, received_quantity=1)
        # 상품B: 재고 1이지만 안전 재고 0이고 출고가 없으면 제안하지 않습니다.
        Item.objects.filter(pk=self.other.pk).update(safety_stock=0)

        res = self.client.get(self.URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['lead_days'], 7)
        self.assertEqual([(r['sku'], r['suggested'], r['incoming'], r['usage_30d'], r['supplier_name']) for r in res.data['rows']],
                         [('A-1', 5, 2, 30, '미래전자')])

    def test_worker_cannot_see(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(self.URL).status_code, 403)


class UserManagementTests(BaseCase):
    URL = '/api/inventory/users/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_create_change_role_and_deactivate(self):
        res = self.client.post(self.URL, {'username': 'kim', 'name': '김작업', 'role': '현장작업자', 'password': 'Kim-pass-2026'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertNotIn('password', res.data)
        user = User.objects.get(username='kim')
        self.assertTrue(user.check_password('Kim-pass-2026'))
        self.assertFalse(user.is_staff)
        self.assertEqual(self.client.patch(f'{self.URL}{user.id}/', {'role': '관리자', 'is_active': False}, format='json').status_code, 200)
        user.refresh_from_db()
        self.assertEqual((user.is_staff, user.is_active), (True, False))
        self.assertEqual(self.client.patch(f'{self.URL}{user.id}/', {'username': 'lee'}, format='json').status_code, 400)

    def test_rules(self):
        self.assertEqual(self.client.post(self.URL, {'username': 'weak', 'role': '현장작업자', 'password': '1234'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{self.URL}{self.admin.id}/', {'is_active': False}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{self.URL}{self.admin.id}/', {'role': '현장작업자'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'{self.URL}{self.worker.id}/').status_code, 405)
        res = self.client.post(f'{self.URL}{self.worker.id}/reset_password/', {'password': 'Reset-pass-2026'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password('Reset-pass-2026'))
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(self.URL).status_code, 403)


class QuantityReturnTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.order = SalesOrder.objects.create(order_no='ORD-1', customer='고객', status='출고완료', contact_name='김수령', address='서울')
        SalesOrderItem.objects.create(order=self.order, item=self.item, quantity=3, picked_quantity=3)

    def create(self, **data):
        return self.client.post(RETURNS, {'customer': '고객', 'reason': '단순변심', **data}, format='json')

    def test_register_with_order_limits_quantity_and_copies_address(self):
        res = self.create(item=self.item.id, quantity=2, sales_order=self.order.id)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['item_sku'], res.data['quantity'], res.data['order_no'], res.data['contact_name']), ('A-1', 2, 'ORD-1', '김수령'))
        self.assertEqual(self.create(item=self.item.id, quantity=2, sales_order=self.order.id).status_code, 400)  # 남은 1개만 가능
        self.assertEqual(self.create(item=self.other.id, sales_order=self.order.id).status_code, 400)  # 주문에 없는 상품
        self.assertEqual(self.create().status_code, 400)

    def test_serial_item_must_use_serial(self):
        product = Item.objects.create(sku='P-1', name='본품', quantity=0)
        self.assertEqual(self.create(item=product.id).status_code, 400)

    def test_restock_and_dispose(self):
        restock = self.create(item=self.item.id, quantity=2).data['id']
        dispose = self.create(item=self.item.id, quantity=1).data['id']
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.post(f'{RETURNS}{restock}/complete/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.post(f'{RETURNS}{restock}/complete/', {'result': 'restock'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(f'{RETURNS}{dispose}/complete/', {'result': 'dispose', 'label': '폐기'}, format='json').status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)  # 5 + 2, 폐기분은 재고에 넣지 않음
        self.assertEqual(list(ReturnOrder.objects.order_by('id').values_list('result', flat=True)), ['재고로 되돌림', '폐기'])
        self.assertEqual(self.client.post(f'{RETURNS}{restock}/complete/', {'result': 'restock'}, format='json').status_code, 400)


class ScanAuditTests(BaseCase):
    URL = f'{ITEMS}audit_scan/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.loc = WarehouseLocation.objects.create(zone='A', rack='R1', tier=1)
        Item.objects.filter(pk=self.item.pk).update(location=self.loc)  # 수량 상품 A-1 (재고 5, 이 위치)
        ItemStock.objects.create(item=self.item, location=self.loc, quantity=5)
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=3, location=self.loc)
        ItemStock.objects.create(item=self.product, location=self.loc, quantity=3)
        for no in ('SN1', 'SN2', 'SN3'):
            ItemSerial.objects.create(item=self.product, serial_number=no, location=self.loc)
        ItemSerial.objects.create(item=self.product, serial_number='SN-OUT', status='출고완료')

    def scan(self, codes, **extra):
        return self.client.post(self.URL, {'location': self.loc.id, 'codes': codes, **extra}, format='json')

    def test_preview_compares_counts_and_serials(self):
        res = self.scan(['A-1', 'A-1', 'A-1', 'SN1', 'SN1', 'SN2', 'SN-OUT', 'P-1', 'B-1', 'NOPE'])
        self.assertEqual(res.status_code, 200)
        rows = {r['sku']: r for r in res.data['rows']}
        self.assertEqual((rows['A-1']['system'], rows['A-1']['counted']), (5, 3))
        self.assertEqual((rows['P-1']['system'], rows['P-1']['counted'], rows['P-1']['missing'], rows['P-1']['unexpected']),
                         (3, 3, ['SN3'], ['SN-OUT (출고완료)']))
        self.assertTrue(rows['B-1']['new_here'])  # 이 위치에 기록이 없던 상품 (미지정 재고 1개)
        self.assertEqual(res.data['unknown'], ['NOPE'])
        self.assertEqual(len(res.data['warnings']), 1)  # 시리얼 상품을 상품코드로 스캔
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)  # 미리보기는 바꾸지 않습니다.

    def test_apply_adjusts_quantity_and_marks_missing(self):
        res = self.scan(['A-1', 'A-1', 'SN1', 'SN2', 'B-1'], apply=True, mark_missing=True)
        self.assertEqual(res.status_code, 200)
        self.item.refresh_from_db()
        self.other.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((self.item.quantity, self.other.quantity, self.product.quantity), (2, 1, 2))
        self.assertEqual(ItemSerial.objects.get(serial_number='SN3').status, '분실')
        self.assertEqual(InventoryLog.objects.filter(item=self.item).latest('id').quantity_changed, -3)
        # B-1은 위치를 모르던 1개를 여기서 찾은 것이라 총재고는 그대로 두고 위치만 기록합니다.
        self.assertEqual(ItemStock.objects.get(item=self.other, location=self.loc).quantity, 1)
        self.assertFalse(InventoryLog.objects.filter(item=self.other).exists())

    def test_rules(self):
        self.assertEqual(self.client.post(self.URL, {'codes': []}, format='json').status_code, 400)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.scan(['A-1']).status_code, 403)


class PartialShipmentTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.order = SalesOrder.objects.create(order_no='ORD-1', customer='고객', note='문 앞', contact_name='김수령', address='서울')
        self.line_a = SalesOrderItem.objects.create(order=self.order, item=self.item, quantity=3, picked_quantity=2)
        self.line_b = SalesOrderItem.objects.create(order=self.order, item=self.other, quantity=1, picked_quantity=0)

    def complete(self, **data):
        return self.client.post(f'{ORDERS}{self.order.id}/complete/', data, format='json')

    def test_partial_ships_scanned_and_creates_backorder(self):
        self.assertEqual(self.complete().status_code, 400)  # 보통 출고는 모두 스캔해야 합니다.
        res = self.complete(partial=True)
        self.assertEqual(res.status_code, 200, res.data)
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.order.status, '출고완료')
        self.assertEqual([(l.item_id, l.quantity) for l in self.order.items.all()], [(self.item.id, 2)])
        self.assertEqual((self.item.quantity, self.other.quantity), (3, 1))
        back = SalesOrder.objects.get(split_from=self.order)
        self.assertIn(back.order_no, res.data['message'])
        self.assertEqual((back.status, back.contact_name, back.note), ('출고대기', '김수령', 'ORD-1의 남은 수량 / 문 앞'))
        self.assertEqual(sorted((l.item_id, l.quantity) for l in back.items.all()), sorted([(self.item.id, 1), (self.other.id, 1)]))
        self.assertEqual(self.client.get(f'{ORDERS}{back.id}/').data['split_from_no'], 'ORD-1')

    def test_partial_needs_a_scan_and_no_bundle(self):
        SalesOrderItem.objects.filter(order=self.order).update(picked_quantity=0)
        self.assertEqual(self.complete(partial=True).status_code, 400)
        SalesOrderItem.objects.filter(pk=self.line_a.pk).update(picked_quantity=1)
        other = SalesOrder.objects.create(order_no='ORD-2', customer='고객', bundle_parent=self.order)
        self.assertEqual(self.complete(partial=True).status_code, 400)
        other.delete()
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.complete(partial=True).status_code, 200)


class OverduePurchaseOrderTests(BaseCase):
    def test_today_lists_overdue_and_command_alerts(self):
        today = timezone.localdate()
        late = PurchaseOrder.objects.create(po_number='PO-LATE', expected_date=today - timedelta(days=3), status='입고중')
        PurchaseOrder.objects.create(po_number='PO-OK', expected_date=today)
        PurchaseOrder.objects.create(po_number='PO-DONE', expected_date=today - timedelta(days=9), status='입고완료')
        self.client.force_authenticate(self.admin)
        overdue = self.client.get('/api/inventory/today/').data['overdue_purchase_orders']
        self.assertEqual((overdue['count'], overdue['items'][0]['po_number'], overdue['items'][0]['days']), (1, 'PO-LATE', 3))

        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        with patch('inventory.management.commands.notify_overdue.send_webhook_alert') as send:
            call_command('notify_overdue', stdout=out)
        self.assertIn('PO-LATE', send.call_args[0][0])
        self.assertIn('3일 지남', out.getvalue())
        late.delete()
        with patch('inventory.management.commands.notify_overdue.send_webhook_alert') as send:
            call_command('notify_overdue', stdout=StringIO())
        send.assert_not_called()


class LocationStockTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.a = WarehouseLocation.objects.create(zone='A', rack='R1', tier=1)
        self.b = WarehouseLocation.objects.create(zone='B', rack='R1', tier=1)
        Item.objects.filter(pk=self.item.pk).update(location=self.a)
        self.item.refresh_from_db()
        ItemStock.objects.create(item=self.item, location=self.a, quantity=5)
        self.product = Item.objects.create(sku='P-1', name='본품', quantity=0, location=self.a)

    def stocks(self, item):
        return {s.location.full_code: s.quantity for s in ItemStock.objects.filter(item=item, quantity__gt=0).select_related('location')}

    def test_receive_to_default_or_scanned_location(self):
        po = PurchaseOrder.objects.create(po_number='PO-1')
        PurchaseOrderItem.objects.create(po=po, item=self.product, order_quantity=2)
        PurchaseOrderItem.objects.create(po=po, item=self.item, order_quantity=3)
        url = f'{POS}{po.id}/receive_inbound/'
        self.client.post(url, {'sku': 'P-1', 'serial_number': 'SN1'}, format='json')
        self.client.post(url, {'sku': 'P-1', 'serial_number': 'SN2', 'location': self.b.id}, format='json')
        self.client.post(url, {'sku': 'A-1', 'quantity': 3, 'location': self.b.id}, format='json')
        self.assertEqual(self.stocks(self.product), {'A-R1-1단': 1, 'B-R1-1단': 1})
        self.assertEqual(ItemSerial.objects.get(serial_number='SN2').location, self.b)
        self.assertEqual(self.stocks(self.item), {'A-R1-1단': 5, 'B-R1-1단': 3})
        # 입고 취소는 그 기기가 있던 위치에서 뺍니다.
        self.client.post(f'{POS}{po.id}/cancel_receipt/', {'sku': 'P-1', 'serial_number': 'SN2'}, format='json')
        self.assertEqual(self.stocks(self.product), {'A-R1-1단': 1})

    def test_shipping_takes_from_serial_location_then_default(self):
        ItemStock.objects.create(item=self.item, location=self.b, quantity=4)
        Item.objects.filter(pk=self.item.pk).update(quantity=9)
        order = SalesOrder.objects.create(order_no='ORD-1', customer='c')
        SalesOrderItem.objects.create(order=order, item=self.item, quantity=7, picked_quantity=7)
        self.assertEqual(self.client.post(f'{ORDERS}{order.id}/complete/').status_code, 200)
        self.assertEqual(self.stocks(self.item), {'B-R1-1단': 2})  # 기본 위치 A에서 5개, 나머지 2개는 B에서

        line = self.client.get(f'{ORDERS}{order.id}/').data['items'][0]
        self.assertEqual([(s['location_name'], s['quantity']) for s in line['stock_locations']], [('B-R1-1단', 2)])

    def test_move_stock_and_change_default(self):
        res = self.client.post(f'{ITEMS}{self.item.id}/move_stock/', {'from': self.a.id, 'to': self.b.id, 'quantity': 2}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(self.stocks(self.item), {'A-R1-1단': 3, 'B-R1-1단': 2})
        self.assertEqual(self.client.post(f'{ITEMS}{self.item.id}/move_stock/', {'from': self.a.id, 'to': self.b.id, 'quantity': 9}, format='json').status_code, 400)
        data = self.client.get(f'{ITEMS}{self.item.id}/').data
        self.assertEqual(([s['location_name'] for s in data['stocks']], data['unassigned']), (['A-R1-1단', 'B-R1-1단'], 0))

        # 시리얼 상품은 시리얼로 옮깁니다.
        ItemSerial.objects.create(item=self.product, serial_number='SN1', location=self.a)
        ItemStock.objects.create(item=self.product, location=self.a, quantity=1)
        Item.objects.filter(pk=self.product.pk).update(quantity=1)
        self.assertEqual(self.client.post(f'{ITEMS}{self.product.id}/move_stock/', {'from': self.a.id, 'to': self.b.id, 'quantity': 1}, format='json').status_code, 400)
        self.assertEqual(self.client.post(f'{ITEMS}{self.product.id}/move_stock/', {'from': self.a.id, 'to': self.b.id, 'serials': ['SN1']}, format='json').status_code, 200)
        self.assertEqual(ItemSerial.objects.get(serial_number='SN1').location, self.b)

        # 기본 위치를 바꾸면 그 위치에 있던 재고가 함께 옮겨집니다.
        self.client.post(f'{ITEMS}{self.item.id}/transfer_location/', {'new_location_id': self.b.id}, format='json')
        self.assertEqual(self.stocks(self.item), {'B-R1-1단': 5})

    def test_location_with_stock_cannot_be_deleted(self):
        Item.objects.filter(pk__in=[self.item.pk, self.product.pk]).update(location=self.b)  # 기본 위치는 모두 B로
        self.assertEqual(self.client.delete(f'/api/inventory/locations/{self.a.id}/').status_code, 400)
        self.client.post(f'{ITEMS}{self.item.id}/move_stock/', {'from': self.a.id, 'to': self.b.id, 'quantity': 5}, format='json')
        self.assertEqual(self.client.delete(f'/api/inventory/locations/{self.a.id}/').status_code, 204)

    def test_adjust_and_return_follow_default_location(self):
        self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': -2}, format='json')
        self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': 4}, format='json')
        self.assertEqual(self.stocks(self.item), {'A-R1-1단': 7})


class BadgeLoginTests(BaseCase):
    URL = '/api/token/badge/'

    def issue(self, user):
        self.client.force_authenticate(self.admin)
        res = self.client.post(f'/api/inventory/users/{user.id}/issue_badge/')
        self.client.force_authenticate(None)
        return res

    def test_worker_logs_in_with_badge_and_reissue_invalidates_old(self):
        old = self.issue(self.worker).data['code']
        self.assertRegex(old, r'^EMP-[A-Z2-9]{12}$')
        res = self.client.post(self.URL, {'code': old})
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data['role'], res.data['username']), ('현장작업자', 'worker'))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.assertEqual(self.client.get('/api/inventory/today/').status_code, 200)
        self.client.credentials()
        new = self.issue(self.worker).data['code']
        self.assertEqual(self.client.post(self.URL, {'code': old}).status_code, 401)
        self.assertEqual(self.client.post(self.URL, {'code': new}).status_code, 200)

    def test_admin_and_inactive_cannot_use_badge(self):
        self.assertEqual(self.issue(self.admin).status_code, 400)
        code = self.issue(self.worker).data['code']
        User.objects.filter(pk=self.worker.pk).update(is_active=False)
        self.assertEqual(self.client.post(self.URL, {'code': code}).status_code, 401)
        self.assertEqual(self.client.post(self.URL, {'code': 'EMP-WRONG'}).status_code, 401)


class WorkerReportTests(BaseCase):
    URL = '/api/inventory/reports/workers/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def ship(self, quantity):
        order = self.client.post(ORDERS, {'customer': '고객', 'items': [{'item': self.item.id, 'quantity': quantity}]}, format='json').data
        self.client.force_authenticate(self.worker)
        self.client.post(f'{ORDERS}{order["id"]}/scan/', {'code': 'A-1', 'quantity': quantity}, format='json')
        self.assertEqual(self.client.post(f'{ORDERS}{order["id"]}/complete/').status_code, 200)
        self.client.force_authenticate(self.admin)
        return order

    def test_counts_documents_per_worker(self):
        order = self.ship(2)
        self.ship(1)
        log = InventoryLog.objects.filter(work='출고').first()
        self.assertEqual((log.user, log.reference), (self.worker, order['order_no']))
        # 관리자가 직접 수량 조정
        self.client.post(f'{ITEMS}{self.item.id}/adjust_stock/', {'change': 4}, format='json')
        # 반품 회수: 폐기해도 실적에 남습니다.
        ret = self.client.post(RETURNS, {'customer': '고객', 'reason': '파손', 'item': self.item.id, 'quantity': 2}, format='json').data
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.post(f'{RETURNS}{ret["id"]}/complete/', {'result': 'dispose'}, format='json').status_code, 200)
        self.client.force_authenticate(self.admin)

        res = self.client.get(self.URL)
        self.assertEqual(res.status_code, 200)
        rows = {row['username']: row for row in res.data['workers']}
        worker = rows['worker']['works']
        self.assertEqual((worker['출고']['count'], worker['출고']['quantity']), (2, 3))
        self.assertEqual((worker['반품']['count'], worker['반품']['quantity']), (1, 2))
        self.assertEqual((rows['boss']['works']['조정']['count'], rows['boss']['works']['조정']['quantity']), (1, 4))
        self.assertEqual(sum(day['lines'] for day in res.data['daily']), 4)

    def test_serial_return_without_restock_is_recorded(self):
        serial = ItemSerial.objects.create(item=self.item, serial_number='S9', status='출고완료')
        ret = self.client.post(RETURNS, {'customer': '고객', 'reason': '불량', 'serial': serial.id}, format='json').data
        self.client.post(f'{RETURNS}{ret["id"]}/complete/', {'status': 'AS진행중'}, format='json')
        log = InventoryLog.objects.get(work='반품')
        self.assertEqual((log.action, log.quantity_changed, log.reference), ('RETURN', 0, ret['return_no']))

    def test_move_counts_moved_quantity(self):
        a = WarehouseLocation.objects.create(zone='A', rack='R1', tier=1)
        b = WarehouseLocation.objects.create(zone='A', rack='R2', tier=1)
        ItemStock.objects.create(item=self.item, location=a, quantity=5)
        res = self.client.post(f'{ITEMS}{self.item.id}/move_stock/', {'from': a.id, 'to': b.id, 'quantity': 3}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        boss = self.client.get(self.URL).data['workers'][0]
        self.assertEqual((boss['works']['이동']['count'], boss['works']['이동']['quantity']), (1, 3))

    def test_period_and_permission(self):
        self.ship(1)
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get(self.URL, {'start_date': yesterday, 'end_date': yesterday}).data['workers'], [])
        self.assertEqual(self.client.get(self.URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'}).status_code, 400)
        self.assertEqual(self.client.get(self.URL, {'start_date': '2026-02-01', 'end_date': '2026-01-01'}).status_code, 400)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(self.URL).status_code, 403)
