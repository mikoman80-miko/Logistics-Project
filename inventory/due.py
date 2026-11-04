"""출고 마감: 주문이 언제까지 나가야 하는지 계산합니다.

마감 시각(SHIP_CUTOFF_TIME, 기본 15:00) 전에 들어온 주문은 그날, 지나서 들어온 주문은 다음 출고일에 나갑니다.
SHIP_ON_WEEKENDS가 꺼져 있으면 토·일요일은 출고일에서 뺍니다. (공휴일은 따로 빼지 않습니다)
"""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone


def cutoff_time():
    hour, minute = (int(part) for part in settings.SHIP_CUTOFF_TIME.split(':'))
    return time(hour, minute)


def next_ship_day(day):
    while not settings.SHIP_ON_WEEKENDS and day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def due_at(created_at):
    """주문이 나가야 하는 마감 일시 (현지 시각)"""
    local = timezone.localtime(created_at)
    day = local.date() + timedelta(days=1 if local.time() >= cutoff_time() else 0)
    return timezone.make_aware(datetime.combine(next_ship_day(day), cutoff_time()))


def due_status(order, now=None):
    """출고대기 주문의 마감 상태: overdue(마감 지남) / today(오늘 마감) / later(다음 출고일), 그 외 상태는 ''"""
    if order.status != '출고대기':
        return ''
    now = now or timezone.now()
    deadline = due_at(order.created_at)
    if deadline <= now:
        return 'overdue'
    return 'today' if timezone.localtime(deadline).date() == timezone.localdate(now) else 'later'


def summary(orders, now=None):
    """출고대기 주문 목록의 마감 현황 (오늘 할 일·일일 마감에서 씀)"""
    counts = {'overdue': 0, 'today': 0, 'later': 0}
    urgent = 0
    for order in orders:
        counts[due_status(order, now)] += 1
        urgent += order.is_urgent
    return {**counts, 'urgent': urgent, 'cutoff': settings.SHIP_CUTOFF_TIME}
