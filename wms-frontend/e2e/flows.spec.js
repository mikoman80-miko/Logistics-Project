// 관리자와 현장작업자의 실제 업무 흐름을 브라우저로 확인합니다. 앞 단계의 결과를 다음 단계가 쓰므로 순서대로 실행합니다.
import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import * as XLSX from 'xlsx'

XLSX.set_fs(fs)
test.describe.configure({ mode: 'serial' })

const SCREENS = path.join(import.meta.dirname, 'screens')
const ADDRESS = { name: '김수령', phone: '010-1234-5678', zipcode: '06236', address: '서울시 강남구 테헤란로 1', detail: '101호' }
const shared = {}
let admin, worker

const shot = (page, name) => page.screenshot({ path: path.join(SCREENS, `${name}.png`), fullPage: true })
const toast = (page, text) => expect(page.getByText(text).first()).toBeVisible()

async function login(browser, username, password, landing) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/login')
  await page.locator('input[type=text]').fill(username)
  await page.locator('.login-table input[type=password]').fill(password)
  await page.getByRole('button', { name: '시스템 접속' }).click()
  await expect(page).toHaveURL(landing)
  return page
}

// select에서 글자가 포함된 첫 항목을 고릅니다. (상품 목록처럼 뒤에 재고 수가 붙는 경우)
async function selectByText(select, text) {
  const value = await select.locator('option', { hasText: text }).first().getAttribute('value')
  await select.selectOption(value)
}

async function fillAddress(scope, overrides = {}) {
  const a = { ...ADDRESS, ...overrides }
  await scope.getByLabel('받는 분', { exact: true }).fill(a.name)
  await scope.getByLabel('연락처', { exact: true }).fill(a.phone)
  await scope.getByLabel('우편번호', { exact: true }).fill(a.zipcode)
  await scope.getByLabel('주소', { exact: true }).fill(a.address)
  await scope.getByLabel('상세주소', { exact: true }).fill(a.detail)
}

async function createOrder(page, customer, sku, address = {}, expected = '등록 완료 (운송장') {
  await page.goto('/orders')
  await page.getByRole('button', { name: '주문 등록' }).click()
  const modal = page.locator('.modal', { hasText: '출고 주문 등록' })
  await modal.locator('label:has-text("거래처/고객") + input').fill(customer)
  await selectByText(modal.locator('select').first(), sku)
  await fillAddress(modal, address)
  await modal.getByRole('button', { name: '등록', exact: true }).click()
  await toast(page, expected)
}

const orderRow = (page, customer) => page.locator('tbody tr', { hasText: customer })

async function scan(page, code) {
  const box = page.locator('input.work-scan')
  await expect(box).toBeEnabled()
  await box.fill(code)
  await box.press('Enter')
}

async function apiGet(page, url) {
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  const res = await page.request.get(url, { headers: { Authorization: `Bearer ${token}` } })
  expect(res.ok()).toBeTruthy()
  return res.json()
}

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SCREENS, { recursive: true })
  admin = await login(browser, 'e2e_admin', 'E2e-admin-pass!', /\/today$/)
  worker = await login(browser, 'e2e_worker', 'E2e-worker-pass!', /\/work$/)
})

test('로그인 실패 안내', async ({ page }) => {
  await page.goto('/login')
  await page.locator('input[type=text]').fill('e2e_admin')
  await page.locator('.login-table input[type=password]').fill('wrong-password')
  await page.getByRole('button', { name: '시스템 접속' }).click()
  await expect(page.getByText('사원번호 또는 비밀번호를 확인하십시오.')).toBeVisible()
  await shot(page, '01-login-error')
})

test('오늘 할 일과 상품 안전 재고 수정', async () => {
  await expect(admin.getByText('출고 대기').first()).toBeVisible()
  await shot(admin, '02-today')
  await admin.goto('/items')
  await orderRow(admin, 'E2E-CABLE').getByRole('button', { name: '수정' }).click()
  const modal = admin.locator('.modal', { hasText: '상품 수정' })
  await modal.getByLabel('안전 재고').fill('7')
  await shot(admin, '03-item-edit')
  await modal.getByRole('button', { name: '저장' }).click()
  await toast(admin, '[E2E-CABLE] 수정되었습니다.')
  await expect(orderRow(admin, 'E2E-CABLE')).toContainText('7')
})

test('주문 등록 시 운송장 발급, 배송지 수정 시 재발급', async () => {
  await createOrder(admin, '첫번째고객', 'E2E-CABLE')
  await orderRow(admin, '첫번째고객').click()
  const waybill = admin.locator('a.font-mono').first()
  await expect(waybill).toHaveText(/^58\d{10}$/)
  shared.firstWaybill = await waybill.textContent()
  await shot(admin, '04-order-detail')

  await admin.getByRole('button', { name: '주문 수정' }).click()
  const modal = admin.locator('.modal', { hasText: '주문 수정' })
  await modal.getByLabel('주소', { exact: true }).fill('서울시 중구 세종대로 110')
  await modal.getByRole('button', { name: '저장' }).click()
  await toast(admin, '새 운송장')
  await expect(admin.locator('a.font-mono').first()).not.toHaveText(shared.firstWaybill)
})

