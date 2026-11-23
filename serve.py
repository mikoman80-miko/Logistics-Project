"""운영 모드 실행: waitress(운영용 WSGI 서버)로 API와 빌드한 화면을 한 주소에서 제공합니다.

    myenv\\Scripts\\python serve.py            # 기본 0.0.0.0:8080

먼저 `npm run prod:build`로 화면을 빌드하고 정적 파일을 모아 두어야 합니다. 보통은 `npm run prod:start`로 pm2에서 실행합니다.
환경 변수: WMS_HOST(기본 0.0.0.0), WMS_PORT(기본 8080), WMS_THREADS(동시 처리 수, 기본 8),
WMS_TRUSTED_PROXY(HTTPS 프록시의 IP. 프록시 뒤에서만 지정하고, 그때 .env에 DJANGO_HTTPS=True를 켭니다)
"""

import os
import socket
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# 운영 모드는 .env의 값과 관계없이 디버그를 끕니다. (오류 화면에 내부 정보가 보이지 않게)
os.environ['DJANGO_DEBUG'] = '0'
os.environ.setdefault('WMS_LOG_NAME', 'prod')  # 운영 로그는 logs/prod.log, logs/prod-error.log
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def own_addresses():
    """이 PC의 이름과 IP. 현장 PC가 http://<이 PC의 IP>:8080 으로 접속할 수 있게 허용 목록에 넣습니다."""
    names = {'localhost', '127.0.0.1', socket.gethostname()}
    try:
        names.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return names


def main():
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / '.env')
    hosts = {h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()} | own_addresses()
    os.environ['DJANGO_ALLOWED_HOSTS'] = ','.join(sorted(hosts))

    from django.conf import settings
    from django.core.wsgi import get_wsgi_application
    from waitress import serve

    application = get_wsgi_application()
    problems = []
    if not (settings.FRONTEND_DIST / 'index.html').exists():
        problems.append('화면 빌드가 없습니다. npm run prod:build 를 먼저 실행하세요.')
    if not Path(settings.STATIC_ROOT).exists():
        problems.append('정적 파일이 없습니다. npm run prod:build 를 먼저 실행하세요.')
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        sys.exit(1)

    host = os.environ.get('WMS_HOST', '0.0.0.0')
    port = int(os.environ.get('WMS_PORT', '8080'))
    threads = int(os.environ.get('WMS_THREADS', '8'))
    lan = sorted(h for h in hosts if h[0].isdigit() and h != '127.0.0.1')
    print(f'WMS 운영 서버 시작: http://127.0.0.1:{port}' + ''.join(f' / http://{ip}:{port}' for ip in lan), flush=True)
    # 요청 본문은 10MB까지만 받습니다. (기본 1GB) 엑셀로 올리는 배송지 목록도 이 안에 들어옵니다.
    options = {}
    proxy = os.environ.get('WMS_TRUSTED_PROXY', '').strip()
    if proxy:
        # HTTPS를 처리하는 프록시(nginx 등) 뒤에서 쓸 때: 이 주소에서 온 요청만 접속자 주소·https 여부 헤더를 믿습니다.
        options = {'trusted_proxy': proxy, 'trusted_proxy_headers': {'x-forwarded-for', 'x-forwarded-proto'}, 'clear_untrusted_proxy_headers': True}
    serve(application, host=host, port=port, threads=threads, ident='WMS', max_request_body_size=10 * 1024 * 1024, **options)


if __name__ == '__main__':
    main()
