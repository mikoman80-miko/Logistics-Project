"""가온택배 웹 화면 (배송 조회, 송장 콘솔, 웹훅 기록, API 문서). 데이터는 server.py가 넘겨줍니다."""
from datetime import datetime
from html import escape
from urllib.parse import urlencode

STYLE = '''
:root{--brand:#0b7a5c;--brand-dark:#075c45;--brand-soft:#e7f4ef;--ink:#222;--muted:#6b7280;--line:#e2e5e9;--bg:#f5f7f8;--warn:#c2410c;--danger:#b91c1c}
*{box-sizing:border-box}body{margin:0;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:var(--ink);background:var(--bg);font-size:15px}
a{color:var(--brand)}header{background:#fff;border-bottom:1px solid var(--line)}
.bar{max-width:1080px;margin:0 auto;padding:0 20px;height:60px;display:flex;align-items:center;gap:28px}
.logo{font-size:22px;font-weight:800;color:var(--brand);text-decoration:none;display:flex;align-items:center;gap:8px}
.logo i{display:inline-block;width:26px;height:26px;border-radius:6px;background:var(--brand);color:#fff;font-style:normal;font-size:15px;text-align:center;line-height:26px}
nav{display:flex;gap:18px;flex:1}nav a{color:var(--ink);text-decoration:none;font-weight:600;padding:19px 2px}nav a.on{color:var(--brand);border-bottom:3px solid var(--brand)}
.demo{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:12px;padding:2px 9px;white-space:nowrap}
main{max-width:1080px;margin:28px auto;padding:0 20px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px;margin-bottom:18px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:18px;margin:0 0 14px}.muted{color:var(--muted)}.small{font-size:13px}
.hero{background:linear-gradient(135deg,var(--brand),#119a76);color:#fff;border-radius:12px;padding:40px 32px;margin-bottom:18px}
.hero h1{font-size:28px}.search{display:flex;gap:8px;margin-top:20px;max-width:560px}
input,select{font:inherit;padding:10px 12px;border:1px solid #cfd5db;border-radius:8px;background:#fff}
.search input{flex:1;font-size:18px;letter-spacing:1px}
button,.btn{font:inherit;font-weight:700;padding:10px 18px;border-radius:8px;border:1px solid var(--brand);background:var(--brand);color:#fff;cursor:pointer;text-decoration:none;display:inline-block}
button.light,.btn.light{background:#fff;color:var(--brand)}button.sm{padding:4px 10px;font-size:13px;font-weight:600}button.danger{background:#fff;color:var(--danger);border-color:#f0b4b4}
.err{background:#fff1f1;border:1px solid #f3c2c2;color:var(--danger);border-radius:8px;padding:10px 14px;margin-top:14px}
.status-big{font-size:30px;font-weight:800;color:var(--brand);margin:6px 0}
.steps{display:flex;margin:26px 0 8px;padding:0;list-style:none}
.steps li{flex:1;text-align:center;position:relative;font-size:13px;color:var(--muted)}
.steps li:before{content:'';display:block;width:30px;height:30px;margin:0 auto 8px;border-radius:50%;background:#e5e7eb;border:3px solid #fff;box-shadow:0 0 0 2px #e5e7eb;position:relative;z-index:1}
.steps li:after{content:'';position:absolute;top:14px;left:-50%;width:100%;height:4px;background:#e5e7eb}.steps li:first-child:after{display:none}
.steps li.done{color:var(--ink)}.steps li.done:before{background:var(--brand);box-shadow:0 0 0 2px var(--brand)}.steps li.done:after{background:var(--brand)}
.steps li.now{color:var(--brand);font-weight:800}.steps li.now:before{background:#fff;box-shadow:0 0 0 4px var(--brand)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}.split{display:grid;grid-template-columns:1fr 2fr;gap:14px}
.info dt{font-size:13px;color:var(--muted)}.info dd{margin:2px 0 12px;font-weight:600}
.timeline{list-style:none;margin:0;padding:0}.timeline li{display:grid;grid-template-columns:150px 110px 1fr;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}
.timeline li:first-child{font-weight:700;color:var(--brand)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:9px 8px;text-align:left;vertical-align:middle}
th{background:#f8faf9;font-size:13px;color:#4b5563}td.mono,.mono{font-family:Consolas,monospace}
.badge{display:inline-block;padding:2px 9px;border-radius:12px;font-size:12px;font-weight:700;background:#eef2f7;color:#374151}
.b-go{background:var(--brand-soft);color:var(--brand-dark)}.b-done{background:#dcfce7;color:#166534}.b-cancel{background:#f3f4f6;color:#9ca3af}.b-err{background:#fee2e2;color:var(--danger)}.b-pick{background:#fff3e6;color:var(--warn)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:18px}
.stat{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px}.stat b{display:block;font-size:26px;color:var(--brand)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}.actions{display:flex;gap:4px;flex-wrap:wrap}
pre{background:#111827;color:#e5e7eb;border-radius:8px;padding:14px;overflow:auto;font-size:13px;line-height:1.5}
code{font-family:Consolas,monospace;background:#f1f5f4;padding:1px 5px;border-radius:4px}pre code{background:none;padding:0}
.ep{display:flex;gap:10px;align-items:center;margin:22px 0 8px}.ep b{font-family:Consolas,monospace;font-size:15px}
.m{font-size:12px;font-weight:800;padding:3px 8px;border-radius:5px;color:#fff}.m-get{background:#2563eb}.m-post{background:var(--brand)}
footer{max-width:1080px;margin:30px auto;padding:0 20px 30px;font-size:12px;color:var(--muted)}
@media(max-width:640px){.bar{gap:12px;height:auto;flex-wrap:wrap;padding:10px 16px}nav{order:3;width:100%;gap:14px;overflow-x:auto;white-space:nowrap}nav a{padding:8px 0}.split{grid-template-columns:1fr}main{margin:18px auto;padding:0 12px}.card{padding:16px}table{display:block;overflow-x:auto;white-space:nowrap}
.hero{padding:28px 20px}.timeline li{grid-template-columns:1fr;gap:2px}.steps li{font-size:11px}.demo{display:none}}
'''

