"""백업 복원 리허설: 백업 파일을 별도 테스트 DB에 실제로 복원해 쓸 수 있는 백업인지 확인합니다.

    myenv\\Scripts\\python restore_check.py                 # 가장 최근 백업
    myenv\\Scripts\\python restore_check.py 파일.sql        # 특정 백업
    myenv\\Scripts\\python restore_check.py --keep          # 확인 후 복원 DB를 지우지 않고 남김

운영 DB(wms_db)는 읽기만 하고 바꾸지 않습니다. 복원 대상은 test_wms_restore입니다.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import MySQLdb
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = BASE_DIR / 'db_backups'
RESTORE_DB = 'test_wms_restore'  # MariaDB 기본 설정에서 앱 계정이 만들 수 있는 test_ 이름
DEFAULT_CLIENT_PATH = r'C:\Program Files\MariaDB 13.0\bin\mariadb.exe'
KEY_TABLES = ['inventory_item', 'inventory_itemserial', 'inventory_inventorylog', 'inventory_purchaseorder',
              'inventory_salesorder', 'inventory_returnorder', 'inventory_warehouselocation', 'auth_user']

load_dotenv(BASE_DIR / '.env')


def connect(db=None):
    options = dict(host=os.environ.get('DB_HOST', 'localhost'), port=int(os.environ.get('DB_PORT', '3306')),
                   user=os.environ['DB_USER'], passwd=os.environ['DB_PASSWORD'], charset='utf8mb4')
    return MySQLdb.connect(db=db, **options) if db else MySQLdb.connect(**options)


def counts(db):
    conn = connect(db)
    cur = conn.cursor()
    cur.execute('SHOW TABLES')
    tables = {row[0] for row in cur.fetchall()}
    result = {}
    for table in KEY_TABLES:
        if table in tables:
            cur.execute(f'SELECT COUNT(*) FROM `{table}`')
            result[table] = cur.fetchone()[0]
    cur.execute("SELECT name FROM django_migrations WHERE app='inventory'") if 'django_migrations' in tables else None
    migrations = {row[0] for row in cur.fetchall()} if 'django_migrations' in tables else set()
    conn.close()
    return tables, result, migrations


def main():
    parser = argparse.ArgumentParser(description='백업 복원 리허설')
    parser.add_argument('backup', nargs='?', help='복원해 볼 백업 파일 (생략하면 가장 최근 것)')
    parser.add_argument('--keep', action='store_true', help='확인 후 복원한 DB를 지우지 않습니다')
    args = parser.parse_args()

    backup = Path(args.backup) if args.backup else max(BACKUP_DIR.glob('*.sql'), key=lambda p: p.stat().st_mtime, default=None)
    if not backup or not backup.exists():
        print('[실패] 백업 파일이 없습니다. 먼저 backup_db.py로 백업하세요.')
        return False
    client = shutil.which('mariadb') or os.environ.get('MARIADB_CLIENT_PATH', DEFAULT_CLIENT_PATH)
    print(f'백업 파일: {backup.name} ({backup.stat().st_size:,} bytes)')

    conn = connect()
    conn.cursor().execute(f'DROP DATABASE IF EXISTS `{RESTORE_DB}`')
    conn.cursor().execute(f'CREATE DATABASE `{RESTORE_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    conn.close()

    # 비밀번호는 명령줄에 남지 않도록 환경 변수로 전달합니다.
    env = {**os.environ, 'MYSQL_PWD': os.environ['DB_PASSWORD']}
    command = [client, '-h', os.environ.get('DB_HOST', 'localhost'), '-P', os.environ.get('DB_PORT', '3306'),
               '-u', os.environ['DB_USER'], '--default-character-set=utf8mb4', RESTORE_DB]
    try:
        with backup.open('rb') as dump:
            subprocess.run(command, env=env, stdin=dump, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.decode('utf-8', 'replace').strip() if getattr(exc, 'stderr', None) else exc
        print(f'[실패] 복원하지 못했습니다. MariaDB 클라이언트 경로와 백업 파일을 확인하세요.\n{detail}')
        return False

    ok = True
    expected_tables = len(re.findall(rb'^CREATE TABLE', backup.read_bytes(), re.M))
    restored_tables, restored, restored_migrations = counts(RESTORE_DB)
    _, live, _ = counts(os.environ.get('DB_NAME', 'wms_db'))
    code_migrations = {p.stem for p in (BASE_DIR / 'inventory' / 'migrations').glob('0*.py')}

    print(f'\n테이블: 백업 {expected_tables}개 → 복원 {len(restored_tables)}개', '' if len(restored_tables) == expected_tables else '  ← 다름')
    ok &= len(restored_tables) == expected_tables
    print('\n주요 데이터 건수 (복원 / 현재 운영):')
    for table in KEY_TABLES:
        note = '' if restored.get(table) == live.get(table) else '  (백업 이후 바뀜)'
        print(f'  {table:<32} {restored.get(table, "-"):>8} / {live.get(table, "-"):<8}{note}')
    missing = sorted(code_migrations - restored_migrations)
    if missing:
        print(f'\n백업이 지금 코드보다 예전 구조입니다. 이 백업으로 되돌린 뒤에는 migrate를 실행해야 합니다: {", ".join(missing)}')
    else:
        print('\nDB 구조: 지금 코드와 같습니다.')

    if not args.keep:
        conn = connect()
        conn.cursor().execute(f'DROP DATABASE IF EXISTS `{RESTORE_DB}`')
        conn.close()
    print(f'\n[{"완료" if ok else "확인 필요"}] 복원 리허설 {"성공" if ok else "결과를 확인하세요"}' + ('' if args.keep else ' (복원 DB는 지웠습니다)'))
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