test('묶음배송 묶기와 해제', async () => {
  await createOrder(admin, '두번째고객', 'E2E-CABLE', { address: '서울시 중구 세종대로 110' })
  await expect(orderRow(admin, '첫번째고객')).toContainText('묶음 가능')
  for (const customer of ['첫번째고객', '두번째고객']) await orderRow(admin, customer).locator('input[type=checkbox]').check()
  await admin.getByRole('button', { name: '묶음배송', exact: true }).click()
  await shot(admin, '05-bundle-confirm')
  await admin.locator('.modal').getByRole('button', { name: '묶기' }).click()
  await toast(admin, '하나로 묶었습니다')
  await expect(admin.getByText('묶음배송 (운송장 하나로 함께 보냄)')).toBeVisible()
  await shot(admin, '06-bundle-detail')

  await admin.getByRole('button', { name: '묶음 해제' }).click()
  await admin.locator('.modal').getByRole('button', { name: '해제', exact: true }).click()
  await toast(admin, '묶음을 풀었습니다')
})

test('배송지 엑셀 일괄 등록', async () => {
  await admin.goto('/orders')
  await admin.getByRole('button', { name: '배송지 일괄 등록' }).click()
  const modal = admin.locator('.modal', { hasText: '배송지 일괄 등록' })
  const [download] = await Promise.all([admin.waitForEvent('download'), modal.getByRole('button', { name: '양식 내려받기' }).click()])
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/)
  const file = path.join(SCREENS, 'address-template.xlsx')
  await download.saveAs(file)

  // 엑셀에서 고친 것처럼 두번째고객의 상세주소를 바꾸고, 우편번호는 숫자로 바뀌어 앞의 0이 빠진 상태로 저장합니다.
  const book = XLSX.readFile(file)
  const rows = XLSX.utils.sheet_to_json(book.Sheets[book.SheetNames[0]], { defval: '' })
  const target = rows.find(row => row['고객'] === '두번째고객')
  target['상세주소'] = '202호'
  target['우편번호'] = 6236
  book.Sheets[book.SheetNames[0]] = XLSX.utils.json_to_sheet(rows)
  XLSX.writeFile(book, file)

  await modal.locator('input[type=file]').setInputFiles(file)
  await expect(modal.getByText('반영할 내용 1건')).toBeVisible()
  await expect(modal.getByText('상세주소: 101호 → 202호')).toBeVisible()
  await shot(admin, '07-address-import-preview')
  await modal.getByRole('button', { name: /저장 \(1건\)/ }).click()
  await toast(admin, '배송지 1건 저장')
  await modal.getByRole('button', { name: '닫기' }).click()
})

test('시스템 팝업: 주문 취소를 닫으면 그대로, 확인하면 취소', async () => {
  await orderRow(admin, '두번째고객').click()
  await admin.getByRole('button', { name: '주문 취소' }).click()
  const dialog = admin.locator('.modal', { hasText: '주문을 취소하시겠습니까?' })
  await expect(dialog).toContainText('운송장')
  await shot(admin, '08-cancel-dialog')
  await dialog.getByRole('button', { name: '닫기' }).click()
  await expect(orderRow(admin, '두번째고객')).toBeVisible()

  await admin.getByRole('button', { name: '주문 취소' }).click()
  await admin.locator('.modal').getByRole('button', { name: '주문 취소' }).click()
  await toast(admin, '취소 완료')
  await expect(orderRow(admin, '두번째고객')).toHaveCount(0)
})

test('현장 출고: 오류 화면, 위치 확인, 스캔, 출고 완료', async () => {
  const locations = await apiGet(worker, '/api/inventory/locations/')
  const shelf = locations.find(loc => loc.full_code === 'A-R01-1단')
  const other = locations.find(loc => loc.full_code !== 'A-R01-1단')

  await worker.goto('/work')
  await shot(worker, '09-work-home')
  await worker.keyboard.press('2')
  await worker.locator('button.work-row', { hasText: '첫번째고객' }).click()

  await scan(worker, 'WRONG-CODE')
  await expect(worker.locator('.work-error')).toBeVisible()
  await shot(worker, '10-work-error')
  await worker.keyboard.press('Space')
  await expect(worker.locator('.work-error')).toBeHidden()

  await scan(worker, other.barcode)
  await expect(worker.locator('.work-error')).toContainText('다른 위치입니다')
  await worker.keyboard.press('Space')
  await scan(worker, shelf.barcode)
  await expect(worker.getByText('✔ 위치 확인', { exact: true })).toBeVisible()
  await shot(worker, '11-work-location-ok')

  await scan(worker, 'E2E-CABLE')
  await expect(worker.getByText('✔ 모든 품목 스캔 완료')).toBeVisible()
  await expect(worker.getByText(/운송장 58\d{10}/)).toBeVisible()
  await shot(worker, '12-work-outbound-done')
  await worker.getByRole('button', { name: '출고 완료 (Enter)' }).click()
  await expect(worker.locator('.work-toast-ok')).toContainText('출고 완료')
})

