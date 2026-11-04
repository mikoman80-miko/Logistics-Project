import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = BASE_DIR / "db_backups"
DEFAULT_DUMP_PATH = r"C:\Program Files\MariaDB 13.0\bin\mariadb-dump.exe"

load_dotenv(BASE_DIR / ".env")


def backup_mariadb():
    BACKUP_DIR.mkdir(exist_ok=True)

    db_name = os.environ.get("DB_NAME", "wms_db")
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{db_name}_{current_time}.sql"
    dump_path = shutil.which("mariadb-dump") or os.environ.get("MARIADB_DUMP_PATH", DEFAULT_DUMP_PATH)

    # 비밀번호는 명령줄에 남지 않도록 환경 변수로 전달합니다.
    env = {**os.environ, "MYSQL_PWD": os.environ["DB_PASSWORD"]}
    command = [
        dump_path,
        "-h", os.environ.get("DB_HOST", "localhost"),
        "-P", os.environ.get("DB_PORT", "3306"),
        "-u", os.environ["DB_USER"],
        "--single-transaction",
        "--no-tablespaces",
        f"--result-file={backup_path}",
        db_name,
    ]

    print(f"[{current_time}] 데이터베이스 백업을 시작합니다...")
    try:
        subprocess.run(command, env=env, check=True)
        if backup_path.stat().st_size == 0:
            raise RuntimeError("백업 파일이 비어 있습니다.")
    except (OSError, subprocess.CalledProcessError, RuntimeError) as e:
        # 실패한 빈 파일이 정상 백업처럼 남지 않게 지웁니다.
        backup_path.unlink(missing_ok=True)
        print(f"[실패] 백업 실패! .env의 DB 설정과 MariaDB 설치 경로를 확인해주세요.\n에러 내용: {e}")
        return False

    print(f"[완료] 백업 성공! 파일이 저장되었습니다: {backup_path}")
    return True


if __name__ == "__main__":
    sys.exit(0 if backup_mariadb() else 1)
