// 엑셀(xlsx) 내려받기와 올린 파일 읽기. 다운로드는 모두 xlsx로 통일하고, 올릴 때는 xlsx·xls·csv를 모두 받습니다.
// 엑셀 라이브러리는 크기가 커서(약 400KB) 처음 내려받거나 올릴 때 불러옵니다. (첫 화면을 가볍게)
const loadXlsx = () => import('xlsx')

export const EXCEL_ACCEPT = '.xlsx,.xls,.csv'

const makeSheet = (XLSX, headers, rows) => {
  const sheet = XLSX.utils.aoa_to_sheet([headers, ...rows])
  sheet['!cols'] = headers.map((header, i) => {
    const longest = Math.max(String(header).length, ...rows.slice(0, 200).map(row => String(row[i] ?? '').length))
    return { wch: Math.min(Math.max(longest + 2, 8), 50) }
  })
  return sheet
}

// 시트 여러 장을 한 파일로 내려받습니다. sheets: [{ name, headers, rows }]
export const downloadXlsxBook = async (filename, sheets) => {
  const XLSX = await loadXlsx()
  const book = XLSX.utils.book_new()
  for (const { name, headers, rows } of sheets) XLSX.utils.book_append_sheet(book, makeSheet(XLSX, headers, rows), name.slice(0, 31))
  XLSX.writeFile(book, filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`)
}

// rows는 headers 순서의 값 배열입니다. 문자열은 수식으로 해석되지 않고 글자 그대로 저장됩니다.
export const downloadXlsx = (filename, sheetName, headers, rows) => downloadXlsxBook(filename, [{ name: sheetName, headers, rows }])

const readBook = async (XLSX, file) => {
  const data = await file.arrayBuffer()
  // csv는 한글 엑셀이 저장한 CP949일 수 있어 UTF-8로 읽히지 않으면 CP949로 다시 읽습니다.
  if (file.name.toLowerCase().endsWith('.csv')) {
    let text = new TextDecoder('utf-8').decode(data)
    if (text.includes('�')) text = new TextDecoder('euc-kr').decode(data)
    return XLSX.read(text.replace(/^\uFEFF/, ''), { type: 'string', raw: true })
  }
  return XLSX.read(data, { type: 'array' })
}

// 첫 시트의 첫 줄을 제목으로 보고 [{제목: 값}] 목록을 돌려줍니다. 빈 줄은 건너뜁니다.
export const readSheetObjects = async (file) => {
  const XLSX = await loadXlsx()
  const book = await readBook(XLSX, file)
  const sheet = book.Sheets[book.SheetNames[0]]
  return XLSX.utils.sheet_to_json(sheet, { defval: '', raw: false })
    .filter(row => Object.values(row).some(value => String(value).trim()))
}

// 서버가 csv만 받는 업로드용: 어떤 형식이든 UTF-8 csv 파일로 바꿉니다.
export const toCsvFile = async (file) => {
  const XLSX = await loadXlsx()
  const book = await readBook(XLSX, file)
  const csv = XLSX.utils.sheet_to_csv(book.Sheets[book.SheetNames[0]], { blankrows: false })
  return new File(['﻿' + csv], file.name.replace(/\.\w+$/, '') + '.csv', { type: 'text/csv' })
}
