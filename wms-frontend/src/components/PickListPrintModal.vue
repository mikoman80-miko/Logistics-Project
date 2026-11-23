<template>
  <!-- 집품 리스트 인쇄: 고른 출고대기 주문의 품목을 위치 순서로 모아 종이로 뽑습니다. 꺼낸 뒤 주문별로 나눕니다. -->
  <Teleport to="body">
    <div class="print-only modal-overlay print:static print:bg-transparent" @click.self="$emit('close')">
      <div class="modal w-[960px] print:w-auto print:shadow-none print:border-none print:max-h-none">
        <div class="modal-header print:hidden">집품 리스트 인쇄 (주문 {{ orders.length }}건)</div>
        <div class="modal-content print:overflow-visible">
          <div class="flex justify-between items-end mb-2">
            <div>
              <div class="text-[20px] font-bold">집품 리스트</div>
              <div class="text-caption">주문 {{ orders.length }}건 · 꺼낼 곳 {{ rows.length }}곳 · 총 {{ rows.reduce((s, r) => s + r.quantity, 0) }}개</div>
            </div>
            <div class="text-caption text-right">출력 {{ printedAt }}<br />작업자: ____________</div>
          </div>
          <table class="data-table data-table-sm">
            <thead>
              <tr><th width="34">순서</th><th width="120">위치</th><th width="130">상품코드</th><th>상품명</th><th width="50">수량</th><th width="250">주문별</th><th width="40">확인</th></tr>
            </thead>
            <tbody>
              <tr v-if="rows.length === 0"><td colspan="7" class="text-center">꺼낼 품목이 없습니다. (이미 모두 스캔한 주문)</td></tr>
              <tr v-for="(row, index) in rows" :key="row.key">
                <td class="text-center">{{ index + 1 }}</td>
                <td class="text-center font-bold">{{ row.location_name }}<div v-if="row.short" class="text-caption text-danger">위치 기록 부족</div></td>
                <td class="text-center font-mono">{{ row.sku }}</td>
                <td>{{ row.name }}<span v-if="row.serial_tracked" class="text-caption"> (시리얼)</span></td>
                <td class="text-right font-bold text-[15px]">{{ row.quantity }}</td>
                <td class="text-caption">{{ row.orders.map(o => `${o.order_no.slice(-9)} ${o.customer} ${o.quantity}`).join(' / ') }}</td>
                <td class="text-center text-[18px]">☐</td>
              </tr>
            </tbody>
          </table>
          <div class="mt-3 text-caption font-bold">주문별 나누기</div>
          <table class="data-table data-table-sm">
            <thead><tr><th width="180">주문번호</th><th width="160">고객</th><th>품목</th><th width="40">확인</th></tr></thead>
            <tbody>
              <tr v-for="order in orders" :key="order.id">
                <td class="text-center font-mono">{{ order.order_no }}<b v-if="order.is_urgent" class="text-danger"> 긴급</b></td>
                <td class="truncate">{{ order.customer }}</td>
                <td class="text-caption">{{ order.items.filter(l => l.quantity > l.picked_quantity).map(l => `${l.item_name} ${l.quantity - l.picked_quantity}`).join(', ') }}</td>
                <td class="text-center text-[18px]">☐</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-footer print:hidden">
          <button class="btn btn-primary btn-lg" :disabled="rows.length === 0" @click="print">인쇄</button>
          <button class="btn btn-lg" @click="$emit('close')">닫기</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { buildPickList } from '../utils/pickList'

// 현장 [집품] 화면과 같은 계산(utils/pickList)을 씁니다.
const props = defineProps({ orders: { type: Array, required: true } })
defineEmits(['close'])
const rows = computed(() => buildPickList(props.orders))
const printedAt = new Date().toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })
const print = () => window.print()
</script>