test('발주 등록 → 현장 입고(시리얼) → 입고 취소', async () => {
  await admin.goto('/purchase-order')
  await admin.getByRole('button', { name: '발주 등록' }).click()
  const modal = admin.locator('.modal', { hasText: '발주서 등록' })
  await selectByText(modal.locator('select').first(), '테스트공급사')
  await selectByText(modal.locator('tbody select').first(), 'E2E-DEV')
  await modal.locator('tbody input[type=number]').first().fill('2')
  await modal.getByRole('button', { name: '등록', exact: true }).click()
  await toast(admin, '등록 완료')

  await worker.goto('/work')
  await worker.keyboard.press('1')
  await worker.locator('button.work-row').first().click()
  await scan(worker, 'E2E-DEV')
  await expect(worker.getByText('시리얼을 스캔하세요').first()).toBeVisible()
  await scan(worker, 'SN-E2E-1')
  await expect(worker.locator('.work-toast-ok')).toContainText('입고')
  await scan(worker, 'SN-E2E-2')
  await expect(worker.getByText('✔ 모든 품목 입고 완료')).toBeVisible()
  await shot(worker, '13-work-inbound-done')

  await worker.getByRole('button', { name: '입고 취소' }).click()
  const dialog = worker.locator('.work-dialog')
  await dialog.locator('input').fill('SN-E2E-2')
  await dialog.locator('input').press('Enter')
  await expect(worker.locator('.work-toast-ok')).toContainText('입고 취소 완료')
  await expect(worker.getByText('✔ 모든 품목 입고 완료')).toBeHidden()
  await worker.getByRole('button', { name: '발주서 목록으로' }).click()
})

test('시리얼 상품 출고 → 반품 등록 시 회수 요청 → 시리얼 이력', async () => {
  await createOrder(admin, '세번째고객', 'E2E-DEV')
  await worker.goto('/work')
  await worker.keyboard.press('2')
  await worker.locator('button.work-row', { hasText: '세번째고객' }).click()
  await scan(worker, 'SN-E2E-1')
  await expect(worker.getByText('✔ 모든 품목 스캔 완료')).toBeVisible()
  await worker.getByRole('button', { name: '출고 완료 (Enter)' }).click()
  await expect(worker.locator('.work-toast-ok')).toContainText('출고 완료')

  await admin.goto('/returns')
  await admin.getByRole('button', { name: '반품 등록' }).click()
  const modal = admin.locator('.modal', { hasText: '반품 등록' })
  await modal.getByLabel('고객명').fill('세번째고객')
  await selectByText(modal.getByLabel('출고된 시리얼'), 'SN-E2E-1')
  await modal.getByRole('button', { name: '등록', exact: true }).click()
  await toast(admin, '회수 운송장')
  await expect(orderRow(admin, '세번째고객')).toContainText('회수접수')
  await shot(admin, '14-returns')

  await admin.goto('/serials')
  await orderRow(admin, 'SN-E2E-1').click()
  const history = admin.locator('.modal', { hasText: '시리얼 이력' })
  for (const title of ['입고', '주문 출고', '반품 등록']) await expect(history.getByText(title, { exact: true })).toBeVisible()
  await shot(admin, '15-serial-history')
})

test('오늘 할 일의 택배 확인 필요 건에서 주문으로 이동', async () => {
  // 택배사가 주소를 거부해도 주문은 등록되고, 실패 사유를 알려줍니다.
  await createOrder(admin, '주소오류고객', 'E2E-CABLE', { address: '없는주소 1번지' }, '운송장 발급 실패: 주소를 확인할 수 없습니다')
  await admin.goto('/today')
  const panel = admin.locator('.panel', { hasText: '택배 확인 필요' })
  await expect(panel).toContainText('주소를 확인할 수 없습니다')
  await shot(admin, '16-today-carrier-issues')
  await panel.locator('tbody tr', { hasText: '주소오류고객' }).click()
  await expect(admin).toHaveURL(/\/orders$/)
  await expect(admin.locator('.panel-title', { hasText: '주소오류고객' })).toBeVisible()
})

