#!/bin/bash
# 통합 검증: 백엔드(Django) 린트·테스트, 화면(Vue) 린트·빌드. 프로젝트 루트에서 ./verify.sh
# 화면 자동 테스트(Playwright)는 2분쯤 걸려 여기서 빼고 따로 돌립니다: cd wms-frontend && npm run e2e
set -e # 어느 한 단계라도 실패하면 즉시 종료
cd "$(dirname "$0")"

PYTHON=myenv/Scripts/python.exe
[ -x "$PYTHON" ] || PYTHON=myenv/bin/python

echo "=== [1/2] Backend (Django) 검증 시작 ==="
"$PYTHON" -m ruff check .
"$PYTHON" -X utf8 manage.py test inventory --noinput

echo "=== [2/2] Frontend (Vue) 검증 시작 ==="
cd wms-frontend
npx eslint src e2e --max-warnings=0
npm run build
cd ..

echo "✅ 모든 검증(Lint / Test / Build) 통과 완료!"
