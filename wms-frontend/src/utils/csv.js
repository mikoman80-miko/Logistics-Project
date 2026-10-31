// 엑셀이 수식으로 실행할 수 있는 값은 글자로 처리되도록 앞에 작은따옴표를 붙입니다.
const toCell = (value) => {
  let text = value === null || value === undefined ? '' : String(value)
  if (typeof value === 'string' && /^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export const downloadCsv = (filename, headers, rows) => {
  const body = [headers, ...rows].map((row) => row.map(toCell).join(',')).join('\r\n')
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob(['﻿' + body], { type: 'text/csv;charset=utf-8;' }))
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}