test('엑셀 다운로드와 오늘 내 작업, 비밀번호 변경', async () => {
  await admin.goto('/stock')
  await expect(orderRow(admin, 'E2E-CABLE')).toBeVisible()  // 목록을 불러온 뒤 눌러야 내용이 담깁니다.
  const [download] = await Promise.all([admin.waitForEvent('download'), admin.getByRole('button', { name: '엑셀 다운로드' }).click()])
  expect(download.suggestedFilename()).toMatch(/^재고현황_.*\.xlsx$/)

  await worker.goto('/work')
  await worker.keyboard.press('4')
  await expect(worker).toHaveURL(/\/work\/today$/)
  await expect(worker.getByText('처리 건수')).toBeVisible()
  await expect(worker.locator('tbody tr').first()).toBeVisible()
  await shot(worker, '17-work-today')

  await worker.getByRole('button', { name: '비밀번호' }).click()
  const modal = worker.locator('.modal', { hasText: '비밀번호 변경' })
  await modal.getByLabel('현재 비밀번호').fill('E2e-worker-pass!')
  await modal.getByLabel('새 비밀번호', { exact: true }).fill('E2e-worker-new-1!')
  await modal.getByLabel('새 비밀번호 확인').fill('E2e-worker-new-1!')
  await modal.getByRole('button', { name: '변경' }).click()
  await toast(worker, '비밀번호를 바꿨습니다')
})

test('재고 부족 카드에서 발주 제안을 열어 발주서 만들기', async () => {
  await admin.goto('/today')
  await admin.locator('.today-card', { hasText: '재고 부족' }).click()
  const modal = admin.locator('.modal', { hasText: '발주 제안' })
  await expect(modal.locator('tbody tr', { hasText: 'E2E-DEV' })).toBeVisible()
  await shot(admin, '18-reorder-suggest')
  const group = modal.locator('div.border', { hasText: 'E2E-DEV' })
  await group.getByRole('button', { name: '발주서 만들기' }).click()
  await toast(admin, '등록 완료 (1개 상품)')
  await modal.getByRole('button', { name: '닫기' }).click()
})

test('사용자 등록과 사용 중지', async () => {
  await admin.goto('/users')
  await admin.locator('label:has-text("사원번호") + input').fill('e2e_new')
  await admin.locator('label:has-text("이름") + input').fill('새작업자')
  await admin.locator('label:has-text("첫 비밀번호") + input').fill('E2e-new-pass-1!')
  await admin.getByRole('button', { name: '사용자 등록' }).click()
  await toast(admin, '[e2e_new] 사용자를 등록했습니다.')
  const row = admin.locator('tbody tr', { hasText: 'e2e_new' })
  await row.getByRole('button', { name: '사용 중지' }).click()
  await admin.locator('.modal').getByRole('button', { name: '사용 중지' }).click()
  await toast(admin, '[e2e_new] 사용 중지했습니다.')
  await expect(row.locator('td').nth(4)).toHaveText('사용 중지')
  // 로그인한 계정은 마지막 로그인 시각이 남습니다.
  await expect(admin.locator('tbody tr', { hasText: 'e2e_admin' }).locator('td').nth(3)).not.toHaveText('로그인 기록 없음')
  await expect(admin.locator('tbody tr', { hasText: 'e2e_admin' }).getByRole('button', { name: '사용 중지' })).toHaveCount(0)
  await shot(admin, '19-users')
})

test('위치별 재고: 재고 이동, 다른 선반에 입고, 출고 위치 안내', async () => {
  await admin.goto('/stock')
  await orderRow(admin, 'E2E-CABLE').getByRole('button', { name: '[이동]' }).click()
  const modal = admin.locator('.modal', { hasText: '재고 이동' })
  await selectByText(modal.locator('label:has-text("어디로") select'), 'B-R02-2단')
  await modal.locator('input[type=number]').fill('2')
  await shot(admin, '25-move-stock')
  await modal.getByRole('button', { name: '이동', exact: true }).click()
  await toast(admin, '2개를 B-R02-2단로 옮겼습니다')
  await expect(orderRow(admin, 'E2E-CABLE')).toContainText('B-R02-2단 2')

  // 현장 입고: 기본 위치가 아닌 선반 라벨을 스캔하면 그 위치에 넣습니다.
  const locations = await apiGet(worker, '/api/inventory/locations/')
  const shelfB = locations.find(loc => loc.full_code === 'B-R02-2단')
  await admin.goto('/purchase-order')
  await admin.getByRole('button', { name: '발주 등록' }).click()
  const po = admin.locator('.modal', { hasText: '발주서 등록' })
  await selectByText(po.locator('select').first(), '테스트공급사')
  await selectByText(po.locator('tbody select').first(), 'E2E-CABLE')
  await po.locator('tbody input[type=number]').first().fill('1')
  await po.getByRole('button', { name: '등록', exact: true }).click()
  await toast(admin, '등록 완료')
  const poNo = (await admin.getByText(/등록 완료/).first().textContent()).match(/PO-\d+-\d+/)[0]

  await worker.goto('/work')
  await worker.keyboard.press('1')
  await worker.locator('button.work-row', { hasText: poNo }).click()
  await scan(worker, shelfB.barcode)  // 선반 라벨 → 상품 순서
  await expect(worker.getByText('다음 상품은 B-R02-2단에 넣습니다')).toBeVisible()
  await scan(worker, 'E2E-CABLE')
  await expect(worker.getByText('✔ 모든 품목 입고 완료')).toBeVisible()
  await worker.getByRole('button', { name: '발주서 목록으로 (Enter)' }).click()

  const items = await apiGet(worker, '/api/inventory/items/')
  const cable = items.find(item => item.sku === 'E2E-CABLE')
  expect(cable.stocks.find(s => s.location_name === 'B-R02-2단').quantity).toBe(3)
})

