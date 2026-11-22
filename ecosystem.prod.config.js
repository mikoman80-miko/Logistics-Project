// 운영 모드: 빌드한 화면과 API를 waitress 한 프로세스로 제공합니다. (http://<이 PC의 IP>:8080)
// 사용법은 README의 "운영 모드로 실행"을 참고하세요. 개발 서버(ecosystem.config.js)와 동시에 띄워도 포트가 겹치지 않습니다.
const path = require('path')

const root = __dirname
const runPython = path.join('scripts', 'run-python.js')
// 운영 서버 포트. 바꾸려면 여기 한 곳만 고칩니다. (택배사 알림 주소도 이 포트를 씁니다)
const PORT = process.env.WMS_PORT || '8080'

module.exports = {
  apps: [
    {
      name: 'wms',
      cwd: root,
      script: runPython,
      args: 'serve.py',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONUTF8: '1',
        WMS_PORT: PORT,
        // 택배사가 배송 상태를 알려줄 주소도 운영 서버로 바꿉니다.
        CARRIER_CALLBACK_URL: `http://127.0.0.1:${PORT}/api/carrier/webhook/`,
      },
      // 운영 중에는 파일 변경으로 재시작하지 않습니다. 업데이트 후 npm run prod:restart
      watch: false,
      autorestart: true,
      // 시작하자마자 계속 죽으면(설정 오류 등) 무한 재시작하지 않고 멈춥니다.
      min_uptime: '10s',
      max_restarts: 10,
      restart_delay: 3000,
      time: true,
      // 메모리가 이만큼 넘게 늘어나면(누수 등) 자동으로 다시 시작합니다.
      max_memory_restart: '700M',
    },
  ],
}
