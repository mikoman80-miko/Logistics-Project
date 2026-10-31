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

- **관리자:** `is_staff`가 켜진 계정입니다. 기준정보, 주문·발주·반품 등록, 통계를 사용할 수 있습니다.
- **현장작업자:** 일반 계정입니다. 피킹·출고, 입고, 반품 회수를 처리합니다.
- 계정은 http://127.0.0.1:8000/admin/ 에서 만듭니다.

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