test('시리얼 없는 상품 반품: 원래 주문 선택 → 현장에서 상품 바코드로 회수', async () => {
  await admin.goto('/returns')
  await admin.getByRole('button', { name: '반품 등록' }).click()
  const modal = admin.locator('.modal', { hasText: '반품 등록' })
  await modal.getByLabel('수량 상품 (시리얼 없음)').check()
  await modal.getByLabel('고객명').fill('첫번째고객')
  await selectByText(modal.locator('label:has-text("상품") select').first(), 'E2E-CABLE')
  await selectByText(modal.locator('label:has-text("원래 주문") select'), '첫번째고객')
  await shot(admin, '20-quantity-return-form')
  await modal.getByRole('button', { name: '등록', exact: true }).click()
  await toast(admin, '회수 운송장')
  await expect(orderRow(admin, '첫번째고객').first()).toContainText('수량 1개')

  await worker.goto('/work')
  await worker.keyboard.press('3')
  await scan(worker, 'E2E-CABLE')
  await expect(worker.getByRole('button', { name: /재고로 되돌림/ })).toBeVisible()
  await shot(worker, '21-work-quantity-return')
  await worker.getByRole('button', { name: /재고로 되돌림/ }).click()
  await expect(worker.locator('.work-toast-ok')).toContainText('회수 완료')
})

test('부분 출고: 스캔한 만큼 출고하고 남은 수량은 새 주문', async () => {
  await admin.goto('/orders')
  await admin.getByRole('button', { name: '주문 등록' }).click()
  const modal = admin.locator('.modal', { hasText: '출고 주문 등록' })
  await modal.locator('label:has-text("거래처/고객") + input').fill('부분고객')
  await selectByText(modal.locator('select').first(), 'E2E-CABLE')
  await modal.locator('tbody input[type=number]').first().fill('2')
  await fillAddress(modal)
  await modal.getByRole('button', { name: '등록', exact: true }).click()
  await toast(admin, '등록 완료 (운송장')

  await worker.goto('/work')
  await worker.keyboard.press('2')
  await worker.locator('button.work-row', { hasText: '부분고객' }).click()
  await scan(worker, 'E2E-CABLE')
  await expect(worker.locator('.work-toast-ok')).toBeVisible()
  await worker.getByRole('button', { name: '있는 것만 출고 (부분 출고)' }).click()
  await expect(worker.locator('.modal')).toContainText('테스트 케이블 1개')
  await shot(worker, '22-work-partial-confirm')
  await worker.locator('.modal').getByRole('button', { name: '부분 출고' }).click()
  await expect(worker.locator('.work-toast-ok')).toContainText('남은 수량은 주문')

  await admin.goto('/orders')
  await orderRow(admin, '부분고객').click()
  await expect(admin.getByText('부분 출고 후 남은 수량으로 만든 주문입니다.')).toBeVisible()
})

test('스캔 재고 조사: 위치를 스캔해 대조하고 반영', async () => {
  await admin.goto('/audit')
  const panel = admin.locator('.panel-body')
  await selectByText(panel.locator('select').first(), 'A-R01-1단')
  const box = panel.locator('input.field-scan')
  for (const code of ['E2E-CABLE', 'E2E-CABLE', 'E2E-CABLE', 'NOT-EXIST']) {
    await box.fill(code)
    await box.press('Enter')
  }
  await panel.getByRole('button', { name: '대조하기' }).click()
  await expect(panel.getByText('등록되지 않은 바코드: NOT-EXIST')).toBeVisible()
  await expect(panel.locator('tbody tr', { hasText: 'E2E-CABLE' }).locator('td').nth(3)).toHaveText('3')
  await shot(admin, '23-scan-audit')
  await panel.getByRole('button', { name: '조사 결과 반영' }).click()
  await admin.locator('.modal').getByRole('button', { name: '반영' }).click()
  await toast(admin, '[E2E-CABLE] 이 위치')
})

