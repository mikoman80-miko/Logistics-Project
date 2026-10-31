import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import axios from 'axios'

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

  const downloadLogs = async (params = {}) => {
    const response = await axios.get('/api/inventory/logs/export/', { params, responseType: 'blob' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(response.data)
    link.download = `WMS_입출고이력_${new Date().toLocaleDateString('sv-SE')}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const addItem = async (itemData) => {
    await axios.post('/api/inventory/items/', itemData)
    await fetchItems()
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

  const fetchOrders = async (status) => {
    const response = await axios.get('/api/inventory/orders/', { params: status ? { status } : {} })
    return response.data
  }

  const createOrder = async (body) => (await axios.post('/api/inventory/orders/', body)).data
  const cancelOrder = async (id) => (await axios.post(`/api/inventory/orders/${id}/cancel/`)).data

  // 주문 하나를 한 번에 출고합니다. 하나라도 부족하면 전체가 처리되지 않습니다.
  const completeOrder = async (id) => {
    const response = await axios.post(`/api/inventory/orders/${id}/complete/`)
    await fetchItems()
    return response.data
  }

  const fetchReturns = async (status) => {
    const response = await axios.get('/api/inventory/returns/', { params: status ? { status } : {} })
    return response.data
  }

  const createReturn = async (body) => (await axios.post('/api/inventory/returns/', body)).data
  const cancelReturn = async (id) => (await axios.post(`/api/inventory/returns/${id}/cancel/`)).data

  const completeReturn = async (id, status, quality, detail) => {
    const response = await axios.post(`/api/inventory/returns/${id}/complete/`, { status, quality, detail })
    await fetchSerials()
    return response.data
  }

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

  const totalQuantity = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0))
  const totalSkuCount = computed(() => items.value.length)
  const lowStockItems = computed(() => items.value.filter(item => item.quantity <= item.safety_stock && item.quantity > 0))

  const serials = ref([])

  const fetchSerials = async () => {
    const response = await axios.get('/api/inventory/serials/')
    serials.value = response.data
  }

  const batchUpdateSerials = async (ids, status, quality) => {
    await axios.patch('/api/inventory/serials/batch_update/', {
      ids, status, quality
    })
    await fetchSerials()
  }

  return { 
    items, fetchItems, fetchLogs, downloadLogs, addItem, updateQuantity, 
    updateItemDetails, deleteItem, scanSerial, serials, fetchSerials, batchUpdateSerials,
    adjustStock, locations, fetchLocations,
    fetchOrders, createOrder, cancelOrder, completeOrder,
    fetchReturns, createReturn, cancelReturn, completeReturn,
    totalQuantity, totalSkuCount, lowStockItems 
  }
})