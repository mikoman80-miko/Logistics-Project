<template>
  <div class="flex flex-col h-full">
    <div v-if="isOrderFormOpen" class="modal-overlay">
      <form class="modal w-[640px]" @submit.prevent="submitOrder">
        <div class="modal-header">출고 주문 등록</div>
        <div class="modal-content">
          <div class="toolbar mb-2.5">
            <label class="field-label">거래처/고객</label>
            <input v-model="orderForm.customer" class="field w-[220px]" maxlength="100" required />
            <label class="field-label ml-2.5">비고</label>
            <input v-model="orderForm.note" class="field flex-1" maxlength="200" />
          </div>
          <OrderLinesEditor :lines="orderForm.items" :items="store.items" />
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">등록</button>
          <button type="button" class="btn btn-lg" @click="isOrderFormOpen = false">닫기</button>
        </div>
      </form>
    </div>
    <!-- 🌟 변경: 모바일은 세로(flex-col), PC는 가로(md:flex-row) -->
    <div class="page-split">
      <!-- 🌟 좌측 패널: 모바일은 꽉 차게(w-full), PC는 고정폭(md:w-[350px]) -->
      <div
        class="panel w-full md:w-[350px] shrink-0">
        <div
          class="panel-header">
          <span class="panel-title">출고 대기 주문 목록</span>
          <div class="flex gap-1">
            <button v-if="isAdmin" class="btn btn-primary btn-sm" @click="openOrderForm">주문 등록</button>
            <button class="btn btn-sm" @click="loadOrders">새로고침</button>
          </div>
        </div>
        <div class="panel-body-flush">
          <table class="data-table">
            <thead>
              <tr>
                <th
                 
                  width="100">주문번호</th>
                <th
                 >
                  수취인</th>
                <th
                 
                  width="80">품목 수</th>
                <th
                 
                  width="80">상태</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="orders.length === 0">
                <td colspan="4" class="text-center">출고 대기 중인 주문이 없습니다.</td>
              </tr>
              <tr v-for="order in orders" :key="order.id" class="is-clickable"
                :class="{ 'is-selected': selectedOrder?.id === order.id }" @click="selectOrder(order)">
                <td class="text-center font-bold text-primary">{{ order.orderNo }}
                </td>
                <td class="text-center">{{ order.customer }}</td>
                <td class="text-right">{{ order.items.length }}종</td>
                <td class="text-center font-bold" :class="statusColor(order.status)">
                  {{ order.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 우측: 작업 영역 -->
      <div class="panel flex-1"
        v-if="selectedOrder">
        <div
          class="panel-header">
          <span class="panel-title">[{{ selectedOrder.orderNo }}] 출고 작업 보드</span>
          <div class="flex gap-0.5 h-full items-end shrink-0">
            <button
              class="tab" :class="{ 'is-active': activeTab === 'picking' }"
              @click="activeTab = 'picking'">1. 피킹 동선 지시서</button>
            <button
              class="tab" :class="{ 'is-active': activeTab === 'packing' }"
              @click="activeTab = 'packing'">2. 바코드 패킹 검수</button>
          </div>
        </div>

        <div class="panel-body">
          <div v-if="activeTab === 'picking'">
            <div class="alert alert-info">
              ※ 보관 구역(Location) 순으로 자동 정렬되었습니다. 순서대로 이동하며 상품을 피킹하십시오.
            </div>
            <table class="data-table">
              <thead>
                <tr>
                  <th
                   
                    width="100">이동 구역 📍</th>
                  <th
                   
                    width="150">SKU 코드</th>
                  <th
                   >
                    상품명</th>
                  <th
                   
                    width="80">지시 수량</th>
                  <th
                   
                    width="100">현재 재고</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in pickingList" :key="item.sku">
                  <td class="text-center font-bold bg-highlight">{{ item.location ||
                    '미지정' }}</td>
                  <td class="text-center font-mono">{{ item.sku }}</td>
                  <td class="truncate">{{ item.name }}</td>
                  <td class="text-right font-bold text-danger">{{ item.reqQty }} 개
                  </td>
                  <td class="text-right">{{ item.currentQty }} 개</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="activeTab === 'packing'">
            <div class="scan-box">
              <form @submit.prevent="handleScan" class="flex flex-col md:flex-row gap-2.5 md:items-center">
                <strong class="text-body whitespace-nowrap">상품 바코드 스캔:</strong>
                <input ref="scanInputRef" v-model="scanInput" type="text"
                  class="field field-scan w-full md:w-[300px]"
                  placeholder="SKU 스캔 후 Enter" autofocus autocomplete="off" />
                <button type="submit"
                  class="btn btn-success btn-lg">수동
                  확인</button>
              </form>
            </div>

            <table class="data-table mb-2.5">
              <thead>
                <tr>
                  <th
                   
                    width="80">검수 상태</th>
                  <th
                   
                    width="150">SKU 코드</th>
                  <th
                   >
                    상품명</th>
                  <th
                   
                    width="80">지시 수량</th>
                  <th
                   
                    width="80">스캔 수량</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in packingList" :key="item.sku"
                  :class="{ 'row-success': item.scanQty === item.reqQty }">
                  <td class="text-center font-bold"
                    :class="item.scanQty === item.reqQty ? 'text-success' : 'text-danger'">
                    {{ item.scanQty === item.reqQty ? '완료' : '미완료' }}
                  </td>
                  <td class="text-center font-mono">{{ item.sku }}</td>
                  <td class="truncate">{{ item.name }}</td>
                  <td class="text-right font-bold">{{ item.reqQty }}</td>
                  <td class="text-right font-bold"
                    :class="{ 'text-primary': item.scanQty > 0 }">{{ item.scanQty }}</td>
                </tr>
              </tbody>
            </table>

            <div class="text-right mt-2.5">
              <button v-if="isAdmin" class="btn btn-danger btn-lg mr-1.5" @click="cancelSelectedOrder">주문 취소</button>
              <button
                class="btn btn-primary btn-lg text-heading"
                :disabled="!isPackingComplete" @click="completeOutbound">
                {{ isPackingComplete ? '✅ 최종 출고 처리' : '검수 완료 대기 중...' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div
        class="panel flex-1 justify-center items-center"
        v-else>
        <div class="text-muted font-bold text-heading">출고 작업할 주문을 선택해 주십시오.</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated, nextTick } from 'vue'
import { useInventoryStore } from '../../stores/inventory'
import { useToastStore } from '../../stores/toastStore'
import { useAuthStore } from '../../stores/auth'
import OrderLinesEditor from '../../components/OrderLinesEditor.vue'
import { apiErrorMessage } from '../../utils/apiError'
import { playBeep } from '../../utils/beep'

const store = useInventoryStore()
const toast = useToastStore()

const orders = ref([])
const selectedOrder = ref(null)
const activeTab = ref('picking')
const scanInput = ref('')
const scanInputRef = ref(null)

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === '관리자')

const isOrderFormOpen = ref(false)
const isSaving = ref(false)
const orderForm = ref({ customer: '', note: '', items: [] })

const loadOrders = async () => {
  const data = await store.fetchOrders('출고대기')
  // 새로고침해도 진행 중인 스캔 수량은 유지합니다.
  const scanned = {}
  orders.value.forEach(o => o.items.forEach(i => { scanned[`${o.id}:${i.sku}`] = i.scanQty }))
  // 먼저 들어온 주문부터 처리하도록 오래된 순으로 표시합니다.
  orders.value = data.reverse().map(order => ({
    id: order.id,
    orderNo: order.order_no,
    customer: order.customer,
    status: order.status,
    items: order.items.map(line => ({
      sku: line.item_sku,
      name: line.item_name,
      location: line.location_name || '',
      reqQty: line.quantity,
      currentQty: line.current_quantity,
      scanQty: scanned[`${order.id}:${line.item_sku}`] || 0
    }))
  }))
  if (selectedOrder.value) selectedOrder.value = orders.value.find(o => o.id === selectedOrder.value.id) || null
}

const openOrderForm = async () => {
  await store.fetchItems()
  orderForm.value = { customer: '', note: '', items: [{ item: null, quantity: 1 }] }
  isOrderFormOpen.value = true
}

const submitOrder = async () => {
  isSaving.value = true
  try {
    const created = await store.createOrder(orderForm.value)
    toast.addToast(`주문 ${created.order_no} 등록 완료`, 'success')
    isOrderFormOpen.value = false
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '주문 등록 중 오류가 발생했습니다.'), 'error', 5000)
  } finally {
    isSaving.value = false
  }
}

