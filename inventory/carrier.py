"""택배사 API 연동. 택배사를 바꾸려면 이 파일만 교체합니다.

현재 구현은 가상 택배사(mock_carrier/server.py)의 API 규격을 따릅니다.
"""

import hashlib
import hmac
import logging

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from . import monitor

logger = logging.getLogger(__name__)

CARRIER_NAME = '데모택배'
DELIVERED = '배송완료'
PICKED_UP = '회수완료'


class CarrierError(Exception):
    """택배사 요청 실패. 메시지는 화면에 그대로 보여줍니다."""


def enabled():
    return bool(settings.CARRIER_API_URL)


def tracking_url(waybill_no):
    return f'{settings.CARRIER_API_URL}/track/{waybill_no}' if enabled() and waybill_no else ''


def _call(method, path, payload=None):
    try:
        res = requests.request(method, f'{settings.CARRIER_API_URL}{path}', json=payload, timeout=5, headers={'X-API-Key': settings.CARRIER_API_KEY})
    except requests.RequestException:
        logger.warning('택배사 연결 실패: %s %s', method, path)
        monitor.carrier_result(False)
        raise CarrierError('택배사 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.')
    # 서버 쪽 장애(5xx)도 연결 장애로 셉니다. 주소 오류 같은 요청 거절(4xx)은 장애가 아닙니다.
    monitor.carrier_result(res.status_code < 500)
    try:
        body = res.json()
    except ValueError:
        body = {}
    if not res.ok or body.get('result') != 'OK':
        raise CarrierError(body.get('message') or f'택배사 요청이 실패했습니다. (HTTP {res.status_code})')
    return body['data']


def _party(record):
    return {
        'name': record.contact_name,
        'phone': record.contact_phone,
        'zipcode': record.zipcode,
        'address': record.address,
        'address_detail': record.address_detail,
    }


def create_shipment(order):
    return _call('POST', '/v1/shipments', {'order_ref': order.order_no, 'receiver': _party(order), 'callback_url': settings.CARRIER_CALLBACK_URL})


def request_collection(waybill_no):
    # 출고 확정: 기사가 물건을 가져가도 된다고 알립니다.
    return _call('POST', f'/v1/shipments/{waybill_no}/ready')


def create_pickup(return_order):
    return _call('POST', '/v1/pickups', {'return_ref': return_order.return_no, 'sender': _party(return_order), 'callback_url': settings.CARRIER_CALLBACK_URL})


def cancel(waybill_no, pickup=False):
    return _call('POST', f'/v1/{"pickups" if pickup else "shipments"}/{waybill_no}/cancel')


def track(waybill_no):
    return _call('GET', f'/v1/shipments/{waybill_no}')


def verify_signature(body, signature):
    secret = settings.CARRIER_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_time(value):
    return parse_datetime(value or '')