test('입고 예정일이 지난 발주를 오늘 할 일에서 열기', async () => {
  const yesterday = new Date(Date.now() - 86400000).toLocaleDateString('sv-SE')
  await admin.goto('/purchase-order')
  await admin.getByRole('button', { name: '발주 등록' }).click()
  const modal = admin.locator('.modal', { hasText: '발주서 등록' })
  await selectByText(modal.locator('select').first(), '테스트공급사')
  await modal.locator('input[type=date]').fill(yesterday)
  await selectByText(modal.locator('tbody select').first(), 'E2E-CABLE')
  await modal.getByRole('button', { name: '등록', exact: true }).click()
  await toast(admin, '등록 완료')

  await admin.goto('/today')
  const panel = admin.locator('.panel', { hasText: '입고 예정일이 지난 발주' })
  await expect(panel).toContainText('1일 지남')
  await shot(admin, '24-today-overdue')
  await panel.locator('tbody tr').first().click()
  await expect(admin).toHaveURL(/\/purchase-order$/)
  await expect(admin.locator('.panel-title', { hasText: `입고 예정일: ${yesterday}` })).toBeVisible()
})

test('사원증 발급 → 현장 화면에서 작업자 전환', async () => {
  await admin.goto('/users')
  await admin.locator('tbody tr', { hasText: 'e2e_worker' }).getByRole('button', { name: '사원증 발급' }).click()
  const [issued] = await Promise.all([
    admin.waitForResponse(res => res.url().includes('/issue_badge/')),
    admin.locator('.modal').getByRole('button', { name: '발급' }).click(),
  ])
  const { code } = await issued.json()
  await expect(admin.locator('.modal', { hasText: '사원증 인쇄' })).toBeVisible()
  await shot(admin, '26-badge-card')
  await admin.locator('.modal', { hasText: '사원증 인쇄' }).getByRole('button', { name: '닫기' }).click()

  await worker.goto('/work')
  await worker.getByRole('button', { name: '작업자 전환' }).click()
  const dialog = worker.locator('.work-dialog')
  await dialog.locator('input').fill('EMP-WRONGCODE')
  await dialog.locator('input').press('Enter')
  await expect(dialog).toContainText('쓸 수 없는 사원증')
  await dialog.locator('input').fill(code)
  await dialog.locator('input').press('Enter')
  await toast(worker, '테스트작업자 님으로 바뀌었습니다.')
  await expect(worker).toHaveURL(/\/work$/)
})

test('집품: 여러 주문을 골라 위치 순서로 한 번에 꺼내기', async () => {
  for (const [customer, count] of [['집품고객A', '1'], ['집품고객B', '2']]) {
    await admin.goto('/orders')
    await admin.getByRole('button', { name: '주문 등록' }).click()
    const modal = admin.locator('.modal', { hasText: '출고 주문 등록' })
    await modal.locator('label:has-text("거래처/고객") + input').fill(customer)
    await selectByText(modal.locator('select').first(), 'E2E-CABLE')
    await modal.locator('tbody input[type=number]').first().fill(count)
    await fillAddress(modal)
    await modal.getByRole('button', { name: '등록', exact: true }).click()
    await toast(admin, '등록 완료 (운송장')
  }

  await worker.goto('/work/outbound')
  await worker.getByRole('button', { name: '여러 주문 한 번에 꺼내기 (집품)' }).click()
  await expect(worker).toHaveURL(/\/work\/picking$/)
  await worker.locator('button.work-row', { hasText: '집품고객A' }).click()
  await worker.locator('button.work-row', { hasText: '집품고객B' }).click()
  await worker.getByRole('button', { name: '집품 시작 (2건)' }).click()
  await expect(worker.locator('.work-task')).toContainText('테스트 케이블')
  await scan(worker, 'E2E-NOPE')
  await expect(worker.locator('.work-error')).toContainText('이번 집품에 없는 상품')
  await worker.keyboard.press('Space')
  await expect(worker.locator('.work-error')).toBeHidden()
  await shot(worker, '27-work-picking')
  for (let i = 0; i < 3; i++) await scan(worker, 'E2E-CABLE')
  await expect(worker.getByText('✔ 집품 완료')).toBeVisible()
  await worker.getByRole('button', { name: '출고 화면으로 (집품 끝내기)' }).click()
  await expect(worker).toHaveURL(/\/work\/outbound$/)
})

test('작업자 실적: 오늘 작업이 작업자별로 집계되고 엑셀로 내려받기', async () => {
  await admin.goto('/workers')
  await admin.getByRole('button', { name: '오늘', exact: true }).click()
  const today = await admin.locator('input[aria-label="종료일"]').inputValue()
  await expect(admin.getByText(`작업자별 실적 (${today} ~ ${today}`)).toBeVisible()
  const row = admin.locator('tbody tr', { hasText: 'e2e_worker' }).first()
  await expect(row).toBeVisible()
  await expect(admin.locator('thead').first()).toContainText('출고')
  await row.click()
  await expect(admin.getByText('일자별 처리 줄 수 (상품 줄 기준) · 테스트작업자')).toBeVisible()
  await shot(admin, '28-worker-report')
  const [download] = await Promise.all([admin.waitForEvent('download'), admin.getByRole('button', { name: '엑셀 다운로드' }).click()])
  const book = XLSX.readFile(await download.path())
  expect(book.SheetNames).toEqual(['작업자별', '일자별'])
  const sheet = XLSX.utils.sheet_to_json(book.Sheets['작업자별'])
  expect(sheet.find(r => r['아이디'] === 'e2e_worker')['출고 건']).toBeGreaterThan(0)
})

