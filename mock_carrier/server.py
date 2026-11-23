"""가상 택배사 '가온택배' API 서버 (개발·시연용)

실제 택배사 API처럼 별도 포트에서 실행되며, WMS는 HTTP로만 통신합니다.
    myenv\\Scripts\\python mock_carrier\\server.py            # 기본 포트 8100

- API: 운송장 발급, 집하 요청, 취소, 배송 조회, 반품 회수 요청 (/docs 에 규격)
- 일정 시간마다 배송 단계가 진행되고, 바뀔 때마다 WMS로 상태를 알립니다(웹훅, HMAC 서명).
- 화면: 배송 조회(/), 송장 콘솔(/console), 웹훅 기록(/webhooks), API 문서(/docs)
"""
import argparse
import hashlib
import hmac
import json
import os
import random
import re
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
import carrier_pages as pages  # noqa: E402  (같은 폴더의 화면 모듈)

load_dotenv(BASE_DIR.parent / '.env')

CARRIER_NAME = '가온택배'
API_KEY = os.environ.get('CARRIER_API_KEY', 'mock-carrier-key')
WEBHOOK_SECRET = os.environ.get('CARRIER_WEBHOOK_SECRET', 'mock-webhook-secret')
STEP_SECONDS = int(os.environ.get('MOCK_CARRIER_STEP_SECONDS', '60'))  # 단계가 자동으로 넘어가는 간격
FAIL_RATE = float(os.environ.get('MOCK_CARRIER_FAIL_RATE', '0'))  # 일시 장애를 흉내 내는 확률 (0~1)
DB_PATH = Path(os.environ.get('MOCK_CARRIER_DB') or BASE_DIR / 'carrier.sqlite3')  # 테스트 환경은 다른 파일을 씁니다
RETRY_WAITS = (0, 3, 10)  # 웹훅 재시도 간격(초)

# 단계와 그때의 위치 안내
FLOWS = {
    'delivery': [('접수', '송장 접수'), ('집하', '출고지 집하'), ('배송중', '중앙 허브 간선 이동'), ('배송출발', '배송지 대리점 출발'), ('배송완료', '수령인 전달 완료')],
    'pickup': [('회수접수', '회수 요청 접수'), ('회수집하', '고객 방문 수거'), ('회수이동중', '중앙 허브 간선 이동'), ('회수완료', '입고지(물류센터) 도착')],
}
CANCELLABLE = {'접수', '회수접수'}
FINISHED = {'배송완료', '회수완료', '취소'}
db_lock = threading.Lock()


def now_text():
    return datetime.now().astimezone().isoformat(timespec='seconds')


