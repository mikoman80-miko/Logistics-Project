import { ref } from 'vue'
import { defineStore } from 'pinia'

// 브라우저 기본 창(alert, confirm, prompt) 대신 쓰는 시스템 팝업입니다.
//   const dialog = useDialogStore()
//   if (!(await dialog.confirm('삭제하시겠습니까?', { danger: true }))) return
//   const name = await dialog.prompt('이름을 입력하세요.')            // 취소하면 null
//   const id = await dialog.select('위치를 고르세요.', { options })   // [{ value, label }]
// 옵션: title, okText, cancelText, danger(빨간 확인 버튼), large(현장 화면용 큰 글씨),
//       focusCancel(Enter가 취소로 가도록. 바코드 스캐너의 Enter로 잘못 확정되는 것을 막습니다)
export const useDialogStore = defineStore('dialog', () => {
  const current = ref(null)
  let resolver = null

  const open = (kind, message, options = {}) => {
    if (resolver) resolver(kind === 'alert' ? undefined : null)  // 이전 창이 남아 있으면 취소로 닫습니다.
    current.value = { kind, message, ...options }
    return new Promise((resolve) => { resolver = resolve })
  }

  const close = (result) => {
    const resolve = resolver
    resolver = null
    current.value = null
    resolve?.(result)
  }

  return {
    current,
    close,
    alert: (message, options) => open('alert', message, options),
    confirm: (message, options) => open('confirm', message, options),
    prompt: (message, options) => open('prompt', message, options),
    select: (message, options) => open('select', message, options),
  }
})
