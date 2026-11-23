<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal w-[760px]">
      <div class="modal-header">시리얼 이력 <span class="font-mono">{{ serialNumber }}</span></div>
      <div class="modal-content">
        <div v-if="loading" class="text-center text-muted p-6">불러오는 중...</div>
        <template v-else-if="data">
          <div class="flex flex-wrap gap-x-4 gap-y-1 mb-3">
            <span><b>{{ data.serial.item_name }}</b> <span class="font-mono text-muted">{{ data.serial.item_sku }}</span></span>
            <span>현재 <b>{{ data.serial.status }}</b> · {{ data.serial.quality }}</span>
          </div>
          <div v-if="data.events.length === 0" class="alert alert-info">기록이 없습니다.</div>
          <ol class="m-0 p-0 list-none border-l-2 border-line ml-2">
            <li v-for="(event, i) in data.events" :key="i" class="relative pl-5 pb-3">
              <span class="absolute -left-[7px] top-1 w-3 h-3 rounded-full border-2 border-white" :class="dotColor(event.kind)"></span>
              <div class="flex flex-wrap items-baseline gap-x-2">
                <b>{{ event.title }}</b>
                <span class="text-caption text-muted">{{ event.time ? formatDateTime(event.time) : '진행 중' }}</span>
                <span v-if="event.user" class="text-caption text-muted">· {{ event.user }}</span>
              </div>
              <div v-if="event.detail" class="text-muted">{{ event.detail }}</div>
              <div v-if="event.waybill_no" class="text-caption">
                운송장
                <a v-if="event.tracking_url" :href="event.tracking_url" target="_blank" rel="noopener" class="font-mono text-primary underline">{{ event.waybill_no }}</a>
                <span v-else class="font-mono">{{ event.waybill_no }}</span>
                <span v-if="event.carrier_status"> · {{ event.carrier_status }}</span>
              </div>
            </li>
          </ol>
        </template>
      </div>
      <div class="modal-footer">
        <button class="btn btn-lg" @click="$emit('close')">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../stores/toastStore'
import { apiErrorMessage } from '../utils/apiError'
import { formatDateTime } from '../utils/date'

const props = defineProps({
  serialId: { type: Number, required: true },
  serialNumber: { type: String, default: '' },
})
const emit = defineEmits(['close'])
const toast = useToastStore()
const data = ref(null)
const loading = ref(true)

const dotColor = (kind) => ({ in: 'bg-success', out: 'bg-primary', return: 'bg-warning' }[kind] || 'bg-line-strong')

onMounted(async () => {
  try {
    data.value = (await axios.get(`/api/inventory/serials/${props.serialId}/history/`)).data
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '이력을 불러오지 못했습니다.'), 'error', 5000)
    emit('close')
  } finally {
    loading.value = false
  }
})
</script>
