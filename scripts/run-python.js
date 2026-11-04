// pm2에서 파이썬 서버를 창 없이 실행합니다.
// Windows에서 pm2가 가상환경 python.exe를 직접 실행하면 빈 콘솔 창이 뜨고, 그 창을 닫으면 서버가 꺼집니다.
// 사용: node scripts/run-python.js <스크립트> [인자...]   (ecosystem.config.js에서 호출)
const { spawn } = require('child_process')
const path = require('path')

const python = path.join(__dirname, '..', 'myenv', 'Scripts', 'python.exe')
const child = spawn(python, process.argv.slice(2), { stdio: 'inherit', windowsHide: true })

// pm2가 멈추거나 재시작할 때 파이썬도 함께 끕니다.
const stop = () => { if (!child.killed) child.kill() }
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
process.on('exit', stop)

child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
child.on('error', (err) => {
  console.error(`파이썬을 실행하지 못했습니다: ${python}\n${err.message}`)
  process.exit(1)
})
