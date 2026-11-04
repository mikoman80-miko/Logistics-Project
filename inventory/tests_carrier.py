"""택배 연동 테스트. 가상 택배사 서버를 실제로 띄워 HTTP로 통신합니다."""
import hashlib
import hmac
import importlib.util
import json
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.test import LiveServerTestCase, override_settings
from rest_framework.test import APITestCase

from . import carrier
from .models import Item, ItemSerial, ReturnOrder, SalesOrder, SalesOrderItem, SalesOrderSerial

ORDERS = '/api/inventory/orders/'
RETURNS = '/api/inventory/returns/'
WEBHOOK = '/api/carrier/webhook/'
SECRET = 'test-webhook-secret'
API_KEY = 'test-carrier-key'
ADDRESS = {'contact_name': '김수령', 'contact_phone': '010-1234-5678', 'zipcode': '06236', 'address': '서울시 강남구 테헤란로 1', 'address_detail': '101호'}


def load_mock_server():
    path = Path(settings.BASE_DIR) / 'mock_carrier' / 'server.py'
    spec = importlib.util.spec_from_file_location('mock_carrier_server', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CarrierCase(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mock = load_mock_server()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.mock.DB_PATH = Path(cls.tmp.name) / 'carrier.sqlite3'
        cls.mock.API_KEY = API_KEY
        cls.mock.init_db()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), cls.mock.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_address[1]}'
        cls.settings_override = override_settings(CARRIER_API_URL=cls.url, CARRIER_API_KEY=API_KEY, CARRIER_WEBHOOK_SECRET=SECRET, CARRIER_CALLBACK_URL='')
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user('boss', password='pw-strong-1', is_staff=True)
        self.item = Item.objects.create(sku='A-1', name='상품A', quantity=5, item_type='부자재', serial_tracked=False)
        self.client.force_authenticate(self.admin)

    def create_order(self, **address):
        return self.client.post(ORDERS, {'customer': '고객', 'items': [{'item': self.item.id, 'quantity': 1}], **(address or ADDRESS)}, format='json')

    def advance(self, waybill_no):
        # 시연용 API로 택배 단계를 한 칸 진행합니다.
        res = requests.post(f'{self.url}/v1/simulate/{waybill_no}/advance', headers={'X-API-Key': API_KEY}, timeout=5)
        self.assertEqual(res.status_code, 200, res.text)