MENU = [('/', '배송 조회', 'track'), ('/console', '송장 콘솔', 'console'), ('/webhooks', '웹훅 기록', 'webhooks'), ('/docs', 'API 문서', 'docs')]


def layout(title, body, active='', refresh=0):
    menu = ''.join(f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>' for href, label, key in MENU)
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ''
    return f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}
<title>{escape(title)} | 가온택배</title><style>{STYLE}</style></head><body>
<header><div class="bar"><a class="logo" href="/"><i>가</i>가온택배</a><nav>{menu}</nav><span class="demo">개발·시연용 가상 택배사</span></div></header>
<main>{body}</main><footer>가온택배는 WMS 개발·시연을 위한 가상 택배사입니다. 실제 배송은 이루어지지 않습니다.</footer></body></html>'''


# ---------- 표시용 도우미 ----------
def fmt_time(value, with_year=False):
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return escape(str(value or ''))
    return moment.strftime('%Y.%m.%d %H:%M:%S' if with_year else '%m.%d %H:%M:%S')


def mask_name(name):
    name = name or ''
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + '*'
    return name[0] + '*' * (len(name) - 2) + name[-1]


def mask_phone(phone):
    digits = ''.join(ch for ch in phone or '' if ch.isdigit())
    return f'{digits[:3]}-****-{digits[-4:]}' if len(digits) >= 9 else '***'


def mask_address(address):
    words = (address or '').split()
    return ' '.join(words[:2]) + (' ***' if len(words) > 2 else '')


def badge(status):
    if status in ('배송완료', '회수완료'):
        cls = 'b-done'
    elif status == '취소':
        cls = 'b-cancel'
    elif status.startswith('회수'):
        cls = 'b-pick'
    else:
        cls = 'b-go'
    return f'<span class="badge {cls}">{escape(status)}</span>'


def kind_label(kind):
    return '반품 회수' if kind == 'pickup' else '배송'


# ---------- 고객용: 배송 조회 ----------
def home_page(error='', number=''):
    err = f'<div class="err">{escape(error)}</div>' if error else ''
    body = f'''<section class="hero"><h1>배송 조회</h1><div>운송장 번호로 배송·반품 회수 진행 상황을 확인하세요.</div>
