// 개발 서버 세 개를 pm2로 한 번에 실행합니다. 사용법은 README의 "실행"을 참고하세요.
const path = require('path')

const root = __dirname
// 파이썬은 scripts/run-python.js를 거쳐 창 없이 실행합니다. (Windows에서 빈 콘솔 창이 뜨는 문제)
const runPython = path.join('scripts', 'run-python.js')
// 파이썬 출력이 바로 로그에 남고, 한글이 깨지지 않게 합니다. 캐시(.pyc)를 쓰지 않아 감시 중 재시작이 반복되지 않습니다.
const pythonEnv = { PYTHONUNBUFFERED: '1', PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' }

module.exports = {
  apps: [
    {
      name: 'django',
      cwd: root,
      script: runPython,
      args: 'manage.py runserver 127.0.0.1:8000 --noreload',
      env: pythonEnv,
      // Django 자체 자동 재시작 대신 pm2가 파이썬 파일 변경을 보고 재시작합니다.
      watch: ['config', 'inventory'],
      watch_options: { usePolling: false },
      ignore_watch: ['**/__pycache__/**', '**/migrations/**', '**/tests*.py'],
      autorestart: true,
    },
    {
      name: 'carrier',
      cwd: root,
      script: runPython,
      args: path.join('mock_carrier', 'server.py'),
      env: pythonEnv,
      // 서버가 쓰는 DB와 캐시 파일 때문에 재시작되지 않도록 소스 파일만 지켜봅니다.
      watch: [path.join('mock_carrier', 'server.py'), path.join('mock_carrier', 'carrier_pages.py')],
      autorestart: true,
    },
    {
      name: 'frontend',
      cwd: path.join(root, 'wms-frontend'),
      // npm.cmd 대신 vite를 직접 실행해야 Windows에서 pm2가 프로세스를 제대로 끕니다.
      script: path.join('node_modules', 'vite', 'bin', 'vite.js'),
      autorestart: true,
    },
  ],
}
