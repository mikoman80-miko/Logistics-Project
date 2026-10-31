<template>
  <div class="page">
    <div class="panel p-2.5">
      <form class="toolbar" @submit.prevent="addSupplier">
        <label class="field-label">거래처명</label>
        <input v-model="form.name" class="field w-[200px]" maxlength="100" required />
        <label class="field-label ml-2">담당자</label>
        <input v-model="form.contact_person" class="field w-[120px]" maxlength="50" />
        <label class="field-label ml-2">연락처</label>
        <input v-model="form.phone" class="field w-[140px]" maxlength="20" />
        <button type="submit" class="btn btn-primary ml-2">거래처 등록</button>
      </form>
    </div>

    <div class="panel flex-1 overflow-hidden">
      <div class="panel-header">
        <span class="panel-title">거래처 목록</span>
        <span>총 <strong>{{ suppliers.length }}</strong>곳</span>
      </div>
      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th>거래처명</th>
              <th width="160">담당자</th>
              <th width="180">연락처</th>
              <th width="120">상태</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="suppliers.length === 0" class="empty-row">
              <td colspan="4">등록된 거래처가 없습니다. 위에서 거래처를 등록하세요.</td>
            </tr>
            <tr v-for="supplier in suppliers" :key="supplier.id" :class="{ 'row-muted': !supplier.is_active }">
              <td class="font-bold">{{ supplier.name }}</td>
              <td class="text-center">{{ supplier.contact_person || '-' }}</td>
              <td class="text-center">{{ supplier.phone || '-' }}</td>
              <td class="text-center">
                <button class="btn btn-sm" @click="toggleActive(supplier)">{{ supplier.is_active ? '사용 중지' : '다시 사용' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onActivated, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore'
import { apiErrorMessage } from '../../utils/apiError'

const toast = useToastStore()
const suppliers = ref([])
const emptyForm = () => ({ name: '', contact_person: '', phone: '' })
const form = ref(emptyForm())

const load = async () => {
  suppliers.value = (await axios.get('/api/inventory/suppliers/')).data
}

const addSupplier = async () => {
  try {
    await axios.post('/api/inventory/suppliers/', form.value)
    toast.addToast('거래처를 등록했습니다.', 'success')
    form.value = emptyForm()
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '거래처 등록 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const toggleActive = async (supplier) => {
  try {
    await axios.patch(`/api/inventory/suppliers/${supplier.id}/`, { is_active: !supplier.is_active })
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '거래처 변경 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

onActivated(load)
</script>