const cancelSelectedOrder = async () => {
  if (!confirm(`[${selectedOrder.value.orderNo}] 주문을 취소하시겠습니까?`)) return
  try {
    const result = await store.cancelOrder(selectedOrder.value.id)
    toast.addToast(result.message, 'info')
    selectedOrder.value = null
    await loadOrders()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '주문 취소 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const selectOrder = (order) => {
  selectedOrder.value = order
  activeTab.value = 'picking'
}

const statusColor = (status) => {
  if (status === '출고대기') return 'text-danger'
  if (status === '출고완료') return 'text-success'
  return ''
}

const pickingList = computed(() => {
  if (!selectedOrder.value) return []
  return [...selectedOrder.value.items].sort((a, b) => (a.location || '').localeCompare(b.location || ''))
})

const packingList = computed(() => {
  if (!selectedOrder.value) return []
  return selectedOrder.value.items
})

const isPackingComplete = computed(() => {
  if (!selectedOrder.value) return false
  return selectedOrder.value.items.every(item => item.scanQty === item.reqQty)
})

const handleScan = async () => {
  if (!scanInput.value || !selectedOrder.value) return

  const targetItem = selectedOrder.value.items.find(i => i.sku === scanInput.value)
  if (!targetItem) {
    playBeep('error')
    toast.addToast(`❌ [오배송 경고] 주문 내역에 없는 상품입니다! (${scanInput.value})`, 'error')
  } else if (targetItem.scanQty >= targetItem.reqQty) {
    playBeep('error')
    toast.addToast('⚠️ 이미 요구 수량만큼 스캔이 완료된 상품입니다.', 'error')
  } else {
    targetItem.scanQty += 1
    playBeep('success')
    toast.addToast(`✅ 스캔 성공 (${targetItem.name})`, 'success', 1500)
  }

  scanInput.value = ''
  await nextTick()
  if (scanInputRef.value) {
    scanInputRef.value.focus()
    scanInputRef.value.select()
  }
}

const completeOutbound = async () => {
  if (!isPackingComplete.value) return
  if (!confirm(`[${selectedOrder.value.orderNo}] 패킹이 완료되었습니다. 재고를 차감하고 최종 출고 처리하시겠습니까?`)) return

  try {
    const result = await store.completeOrder(selectedOrder.value.id)
    toast.addToast(`📦 ${result.message}`, 'info')
    selectedOrder.value = null
    await loadOrders()
  } catch (err) {
    playBeep('error')
    toast.addToast(apiErrorMessage(err, '출고 처리 중 오류가 발생했습니다. 재고는 차감되지 않았습니다.'), 'error', 5000)
  }
}


onActivated(() => { store.fetchItems(); loadOrders() })
</script>