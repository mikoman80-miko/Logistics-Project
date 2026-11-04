"""입고 예정일이 지난 발주를 슬랙·디스코드(ALERT_WEBHOOK_URL)로 알립니다.

    myenv\Scripts\python manage.py notify_overdue

백업처럼 Windows 작업 스케줄러에 매일 아침 한 번 실행하도록 등록해 두면 됩니다.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from inventory.views import overdue_purchase_orders, send_webhook_alert


class Command(BaseCommand):
    help = '입고 예정일이 지난 발주를 알림으로 보냅니다.'

    def handle(self, *args, **options):
        overdue = overdue_purchase_orders(limit=20)
        if not overdue['count']:
            self.stdout.write('입고 예정일이 지난 발주가 없습니다.')
            return
        lines = [f"- {po['po_number']} {po['supplier'] or '거래처 미지정'}: 예정일 {po['expected_date']} ({po['days']}일 지남)" for po in overdue['items']]
        more = overdue['count'] - len(overdue['items'])
        message = f"입고 예정일이 지난 발주 {overdue['count']}건\n" + '\n'.join(lines) + (f'\n외 {more}건' if more > 0 else '')
        send_webhook_alert(message, kind='입고 지연', link='/today')
        sent = '보냈습니다' if settings.ALERT_WEBHOOK_URL else '알림 주소(ALERT_WEBHOOK_URL)가 없어 화면에만 표시합니다'
        self.stdout.write(f'{message}\n\n{sent}.')
