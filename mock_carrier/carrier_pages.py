"""데모택배 웹 화면 (배송 조회, 송장 콘솔, 웹훅 기록, API 문서). 데이터는 server.py가 넘겨줍니다."""

from datetime import datetime
from html import escape
from urllib.parse import urlencode

STYLE = """
:root{--brand:#0b7a5c;--brand-dark:#075c45;--brand-deep:#0c2e25;--brand-soft:#e7f4ef;--accent:#f5a524;--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;--bg:#f4f6f8;--warn:#c2410c;--danger:#b91c1c}
*{box-sizing:border-box}
body{margin:0;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:var(--ink);background:var(--bg);font-size:15px;line-height:1.55;word-break:keep-all;overflow-wrap:anywhere}
a{color:var(--brand)}.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
.util{background:var(--brand-deep);color:#b9d6cc;font-size:12px}.util .wrap{display:flex;justify-content:space-between;align-items:center;height:34px;gap:16px}
.util a{color:#b9d6cc;text-decoration:none}.util a:hover{color:#fff}.util .links a+a:before{content:'';display:inline-block;width:1px;height:10px;background:#3d6457;margin:0 12px}
.gnb{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}.gnb .wrap{display:flex;align-items:center;gap:40px;height:70px}
.logo{font-size:23px;font-weight:800;color:var(--brand);text-decoration:none;display:flex;align-items:center;gap:9px;white-space:nowrap;letter-spacing:-.5px}
.logo i{display:inline-block;width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--brand),#15a07c);color:#fff;font-style:normal;font-size:16px;text-align:center;line-height:30px}
nav{display:flex;flex:1;height:100%}nav a{display:flex;align-items:center;padding:0 18px;color:var(--ink);text-decoration:none;font-weight:700;font-size:16px;border-bottom:3px solid transparent;white-space:nowrap}
nav a:hover{color:var(--brand)}nav a.on{color:var(--brand);border-bottom-color:var(--brand)}
.demo{font-size:12px;font-weight:700;color:var(--brand-dark);background:var(--brand-soft);border-radius:14px;padding:4px 11px;white-space:nowrap}
.band{background:#fff;border-bottom:1px solid var(--line)}.band .wrap{padding-top:28px;padding-bottom:24px}
.crumb{font-size:12px;color:var(--muted);margin-bottom:6px}.crumb b{color:var(--ink);font-weight:600}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.6px}h2{font-size:18px;margin:0 0 14px;letter-spacing:-.3px}h3{font-size:16px;margin:0 0 6px}
.lead{color:var(--muted);margin:0;max-width:820px}.muted{color:var(--muted)}.small{font-size:13px}.mono,td.mono{font-family:Consolas,monospace}
main{padding:28px 0 56px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:24px;margin-bottom:18px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.card-head h2{margin:0}
input,select{font:inherit;padding:9px 12px;border:1px solid #cfd5db;border-radius:8px;background:#fff;color:var(--ink)}input:focus,select:focus{outline:2px solid var(--brand);outline-offset:-1px;border-color:var(--brand)}
button,.btn{font:inherit;font-weight:700;padding:9px 18px;border-radius:8px;border:1px solid var(--brand);background:var(--brand);color:#fff;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;white-space:nowrap}
button:hover,.btn:hover{background:var(--brand-dark)}button.light,.btn.light{background:#fff;color:var(--brand)}button.light:hover,.btn.light:hover{background:var(--brand-soft)}
button.sm{padding:4px 10px;font-size:13px;font-weight:600}button.danger{background:#fff;color:var(--danger);border-color:#f0b4b4}button.danger:hover{background:#fff1f1}
.err{background:#fff1f1;border:1px solid #f3c2c2;color:var(--danger);border-radius:8px;padding:11px 14px;margin-top:14px;font-weight:600}
.hero{background:radial-gradient(circle at 85% 20%,rgba(255,255,255,.12),transparent 40%),linear-gradient(120deg,var(--brand-deep),var(--brand) 70%,#15a07c);color:#fff}
.hero .wrap{padding-top:64px;padding-bottom:84px}.hero .eyebrow{display:inline-block;font-size:13px;font-weight:700;color:var(--accent);margin-bottom:10px;letter-spacing:.5px}
.hero h1{font-size:38px;line-height:1.3;margin-bottom:10px}.hero p{color:#d5ebe3;margin:0}
.search{display:flex;margin-top:28px;max-width:640px;background:#fff;border-radius:12px;padding:6px;box-shadow:0 12px 30px rgba(0,0,0,.18)}
.search input{flex:1;min-width:0;border:0;font-size:19px;letter-spacing:1px;padding:12px 14px}.search input:focus{outline:none}.search button{padding:0 30px;font-size:16px;border-radius:9px}
.hero .err{max-width:640px}.hero-note{font-size:13px;color:#b9d6cc;margin-top:12px}
.home main{padding-top:0}.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:-44px;position:relative}
.tile{display:block;background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px;text-decoration:none;color:var(--ink);box-shadow:0 6px 18px rgba(16,24,40,.07);transition:transform .15s,box-shadow .15s}
.tile:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(16,24,40,.12)}.tile .ico{display:flex;align-items:center;justify-content:center;width:46px;height:46px;border-radius:12px;background:var(--brand-soft);font-size:22px;margin-bottom:12px}
.tile p{margin:0;color:var(--muted);font-size:14px}
.section{margin-top:36px}.section-title{margin-bottom:14px}.section-title h2{margin:0;font-size:21px}
.cols{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}.cols .card{margin:0}
.flow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0;padding:0;list-style:none}
.flow li{background:var(--brand-soft);color:var(--brand-dark);font-weight:700;font-size:14px;border-radius:20px;padding:5px 13px;white-space:nowrap}
.flow li+li:before{content:'\\203A';color:var(--muted);margin:0 8px 0 -2px;font-weight:400}.flow.pick li{background:#fff3e6;color:var(--warn)}
.notice{list-style:none;margin:0;padding:0}.notice li{display:flex;gap:10px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}.notice li:last-child{border-bottom:0}
.notice a{color:var(--ink);text-decoration:none;flex:1}.notice a:hover{color:var(--brand);text-decoration:underline}
.tag{flex-shrink:0;font-size:12px;font-weight:700;border-radius:5px;padding:2px 8px;background:#eef2f7;color:#374151;white-space:nowrap}.tag.g{background:var(--brand-soft);color:var(--brand-dark)}
.guide{margin:0;padding-left:18px;color:#374151}.guide li{margin:8px 0}
.mini-search{display:flex;gap:8px;margin-top:16px;max-width:460px}.mini-search input{flex:1;min-width:0}
.kind{display:inline-block;font-size:12px;font-weight:700;border-radius:5px;padding:2px 8px;background:var(--brand-soft);color:var(--brand-dark);margin-right:6px}
.status-big{font-size:32px;font-weight:800;color:var(--brand);margin:8px 0 2px;letter-spacing:-.5px}
.steps{display:flex;margin:30px 0 4px;padding:0;list-style:none}
.steps li{flex:1;text-align:center;position:relative;font-size:13px;color:var(--muted);white-space:nowrap}
.steps li:before{content:'';display:block;width:30px;height:30px;margin:0 auto 8px;border-radius:50%;background:#e5e7eb;border:3px solid #fff;box-shadow:0 0 0 2px #e5e7eb;position:relative;z-index:1}
.steps li:after{content:'';position:absolute;top:14px;left:-50%;width:100%;height:4px;background:#e5e7eb}.steps li:first-child:after{display:none}
.steps li.done{color:var(--ink)}.steps li.done:before{background:var(--brand);box-shadow:0 0 0 2px var(--brand)}.steps li.done:after{background:var(--brand)}
.steps li.now{color:var(--brand);font-weight:800}.steps li.now:before{background:#fff;box-shadow:0 0 0 4px var(--brand)}.steps li.now:after{background:var(--brand)}
.split{display:grid;grid-template-columns:1fr 2fr;gap:18px;margin-bottom:18px}.split .card{margin:0}
.info{margin:0}.info dt{font-size:13px;color:var(--muted)}.info dd{margin:2px 0 14px;font-weight:600}
.timeline{list-style:none;margin:0;padding:0}.timeline li{display:grid;grid-template-columns:150px 110px 1fr;gap:12px;padding:12px 0 12px 22px;border-bottom:1px solid var(--line);position:relative}
.timeline li:before{content:'';position:absolute;left:3px;top:19px;width:9px;height:9px;border-radius:50%;background:#cbd5e1}
.timeline li:first-child{font-weight:700;color:var(--brand)}.timeline li:first-child:before{background:var(--brand);box-shadow:0 0 0 4px var(--brand-soft)}.timeline li:last-child{border-bottom:0}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:middle;white-space:nowrap}
tr:last-child td{border-bottom:0}tr:hover td{background:#fafcfb}
th{background:#f7f9f8;font-size:13px;font-weight:700;color:#4b5563}
td.clip{max-width:280px;overflow:hidden;text-overflow:ellipsis}td.empty{text-align:center;padding:36px;color:var(--muted);white-space:normal}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:700;background:#eef2f7;color:#374151;white-space:nowrap}
.b-go{background:var(--brand-soft);color:var(--brand-dark)}.b-done{background:#dcfce7;color:#166534}.b-cancel{background:#f3f4f6;color:#9ca3af}.b-err{background:#fee2e2;color:var(--danger)}.b-pick{background:#fff3e6;color:var(--warn)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.stat{background:#fff;border:1px solid var(--line);border-top:3px solid var(--brand);border-radius:10px;padding:14px 16px}.stat b{display:block;font-size:26px;color:var(--ink);margin-top:2px}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}.filters .grow{flex:1}.actions{display:flex;gap:4px}
pre{background:#111827;color:#e5e7eb;border-radius:8px;padding:14px;overflow:auto;font-size:13px;line-height:1.5}
code{font-family:Consolas,monospace;background:#f1f5f4;padding:1px 5px;border-radius:4px}pre code{background:none;padding:0}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}.toc a{background:#fff;border:1px solid var(--line);border-radius:20px;padding:5px 14px;font-size:14px;font-weight:600;text-decoration:none;color:var(--ink)}.toc a:hover{border-color:var(--brand);color:var(--brand)}
.ep{display:flex;gap:10px;align-items:center;margin:22px 0 8px}.ep b{font-family:Consolas,monospace;font-size:15px}
.m{font-size:12px;font-weight:800;padding:3px 8px;border-radius:5px;color:#fff}.m-get{background:#2563eb}.m-post{background:var(--brand)}
footer{background:#1b2420;color:#9aa8a2;font-size:13px}footer .wrap{padding-top:34px;padding-bottom:30px}
.foot{display:flex;justify-content:space-between;gap:30px;flex-wrap:wrap}.foot .logo{color:#fff;font-size:19px;margin-bottom:10px}.foot p{margin:0;max-width:520px}
.foot-links{display:flex;gap:22px;flex-wrap:wrap}.foot-links a{color:#d6dfdb;text-decoration:none;font-weight:600}.foot-links a:hover{color:#fff}
.copy{border-top:1px solid #2c3833;margin-top:24px;padding-top:16px;font-size:12px}
@media(max-width:900px){.tiles{grid-template-columns:repeat(2,1fr)}.split,.cols{grid-template-columns:1fr}}
@media(max-width:640px){.wrap{padding:0 16px}.util .links{display:none}.gnb .wrap{flex-wrap:wrap;height:auto;gap:0;padding-top:12px}.gnb .demo{margin-left:auto}
nav{order:3;flex:0 0 calc(100% + 32px);overflow-x:auto;margin:6px -16px 0;padding:0 6px;height:auto}nav a{padding:10px 10px 11px;font-size:15px}
.hero .wrap{padding-top:40px;padding-bottom:64px}.hero h1{font-size:27px}.search input{font-size:16px}.search button{padding:0 18px}
.tiles{gap:10px}.tile{padding:16px}.card{padding:18px}h1{font-size:23px}.status-big{font-size:26px}
.timeline li{grid-template-columns:1fr;gap:2px}.steps li{font-size:11px;white-space:normal}.mini-search{max-width:none}}
"""