<form class="search" action="/track" method="get"><input name="no" value="{escape(number)}" placeholder="운송장 번호 12자리" inputmode="numeric" autofocus aria-label="운송장 번호">
<button class="light">조회</button></form>{err}</section>
<div class="grid"><div class="card"><h2>📦 배송</h2><div class="muted">접수 → 집하 → 배송중 → 배송출발 → 배송완료</div></div>
<div class="card"><h2>↩ 반품 회수</h2><div class="muted">회수접수 → 회수집하 → 회수이동중 → 회수완료</div></div>
<div class="card"><h2>🔗 기업 고객</h2><div class="muted">쇼핑몰·WMS 연동은 <a href="/docs">API 문서</a>를 참고하세요.</div></div></div>'''
    return layout('배송 조회', body, 'track')


def tracking_page(data, flow, eta_text):
    names = [name for name, _ in flow]
    current = data['status']
    cancelled = current == '취소'
    reached = max((names.index(e['status']) for e in data['events'] if e['status'] in names), default=0)
    steps = ''.join(
        f'<li class="{"now" if i == reached and not cancelled else "done" if i < reached or (cancelled and i <= reached) else ""}">{escape(name)}</li>'
        for i, name in enumerate(names))
    timeline = ''.join(
        f'<li><span class="muted">{fmt_time(e["occurred_at"], True)}</span><span>{escape(e["status"])}</span><span>{escape(e["location"])}</span></li>'
        for e in reversed(data['events']))
    party = '받는 분' if data['kind'] == 'delivery' else '보내는 분'
    headline = '취소된 송장입니다' if cancelled else escape(current)
    eta = f'<div class="muted">{escape(eta_text)}</div>' if eta_text and not cancelled else ''
    body = f'''<div class="card"><div class="muted small">{kind_label(data['kind'])} · 운송장 번호 <b class="mono">{escape(data['waybill_no'])}</b></div>
<div class="status-big">{headline}</div>{eta}<ol class="steps">{steps}</ol></div>
<div class="split"><div class="card"><h2>배송 정보</h2><dl class="info">
<dt>{party}</dt><dd>{escape(mask_name(data['name']))} · {escape(mask_phone(data['phone']))}</dd>
<dt>주소</dt><dd>{escape(mask_address(data['address']))}</dd>
<dt>주문 번호</dt><dd class="mono">{escape(data['ref'])}</dd></dl>
<div class="muted small">개인정보 보호를 위해 일부만 표시합니다.</div></div>
<div class="card"><h2>진행 이력</h2><ul class="timeline">{timeline}</ul></div></div>
<div class="muted small">이 페이지는 30초마다 새로 고칩니다. <a href="/">다른 운송장 조회</a></div>'''
    return layout(f'{data["waybill_no"]} 배송 조회', body, 'track', refresh=0 if cancelled or current == names[-1] else 30)


# ---------- 운영자용: 송장 콘솔 ----------
def console_page(rows, counts, query, settings):
    def option(value, label, selected):
        return f'<option value="{escape(value)}"{" selected" if value == selected else ""}>{escape(label)}</option>'

    kinds = option('', '전체 구분', query['kind']) + option('delivery', '배송', query['kind']) + option('pickup', '반품 회수', query['kind'])
    statuses = option('', '전체 상태', query['status']) + ''.join(option(s, s, query['status']) for s in settings['statuses'])
    back = '/console' + ('?' + urlencode({k: v for k, v in query.items() if v}) if any(query.values()) else '')

    def actions(r):
        if r['status'] in ('배송완료', '회수완료', '취소'):
            return '<span class="muted small">종료</span>'
        buttons = [('advance', '다음 단계', ''), ('finish', '완료까지', 'light')]
        if r['status'] in ('접수', '회수접수'):
            buttons.append(('cancel', '취소', 'danger'))
        return '<div class="actions">' + ''.join(
            f'<form method="post" action="/console/{act}/{r["waybill_no"]}"><input type="hidden" name="back" value="{escape(back)}">'
            f'<button class="sm {cls}">{label}</button></form>' for act, label, cls in buttons) + '</div>'

    def ready(r):
        if r['kind'] == 'pickup':
            return '<span class="muted">-</span>'
        return '<span class="badge b-go">요청됨</span>' if r['ready'] else '<span class="badge">출고 대기</span>'

    lines = ''.join(
        f'<tr><td class="mono"><a href="/track/{r["waybill_no"]}">{r["waybill_no"]}</a></td><td>{kind_label(r["kind"])}</td>'
        f'<td class="mono">{escape(r["ref"])}</td><td>{escape(r["name"])}</td><td>{badge(r["status"])}</td><td>{ready(r)}</td>'
        f'<td class="muted small">{fmt_time(r["created_at"])}</td><td>{actions(r)}</td></tr>' for r in rows
    ) or '<tr><td colspan="8" class="muted" style="text-align:center;padding:30px">조건에 맞는 송장이 없습니다. WMS에서 주문이나 반품을 등록하면 여기에 나타납니다.</td></tr>'
    stats = ''.join(f'<div class="stat"><span class="muted small">{escape(label)}</span><b>{value}</b></div>' for label, value in counts)
    auto = query.get('auto') == '1'
    auto_link = back.replace('auto=1', '').rstrip('?&') if auto else back + ('&' if '?' in back else '?') + 'auto=1'
    body = f'''<h1>송장 콘솔</h1><p class="muted">단계는 {settings['step']}초마다 자동으로 진행됩니다. 배송 송장은 WMS에서 출고를 완료(집하 요청)해야 진행되며,
