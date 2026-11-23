"""오류 감시: 서버 오류와 택배사 연결 장애를 슬랙·디스코드로 알립니다.

- 서버 오류(500)는 로그 파일(logs/)에 남기고, 같은 오류는 ALERT_REPEAT_MINUTES(기본 10분)에 한 번만 알립니다.
- 택배사 연결이 CARRIER_FAIL_ALERT번(기본 3번) 연속 실패하면 알리고, 다시 연결되면 복구를 알립니다.
알림은 요청 처리와 따로(스레드) 보냅니다. 오류가 난 요청은 트랜잭션이 취소되므로 '저장 후 보내기'를 쓸 수 없습니다.
"""
import logging
import threading
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_last_sent = {}
_carrier_failures = 0


def record(kind, message, link=''):
    """화면 안 알림으로 남깁니다. 진행 중인 트랜잭션이 있으면 저장된 뒤에 남기고, 취소되면 남기지 않습니다."""
    from django.db import transaction

    from .models import AppNotification
    transaction.on_commit(lambda: AppNotification.objects.create(kind=kind, message=message[:2000], link=link))


def alert(message, key=None, kind='오류', link=''):
    """화면 안 알림으로 남기고 슬랙·디스코드로도 보냅니다. key가 같으면 정해진 시간 안에 다시 보내지 않습니다. 보냈으면 True"""
    url = settings.ALERT_WEBHOOK_URL
    key = key or message
    now = time.monotonic()
    with _lock:
        if now - _last_sent.get(key, -10 ** 9) < settings.ALERT_REPEAT_MINUTES * 60:
            return False
        _last_sent[key] = now
    record(kind, message, link)
    if not url:
        return True

    def post():
        try:
            requests.post(url, json={'text': f'🚨 [WMS 오류 감시] {message}'}, timeout=3)
        except requests.RequestException:
            logger.warning('오류 알림 전송 실패')

    threading.Thread(target=post, daemon=True).start()
    return True


class AlertLogHandler(logging.Handler):
    """ERROR 이상 로그(처리하지 못한 서버 오류 등)를 알림으로 보냅니다."""

    def emit(self, record):
        if record.name == __name__:
            return  # 알림 실패 로그로 다시 알림을 보내지 않습니다.
        try:
            request = getattr(record, 'request', None)
            where = f' ({request.method} {request.path})' if request is not None else ''
            detail = ''
            if record.exc_info and record.exc_info[1] is not None:
                exc = record.exc_info[1]
                detail = f' · {type(exc).__name__}: {str(exc)[:200]}'
            summary = record.getMessage().splitlines()[0][:200]
            key = f'{record.name}:{summary}:{type(record.exc_info[1]).__name__ if record.exc_info else ""}'
            alert(f'서버 오류{where}: {summary}{detail} · 자세한 내용은 logs 폴더의 오류 로그를 보세요.', key=key, kind='서버 오류')
        except Exception:  # 로그 처리 중 오류로 요청이 실패하지 않게 합니다.
            self.handleError(record)


def carrier_result(ok):
    """택배사 호출 결과를 세어 연속 실패와 복구를 알립니다."""
    global _carrier_failures
    with _lock:
        before = _carrier_failures
        _carrier_failures = 0 if ok else before + 1
        after = _carrier_failures
    limit = settings.CARRIER_FAIL_ALERT
    if not ok and after == limit:
        alert(f'택배사 서버 연결이 {limit}번 연속 실패했습니다. 운송장 발급·회수 요청이 쌓이고 있을 수 있습니다.', key='carrier-down', kind='택배', link='/today')
    elif ok and before >= limit:
        with _lock:
            _last_sent.pop('carrier-down', None)
        alert(f'택배사 서버 연결이 복구되었습니다. (연속 실패 {before}번) 오늘 할 일의 택배 확인 목록을 확인하세요.', key='carrier-up', kind='택배', link='/today')