MENU = [('/', '배송 조회', 'track'), ('/console', '송장 콘솔', 'console'), ('/webhooks', '웹훅 기록', 'webhooks'), ('/docs', 'API 문서', 'docs')]
DISCLAIMER = '데모택배는 WMS 개발·시연을 위한 가상 택배사입니다. 실제 배송은 이루어지지 않습니다.'


def layout(title, body, active='', refresh=0, lead=None, crumb=''):
    # lead를 주면 본문 위에 제목 띠(경로·제목·설명)를 붙입니다. 첫 화면은 큰 검색 영역(hero)을 쓰므로 주지 않습니다.
    menu = ''.join(f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>' for href, label, key in MENU)
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ''
    band = (
        (
            f'<section class="band"><div class="wrap"><div class="crumb">홈 › {escape(crumb)} › <b>{escape(title)}</b></div>'
            f'<h1>{escape(title)}</h1>{lead}</div></section>'
        )
        if lead is not None
        else ''
    )
    foot = ''.join(f'<a href="{href}">{label}</a>' for href, label, _ in MENU)
    content = f'<div class="wrap">{body}</div>' if band else body
    return f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}
<title>{escape(title)} | 데모택배</title><style>{STYLE}</style></head><body class="{'' if band else 'home'}">
<div class="util"><div class="wrap"><span>개발·시연용 가상 택배 서비스</span><span class="links"><a href="/">배송 조회</a><a href="/docs">기업고객 API</a><a href="/console">운영자 콘솔</a></span></div></div>
<header class="gnb"><div class="wrap"><a class="logo" href="/"><i>데</i>데모택배</a><nav>{menu}</nav><span class="demo">가상 택배사</span></div></header>
{band}<main>{content}</main>
<footer><div class="wrap"><div class="foot"><div><div class="logo"><i>데</i>데모택배</div><p>{DISCLAIMER}</p></div><div class="foot-links">{foot}</div></div>
<div class="copy">© 데모택배 (가상 서비스) · 화면의 이름·주소·전화번호는 시연용 데이터입니다.</div></div></footer></body></html>'''


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
    tiles = ''.join(
        f'<a class="tile" href="{href}"><span class="ico">{icon}</span><h3>{title}</h3><p>{desc}</p></a>'
        for href, icon, title, desc in [
            ('#track', '📦', '배송 조회', '운송장 번호로 현재 단계와 진행 이력을 확인합니다.'),
            ('#flow', '↩', '반품 회수', '회수 운송장도 같은 번호로 조회됩니다.'),
            ('/docs', '🔗', '기업고객 API', '쇼핑몰·WMS의 운송장 발급과 상태 알림 연동'),
            ('/console', '🗂', '운영자 콘솔', '발급된 송장 목록과 시연용 단계 진행'),
        ]
    )
    notices = ''.join(
        f'<li><span class="tag{" g" if g else ""}">{tag}</span><a href="{href}">{text}</a></li>'
        for tag, g, href, text in [
            ('안내', True, '#track', '이 사이트는 WMS 개발·시연을 위한 가상 택배사입니다.'),
            ('시연', False, '/console', '송장 콘솔에서 [다음 단계]·[완료까지]로 배송을 바로 진행할 수 있습니다.'),
            ('연동', False, '/docs', '상태 알림(웹훅)의 서명(HMAC-SHA256) 확인 방법을 안내합니다.'),
            ('연동', False, '/webhooks', 'WMS로 보낸 상태 알림과 재전송 기록은 웹훅 기록에서 확인하세요.'),
        ]
    )
    body = f'''<section class="hero" id="track"><div class="wrap"><span class="eyebrow">데모택배 배송 조회</span>