[다음 단계]·[완료까지]는 시연을 위해 즉시 진행합니다. 일시 장애 확률 {settings['fail_rate']:.0%}.</p>
<div class="stats">{stats}</div><div class="card">
<form class="filters" method="get" action="/console"><select name="kind">{kinds}</select><select name="status">{statuses}</select>
<input name="q" value="{escape(query['q'])}" placeholder="운송장·주문번호·이름"><button>검색</button>
{'<input type="hidden" name="auto" value="1">' if auto else ''}<span style="flex:1"></span>
<a class="btn light" href="{escape(auto_link or '/console')}">{'자동 새로고침 끄기' if auto else '자동 새로고침 (10초)'}</a></form>
<table><tr><th>운송장</th><th>구분</th><th>WMS 번호</th><th>이름</th><th>상태</th><th>집하 요청</th><th>접수 시각</th><th>시연 조작</th></tr>{lines}</table></div>'''
    return layout('송장 콘솔', body, 'console', refresh=10 if auto else 0)


def webhooks_page(rows, url_hint):
    def result(r):
        code = r['result_code']
        ok = code and code < 300
        return f'<span class="badge {"b-done" if ok else "b-err"}">{code or "연결 실패"}</span>'

    lines = ''.join(
        f'<tr><td class="muted small">{fmt_time(r["sent_at"])}</td><td class="mono"><a href="/track/{r["waybill_no"]}">{r["waybill_no"]}</a></td>'
        f'<td>{badge(r["status"])}</td><td>{r["attempt"]}회차</td>'
        f'<td>{result(r)}</td>'
        f'<td class="small">{escape(r["error"] or "")}</td><td class="mono small">{escape(r["url"])}</td></tr>' for r in rows
    ) or '<tr><td colspan="7" class="muted" style="text-align:center;padding:30px">아직 보낸 알림이 없습니다.</td></tr>'
    body = f'''<h1>웹훅 기록</h1><p class="muted">배송 단계가 바뀔 때마다 WMS에 보낸 알림입니다. 실패하면 3초, 10초 뒤 다시 보냅니다. {escape(url_hint)}</p>
<div class="card"><table><tr><th>보낸 시각</th><th>운송장</th><th>상태</th><th>시도</th><th>응답</th><th>오류</th><th>받는 주소</th></tr>{lines}</table></div>'''
    return layout('웹훅 기록', body, 'webhooks')


# ---------- 기업 고객용: API 문서 ----------
def docs_page(base_url):
    def ep(method, path, desc, request=None, response=None):
        req = f'<div class="muted small">요청 본문</div><pre><code>{escape(request)}</code></pre>' if request else ''
        res = f'<div class="muted small">응답 예시</div><pre><code>{escape(response)}</code></pre>' if response else ''
        return f'<div class="ep"><span class="m m-{method.lower()}">{method}</span><b>{escape(path)}</b></div><div>{desc}</div>{req}{res}'

    shipment = '''{
  "result": "OK",
  "data": {
    "waybill_no": "581234567890",
    "kind": "delivery",
    "ref": "ORD-20261104-0001",
    "status": "접수",
    "carrier": "가온택배",
    "events": [
      {"event_id": "9f1c...", "waybill_no": "581234567890", "status": "접수",
       "location": "송장 접수", "occurred_at": "2026-11-04T10:00:00+09:00"}
    ]
  }
}'''
    party = '''{
  "order_ref": "ORD-20261104-0001",
  "receiver": {"name": "김수령", "phone": "010-1234-5678", "zipcode": "06236",
               "address": "서울시 강남구 테헤란로 1", "address_detail": "101호"},
  "callback_url": "https://wms.example.com/api/carrier/webhook/"
}'''
    pickup = party.replace('"order_ref"', '"return_ref"').replace('ORD-', 'RTN-').replace('"receiver"', '"sender"')
    verify = '''import hashlib, hmac

