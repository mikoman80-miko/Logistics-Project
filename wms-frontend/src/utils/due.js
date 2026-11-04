// 출고 마감 표시와 정렬. 서버가 주문마다 due_at(마감 일시)과 due_status(overdue/today/later)를 내려줍니다.
import { onMounted, onUnmounted, ref } from 'vue'

// 긴급 → 마감 빠른 순 → 먼저 들어온 순
export const sortByDue = (orders) => [...orders].sort((a, b) =>
  (b.is_urgent - a.is_urgent) || (a.due_at || '').localeCompare(b.due_at || '') || a.created_at.localeCompare(b.created_at))

const pad = (n) => String(n).padStart(2, '0')

// 화면에 보일 마감 글자와 색. now는 1분마다 바뀌는 시각(useNow)을 넘깁니다.
export const dueLabel = (order, now = new Date()) => {
  if (order.status !== '출고대기' || !order.due_at) return null
  const due = new Date(order.due_at)
  const minutes = Math.round((due - now) / 60000)
  const hhmm = `${pad(due.getHours())}:${pad(due.getMinutes())}`
  if (minutes <= 0) {
    const days = Math.floor((now - due) / 86400000)
    return { text: days >= 1 ? `마감 ${days}일 지남` : `마감 지남 (${hhmm})`, tone: 'danger' }
  }
  const sameDay = due.toDateString() === now.toDateString()
  if (sameDay) {
    const left = minutes >= 60 ? `${Math.floor(minutes / 60)}시간 ${minutes % 60}분` : `${minutes}분`
    return { text: `오늘 ${hhmm} 마감 · ${left} 남음`, tone: minutes <= 60 ? 'danger' : 'warning' }
  }
  return { text: `${due.getMonth() + 1}/${due.getDate()} ${hhmm} 마감`, tone: 'muted' }
}

export const toneClass = { danger: 'text-danger', warning: 'text-warning', muted: 'text-muted' }

// 남은 시간 표시가 흐르도록 1분마다 바뀌는 현재 시각
export const useNow = () => {
  const now = ref(new Date())
  let timer
  onMounted(() => { timer = setInterval(() => { now.value = new Date() }, 60000) })
  onUnmounted(() => clearInterval(timer))
  return now
}
