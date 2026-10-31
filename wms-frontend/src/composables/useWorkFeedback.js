import { ref } from 'vue'
import { playBeep } from '../utils/beep'

// 현장 화면 공용 결과 표시. 정상은 잠깐 보이고, 오류는 확인할 때까지 화면을 막습니다.
const feedback = ref(null)
let timer = null

export const useWorkFeedback = () => {
  const ok = (message) => {
    clearTimeout(timer)
    playBeep('success')
    feedback.value = { type: 'ok', message }
    timer = setTimeout(() => { feedback.value = null }, 1200)
  }

  const fail = (message) => {
    clearTimeout(timer)
    playBeep('error')
    feedback.value = { type: 'error', message }
  }

  const dismiss = () => { feedback.value = null }

  return { feedback, ok, fail, dismiss }
}
