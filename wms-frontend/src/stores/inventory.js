import { ref } from 'vue'
import { defineStore } from 'pinia'
import axios from 'axios'
import { downloadXlsx } from '../utils/excel'

export const useInventoryStore = defineStore('inventory', () => {
  const items = ref([])

  const fetchItems = async () => {
    const response = await axios.get('/api/inventory/items/')
    items.value = response.data
  }

  // 이력은 양이 많아 필요한 만큼만 페이지 단위로 가져옵니다.
  const fetchLogs = async (params = {}) => {
    const response = await axios.get('/api/inventory/logs/', { params })
    return response.data
  }

  // 조건에 맞는 입출고 기록을 200건씩 받아 엑셀로 저장합니다. 너무 많으면 최근 20,000건까지만 받습니다.
  const LOG_EXPORT_LIMIT = 20000
  const downloadLogs = async (params = {}) => {
    const rows = []
    let total = 0
    for (let page = 1; rows.length < LOG_EXPORT_LIMIT; page++) {
      const data = await fetchLogs({ ...params, page, page_size: 200 })
      total = data.count
      rows.push(...data.results)
      if (!data.next) break
    }
    const headers = ['발생일시', '구분', '상품코드', '상품명', '변동수량', '처리자', '비고']
    downloadXlsx(`입출고기록_${new Date().toLocaleDateString('sv-SE')}`, '입출고기록', headers, rows.map(log => [
      new Date(log.timestamp).toLocaleString('ko-KR'), log.action_display, log.item_sku, log.item_name,
      log.quantity_changed, log.user_name, log.description || '',
    ]))
    return { saved: rows.length, total }
  }

  const updateQuantity = async (id, newQuantity, isAudit = false) => {
    const body = isAudit ? { quantity: newQuantity, physicalQty: newQuantity } : { quantity: newQuantity }
    await axios.patch(`/api/inventory/items/${id}/`, body)
    await fetchItems()
  }

  // 화면의 옛 수량이 아니라 증감량을 보내, 서버의 최신 수량 기준으로 계산합니다.
  const adjustStock = async (id, change) => {
    await axios.post(`/api/inventory/items/${id}/adjust_stock/`, { change })
    await fetchItems()
  }

  // params: { status, q, start_date, end_date } 중 값이 있는 것만 보냅니다.
  const listParams = (params = {}) => Object.fromEntries(Object.entries(params).filter(([, value]) => value))

  // 목록을 페이지로 나눠 받습니다. { count, results }
  const fetchPage = async (url, params, page, pageSize = 50) =>
    (await axios.get(url, { params: { ...listParams(params), page, page_size: pageSize } })).data

  const createOrder = async (body) => (await axios.post('/api/inventory/orders/', body)).data
  const cancelOrder = async (id) => (await axios.post(`/api/inventory/orders/${id}/cancel/`)).data

  const createReturn = async (body) => (await axios.post('/api/inventory/returns/', body)).data
  const cancelReturn = async (id) => (await axios.post(`/api/inventory/returns/${id}/cancel/`)).data

  const locations = ref([])
  const fetchLocations = async () => {
    const response = await axios.get('/api/inventory/locations/')
    locations.value = response.data
  }

  const updateItemDetails = async (id, name, location) => {
    await axios.patch(`/api/inventory/items/${id}/`, { name, location })
    await fetchItems()
  }

  const deleteItem = async (id) => {
    await axios.delete(`/api/inventory/items/${id}/`)
    await fetchItems()
  }

  const scanSerial = async (sku, serialNumber, scanType) => {
    try {
      const response = await axios.post('/api/inventory/items/scan_serial/', {
        sku: sku,
        serial_number: serialNumber,
        type: scanType
      })
      await fetchItems()
      return { success: true, message: response.data.message }
    } catch (error) {
      return { success: false, message: error.response?.data?.error || '스캔 처리 중 오류 발생' }
    }
  }

  const batchUpdateSerials = async (ids, status, quality) => {
    await axios.patch('/api/inventory/serials/batch_update/', {
      ids, status, quality
    })
  }

  return {
    items, fetchItems, fetchLogs, downloadLogs, updateQuantity,
    updateItemDetails, deleteItem, scanSerial, batchUpdateSerials,
    adjustStock, locations, fetchLocations,
    fetchPage, createOrder, cancelOrder,
    createReturn, cancelReturn,
  }
})
