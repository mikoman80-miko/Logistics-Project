# Project Architecture Map

창고 관리 시스템(WMS). 백엔드는 Django REST API(저장소 루트), 화면은 Vue 3(`wms-frontend/`), DB는 MariaDB입니다.

## 디렉토리 구조

- `config/`: Django 전역 설정
  - `settings.py`: 설정 (값은 루트의 `.env`에서 읽음, 예시는 `.env.example`)
  - `urls.py`: 주소 연결 (`api/…` + 운영 모드의 화면 주소)
  - `spa.py`: 운영 모드에서 빌드한 화면(index.html) 제공
- `inventory/`: 업무 앱 (하나의 앱에 모든 업무가 들어 있음)
  - `models.py`: 상품·위치·위치별 재고·발주·주문·반품·시리얼·이력·알림 등 모델
  - `views.py`: API 대부분 (뷰셋, 보고서 API, 택배 웹훅)
  - `serializers.py`: API 입출력 형식
  - `api_routes.py`: `api/inventory/` 아래 주소 목록
  - `stock.py`: 위치별 재고 증감 (재고 수량을 바꾸는 곳은 모두 이 함수를 거침)
  - `carrier.py`: 택배사 API 호출 / `due.py`: 출고 마감 계산 / `audit.py`: 기준정보 변경 이력 / `monitor.py`: 오류 감시·알림
  - `management/commands/notify_overdue.py`: 입고 지연 알림 (작업 스케줄러용)
  - `management/commands/seed_demo.py`: 시연·테스트용 데이터 생성 (실제 API로 발주→입고→주문→출고→반품 처리)
  - `migrations/`: DB 구조 변경 (0028: 사원증 코드를 해시로 저장)
  - `tests.py`, `tests_carrier.py`: 단위 테스트
- `mock_carrier/`: 개발·시연용 가상 택배사 서버 (`server.py`, 화면 `carrier_pages.py`)
- `wms-frontend/`: Vue 3 + Pinia + vue-router + Tailwind v4 (Vite)
  - `src/views/`: 관리 화면 (`inbound/`, `outbound/`, `inventory/`, `master/`)과 현장 화면 (`work/`)
  - `src/components/`: 공통 컴포넌트 (`work/`는 현장 화면용 큰 글씨 대화상자)
  - `src/stores/`: Pinia 스토어 (로그인, 재고, 탭, 대화상자, 토스트)
  - `src/composables/`, `src/utils/`: 공통 로직 (엑셀, 바코드, 날짜, 집품 리스트, 현장 도움말 등)
  - `src/router/index.js`: 화면 주소 (관리 화면은 관리자만, `/work/…`는 현장 화면)
  - `e2e/`: Playwright 화면 자동 테스트 (`flows.spec.js`, 테스트 DB 준비 `setup_db.py`)
- 루트 스크립트: `serve.py`(운영 서버), `backup_db.py`(DB 백업), `restore_check.py`(복원 리허설), `scripts/run-python.js`(pm2용 실행 도우미)
- 품질 설정: `ruff.toml`(파이썬 린트), `wms-frontend/eslint.config.js`(화면 린트), `.pre-commit-config.yaml`(커밋 시 검사), `.gitattributes`(줄바꿈 LF 통일)
- pm2 설정: `ecosystem.config.js`(개발 서버 3개), `ecosystem.prod.config.js`(운영 서버)

## 주요 실행 및 검증 명령어

- 통합 검증: `./verify.sh` (ruff, 단위 테스트, ESLint, 화면 빌드)
- 화면 자동 테스트: `cd wms-frontend && npm run e2e` (운영 모드로: `npm run e2e:prod`)
- 개발 서버 실행 (Django 8000, 화면 5173, 가상 택배사 8100): `npm run start` (루트, pm2)
- 운영 서버 실행 (8080): `npm run prod:start`
- 파이썬은 가상환경 `myenv\Scripts\python`을 씁니다.
- 자세한 사용법은 `README.md`를 참고합니다.