test('일일 마감: 오늘 처리 실적과 남은 일을 저장하고 기록에서 다시 보기', async () => {
  await admin.goto('/daily-close')
  await expect(admin.getByText('마감 전 (지금 기준 계산')).toBeVisible()
  await expect(admin.locator('.today-card', { hasText: '출고' }).first()).not.toContainText('주문 0건')
  await admin.getByLabel('마감 메모').fill('E2E 마감 확인')
  await admin.getByRole('button', { name: '마감하기' }).click()
  await admin.locator('.modal').getByRole('button', { name: '마감', exact: true }).click()
  await toast(admin, '마감 완료')
  await expect(admin.getByText('✔ 마감됨')).toBeVisible()
  await expect(admin.locator('tbody tr', { hasText: 'E2E 마감 확인' })).toBeVisible()
  await expect(admin.getByRole('button', { name: '다시 마감' })).toBeVisible()
  await shot(admin, '29-daily-close')

  await admin.getByLabel('전날').click()
  await expect(admin.getByText('마감 전 (지금 기준 계산')).toBeVisible()
  await admin.locator('tbody tr', { hasText: 'E2E 마감 확인' }).click()
  await expect(admin.getByText('✔ 마감됨')).toBeVisible()
  const [download] = await Promise.all([admin.waitForEvent('download'), admin.getByRole('button', { name: '엑셀 다운로드' }).click()])
  expect(XLSX.readFile(await download.path()).SheetNames).toEqual(['요약', '출고대기', '작업자', '재고부족'])
})

test('긴급 주문과 출고 마감: 관리자가 긴급 지정하면 현장 출고 목록 맨 위', async () => {
  await admin.goto('/orders')
  await orderRow(admin, '집품고객B').click()
  await admin.getByRole('button', { name: '긴급 지정' }).click()
  await toast(admin, '긴급 지정')
  await expect(orderRow(admin, '집품고객B')).toContainText('긴급')
  await expect(orderRow(admin, '집품고객B').locator('td').nth(4)).toContainText(/남음|지남|마감/)

  await worker.goto('/work/outbound')
  const first = worker.locator('button.work-row').first()
  await expect(first).toContainText('집품고객B')
  await expect(first.locator('.work-urgent')).toHaveText('긴급')
  await expect(first).toContainText('마감')
  await shot(worker, '30-work-urgent')

  await admin.goto('/today')
  await expect(admin.locator('.today-card', { hasText: '출고 대기' })).toContainText('긴급 1')
  await admin.goto('/orders')
  await orderRow(admin, '집품고객B').click()
  await admin.getByRole('button', { name: '긴급 해제' }).click()
  await toast(admin, '긴급 해제')
})

test('위치 보충: 기본 위치가 모자라면 현장에서 다른 선반 재고를 옮겨 채우기', async () => {
  await admin.goto('/items')
  await orderRow(admin, 'E2E-CABLE').getByRole('button', { name: '수정' }).click()
  const modal = admin.locator('.modal', { hasText: '상품 수정' })
  await modal.getByLabel('보충 최소').fill('99')
  await modal.getByLabel('보충 최대').fill('100')
  await modal.getByRole('button', { name: '저장' }).click()
  await toast(admin, '수정되었습니다')

  const locations = await apiGet(worker, '/api/inventory/locations/')
  const shelfA = locations.find(loc => loc.full_code === 'A-R01-1단')
  const shelfB = locations.find(loc => loc.full_code === 'B-R02-2단')
  const before = (await apiGet(worker, '/api/inventory/items/')).find(item => item.sku === 'E2E-CABLE')
  const reserve = before.stocks.find(s => s.location_name === 'B-R02-2단').quantity

  await worker.goto('/work')
  await expect(worker.getByRole('button', { name: /5번 키 · 위치 보충 1건/ })).toBeVisible()
  await worker.keyboard.press('5')
  await worker.locator('button.work-row', { hasText: '테스트 케이블' }).click()
  await scan(worker, shelfA.barcode)
  await expect(worker.locator('.work-error')).toContainText('먼저 B-R02-2단에서 꺼내')
  await worker.keyboard.press('Space')
  await scan(worker, shelfB.barcode)
  await expect(worker.locator('.work-task')).toContainText('✔ 위치 확인')
  for (let i = 0; i < reserve; i++) await scan(worker, 'E2E-CABLE')
  await expect(worker.getByText('2단계 · 꺼내는 자리에 채우기')).toBeVisible()
  await shot(worker, '31-work-replenish')
  await scan(worker, shelfA.barcode)
  await expect(worker.locator('.work-toast-ok')).toContainText(`${reserve}개를 A-R01-1단로 옮겼습니다`)
  // 다른 위치 재고를 다 옮겨도 최소에 못 미치면 발주가 필요하다고 보입니다.
  await expect(worker.locator('button.work-row', { hasText: '테스트 케이블' })).toContainText('발주 필요')

  const after = (await apiGet(worker, '/api/inventory/items/')).find(item => item.sku === 'E2E-CABLE')
  expect(after.stocks.find(s => s.location_name === 'A-R01-1단').quantity).toBe(before.stocks.find(s => s.location_name === 'A-R01-1단').quantity + reserve)
  await admin.goto('/items')
  await orderRow(admin, 'E2E-CABLE').getByRole('button', { name: '수정' }).click()
  await admin.locator('.modal').getByLabel('보충 최소').fill('0')
  await admin.locator('.modal').getByRole('button', { name: '저장' }).click()
  await toast(admin, '수정되었습니다')
})

