<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <form class="modal w-[520px]" @submit.prevent="submit">
      <div class="modal-header">재고 이동 · [{{ item.sku }}] {{ item.name }}</div>
      <div class="modal-content flex flex-col gap-2.5">
        <div class="flex flex-wrap gap-1.5">
          <span v-for="row in item.stocks" :key="row.location" class="px-2 py-0.5 border border-line bg-surface-head">{{ row.location_name }} <b>{{ row.quantity }}</b></span>
          <span v-if="item.unassigned" class="px-2 py-0.5 border border-warning text-warning">위치 미지정 <b>{{ item.unassigned }}</b></span>
          <span v-if="!item.stocks.length && !item.unassigned" class="text-muted">옮길 재고가 없습니다.</span>
        </div>
        <label class="field-label">어디에서
          <select v-model="form.from" class="field w-full mt-1" required>
            <option v-for="row in item.stocks" :key="row.location" :value="row.location">{{ row.location_name }} ({{ row.quantity }}개)</option>
            <option v-if="item.unassigned" value="">위치 미지정 ({{ item.unassigned }}개)</option>
          </select>
        </label>
        <label class="field-label">어디로
          <select v-model="form.to" class="field w-full mt-1" required>
            <option :value="null" disabled>보관 위치 선택</option>
            <option v-for="loc in locations" :key="loc.id" :value="loc.id" :disabled="loc.id === form.from">{{ loc.full_code }}</option>
          </select>
        </label>
        <label v-if="!item.serial_tracked" class="field-label">수량
          <input v-model.number="form.quantity" type="number" min="1" class="field field-num w-[120px] mt-1 block" required />
        </label>
        <label v-else class="field-label">옮길 기기의 시리얼 <span class="font-normal text-muted">(한 줄에 하나씩 스캔)</span>
          <textarea v-model="form.serials" rows="4" class="field w-full mt-1 font-mono" required></textarea>
        </label>
      </div>
      <div class="modal-footer">
        <button type="submit" class="btn btn-primary btn-lg" :disabled="isSaving">이동</button>
        <button type="button" class="btn btn-lg" @click="$emit('close')">닫기</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../stores/toastStore'
import { apiErrorMessage } from '../utils/apiError'

const props = defineProps({ item: { type: Object, required: true } })
const emit = defineEmits(['close', 'moved'])
const toast = useToastStore()
const locations = ref([])
const isSaving = ref(false)
const form = ref({ from: props.item.stocks[0]?.location ?? '', to: null, quantity: 1, serials: '' })

const submit = async () => {
  isSaving.value = true
  try {
    const body = { from: form.value.from || null, to: form.value.to }
    if (props.item.serial_tracked) body.serials = form.value.serials.split(/\s+/).filter(Boolean)
    else body.quantity = form.value.quantity
    const res = await axios.post(`/api/inventory/items/${props.item.id}/move_stock/`, body)
    toast.addToast(res.data.message, 'success')
    emit('moved')
    emit('close')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '재고 이동 중 오류가 발생했습니다.'), 'error', 6000)
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  locations.value = (await axios.get('/api/inventory/locations/')).data.filter(loc => loc.is_active)
})
</script>