def verify(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)'''
    webhook = '''POST {callback_url}
Content-Type: application/json
X-Carrier-Signature: 3b5d...(HMAC-SHA256 16진수)

{"event_id": "a71e...", "waybill_no": "581234567890", "kind": "delivery",
 "status": "집하", "location": "출고지 집하", "occurred_at": "2026-11-04T10:01:00+09:00"}'''
    errors = ''.join(f'<tr><td>{c}</td><td class="mono">{escape(k)}</td><td>{escape(m)}</td></tr>' for c, k, m in [
        (400, 'INVALID_PARAMETER / INVALID_PHONE / INVALID_ZIPCODE', '필수값 누락 또는 형식 오류'),
        (401, 'UNAUTHORIZED', 'API 키가 없거나 다름'),
        (404, 'WAYBILL_NOT_FOUND', '없는 운송장 번호'),
        (409, 'ALREADY_COLLECTED / INVALID_STATE', '이미 집하되어 취소 불가, 진행할 수 없는 단계'),
        (422, 'ADDRESS_NOT_FOUND', '주소 검증 실패 (시연: 주소에 "없는주소" 포함)'),
        (503, 'SYSTEM_BUSY', '일시 장애. 잠시 후 다시 시도'),
    ])
    body = f'''<h1>API 문서</h1><p class="muted">쇼핑몰·WMS가 가온택배와 연동하는 방법입니다. 기본 주소 <code>{escape(base_url)}</code></p>
<div class="card"><h2>공통</h2>
<ul><li>모든 API 요청에 <code>X-API-Key</code> 헤더를 붙입니다.</li>
<li>본문과 응답은 JSON(UTF-8)입니다. 성공하면 <code>{{"result":"OK","data":...}}</code>, 실패하면 <code>{{"result":"ERROR","code":...,"message":...}}</code>를 돌려줍니다.</li>
<li>전화번호는 <code>010-1234-5678</code> 형식, 우편번호는 숫자 5자리입니다.</li></ul>
<table><tr><th>HTTP</th><th>code</th><th>뜻</th></tr>{errors}</table></div>
<div class="card"><h2>배송</h2>
{ep('POST', '/v1/shipments', '운송장을 발급합니다. 발급 즉시 <b>접수</b> 상태입니다.', party, shipment)}
{ep('POST', '/v1/shipments/{waybill_no}/ready', '출고를 확정하고 집하를 요청합니다. 이후 기사가 방문해 <b>집하</b>합니다.')}
{ep('POST', '/v1/shipments/{waybill_no}/cancel', '집하 전(접수 상태)에만 취소할 수 있습니다.')}
{ep('GET', '/v1/shipments/{waybill_no}', '현재 상태와 전체 이력을 조회합니다. 반품 회수 운송장도 같은 주소로 조회합니다.')}</div>
<div class="card"><h2>반품 회수</h2>
{ep('POST', '/v1/pickups', '고객 주소로 회수 기사를 보냅니다. 발급 즉시 <b>회수접수</b> 상태입니다.', pickup)}
{ep('POST', '/v1/pickups/{waybill_no}/cancel', '기사가 수거하기 전(회수접수 상태)에만 취소할 수 있습니다.')}</div>
<div class="card"><h2>상태 알림 (웹훅)</h2><p>단계가 바뀔 때마다 등록한 <code>callback_url</code>로 알립니다. 2xx 이외의 응답이면 3초, 10초 뒤 다시 보냅니다.
같은 알림이 여러 번 갈 수 있으니 <code>event_id</code>로 중복을 거르고, 순서가 바뀔 수 있으니 <code>occurred_at</code>으로 최신 단계를 판단하세요.</p>
<pre><code>{escape(webhook)}</code></pre>
<p>본문 전체를 공유 비밀값으로 HMAC-SHA256 서명해 <code>X-Carrier-Signature</code>에 담습니다. 받는 쪽 확인 예시:</p>
<pre><code>{escape(verify)}</code></pre></div>
<div class="card"><h2>시연용</h2>{ep('POST', '/v1/simulate/{waybill_no}/advance', '다음 단계로 즉시 진행합니다. 실제 택배사에는 없는 기능입니다.')}</div>'''
    return layout('API 문서', body, 'docs')
