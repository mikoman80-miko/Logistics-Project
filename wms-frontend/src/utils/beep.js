// 스캔이 반복되어도 브라우저 오디오 자원이 쌓이지 않도록 하나만 만들어 재사용합니다.
let ctx = null

export const playBeep = (type) => {
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)()
  if (ctx.state === 'suspended') ctx.resume()

  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.connect(gain)
  gain.connect(ctx.destination)
  gain.gain.setValueAtTime(0.1, ctx.currentTime)

  const success = type === 'success'
  osc.type = success ? 'sine' : 'square'
  osc.frequency.setValueAtTime(success ? 1000 : 200, ctx.currentTime)
  osc.start()
  osc.stop(ctx.currentTime + (success ? 0.1 : 0.4))
}