test('순환 재고 조사: 반영한 위치는 오늘 완료로, 스캔이 모두 맞아도 완료로 기록', async () => {
  await admin.goto('/audit')
  // 앞의 스캔 재고 조사에서 반영한 A-R01-1단은 오늘 완료 목록에 있습니다.
  const plan = await apiGet(admin, '/api/inventory/locations/cycle_count/')
  expect(plan.done.map(loc => loc.full_code)).toContain('A-R01-1단')
  const cycle = admin.locator('.panel', { hasText: '오늘의 순환 조사' }).last()
  await expect(cycle).toContainText('✔ A-R01-1단')

  // 전산상 그 위치에 있는 것을 그대로 스캔하면 "모두 일치"로 조사 완료가 기록됩니다.
  const target = plan.done.find(loc => loc.full_code === 'A-R01-1단')
  const token = await admin.evaluate(() => localStorage.getItem('access_token'))
  const preview = await (await admin.request.post('/api/inventory/items/audit_scan/', {
    headers: { Authorization: `Bearer ${token}` }, data: { location: target.id, codes: [] },
  })).json()
  const codes = preview.rows.flatMap(row => (row.serial_tracked ? row.missing : Array(row.system).fill(row.sku)))
  await selectByText(admin.locator('.panel-body select').first(), 'A-R01-1단')
  const box = admin.locator('input.field-scan')
  for (const code of codes) {
    await box.fill(code)
    await box.press('Enter')
  }
  await admin.getByRole('button', { name: '대조하기' }).click()
  await expect(admin.getByText('✔ 모두 일치합니다. A-R01-1단 조사 완료로 기록했습니다.')).toBeVisible()
  await shot(admin, '32-cycle-count')
  await admin.goto('/today')
  await expect(admin.locator('.today-card', { hasText: '순환 재고 조사' })).toContainText('1곳 완료')
})

test('기준정보 변경 이력: 앞에서 바꾼 상품·사용자 기록 확인', async () => {
  await admin.goto('/changes')
  await admin.getByRole('button', { name: '상품', exact: true }).click()
  const itemRow = admin.locator('tbody tr', { hasText: 'E2E-CABLE' }).filter({ hasText: '보충 최소' }).first()
  await expect(itemRow).toContainText('99')
  await expect(itemRow).toContainText('테스트관리자')
  await admin.getByRole('button', { name: '사용자', exact: true }).click()
  await expect(admin.locator('tbody tr', { hasText: '사원증 발급' }).first()).toContainText('e2e_worker')
  await admin.locator('input[placeholder^="대상"]').fill('e2e_worker')
  await admin.getByRole('button', { name: '검색' }).click()
  await expect(admin.locator('tbody tr').first()).toContainText('e2e_worker')
  await shot(admin, '33-change-history')
})

test('관리자 집품 리스트 인쇄: 고른 주문을 위치 순서로 모아 인쇄 화면', async () => {
  await admin.goto('/orders')
  await orderRow(admin, '집품고객A').locator('input[type=checkbox]').check()
  await orderRow(admin, '집품고객B').locator('input[type=checkbox]').check()
  await admin.getByRole('button', { name: '집품 리스트 인쇄 (2건)' }).click()
  const modal = admin.locator('.modal', { hasText: '집품 리스트 인쇄' })
  const line = modal.locator('tbody tr', { hasText: 'E2E-CABLE' }).first()
  await expect(line).toContainText('A-R01-1단')
  await expect(line.locator('td').nth(4)).toHaveText('3')
  await expect(modal).toContainText('주문별 나누기')
  await shot(admin, '34-pick-list-print')
  await modal.getByRole('button', { name: '닫기' }).click()
})
