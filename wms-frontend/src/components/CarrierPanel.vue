<template>
  <!-- 주문·반품 상세의 택배 정보: 운송장, 현재 단계, 오류, 단계 이력 -->
  <div class="border border-line p-2.5 mb-2.5">
    <div class="flex flex-wrap items-center gap-2">
      <span class="font-bold">{{ title }}</span>
      <template v-if="record.waybill_no">
        <span>{{ record.carrier_name }}</span>
        <a v-if="record.tracking_url" :href="record.tracking_url" target="_blank" rel="noopener" class="font-mono text-primary underline">{{ record.waybill_no }}</a>
        <span class="font-bold" :class="statusColor">{{ record.carrier_status || '-' }}</span>
      </template>
      <span v-else class="text-muted">운송장 없음</span>
      <span class="flex-1"></span>
      <slot />
    </div>
    <div v-if="record.carrier_error" class="alert alert-danger mt-2 mb-0">{{ record.carrier_error }}</div>
    <div v-if="record.address" class="mt-1.5 text-muted">
      {{ record.contact_name }} · {{ record.contact_phone }} · ({{ record.zipcode }}) {{ record.address }} {{ record.address_detail }}
    </div>
    <ol v-if="record.carrier_events?.length" class="flex flex-wrap gap-1 m-0 mt-2 p-0 list-none">
      <li v-for="(event, i) in record.carrier_events" :key="i" class="px-2 py-0.5 border border-line bg-surface-head text-caption"
        :title="event.location">
        <b>{{ event.status }}</b> {{ formatDateTime(event.occurred_at) }}
      </li>
    </ol>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDateTime } from '../utils/date'

const props = defineProps({
  record: { type: Object, required: true },
  title: { type: String, default: '택배' },
})

const DONE = ['배송완료', '회수완료']
const statusColor = computed(() => {
  const s = props.record.carrier_status
  if (DONE.includes(s)) return 'text-success'
  if (s === '취소') return 'text-muted'
  return 'text-primary'
})
</script>