<h1>운송장 번호 하나로<br>배송과 반품 회수를 확인하세요</h1><p>집하부터 배송 완료까지 단계별 진행 상황을 바로 보여드립니다.</p>
<form class="search" action="/track" method="get"><input name="no" value="{escape(number)}" placeholder="운송장 번호 12자리" inputmode="numeric" autofocus aria-label="운송장 번호">
<button>조회</button></form>{err}<div class="hero-note">운송장 번호는 숫자만 입력해 주세요. 개인정보는 일부만 표시합니다.</div></div></section>
<div class="wrap"><div class="tiles">{tiles}</div>
<div class="section" id="flow"><div class="section-title"><h2>배송 단계 안내</h2></div><div class="cols">
<div class="card"><h3>📦 배송</h3><p class="muted small">보내는 곳에서 출고가 확정되면 기사가 방문해 집하합니다.</p>
<ol class="flow"><li>접수</li><li>집하</li><li>배송중</li><li>배송출발</li><li>배송완료</li></ol></div>
<div class="card"><h3>↩ 반품 회수</h3><p class="muted small">고객 주소로 회수 기사가 방문해 물건을 수거합니다.</p>
<ol class="flow pick"><li>회수접수</li><li>회수집하</li><li>회수이동중</li><li>회수완료</li></ol></div></div></div>
<div class="section"><div class="cols"><div class="card"><div class="card-head"><h2>공지사항</h2></div><ul class="notice">{notices}</ul></div>
<div class="card"><div class="card-head"><h2>이용 안내</h2></div><ul class="guide">
<li>배송 조회 화면은 30초마다 새로 고쳐집니다.</li><li>받는 분·보내는 분의 이름, 전화번호, 주소는 일부를 가려서 표시합니다.</li>
<li>집하 전(접수 상태)에만 송장을 취소할 수 있습니다.</li><li>기업 고객 연동은 <a href="/docs">API 문서</a>를 참고하세요.</li></ul></div></div></div></div>'''
    return layout('배송 조회', body, 'track')


def tracking_page(data, flow, eta_text):
    names = [name for name, _ in flow]
    current = data['status']
    cancelled = current == '취소'
    reached = max((names.index(e['status']) for e in data['events'] if e['status'] in names), default=0)
    steps = ''.join(
        f'<li class="{"now" if i == reached and not cancelled else "done" if i < reached or (cancelled and i <= reached) else ""}">{escape(name)}</li>'
        for i, name in enumerate(names)
    )
    timeline = ''.join(
        f'<li><span class="muted">{fmt_time(e["occurred_at"], True)}</span><span>{escape(e["status"])}</span><span>{escape(e["location"])}</span></li>'
        for e in reversed(data['events'])
    )
    party = '받는 분' if data['kind'] == 'delivery' else '보내는 분'
    headline = '취소된 송장입니다' if cancelled else escape(current)
    eta = f'<div class="muted">{escape(eta_text)}</div>' if eta_text and not cancelled else ''
    lead = (
        f'<form class="mini-search" action="/track" method="get"><input name="no" value="{escape(data["waybill_no"])}" '
        f'inputmode="numeric" aria-label="운송장 번호"><button>다시 조회</button></form>'
    )
    body = f"""<div class="card"><div class="small"><span class="kind">{kind_label(data['kind'])}</span><span class="muted">운송장 번호</span> <b class="mono">{escape(data['waybill_no'])}</b></div>
<div class="status-big">{headline}</div>{eta}<ol class="steps">{steps}</ol></div>
<div class="split"><div class="card"><h2>배송 정보</h2><dl class="info">
<dt>{party}</dt><dd>{escape(mask_name(data['name']))} · {escape(mask_phone(data['phone']))}</dd>
<dt>주소</dt><dd>{escape(mask_address(data['address']))}</dd>
<dt>주문 번호</dt><dd class="mono">{escape(data['ref'])}</dd></dl>
<div class="muted small">개인정보 보호를 위해 일부만 표시합니다.</div></div>
<div class="card"><h2>진행 이력</h2><ul class="timeline">{timeline}</ul></div></div>
<div class="muted small">이 페이지는 30초마다 새로 고칩니다. <a href="/">다른 운송장 조회</a></div>"""
    return layout('배송 조회 결과', body, 'track', refresh=0 if cancelled or current == names[-1] else 30, lead=lead, crumb='배송 조회')


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
        return (
            '<div class="actions">'
            + ''.join(
                f'<form method="post" action="/console/{act}/{r["waybill_no"]}"><input type="hidden" name="back" value="{escape(back)}">'
                f'<button class="sm {cls}">{label}</button></form>'
                for act, label, cls in buttons
            )
            + '</div>'
        )

    def ready(r):
        if r['kind'] == 'pickup':
            return '<span class="muted">-</span>'
        return '<span class="badge b-go">요청됨</span>' if r['ready'] else '<span class="badge">출고 대기</span>'

    lines = (
        ''.join(
            f'<tr><td class="mono"><a href="/track/{r["waybill_no"]}">{r["waybill_no"]}</a></td><td>{kind_label(r["kind"])}</td>'
            f'<td class="mono">{escape(r["ref"])}</td><td>{escape(r["name"])}</td><td>{badge(r["status"])}</td><td>{ready(r)}</td>'
            f'<td class="muted small">{fmt_time(r["created_at"])}</td><td>{actions(r)}</td></tr>'
            for r in rows
        )
        or '<tr><td colspan="8" class="empty">조건에 맞는 송장이 없습니다. WMS에서 주문이나 반품을 등록하면 여기에 나타납니다.</td></tr>'
    )
    stats = ''.join(f'<div class="stat"><span class="muted small">{escape(label)}</span><b>{value}</b></div>' for label, value in counts)
    auto = query.get('auto') == '1'
    auto_link = back.replace('auto=1', '').rstrip('?&') if auto else back + ('&' if '?' in back else '?') + 'auto=1'
    lead = (
        f'<p class="lead">단계는 {settings["step"]}초마다 자동으로 진행됩니다. 배송 송장은 WMS에서 출고를 완료(집하 요청)해야 진행되며, '
        f'[다음 단계]·[완료까지]는 시연을 위해 즉시 진행합니다. 일시 장애 확률 {settings["fail_rate"]:.0%}.</p>'
    )
    body = f'''<div class="stats">{stats}</div><div class="card">