@contextmanager
def store():
    # 한 번에 한 요청만 DB를 쓰고, 끝나면 저장 후 닫습니다.
    with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def init_db():
    with store() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS shipments (
                waybill_no TEXT PRIMARY KEY, kind TEXT, ref TEXT, name TEXT, phone TEXT, zipcode TEXT,
                address TEXT, address_detail TEXT, callback_url TEXT, status TEXT, ready INTEGER DEFAULT 0,
                created_at TEXT, changed_at REAL);
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, waybill_no TEXT, status TEXT, location TEXT, occurred_at TEXT);
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, waybill_no TEXT, status TEXT, url TEXT,
                attempt INTEGER, result_code INTEGER, error TEXT, sent_at TEXT);
        ''')


def new_waybill(conn):
    while True:
        number = '58' + ''.join(random.choices('0123456789', k=10))
        if not conn.execute('SELECT 1 FROM shipments WHERE waybill_no=?', (number,)).fetchone():
            return number


def location_of(kind, status):
    return dict(FLOWS[kind]).get(status, '송장 취소' if status == '취소' else status)


def add_event(conn, waybill_no, kind, status):
    event = {'event_id': uuid.uuid4().hex, 'waybill_no': waybill_no, 'status': status, 'location': location_of(kind, status), 'occurred_at': now_text()}
    conn.execute('INSERT INTO events VALUES (:event_id, :waybill_no, :status, :location, :occurred_at)', event)
    conn.execute('UPDATE shipments SET status=?, changed_at=? WHERE waybill_no=?', (status, time.time(), waybill_no))
    return event


def shipment_data(conn, waybill_no, private=False):
    row = conn.execute('SELECT * FROM shipments WHERE waybill_no=?', (waybill_no,)).fetchone()
    if not row:
        return None
    events = [dict(e) for e in conn.execute('SELECT * FROM events WHERE waybill_no=? ORDER BY occurred_at, rowid', (waybill_no,))]
    data = {'waybill_no': row['waybill_no'], 'kind': row['kind'], 'ref': row['ref'], 'status': row['status'], 'carrier': CARRIER_NAME, 'events': events}
    if private:  # 조회 화면용 (API 응답에는 개인정보를 돌려주지 않습니다)
        data.update(name=row['name'], phone=row['phone'], address=row['address'], ready=row['ready'], changed_at=row['changed_at'])
    return data


def log_webhook(waybill_no, status, url, attempt, result_code=None, error=''):
    with store() as conn:
        conn.execute('INSERT INTO webhook_logs (waybill_no, status, url, attempt, result_code, error, sent_at) VALUES (?,?,?,?,?,?,?)',
                     (waybill_no, status, url, attempt, result_code, error[:200], now_text()))


def notify(callback_url, kind, event):
    # WMS에 상태 변경을 알립니다. 실패(연결 오류, 5xx)하면 잠시 뒤 다시 시도합니다.
    if not callback_url:
        return

    def send():
        body = json.dumps({**event, 'kind': kind}, ensure_ascii=False).encode('utf-8')
        signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        for attempt, wait in enumerate(RETRY_WAITS, start=1):
            time.sleep(wait)
            try:
                res = requests.post(callback_url, data=body, timeout=5, headers={'Content-Type': 'application/json', 'X-Carrier-Signature': signature})
            except requests.RequestException as exc:
                log_webhook(event['waybill_no'], event['status'], callback_url, attempt, error=type(exc).__name__)
                continue
            log_webhook(event['waybill_no'], event['status'], callback_url, attempt, res.status_code, '' if res.ok else res.text[:200])
            if res.status_code < 500:
                return

    threading.Thread(target=send, daemon=True).start()


def advance(conn, row, force=False):
    """다음 단계로 진행합니다. 진행하지 않았으면 None. force는 시연용으로 집하 요청 전에도 진행합니다."""
    names = [name for name, _ in FLOWS[row['kind']]]
    if row['status'] not in names or row['status'] == names[-1]:
        return None
    if row['kind'] == 'delivery' and not row['ready'] and not force:
        return None  # 출고 확정(집하 요청) 전에는 기사가 가져가지 않습니다.
    event = add_event(conn, row['waybill_no'], row['kind'], names[names.index(row['status']) + 1])
    notify(row['callback_url'], row['kind'], event)
    return event


def cancel_shipment(conn, row):
    if row['status'] == '취소':
        return None
    if row['status'] not in CANCELLABLE:
        raise ApiError(409, 'ALREADY_COLLECTED', f'이미 {row["status"]} 단계라 취소할 수 없습니다.')
    event = add_event(conn, row['waybill_no'], row['kind'], '취소')
    notify(row['callback_url'], row['kind'], event)
    return event


def eta_text(data):
    # 시연 기준 예상 완료 시각: 남은 단계 수 × 단계 간격
    names = [name for name, _ in FLOWS[data['kind']]]
    if data['status'] not in names or data['status'] == names[-1]:
        return ''
    if data['kind'] == 'delivery' and not data['ready']:
        return '판매자가 상품을 준비하고 있습니다. 출고되면 기사가 집하합니다.'
    remaining = (len(names) - 1 - names.index(data['status'])) * STEP_SECONDS - (time.time() - data['changed_at'])
    minutes = max(1, round(remaining / 60))
    label = '배송완료' if data['kind'] == 'delivery' else '회수완료'
    return f'{label} 예정: 약 {minutes}분 후 (시연 기준)'


def ticker():
    while True:
        time.sleep(5)
        with store() as conn:
            due = conn.execute('SELECT * FROM shipments WHERE changed_at <= ? AND status NOT IN (?,?,?)',
                               (time.time() - STEP_SECONDS, *FINISHED)).fetchall()
            for row in due:
                advance(conn, row)


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def validate_party(party):
    party = party if isinstance(party, dict) else {}
    clean = {key: str(party.get(key) or '').strip() for key in ('name', 'phone', 'zipcode', 'address', 'address_detail')}
    if not clean['name'] or not clean['address']:
        raise ApiError(400, 'INVALID_PARAMETER', '이름과 주소는 필수입니다.')
    if not re.fullmatch(r'0\d{1,2}-?\d{3,4}-?\d{4}', clean['phone']):
        raise ApiError(400, 'INVALID_PHONE', f'전화번호 형식이 올바르지 않습니다: {clean["phone"]}')
    if not re.fullmatch(r'\d{5}', clean['zipcode']):
        raise ApiError(400, 'INVALID_ZIPCODE', f'우편번호는 숫자 5자리입니다: {clean["zipcode"]}')
    if '없는주소' in clean['address']:  # 시연용: 주소 검증 실패
        raise ApiError(422, 'ADDRESS_NOT_FOUND', '주소를 확인할 수 없습니다. 도로명 주소를 확인해 주세요.')
    return clean


class Handler(BaseHTTPRequestHandler):
    server_version = 'GaonCarrierAPI/1.1'

    def log_message(self, fmt, *args):
        print(f'[{self.log_date_time_string()}] {self.command} {self.path} {args[1] if len(args) > 1 else ""}')

    # ---------- 응답 ----------
    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_body(status, json.dumps(payload, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def send_html(self, status, text):
        self.send_body(status, text.encode('utf-8'), 'text/html; charset=utf-8')

    def redirect(self, location):
        self.send_response(303)
        self.send_header('Location', location)
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length) if length else b''

    def read_json(self):
        try:
            return json.loads((self.read_body() or b'{}').decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, 'INVALID_JSON', '요청 본문이 UTF-8 JSON 형식이 아닙니다.')

    def check_api(self):
        if not hmac.compare_digest(self.headers.get('X-API-Key', ''), API_KEY):
            raise ApiError(401, 'UNAUTHORIZED', 'API 키가 올바르지 않습니다.')
        if FAIL_RATE and random.random() < FAIL_RATE:
            raise ApiError(503, 'SYSTEM_BUSY', '택배사 시스템이 일시적으로 혼잡합니다. 잠시 후 다시 시도해 주세요.')

    def handle_api(self, fn):
        try:
            self.check_api()
            status, data = fn()
            self.send_json(status, {'result': 'OK', 'data': data})
        except ApiError as exc:
            self.send_json(exc.status, {'result': 'ERROR', 'code': exc.code, 'message': exc.message})

    def base_url(self):
        host = self.headers.get('Host') or f'127.0.0.1:{self.server.server_address[1]}'
        return f'http://{host}'

    # ---------- 라우팅 ----------
    def do_GET(self):
        url = urlsplit(self.path)
        path, query = url.path.rstrip('/') or '/', {k: v[0] for k, v in parse_qs(url.query).items()}
        if match := re.fullmatch(r'/v1/shipments/(\d+)', path):
            return self.handle_api(lambda: self.get_shipment(match[1]))
        pages_by_path = {
            '/': lambda: pages.home_page(),
            '/track': lambda: self.track_search(query.get('no', '')),
            '/console': lambda: self.console(query),
            '/webhooks': lambda: self.webhooks(),
            '/docs': lambda: pages.docs_page(self.base_url()),
        }
        if path in pages_by_path:
            result = pages_by_path[path]()
            return result if result is None else self.send_html(200, result)
        if match := re.fullmatch(r'/track/(\d+)', path):
            return self.tracking(match[1])
        self.send_json(404, {'result': 'ERROR', 'code': 'NOT_FOUND', 'message': '없는 주소입니다.'})

    def do_POST(self):
        path = urlsplit(self.path).path.rstrip('/')
        routes = [
            (r'/v1/shipments', lambda m: self.create('delivery', 'order_ref', 'receiver')),
            (r'/v1/pickups', lambda m: self.create('pickup', 'return_ref', 'sender')),
            (r'/v1/shipments/(\d+)/ready', lambda m: self.ready(m[1])),
            (r'/v1/(?:shipments|pickups)/(\d+)/cancel', lambda m: self.cancel(m[1])),
            (r'/v1/simulate/(\d+)/advance', lambda m: self.simulate(m[1])),
        ]
        for pattern, fn in routes:
            if match := re.fullmatch(pattern, path):
                return self.handle_api(lambda: fn(match))
        if match := re.fullmatch(r'/console/(advance|finish|cancel)/(\d+)', path):
            return self.console_action(match[1], match[2])
        self.send_json(404, {'result': 'ERROR', 'code': 'NOT_FOUND', 'message': '없는 주소입니다.'})

    # ---------- API ----------
    def create(self, kind, ref_key, party_key):
        data = self.read_json()
        party = validate_party(data.get(party_key))
        ref = str(data.get(ref_key) or '').strip()
        if not ref:
            raise ApiError(400, 'INVALID_PARAMETER', f'{ref_key}는 필수입니다.')
        with store() as conn:
            waybill_no = new_waybill(conn)
            conn.execute(
                'INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)',
                (waybill_no, kind, ref, party['name'], party['phone'], party['zipcode'], party['address'], party['address_detail'],
                 str(data.get('callback_url') or ''), '', now_text(), time.time()))
            add_event(conn, waybill_no, kind, FLOWS[kind][0][0])
            return 201, shipment_data(conn, waybill_no)

    def get_shipment(self, waybill_no):
        with store() as conn:
            data = shipment_data(conn, waybill_no)
        if not data:
            raise ApiError(404, 'WAYBILL_NOT_FOUND', f'운송장 번호를 찾을 수 없습니다: {waybill_no}')
        return 200, data

    def find(self, conn, waybill_no):
        row = conn.execute('SELECT * FROM shipments WHERE waybill_no=?', (waybill_no,)).fetchone()
        if not row:
            raise ApiError(404, 'WAYBILL_NOT_FOUND', f'운송장 번호를 찾을 수 없습니다: {waybill_no}')
        return row

    def ready(self, waybill_no):
        self.read_body()
        with store() as conn:
            row = self.find(conn, waybill_no)
            if row['kind'] != 'delivery':
                raise ApiError(400, 'INVALID_STATE', '배송 송장만 집하 요청할 수 있습니다.')
            if row['status'] == '취소':
                raise ApiError(409, 'INVALID_STATE', '취소된 송장입니다.')
            if not row['ready']:  # 다시 요청해도 진행 시계를 처음으로 돌리지 않습니다.
                conn.execute('UPDATE shipments SET ready=1, changed_at=? WHERE waybill_no=?', (time.time(), waybill_no))
            return 200, shipment_data(conn, waybill_no)

    def cancel(self, waybill_no):
        self.read_body()
        with store() as conn:
            cancel_shipment(conn, self.find(conn, waybill_no))
            return 200, shipment_data(conn, waybill_no)

    def simulate(self, waybill_no):
        self.read_body()
        with store() as conn:
            row = self.find(conn, waybill_no)
            if not advance(conn, row, force=True):
                raise ApiError(409, 'INVALID_STATE', f'{row["status"]} 단계에서는 더 진행할 수 없습니다.')
            return 200, shipment_data(conn, waybill_no)

    # ---------- 화면 ----------
    def track_search(self, number):
        number = re.sub(r'\D', '', number)
        if not number:
            return pages.home_page('운송장 번호를 입력해 주세요.')
        with store() as conn:
            exists = conn.execute('SELECT 1 FROM shipments WHERE waybill_no=?', (number,)).fetchone()
        if not exists:
            return pages.home_page(f'운송장 번호 {number}를 찾을 수 없습니다. 번호를 다시 확인해 주세요.', number)
        self.redirect(f'/track/{number}')

    def tracking(self, waybill_no):
        with store() as conn:
            data = shipment_data(conn, waybill_no, private=True)
        if not data:
            return self.send_html(404, pages.home_page(f'운송장 번호 {waybill_no}를 찾을 수 없습니다.', waybill_no))
        self.send_html(200, pages.tracking_page(data, FLOWS[data['kind']], eta_text(data)))

    def console(self, query):
        query = {key: query.get(key, '').strip() for key in ('kind', 'status', 'q', 'auto')}
        sql, params = 'SELECT * FROM shipments WHERE 1=1', []
        if query['kind'] in FLOWS:
            sql += ' AND kind=?'
            params.append(query['kind'])
        if query['status']:
            sql += ' AND status=?'
            params.append(query['status'])
        if query['q']:
            sql += ' AND (waybill_no LIKE ? OR ref LIKE ? OR name LIKE ?)'
            params += [f'%{query["q"]}%'] * 3
        with store() as conn:
            rows = conn.execute(sql + ' ORDER BY created_at DESC LIMIT 200', params).fetchall()
            total = dict(conn.execute('SELECT status, COUNT(*) FROM shipments GROUP BY status').fetchall())
        moving = sum(v for k, v in total.items() if k not in FINISHED and k not in CANCELLABLE)
        counts = [('전체 송장', sum(total.values())), ('접수 대기', total.get('접수', 0) + total.get('회수접수', 0)), ('이동 중', moving),
                  ('배송완료', total.get('배송완료', 0)), ('회수완료', total.get('회수완료', 0)), ('취소', total.get('취소', 0))]
        statuses = [name for flow in FLOWS.values() for name, _ in flow] + ['취소']
        return pages.console_page(rows, counts, query, {'step': STEP_SECONDS, 'fail_rate': FAIL_RATE, 'statuses': statuses})

    def console_action(self, act, waybill_no):
        form = {k: v[0] for k, v in parse_qs(self.read_body().decode('utf-8')).items()}
        back = form.get('back', '/console')
        back = back if back.startswith('/console') else '/console'  # 다른 사이트로 보내지 않습니다.
        with store() as conn:
            row = conn.execute('SELECT * FROM shipments WHERE waybill_no=?', (waybill_no,)).fetchone()
            if row:
                try:
                    if act == 'advance':
                        advance(conn, row, force=True)
                    elif act == 'finish':
                        while advance(conn, conn.execute('SELECT * FROM shipments WHERE waybill_no=?', (waybill_no,)).fetchone(), force=True):
                            pass
                    else:
                        cancel_shipment(conn, row)
                except ApiError:
                    pass  # 이미 집하된 송장 취소 등: 화면에서 상태를 보고 판단합니다.
        self.redirect(back)

    def webhooks(self):
        with store() as conn:
            rows = conn.execute('SELECT * FROM webhook_logs ORDER BY id DESC LIMIT 200').fetchall()
        return pages.webhooks_page(rows, '받는 주소는 WMS의 CARRIER_CALLBACK_URL입니다.')


def main():
    parser = argparse.ArgumentParser(description=f'{CARRIER_NAME} 가상 API 서버')
    parser.add_argument('--port', type=int, default=8100)
    args = parser.parse_args()
    init_db()
    threading.Thread(target=ticker, daemon=True).start()
    print(f'{CARRIER_NAME} 가상 택배사: http://127.0.0.1:{args.port}/ (콘솔 /console, API 문서 /docs, 단계 간격 {STEP_SECONDS}초)')
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
