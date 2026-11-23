"""시연·테스트용 데이터를 만듭니다. 모든 메뉴를 눌러 볼 수 있도록 메뉴마다 10건 안팎씩 만듭니다.

    myenv\\Scripts\\python manage.py seed_demo

- 실제 화면과 같은 API로 발주 → 입고 → 주문 → 출고 → 반품을 처리하므로 재고·이력·알림이 서로 맞습니다.
- 만든 기록은 지난 3주에 나눠 날짜를 옮겨, 보고서(작업자 실적, 일일 마감, 분석)에 기간별 숫자가 나옵니다.
- 데모 상품코드는 DM-로 시작합니다. 이미 만들었으면 다시 만들지 않습니다.
- 개발 DB에서만 쓰세요. 실행 전에 backup_db.py로 백업해 두면 되돌릴 수 있습니다.
"""

import random
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from inventory.models import InventoryLog, Item, ItemSerial, ItemStock, PurchaseOrder, ReturnOrder, SalesOrder

DEMO_PASSWORD = 'Demo-wms-2026!'
ADDRESSES = [
    ('김민수', '010-2345-6789', '06236', '서울시 강남구 테헤란로 152', '12층'),
    ('이서연', '010-3456-7890', '04524', '서울시 중구 세종대로 110', '3층'),
    ('박지훈', '010-4567-8901', '13494', '경기도 성남시 분당구 판교역로 235', 'A동 501호'),
    ('최유나', '010-5678-9012', '48058', '부산시 해운대구 센텀중앙로 79', '201호'),
    ('정우성', '010-6789-0123', '34126', '대전시 유성구 대학로 99', '연구동 2층'),
    ('한지민', '010-7890-1234', '61945', '광주시 서구 상무중앙로 110', '1층'),
]


