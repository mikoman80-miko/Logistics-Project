"""운영 모드에서 빌드한 화면(wms-frontend/dist)을 제공합니다.

/assets/... 같은 파일은 WhiteNoise가 바로 내려주고(settings.WHITENOISE_ROOT),
/orders, /work/outbound 처럼 화면 안에서 쓰는 주소는 모두 index.html을 돌려줘 Vue 라우터가 처리합니다.
"""
from django.conf import settings
from django.http import FileResponse, Http404


def index(request, path=''):
    index_file = settings.FRONTEND_DIST / 'index.html'
    if not index_file.exists():
        raise Http404('화면 빌드가 없습니다. 개발 중에는 http://localhost:5173 을 쓰세요.')
    response = FileResponse(open(index_file, 'rb'), content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-cache'  # 새로 빌드하면 바로 반영되도록 index.html은 매번 확인합니다.
    return response
