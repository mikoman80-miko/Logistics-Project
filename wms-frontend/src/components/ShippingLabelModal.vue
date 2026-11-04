<template>
  <!-- body 바로 아래에 붙이고, 인쇄할 때는 이 송장만 나오게 합니다. (components.css의 print-only) -->
  <Teleport to="body">
  <div class="print-only modal-overlay print:static print:bg-transparent" @click.self="$emit('close')">
    <div class="modal w-[460px] print:shadow-none print:border-none print:w-full print:max-h-none">
      <div class="modal-header print:hidden">송장 출력 미리보기</div>
      <div class="modal-content">
        <!-- 100 x 150mm 택배 송장 -->
        <div class="border-2 border-black p-3 text-[13px] leading-snug text-black bg-white">
          <div class="flex justify-between items-end border-b-2 border-black pb-1.5">
            <span class="text-[20px] font-bold">{{ order.carrier_name || '택배' }}</span>
            <span class="font-mono font-bold">{{ formatted }}</span>
          </div>
          <div class="py-2 border-b border-black">
            <Barcode :value="order.waybill_no" :height="70" />
            <div class="text-center font-mono tracking-widest mt-1">{{ order.waybill_no }}</div>
          </div>
          <div class="py-2 border-b border-black">
            <div class="text-caption text-muted">받는 분</div>
            <div class="text-[18px] font-bold">{{ order.contact_name }} <span class="text-[14px] font-normal">{{ order.contact_phone }}</span></div>
            <div class="mt-1">({{ order.zipcode }}) {{ order.address }} {{ order.address_detail }}</div>
          </div>
          <div class="py-2 border-b border-black">
            <div class="text-caption text-muted">보내는 분</div>
            <div>WMS 물류센터</div>
          </div>
          <div class="pt-2 flex justify-between">
            <span>주문번호 <b class="font-mono">{{ order.order_no }}</b></span>
            <span>{{ order.items?.length || 0 }}종 {{ totalQuantity }}개</span>
          </div>
        </div>
      </div>
      <div class="modal-footer print:hidden">
        <button class="btn btn-primary btn-lg" @click="print">인쇄</button>
        <button class="btn btn-lg" @click="$emit('close')">닫기</button>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import Barcode from './Barcode.vue'

const props = defineProps({ order: { type: Object, required: true } })
defineEmits(['close'])

// 운송장 번호를 4자리씩 끊어 읽기 쉽게 보여줍니다.
const formatted = computed(() => props.order.waybill_no.replace(/(\d{4})(?=\d)/g, '$1-'))
const totalQuantity = computed(() => (props.order.items || []).reduce((sum, line) => sum + line.quantity, 0))
const print = () => window.print()
</script>