<form class="filters" method="get" action="/console"><select name="kind">{kinds}</select><select name="status">{statuses}</select>
<input name="q" value="{escape(query['q'])}" placeholder="운송장·주문번호·이름"><button>검색</button>
{'<input type="hidden" name="auto" value="1">' if auto else ''}<span class="grow"></span>
<a class="btn light" href="{escape(auto_link or '/console')}">{'자동 새로고침 끄기' if auto else '자동 새로고침 (10초)'}</a></form>
<div class="table-wrap"><table><tr><th>운송장</th><th>구분</th><th>WMS 번호</th><th>이름</th><th>상태</th><th>집하 요청</th><th>접수 시각</th><th>시연 조작</th></tr>{lines}</table></div></div>'''
    return layout('송장 콘솔', body, 'console', refresh=10 if auto else 0, lead=lead, crumb='운영자')


def webhooks_page(rows, url_hint):
    def result(r):
        code = r['result_code']
        ok = code and code < 300
        return f'<span class="badge {"b-done" if ok else "b-err"}">{code or "연결 실패"}</span>'

    lines = (
        ''.join(
            f'<tr><td class="muted small">{fmt_time(r["sent_at"])}</td><td class="mono"><a href="/track/{r["waybill_no"]}">{r["waybill_no"]}</a></td>'
            f'<td>{badge(r["status"])}</td><td>{r["attempt"]}회차</td>'
            f'<td>{result(r)}</td>'
            f'<td class="small clip" title="{escape(r["error"] or "")}">{escape(r["error"] or "-")}</td>'
            f'<td class="mono small clip" title="{escape(r["url"])}">{escape(r["url"])}</td></tr>'
            for r in rows
        )
        or '<tr><td colspan="7" class="empty">아직 보낸 알림이 없습니다.</td></tr>'
    )
    lead = f'<p class="lead">배송 단계가 바뀔 때마다 WMS에 보낸 알림입니다. 실패하면 3초, 10초 뒤 다시 보냅니다. {escape(url_hint)}</p>'
    body = f"""<div class="card"><div class="table-wrap"><table><tr><th>보낸 시각</th><th>운송장</th><th>상태</th><th>시도</th><th>응답</th><th>오류</th><th>받는 주소</th></tr>{lines}</table></div></div>"""
    return layout('웹훅 기록', body, 'webhooks', lead=lead, crumb='운영자')


# ---------- 기업 고객용: API 문서 ----------
def docs_page(base_url):
    def ep(method, path, desc, request=None, response=None):
        req = f'<div class="muted small">요청 본문</div><pre><code>{escape(request)}</code></pre>' if request else ''
        res = f'<div class="muted small">응답 예시</div><pre><code>{escape(response)}</code></pre>' if response else ''
        return f'<div class="ep"><span class="m m-{method.lower()}">{method}</span><b>{escape(path)}</b></div><div>{desc}</div>{req}{res}'

    shipment = """{
  "result": "OK",
  "data": {
    "waybill_no": "581234567890",
    "kind": "delivery",
    "ref": "ORD-20261104-0001",
    "status": "접수",
    "carrier": "데모택배",
    "events": [
      {"event_id": "9f1c...", "waybill_no": "581234567890", "status": "접수",
       "location": "송장 접수", "occurred_at": "2026-11-04T10:00:00+09:00"}
    ]
  }
}"""
    party = """{
  "order_ref": "ORD-20261104-0001",
  "receiver": {"name": "김수령", "phone": "010-1234-5678", "zipcode": "06236",
               "address": "서울시 강남구 테헤란로 1", "address_detail": "101호"},
  "callback_url": "https://wms.example.com/api/carrier/webhook/"
}"""
    pickup = party.replace('"order_ref"', '"return_ref"').replace('ORD-', 'RTN-').replace('"receiver"', '"sender"')
    verify = """import hashlib, hmac

def verify(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)"""
    webhook = """POST {callback_url}
Content-Type: application/json
X-Carrier-Signature: 3b5d...(HMAC-SHA256 16진수)

{"event_id": "a71e...", "waybill_no": "581234567890", "kind": "delivery",
 "status": "집하", "location": "출고지 집하", "occurred_at": "2026-11-04T10:01:00+09:00"}"""
    errors = ''.join(
        f'<tr><td>{c}</td><td class="mono">{escape(k)}</td><td>{escape(m)}</td></tr>'
        for c, k, m in [
            (400, 'INVALID_PARAMETER / INVALID_PHONE / INVALID_ZIPCODE', '필수값 누락 또는 형식 오류'),
            (401, 'UNAUTHORIZED', 'API 키가 없거나 다름'),
            (404, 'WAYBILL_NOT_FOUND', '없는 운송장 번호'),
            (409, 'ALREADY_COLLECTED / INVALID_STATE', '이미 집하되어 취소 불가, 진행할 수 없는 단계'),
            (422, 'ADDRESS_NOT_FOUND', '주소 검증 실패 (시연: 주소에 "없는주소" 포함)'),
            (503, 'SYSTEM_BUSY', '일시 장애. 잠시 후 다시 시도'),
        ]
    )
    lead = f'<p class="lead">쇼핑몰·WMS가 데모택배와 연동하는 방법입니다. 기본 주소 <code>{escape(base_url)}</code></p>'
    toc = ''.join(
        f'<a href="#{key}">{label}</a>'
        for key, label in [('common', '공통'), ('delivery', '배송'), ('pickup', '반품 회수'), ('webhook', '상태 알림'), ('demo', '시연용')]
    )
    body = f"""<div class="toc">{toc}</div>
<div class="card" id="common"><h2>공통</h2>
<ul><li>모든 API 요청에 <code>X-API-Key</code> 헤더를 붙입니다.</li>
<li>본문과 응답은 JSON(UTF-8)입니다. 성공하면 <code>{{"result":"OK","data":...}}</code>, 실패하면 <code>{{"result":"ERROR","code":...,"message":...}}</code>를 돌려줍니다.</li>
<li>전화번호는 <code>010-1234-5678</code> 형식, 우편번호는 숫자 5자리입니다.</li></ul>
<div class="table-wrap"><table><tr><th>HTTP</th><th>code</th><th>뜻</th></tr>{errors}</table></div></div>
<div class="card" id="delivery"><h2>배송</h2>
{ep('POST', '/v1/shipments', '운송장을 발급합니다. 발급 즉시 <b>접수</b> 상태입니다.', party, shipment)}
{ep('POST', '/v1/shipments/{waybill_no}/ready', '출고를 확정하고 집하를 요청합니다. 이후 기사가 방문해 <b>집하</b>합니다.')}
{ep('POST', '/v1/shipments/{waybill_no}/cancel', '집하 전(접수 상태)에만 취소할 수 있습니다.')}
{ep('GET', '/v1/shipments/{waybill_no}', '현재 상태와 전체 이력을 조회합니다. 반품 회수 운송장도 같은 주소로 조회합니다.')}</div>
<div class="card" id="pickup"><h2>반품 회수</h2>
{ep('POST', '/v1/pickups', '고객 주소로 회수 기사를 보냅니다. 발급 즉시 <b>회수접수</b> 상태입니다.', pickup)}
{ep('POST', '/v1/pickups/{waybill_no}/cancel', '기사가 수거하기 전(회수접수 상태)에만 취소할 수 있습니다.')}</div>
<div class="card" id="webhook"><h2>상태 알림 (웹훅)</h2><p>단계가 바뀔 때마다 등록한 <code>callback_url</code>로 알립니다. 2xx 이외의 응답이면 3초, 10초 뒤 다시 보냅니다.
같은 알림이 여러 번 갈 수 있으니 <code>event_id</code>로 중복을 거르고, 순서가 바뀔 수 있으니 <code>occurred_at</code>으로 최신 단계를 판단하세요.</p>
<pre><code>{escape(webhook)}</code></pre>
<p>본문 전체를 공유 비밀값으로 HMAC-SHA256 서명해 <code>X-Carrier-Signature</code>에 담습니다. 받는 쪽 확인 예시:</p>
<pre><code>{escape(verify)}</code></pre></div>
<div class="card" id="demo"><h2>시연용</h2>{ep('POST', '/v1/simulate/{waybill_no}/advance', '다음 단계로 즉시 진행합니다. 실제 택배사에는 없는 기능입니다.')}</div>"""
    return layout('API 문서', body, 'docs', lead=lead, crumb='기업고객')
