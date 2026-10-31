// 서버 오류 응답에서 사용자에게 보여줄 문구를 꺼냅니다.
export const apiErrorMessage = (err, fallback = '처리 중 오류가 발생했습니다.') => {
  const data = err.response?.data
  if (!data || typeof data !== 'object') return fallback
  if (data.error) return data.error
  if (data.detail) return data.detail
  const first = Object.values(data).flat(Infinity)[0]
  if (typeof first === 'string') return first
  if (first && typeof first === 'object') return Object.values(first).flat(Infinity)[0] || fallback
  return fallback
}
