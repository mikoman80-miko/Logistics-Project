"""화면 자동 테스트용 DB를 처음 상태로 만듭니다. (playwright.config.js가 Django를 띄우기 전에 실행)

운영 DB를 지우는 사고를 막기 위해 DB 이름에 e2e가 들어 있어야만 동작합니다.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / '.env')
db_name = os.environ.get('DB_NAME', '')
if 'e2e' not in db_name:
    sys.exit(f'테스트 DB 이름에 e2e가 없어 중단합니다: {db_name!r}')

import MySQLdb  # noqa: E402

conn = MySQLdb.connect(host=os.environ.get('DB_HOST', 'localhost'), port=int(os.environ.get('DB_PORT', '3306')),
                       user=os.environ['DB_USER'], passwd=os.environ['DB_PASSWORD'])
conn.cursor().execute(f'CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
conn.close()

import django  # noqa: E402

django.setup()
from django.contrib.auth.models import User  # noqa: E402
from django.core.management import call_command  # noqa: E402

from inventory.models import Item, Supplier, WarehouseLocation  # noqa: E402

call_command('migrate', verbosity=0)
call_command('flush', interactive=False, verbosity=0)

User.objects.create_user('e2e_admin', password='E2e-admin-pass!', is_staff=True, first_name='테스트관리자')
User.objects.create_user('e2e_worker', password='E2e-worker-pass!', first_name='테스트작업자')
shelf = WarehouseLocation.objects.create(zone='A', rack='R01', tier=1, description='테스트 선반')
WarehouseLocation.objects.create(zone='B', rack='R02', tier=2)
Supplier.objects.create(name='테스트공급사', contact_person='공급담당')
Item.objects.create(sku='E2E-CABLE', name='테스트 케이블', item_type='부자재', serial_tracked=False, quantity=50, location=shelf)
Item.objects.create(sku='E2E-DEV', name='테스트 단말기', item_type='상품', serial_tracked=True, quantity=0, location=shelf)
print(f'테스트 DB 준비 완료: {db_name}')
