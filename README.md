# WMS 물류관리시스템

Django(백엔드)와 Vue(프런트엔드)로 만든 창고 관리 시스템입니다.

## 처음 설치

필요한 프로그램: Python 3.14, Node.js 24, MariaDB

```powershell
# 백엔드 (프로젝트 루트)
python -m venv myenv
myenv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env    # 값을 채웁니다
myenv\Scripts\python manage.py migrate
myenv\Scripts\python manage.py createsuperuser

# 프런트엔드
cd wms-frontend
npm ci
```

`.env`의 `DJANGO_SECRET_KEY`는 아래 명령으로 만듭니다.

```powershell
myenv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 실행

```powershell
# 터미널 1 (프로젝트 루트)
myenv\Scripts\python manage.py runserver

# 터미널 2 (wms-frontend)
npm run dev
```

브라우저에서 http://localhost:5173 으로 접속합니다.

## 권한

- **관리자:** `is_staff`가 켜진 계정입니다. 로그인하면 "오늘 할 일" 화면이 열리고, 주문·발주·반품 등록과 기본 설정, 보고서를 사용합니다.
- **현장작업자:** 일반 계정입니다. 로그인하면 현장 작업 화면(`/work`)만 열리고, 스캔으로 입고·출고·반품 회수를 처리합니다.
- 계정은 http://127.0.0.1:8000/admin/ 에서 만듭니다.

## 시리얼 관리

- 상품마다 구분(상품, 구성품, 부자재, 사은품)과 시리얼 관리 여부를 정합니다. 기본값은 상품만 시리얼 관리입니다.
- 설정은 기본 설정 → 상품에서 언제든 바꿀 수 있습니다. 단, 진행 중인 주문이나 발주서에 포함된 상품은 끝난 뒤에 바꿉니다.
- 시리얼 관리 상품은 입출고할 때 시리얼을 1개씩 스캔합니다. 관리하지 않는 상품은 상품코드를 스캔하거나 수량을 입력합니다.
- 시리얼 없이 들어와 있던 재고는 그 수량 안에서, 상품코드를 스캔한 뒤 시리얼을 스캔하면 출고 때 등록됩니다.
- 바코드 스캐너는 키보드처럼 입력하므로 영문 입력 상태여야 합니다. 한글 상태로 스캔하면 화면이 안내합니다.

## 테스트와 백업

```powershell
myenv\Scripts\python manage.py test inventory
myenv\Scripts\python backup_db.py    # db_backups 폴더에 저장
```

테스트에는 `test_wms_db` 데이터베이스를 쓰며, 운영 데이터는 건드리지 않습니다.

## 배포 전 확인

- `.env`에서 `DJANGO_DEBUG=False`, `DJANGO_HTTPS=True`, `DJANGO_ALLOWED_HOSTS`를 실제 값으로 설정합니다.
- 기본 비밀번호를 쓰는 계정이 없는지 확인합니다.
- `.env`와 `db_backups`는 저장소에 올리지 않습니다.