class Command(BaseCommand):
    help = '모든 메뉴를 시험해 볼 수 있는 데모 데이터를 만듭니다. (개발 DB 전용)'

    def handle(self, *args, **options):
        if Item.objects.filter(sku__startswith='DM-').exists():
            raise CommandError('데모 데이터가 이미 있습니다. (DM-로 시작하는 상품) 다시 만들려면 백업으로 되돌린 뒤 실행하세요.')
        random.seed(2026)
        self.client = APIClient(SERVER_NAME='localhost')
        self.admin = User.objects.filter(is_superuser=True).order_by('id').first()
        if not self.admin:
            raise CommandError('관리자(슈퍼유저) 계정이 필요합니다. createsuperuser로 먼저 만드세요.')
        self.dated = []  # (모델, pk, 문서번호, 며칠 전)

        # 중간에 실패하면 만든 것을 모두 되돌립니다.
        with transaction.atomic():
            self.make_master()
            self.make_purchase_orders()
            self.move_and_adjust()
            self.make_orders()
            self.make_returns()
            self.cycle_count()
            self.backdate()
            self.daily_close()
            self.low_stock_and_replenish()
        self.report()

    # ---------- 공통 ----------
    def api(self, method, url, data=None, user=None, ok=(200, 201, 204)):
        self.client.force_authenticate(user or self.admin)
        res = getattr(self.client, method)(url, data or {}, format='json')
        if res.status_code not in ok:
            raise CommandError(f'{method.upper()} {url} 실패 ({res.status_code}): {getattr(res, "data", res.content)}')
        return res.data

    def worker(self, index=None):
        return self.workers[index if index is not None else random.randrange(len(self.workers))]

    # ---------- 기준정보 ----------
    def make_master(self):
        api = self.api
        people = [
            ('manager01', '김관리', '관리자'),
            ('worker01', '이현장', '현장작업자'),
            ('worker02', '박입고', '현장작업자'),
            ('worker03', '최출고', '현장작업자'),
            ('worker04', '정반품', '현장작업자'),
            ('worker05', '한보충', '현장작업자'),
        ]
        for username, name, role in people:
            if not User.objects.filter(username=username).exists():
                api('post', '/api/inventory/users/', {'username': username, 'name': name, 'role': role, 'password': DEMO_PASSWORD})
        self.workers = list(User.objects.filter(username__startswith='worker').order_by('username'))
        self.badges = {u.username: api('post', f'/api/inventory/users/{u.id}/issue_badge/')['code'] for u in self.workers[:3]}

        categories = {}
        for name in ['스마트기기', '음향기기', '충전·케이블', '보호용품', '포장재', '사은품']:
            categories[name] = api('post', '/api/inventory/categories/', {'name': name})['id']

        self.locations = {}
        for zone, rack, tier in [
            ('A', 'R01', 1),
            ('A', 'R01', 2),
            ('A', 'R02', 1),
            ('A', 'R02', 2),
            ('B', 'R01', 1),
            ('B', 'R01', 2),
            ('B', 'R02', 1),
            ('C', 'R01', 1),
            ('C', 'R01', 2),
            ('C', 'R02', 1),
        ]:
            loc = api('post', '/api/inventory/locations/', {'zone': zone, 'rack': rack, 'tier': tier, 'description': f'{zone}구역 데모 선반'})
            self.locations[f'{zone}-{rack}-{tier}'] = loc['id']

        self.suppliers = []
        for name, person, phone in [
            ('한빛전자', '김영업', '02-1234-5678'),
            ('누리모바일', '이과장', '02-2345-6789'),
            ('소리공방', '박대리', '031-345-6789'),
            ('코드라인', '최팀장', '032-456-7890'),
            ('세이프케이스', '정주임', '02-567-8901'),
            ('그린패키지', '한부장', '031-678-9012'),
            ('바른포장', '오실장', '02-789-0123'),
            ('기프트몰', '서대리', '051-890-1234'),
            ('파워셀', '윤과장', '042-901-2345'),
            ('스마트링크', '장팀장', '02-012-3456'),
        ]:
            self.suppliers.append(api('post', '/api/inventory/suppliers/', {'name': name, 'contact_person': person, 'phone': phone})['id'])

        L = self.locations
        products = [  # sku, 이름, 구분, 시리얼, 카테고리, 기본 위치, 안전재고, (보충 최소, 최대)
            ('DM-PHONE-01', '데모 스마트폰 X1', '상품', True, '스마트기기', 'A-R01-1', 3, None),
            ('DM-TAB-01', '데모 태블릿 T10', '상품', True, '스마트기기', 'A-R01-2', 2, None),
            ('DM-WATCH-01', '데모 스마트워치 W2', '상품', True, '스마트기기', 'A-R02-1', 2, None),
            ('DM-BUDS-01', '데모 무선이어폰 B3', '상품', True, '음향기기', 'A-R02-2', 3, None),
            ('DM-CABLE-C', '데모 USB-C 케이블 1m', '부자재', False, '충전·케이블', 'B-R01-1', 20, (10, 40)),
            ('DM-CHARGER-25', '데모 25W 충전기', '구성품', False, '충전·케이블', 'B-R01-2', 10, (5, 20)),
            ('DM-CASE-X1', '데모 X1 전용 케이스', '부자재', False, '보호용품', 'B-R02-1', 10, None),
            ('DM-FILM-X1', '데모 X1 보호필름', '부자재', False, '보호용품', 'B-R02-1', 15, None),
            ('DM-BOX-M', '데모 택배상자 중', '부자재', False, '포장재', 'C-R01-1', 30, None),
            ('DM-TAPE-48', '데모 박스테이프 48mm', '부자재', False, '포장재', 'C-R01-2', 10, None),
            ('DM-BUBBLE', '데모 완충재(롤)', '부자재', False, '포장재', 'C-R02-1', 5, None),
            ('DM-GIFT-STK', '데모 사은품 스티커팩', '사은품', False, '사은품', 'C-R02-1', 20, None),
        ]
        self.items = {}
        for sku, name, kind, serial, category, location, safety, pick in products:
            body = {
                'sku': sku,
                'name': name,
                'item_type': kind,
                'serial_tracked': serial,
                'category': categories[category],
                'location': L[location],
                'quantity': 0,
                'safety_stock': safety,
            }
            if pick:
                body.update(pick_min=pick[0], pick_max=pick[1])
            self.items[sku] = api('post', '/api/inventory/items/', body)['id']
        # 기준정보 변경 이력이 보이도록 몇 가지를 고칩니다.
        api('patch', f'/api/inventory/items/{self.items["DM-GIFT-STK"]}/', {'name': '데모 사은품 스티커팩(신규)', 'safety_stock': 15})
        api('patch', f'/api/inventory/suppliers/{self.suppliers[9]}/', {'phone': '02-111-2222'})

    # ---------- 발주·입고 ----------
    def receive(self, po, sku, count, user, start=1):
        if Item.objects.get(sku=sku).serial_tracked:
            for n in range(start, start + count):
                self.api('post', f'/api/inventory/purchase-orders/{po["id"]}/receive_inbound/', {'sku': sku, 'serial_number': f'{sku}-SN{n:04d}'}, user)
        elif count:
            self.api('post', f'/api/inventory/purchase-orders/{po["id"]}/receive_inbound/', {'sku': sku, 'quantity': count}, user)

    def make_purchase_orders(self):
        today = timezone.localdate()
        plans = [  # 거래처, 품목 [(sku, 수량)], 예정일(오늘 기준), 처리, 며칠 전 발주
            (1, [('DM-PHONE-01', 8), ('DM-TAB-01', 4)], -15, 'full', 20),
            (0, [('DM-WATCH-01', 5), ('DM-BUDS-01', 6)], -14, 'full', 19),
            (3, [('DM-CABLE-C', 80), ('DM-CHARGER-25', 30)], -12, 'full', 18),
            (4, [('DM-CASE-X1', 40), ('DM-FILM-X1', 50)], -11, 'full', 17),
            (5, [('DM-BOX-M', 120), ('DM-TAPE-48', 30), ('DM-BUBBLE', 12)], -10, 'full', 16),
            (7, [('DM-GIFT-STK', 60)], -9, 'full', 15),
            (8, [('DM-CHARGER-25', 20)], -3, 'partial', 8),
            (2, [('DM-BUDS-01', 4), ('DM-CABLE-C', 30)], -4, 'issues', 7),
            (9, [('DM-PHONE-01', 3)], -2, 'over', 5),
            (6, [('DM-BOX-M', 50), ('DM-TAPE-48', 20)], -2, 'none', 6),  # 예정일 지남 → 입고 지연
            (1, [('DM-TAB-01', 2)], 5, 'none', 1),
            (3, [('DM-CABLE-C', 10)], 3, 'cancel', 2),
        ]
        serial_next = {}
        for supplier, lines, due, how, days_ago in plans:
            po = self.api(
                'post',
                '/api/inventory/purchase-orders/',
                {
                    'supplier': self.suppliers[supplier],
                    'expected_date': (today + timedelta(days=due)).isoformat(),
                    'items': [{'item': self.items[sku], 'order_quantity': qty} for sku, qty in lines],
                },
            )
            self.dated.append((PurchaseOrder, po['id'], po['po_number'], days_ago))
            user = self.worker()
            for sku, qty in lines:
                start = serial_next.get(sku, 1)
                count = {'full': qty, 'over': qty, 'partial': qty // 2, 'issues': max(qty - 3, 0)}.get(how, 0)
                self.receive(po, sku, count, user, start)
                serial_next[sku] = start + (count if Item.objects.get(sku=sku).serial_tracked else 0)
            url = f'/api/inventory/purchase-orders/{po["id"]}'
            if how == 'issues':
                self.api('post', f'{url}/report_issue/', {'sku': 'DM-BUDS-01', 'kind': '파손', 'quantity': 1, 'note': '케이스 모서리 깨짐'}, user)
                self.api('post', f'{url}/report_issue/', {'sku': 'DM-BUDS-01', 'kind': '부족', 'quantity': 2}, user)
                self.api('post', f'{url}/report_issue/', {'sku': 'DM-CABLE-C', 'kind': '부족', 'quantity': 3, 'note': '거래처 재고 부족'}, user)
            elif how == 'over':
                self.api('post', f'{url}/report_issue/', {'sku': 'DM-PHONE-01', 'kind': '초과', 'quantity': 1, 'note': '1대 더 와서 반송'}, user)
            elif how == 'cancel':
                self.api('post', f'{url}/cancel/')

    # ---------- 재고 이동·조정 ----------
    def move_and_adjust(self):
        loc, item = self.locations, self.items
        self.api('post', f'/api/inventory/items/{item["DM-CABLE-C"]}/move_stock/', {'from': loc['B-R01-1'], 'to': loc['C-R01-2'], 'quantity': 70})
        self.api('post', f'/api/inventory/items/{item["DM-CHARGER-25"]}/move_stock/', {'from': loc['B-R01-2'], 'to': loc['C-R02-1'], 'quantity': 25})
        self.api('post', f'/api/inventory/items/{item["DM-BOX-M"]}/adjust_stock/', {'change': -4})
        self.api('post', f'/api/inventory/items/{item["DM-GIFT-STK"]}/adjust_stock/', {'change': 5})
        serials = list(
            ItemSerial.objects.filter(item_id=item['DM-PHONE-01'], status='재고보유').order_by('serial_number').values_list('serial_number', flat=True)[:2]
        )
        self.api('post', f'/api/inventory/items/{item["DM-PHONE-01"]}/move_stock/', {'from': loc['A-R01-1'], 'to': loc['A-R02-2'], 'serials': serials})
        # 현장 위치 보충: 케이블 꺼내는 자리를 채웁니다.
        self.api('post', f'/api/inventory/items/{item["DM-CABLE-C"]}/replenish/', {'from': loc['C-R01-2'], 'quantity': 20}, self.worker(4))

    # ---------- 주문·출고 ----------
    def ship(self, order, user, partial=False, skip_sku=None):
        for line in order['items']:
            if line['item_sku'] == skip_sku:
                continue
            item = Item.objects.get(pk=line['item'])
            if item.serial_tracked:
                for serial in (
                    ItemSerial.objects.filter(item=item, status='재고보유').exclude(order_picks__isnull=False).order_by('serial_number')[: line['quantity']]
                ):
                    self.api('post', f'/api/inventory/orders/{order["id"]}/scan/', {'code': serial.serial_number}, user)
            else:
                self.api('post', f'/api/inventory/orders/{order["id"]}/scan/', {'code': item.sku, 'quantity': line['quantity']}, user)
        self.api('post', f'/api/inventory/orders/{order["id"]}/complete/', {'partial': True} if partial else {}, user)
        return self.api('get', f'/api/inventory/orders/{order["id"]}/')

    def make_orders(self):
        item_ids = self.items
        plans = [  # 고객, 주소 번호, 품목, 처리, 며칠 전
            ('누리상사', 0, [('DM-PHONE-01', 1), ('DM-CASE-X1', 1), ('DM-FILM-X1', 2)], 'ship', 10),
            ('한결몰', 1, [('DM-TAB-01', 1), ('DM-CHARGER-25', 1)], 'ship', 9),
            ('바다마켓', 2, [('DM-BUDS-01', 2), ('DM-CABLE-C', 3)], 'ship', 8),
            ('온누리쇼핑', 3, [('DM-WATCH-01', 1), ('DM-GIFT-STK', 2)], 'ship', 7),
            ('하늘스토어', 4, [('DM-CABLE-C', 10), ('DM-CHARGER-25', 5)], 'ship', 6),
            ('누리상사', 0, [('DM-PHONE-01', 2), ('DM-CASE-X1', 2)], 'ship', 4),
            ('미래전자', 5, [('DM-BUDS-01', 1), ('DM-FILM-X1', 3)], 'partial', 3),
            ('한결몰', 1, [('DM-CASE-X1', 1)], 'cancel', 3),
            ('바다마켓', 2, [('DM-TAB-01', 1)], 'urgent', 2),
            ('온누리쇼핑', 3, [('DM-CABLE-C', 2)], 'bundle', 1),
            ('온누리쇼핑', 3, [('DM-CHARGER-25', 1)], 'bundle', 1),
            ('주소오류상사', None, [('DM-GIFT-STK', 1)], 'wait', 1),  # 택배사가 주소를 거부 → 오늘 할 일의 택배 확인
            ('하늘스토어', 4, [('DM-WATCH-01', 1), ('DM-CABLE-C', 2)], 'wait', 0),
        ]
        self.shipped = []
        bundle = []
        for customer, address, lines, how, days_ago in plans:
            name, phone, zipcode, addr, detail = ADDRESSES[address] if address is not None else ('오류수령', '010-0000-0000', '00000', '없는주소 1번지', '')
            order = self.api(
                'post',
                '/api/inventory/orders/',
                {
                    'customer': customer,
                    'items': [{'item': item_ids[sku], 'quantity': qty} for sku, qty in lines],
                    'contact_name': name,
                    'contact_phone': phone,
                    'zipcode': zipcode,
                    'address': addr,
                    'address_detail': detail,
                },
            )
            self.dated.append((SalesOrder, order['id'], order['order_no'], days_ago))
            user = self.worker()
            if how == 'ship':
                self.shipped.append(self.ship(order, user))
            elif how == 'partial':
                self.ship(order, user, partial=True, skip_sku='DM-FILM-X1')
            elif how == 'cancel':
                self.api('post', f'/api/inventory/orders/{order["id"]}/cancel/')
            elif how == 'urgent':
                self.api('post', f'/api/inventory/orders/{order["id"]}/urgent/', {'urgent': True})
            elif how == 'bundle':
                bundle.append(order['id'])
        self.api('post', '/api/inventory/orders/bundle/', {'ids': bundle})

    # ---------- 반품 ----------
    def make_returns(self):
        shipped_serials = list(ItemSerial.objects.filter(status='출고완료', item__sku__startswith='DM-').order_by('serial_number'))
        returns = []
        reasons = ['단순변심', '전원불량', '액정파손', '단순변심', '기타']
        for index, serial in enumerate(shipped_serials[:5]):
            order = next((o for o in self.shipped if any(line['item'] == serial.item_id for line in o['items'])), None)
            returns.append(
                (
                    self.api(
                        'post',
                        '/api/inventory/returns/',
                        {'customer': order['customer'] if order else '반품고객', 'reason': reasons[index], 'serial': serial.id},
                    ),
                    serial,
                )
            )
        quantity_returns = [
            (self.shipped[0], 'DM-FILM-X1', 1, '단순변심'),
            (self.shipped[2], 'DM-CABLE-C', 2, '기타'),
            (self.shipped[4], 'DM-CABLE-C', 3, '단순변심'),
            (self.shipped[4], 'DM-CHARGER-25', 1, '전원불량'),
            (self.shipped[3], 'DM-GIFT-STK', 1, '단순변심'),
        ]
        for order, sku, qty, reason in quantity_returns:
            returns.append(
                (
                    self.api(
                        'post',
                        '/api/inventory/returns/',
                        {'customer': order['customer'], 'reason': reason, 'item': self.items[sku], 'quantity': qty, 'sales_order': order['id']},
                    ),
                    None,
                )
            )
        for index, (ret, serial) in enumerate(returns):
            self.dated.append((ReturnOrder, ret['id'], ret['return_no'], max(0, 5 - index // 2)))
        user = self.worker(3)
        done = [
            (returns[0], {'status': '재고보유', 'quality': '양품A급', 'label': '정상 (A급)'}),
            (returns[1], {'status': 'AS진행중', 'label': 'AS 필요', 'detail': '전원 안 켜짐'}),
            (returns[2], {'status': '불량폐기', 'quality': '사용불가', 'label': '폐기', 'detail': '액정 파손'}),
            (returns[5], {'result': 'restock', 'label': '재고로 되돌림'}),
            (returns[6], {'result': 'dispose', 'label': '폐기', 'detail': '피복 손상'}),
            (returns[8], {'result': 'restock', 'label': '재고로 되돌림'}),
        ]
        for (ret, _), body in done:
            self.api('post', f'/api/inventory/returns/{ret["id"]}/complete/', body, user)
        self.api('post', f'/api/inventory/returns/{returns[9][0]["id"]}/cancel/')

    # ---------- 재고 조사 ----------
    def cycle_count(self):
        # 위치 두 곳을 조사합니다. 한 곳은 전산과 같게, 한 곳은 1개 모자라게 스캔해 반영합니다.
        for key, short in [('C-R01-1', 0), ('B-R02-1', 1)]:
            location = self.locations[key]
            preview = self.api('post', '/api/inventory/items/audit_scan/', {'location': location, 'codes': []})
            codes = []
            for row in preview['rows']:
                codes += row['missing'] if row['serial_tracked'] else [row['sku']] * row['system']
            if short:
                codes = codes[:-short]
            self.api('post', '/api/inventory/items/audit_scan/', {'location': location, 'codes': codes, 'apply': True, 'mark_missing': False})

    # ---------- 날짜 나누기 ----------
    def backdate(self):
        # 기록을 지난 날짜로 옮깁니다. 문서와 그 문서의 입출고 이력을 같은 날로 맞춥니다.
        now = timezone.localtime()
        for model, pk, number, days_ago in self.dated:
            if days_ago <= 0:
                continue
            day = now.date() - timedelta(days=days_ago)
            when = timezone.make_aware(datetime.combine(day, time(random.randint(9, 16), random.randint(0, 59))))
            if model is PurchaseOrder:
                PurchaseOrder.objects.filter(pk=pk).update(order_date=day)
            else:
                fields = {'created_at': when}
                obj = model.objects.get(pk=pk)
                if obj.completed_at:
                    fields['completed_at'] = when + timedelta(hours=random.randint(1, 3))
                model.objects.filter(pk=pk).update(**fields)
            for log in InventoryLog.objects.filter(reference=number):
                InventoryLog.objects.filter(pk=log.pk).update(timestamp=when + timedelta(hours=random.randint(0, 3), minutes=random.randint(0, 59)))
            # 부분 출고로 생긴 주문도 원래 주문 날짜에 맞춥니다.
            if model is SalesOrder:
                SalesOrder.objects.filter(split_from_id=pk).update(created_at=when + timedelta(hours=4))

    def daily_close(self):
        # 지난 사흘은 마감해 둡니다. (오늘은 직접 [마감하기]를 눌러 보세요)
        today = timezone.localdate()
        for days_ago in (3, 2, 1):
            self.api('post', '/api/inventory/reports/daily/', {'date': (today - timedelta(days=days_ago)).isoformat(), 'note': '데모 마감'})

    def low_stock_and_replenish(self):
        # 재고 부족 카드·발주 제안·알림과 현장 [위치 보충]에 보일 거리를 만듭니다.
        item, loc = self.items, self.locations
        self.api('post', f'/api/inventory/items/{item["DM-BUBBLE"]}/adjust_stock/', {'change': -9})
        self.api('post', f'/api/inventory/items/{item["DM-TAPE-48"]}/adjust_stock/', {'change': -22})
        here = ItemStock.objects.filter(item_id=item['DM-CHARGER-25'], location_id=loc['B-R01-2']).values_list('quantity', flat=True).first() or 0
        if here > 3:
            self.api('post', f'/api/inventory/items/{item["DM-CHARGER-25"]}/move_stock/', {'from': loc['B-R01-2'], 'to': loc['C-R02-1'], 'quantity': here - 3})

    def report(self):
        self.stdout.write(self.style.SUCCESS('데모 데이터를 만들었습니다.'))
        self.stdout.write(f'  상품 {len(self.items)}종 · 위치 {len(self.locations)}곳 · 거래처 {len(self.suppliers)}곳')
        self.stdout.write(
            f'  발주 {PurchaseOrder.objects.filter(items__item__sku__startswith="DM-").distinct().count()}건 · '
            f'주문 {SalesOrder.objects.filter(items__item__sku__startswith="DM-").distinct().count()}건 · '
            f'반품 {ReturnOrder.objects.filter(item__sku__startswith="DM-").count()}건'
        )
        self.stdout.write(f'  데모 계정 (비밀번호 {DEMO_PASSWORD}): manager01(관리자), worker01~worker05(현장작업자)')
        for username, code in self.badges.items():
            self.stdout.write(f'  사원증 {username}: {code}')
