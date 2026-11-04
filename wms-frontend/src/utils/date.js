// 브라우저(한국 시간) 기준 날짜 문자열 YYYY-MM-DD. toISOString()은 UTC라 새벽 9시 전에는 전날이 됩니다.
export const localDate = (date = new Date()) => {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export const daysAgo = (days) => {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return localDate(date)
}