class OrderShippingTests(CarrierCase):
    def test_order_gets_waybill_and_collection_starts_after_shipping(self):
        res = self.create_order()
        self.assertEqual(res.status_code, 201, res.data)
        order = SalesOrder.objects.get(pk=res.data['id'])
        self.assertTrue(order.waybill_no.startswith('58'))
        self.assertEqual(order.carrier_status, '접수')

        SalesOrderItem.objects.filter(order=order).update(picked_quantity=1)
        self.assertEqual(self.client.post(f'{ORDERS}{order.id}/complete/').status_code, 200)
        self.advance(order.waybill_no)
        res = self.client.post(f'{ORDERS}{order.id}/track/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['order']['carrier_status'], '집하')
        self.assertEqual([e['status'] for e in res.data['order']['carrier_events']], ['접수', '집하'])
        self.assertIn(f'/track/{order.waybill_no}', res.data['order']['tracking_url'])

    def test_address_is_required_and_checked(self):
        self.assertEqual(self.client.post(ORDERS, {'customer': '고객', 'items': [{'item': self.item.id, 'quantity': 1}]}, format='json').status_code, 400)
        self.assertEqual(self.create_order(**{**ADDRESS, 'zipcode': '123'}).status_code, 400)
        self.assertEqual(self.create_order(**{**ADDRESS, 'contact_phone': '12345'}).status_code, 400)

    def test_rejected_address_keeps_order_and_can_retry(self):
        res = self.create_order(**{**ADDRESS, 'address': '없는주소 1번지'})
        self.assertEqual(res.status_code, 201)
        order = SalesOrder.objects.get(pk=res.data['id'])
        self.assertEqual(order.waybill_no, '')
        self.assertIn('주소를 확인할 수 없습니다', order.carrier_error)

        res = self.client.post(f'{ORDERS}{order.id}/issue_waybill/', {'address': '서울시 중구 세종대로 110'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['order']['carrier_error'], '')
        self.assertTrue(res.data['order']['waybill_no'])
        self.assertEqual(self.client.post(f'{ORDERS}{order.id}/issue_waybill/').status_code, 400)

    def test_cancel_order_cancels_waybill(self):
        order = SalesOrder.objects.get(pk=self.create_order().data['id'])
        self.assertEqual(self.client.post(f'{ORDERS}{order.id}/cancel/').status_code, 200)
        order.refresh_from_db()
        self.assertEqual((order.status, order.carrier_status), ('취소됨', '취소'))

    @override_settings(CARRIER_API_URL='http://127.0.0.1:9')
    def test_carrier_down_keeps_order(self):
        res = self.create_order()
        self.assertEqual(res.status_code, 201)
        self.assertIn('연결할 수 없습니다', SalesOrder.objects.get(pk=res.data['id']).carrier_error)


class ReturnPickupTests(CarrierCase):
    def setUp(self):
        super().setUp()
        product = Item.objects.create(sku='P-1', name='본품', quantity=0)
        self.serial = ItemSerial.objects.create(item=product, serial_number='SN1', status='출고완료')
        order = SalesOrder.objects.create(order_no='ORD-1', customer='고객', status='출고완료', **ADDRESS)
        line = SalesOrderItem.objects.create(order=order, item=product, quantity=1, picked_quantity=1)
        SalesOrderSerial.objects.create(line=line, serial=self.serial)

    def test_return_copies_order_address_and_requests_pickup(self):
        res = self.client.post(RETURNS, {'customer': '고객', 'reason': '전원불량', 'serial': self.serial.id}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        ret = ReturnOrder.objects.get(pk=res.data['id'])
        self.assertEqual((ret.contact_name, ret.address, ret.carrier_status), ('김수령', ADDRESS['address'], '회수접수'))

        self.advance(ret.waybill_no)
        res = self.client.post(f'{RETURNS}{ret.id}/cancel/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('택배사 취소 실패', res.data['error'])
        ret.refresh_from_db()
        self.assertEqual(ret.status, '회수대기')

    def test_cancel_before_pickup(self):
        ret_id = self.client.post(RETURNS, {'customer': '고객', 'reason': '단순변심', 'serial': self.serial.id}, format='json').data['id']
        self.assertEqual(self.client.post(f'{RETURNS}{ret_id}/cancel/').status_code, 200)
        self.assertEqual(ReturnOrder.objects.get(pk=ret_id).carrier_status, '취소')


class WebhookTests(CarrierCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(None)
        self.order = SalesOrder.objects.create(order_no='ORD-1', customer='고객', waybill_no='581234567890', carrier_status='접수', **ADDRESS)

    def post_event(self, event, secret=SECRET):
        body = json.dumps(event).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.generic('POST', WEBHOOK, body, content_type='application/json', HTTP_X_CARRIER_SIGNATURE=signature)

    def event(self, status, event_id, at):
        return {'event_id': event_id, 'waybill_no': '581234567890', 'status': status, 'location': '중앙 허브', 'occurred_at': at}

    def test_signed_events_update_status_once_and_in_time_order(self):
        self.assertEqual(self.post_event(self.event('배송중', 'e2', '2026-11-04T10:00:00+09:00')).status_code, 200)
        self.assertEqual(self.post_event(self.event('배송중', 'e2', '2026-11-04T10:00:00+09:00')).status_code, 200)
        # 늦게 도착한 이전 단계 알림은 상태를 되돌리지 않습니다.
        self.assertEqual(self.post_event(self.event('집하', 'e1', '2026-11-04T09:00:00+09:00')).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.carrier_status, '배송중')
        self.assertEqual(self.order.carrier_events.count(), 2)

    def test_rejects_bad_signature_and_unknown_waybill(self):
        self.assertEqual(self.post_event(self.event('집하', 'e1', '2026-11-04T09:00:00+09:00'), secret='wrong').status_code, 401)
        self.assertEqual(self.post_event({**self.event('집하', 'e1', '2026-11-04T09:00:00+09:00'), 'waybill_no': '000'}).status_code, 404)


class LiveWebhookTests(LiveServerTestCase):
    """가상 택배사가 실제로 WMS 웹훅 주소를 호출해 상태가 바뀌는지 확인합니다."""

    def test_carrier_pushes_status_to_wms(self):
        mock = load_mock_server()
        with tempfile.TemporaryDirectory() as tmp:
            mock.DB_PATH = Path(tmp) / 'carrier.sqlite3'
            mock.API_KEY, mock.WEBHOOK_SECRET = API_KEY, SECRET
            mock.init_db()
            server = ThreadingHTTPServer(('127.0.0.1', 0), mock.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = f'http://127.0.0.1:{server.server_address[1]}'
            try:
                with override_settings(CARRIER_API_URL=url, CARRIER_API_KEY=API_KEY, CARRIER_WEBHOOK_SECRET=SECRET,
                                       CARRIER_CALLBACK_URL=f'{self.live_server_url}{WEBHOOK}'):
                    order = SalesOrder.objects.create(order_no='ORD-LIVE', customer='고객', **ADDRESS)
                    order.waybill_no = carrier.create_shipment(order)['waybill_no']
                    order.save()
                    requests.post(f'{url}/v1/simulate/{order.waybill_no}/advance', headers={'X-API-Key': API_KEY}, timeout=5).raise_for_status()
                    for _ in range(50):
                        order.refresh_from_db()
                        if order.carrier_status == '집하':
                            break
                        time.sleep(0.1)
                    self.assertEqual(order.carrier_status, '집하')
            finally:
                server.shutdown()
                server.server_close()


class CarrierPagesTests(CarrierCase):
    """가온택배 웹 화면: 배송 조회(개인정보 가림), 콘솔 조작, 웹훅 기록, API 문서"""

    def page(self, path, **kwargs):
        return requests.get(f'{self.url}{path}', timeout=5, **kwargs)

    def test_tracking_page_masks_personal_info(self):
        waybill_no = SalesOrder.objects.get(pk=self.create_order().data['id']).waybill_no
        res = self.page(f'/track?no={waybill_no}', allow_redirects=False)
        self.assertEqual((res.status_code, res.headers['Location']), (303, f'/track/{waybill_no}'))
        html = self.page(f'/track/{waybill_no}').text
        self.assertIn('김*령', html)
        self.assertIn('010-****-5678', html)
        self.assertNotIn('010-1234-5678', html)
        self.assertNotIn('테헤란로', html)
        self.assertEqual(self.page('/track/000').status_code, 404)
        self.assertIn('찾을 수 없습니다', self.page('/track?no=12').text)

    def test_console_search_and_finish(self):
        order = SalesOrder.objects.get(pk=self.create_order().data['id'])
        self.assertIn(order.waybill_no, self.page('/console', params={'q': order.order_no}).text)
        self.assertNotIn(order.waybill_no, self.page('/console', params={'q': '없는번호'}).text)
        res = requests.post(f'{self.url}/console/finish/{order.waybill_no}', data={'back': 'https://evil.example'}, allow_redirects=False, timeout=5)
        self.assertEqual((res.status_code, res.headers['Location']), (303, '/console'))
        self.client.post(f'{ORDERS}{order.id}/track/')
        order.refresh_from_db()
        self.assertEqual(order.carrier_status, '배송완료')

    def test_bad_body_gets_json_error(self):
        for body in ('{"order_ref":"한글"}'.encode('cp949'), b'not json'):
            res = requests.post(f'{self.url}/v1/shipments', data=body, headers={'X-API-Key': API_KEY}, timeout=5)
            self.assertEqual((res.status_code, res.json()['code']), (400, 'INVALID_JSON'))

    def test_other_pages(self):
        self.assertEqual(self.page('/').status_code, 200)
        self.assertEqual(self.page('/webhooks').status_code, 200)
        self.assertIn('/v1/shipments', self.page('/docs').text)


class OrderEditCarrierTests(CarrierCase):
    def test_address_change_reissues_waybill(self):
        order = SalesOrder.objects.get(pk=self.create_order().data['id'])
        old = order.waybill_no
        res = self.client.post(f'{ORDERS}{order.id}/edit/', {'address': '서울시 중구 세종대로 110'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        new = res.data['order']['waybill_no']
        self.assertTrue(new and new != old)
        self.assertEqual([e['status'] for e in res.data['order']['carrier_events']], ['접수'])
        old_status = requests.get(f'{self.url}/v1/shipments/{old}', headers={'X-API-Key': API_KEY}, timeout=5).json()['data']['status']
        self.assertEqual(old_status, '취소')
        # 배송지를 그대로 두면 운송장도 그대로입니다.
        res = self.client.post(f'{ORDERS}{order.id}/edit/', {'note': '문 앞'}, format='json')
        self.assertEqual(res.data['order']['waybill_no'], new)

    def test_today_lists_carrier_issues(self):
        self.create_order(**{**ADDRESS, 'address': '없는주소 1번지'})
        res = self.client.get('/api/inventory/today/')
        issues = res.data['carrier_issues']
        self.assertEqual(issues['count'], 1)
        self.assertIn('주소를 확인할 수 없습니다', issues['items'][0]['reason'])
