// 화면 자동 테스트. 운영 서버(8000, 5173, 8100)와 겹치지 않는 포트에 테스트 전용 서버를 띄웁니다.
//   npm run e2e            (wms-frontend 폴더)
// 매번 테스트 DB(test_wms_e2e)를 비우고 시작하며, 브라우저는 PC에 설치된 Edge를 씁니다.
//   npm run e2e:prod       빌드한 화면을 운영 서버(serve.py, waitress)로 띄워 같은 테스트를 돌립니다.
import { defineConfig } from '@playwright/test'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'myenv', 'Scripts', 'python.exe')
const PORTS = { django: 8020, carrier: 8120, web: 5190 }
const PROD = process.env.npm_lifecycle_event === 'e2e:prod'

const backendEnv = {
  DB_NAME: 'test_wms_e2e',  // MariaDB는 test_로 시작하는 DB를 앱 계정이 만들 수 있게 허용합니다.
  CARRIER_API_URL: `http://127.0.0.1:${PORTS.carrier}`,
  CARRIER_API_KEY: 'e2e-carrier-key',
  CARRIER_WEBHOOK_SECRET: 'e2e-webhook-secret',
  CARRIER_CALLBACK_URL: `http://127.0.0.1:${PORTS.django}/api/carrier/webhook/`,
  MOCK_CARRIER_DB: path.join(root, 'mock_carrier', 'carrier_e2e.sqlite3'),
  MOCK_CARRIER_STEP_SECONDS: '3600',  // 테스트 중에는 자동으로 진행하지 않습니다.
  PYTHONUTF8: '1',
}

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/results',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: PROD ? `http://localhost:${PORTS.django}` : `http://localhost:${PORTS.web}`,
    channel: 'msedge',
    viewport: { width: 1600, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
  },
  webServer: [
    {
      // 테스트 DB를 처음 상태로 만든 뒤 Django를 띄웁니다.
      command: `"${python}" e2e/setup_db.py && ` + (PROD ? `"${python}" ../serve.py` : `"${python}" ../manage.py runserver 127.0.0.1:${PORTS.django} --noreload`),
      url: `http://127.0.0.1:${PORTS.django}/api/inventory/today/`,
      env: PROD ? { ...backendEnv, WMS_HOST: '127.0.0.1', WMS_PORT: String(PORTS.django) } : backendEnv,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: 'ignore',
    },
    {
      command: `node -e "require('fs').rmSync(process.env.MOCK_CARRIER_DB,{force:true})" && "${python}" ../mock_carrier/server.py --port ${PORTS.carrier}`,
      url: `http://127.0.0.1:${PORTS.carrier}/`,
      env: backendEnv,
      reuseExistingServer: false,
    },
    ...(PROD ? [] : [{
      command: `node node_modules/vite/bin/vite.js --port ${PORTS.web} --strictPort`,
      url: `http://localhost:${PORTS.web}/`,
      env: { API_PROXY_TARGET: `http://127.0.0.1:${PORTS.django}` },
      reuseExistingServer: false,
    }]),
  ],
})
