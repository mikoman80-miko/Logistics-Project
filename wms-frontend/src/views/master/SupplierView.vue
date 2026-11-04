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
        <label class="field-label ml-2">이메일</label>
        <input v-model="form.email" type="email" class="field w-[200px]" maxlength="254" />
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
              <th width="140">담당자</th>
              <th width="160">연락처</th>
              <th width="220">이메일</th>
              <th width="170">관리</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="suppliers.length === 0" class="empty-row">
              <td colspan="5">등록된 거래처가 없습니다. 위에서 거래처를 등록하세요.</td>
            </tr>
            <tr v-for="supplier in suppliers" :key="supplier.id" :class="{ 'row-muted': !supplier.is_active }">
              <td class="font-bold">{{ supplier.name }}</td>
              <td class="text-center">{{ supplier.contact_person || '-' }}</td>
              <td class="text-center">{{ supplier.phone || '-' }}</td>
              <td class="truncate">{{ supplier.email || '-' }}</td>
              <td class="text-center">
                <button class="btn btn-sm" @click="openEdit(supplier)">수정</button>
                <button class="btn btn-sm ml-1" @click="toggleActive(supplier)">{{ supplier.is_active ? '사용 중지' : '다시 사용' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="editForm" class="modal-overlay" @click.self="editForm = null">
      <form class="modal w-[450px]" @submit.prevent="submitEdit">
        <div class="modal-header">거래처 수정</div>
        <div class="modal-content flex flex-col gap-2.5">
          <label class="field-label">거래처명
            <input v-model="editForm.name" class="field w-full mt-1" maxlength="100" required />
          </label>
          <label class="field-label">담당자
            <input v-model="editForm.contact_person" class="field w-full mt-1" maxlength="50" />
          </label>
          <label class="field-label">연락처
            <input v-model="editForm.phone" class="field w-full mt-1" maxlength="20" />
          </label>
          <label class="field-label">이메일
            <input v-model="editForm.email" type="email" class="field w-full mt-1" maxlength="254" />
          </label>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg">저장</button>
          <button type="button" class="btn btn-lg" @click="editForm = null">취소</button>
        </div>
      </form>
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
const emptyForm = () => ({ name: '', contact_person: '', phone: '', email: '' })
const form = ref(emptyForm())
const editForm = ref(null)

// 빈 칸은 빈 문자열 대신 비워 둔 값(null)으로 저장합니다. (이메일 형식 검사 오류 방지)
const clean = (data) => Object.fromEntries(Object.entries(data).map(([key, value]) => [key, typeof value === 'string' && !value.trim() ? null : value]))

const load = async () => {
  suppliers.value = (await axios.get('/api/inventory/suppliers/')).data
}

const addSupplier = async () => {
  try {
    await axios.post('/api/inventory/suppliers/', clean(form.value))
    toast.addToast('거래처를 등록했습니다.', 'success')
    form.value = emptyForm()
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '거래처 등록 중 오류가 발생했습니다.'), 'error', 5000)
  }
}

const openEdit = (supplier) => {
  const { id, name, contact_person, phone, email } = supplier
  editForm.value = { id, name, contact_person: contact_person || '', phone: phone || '', email: email || '' }
}

const submitEdit = async () => {
  const { id, ...change } = editForm.value
  try {
    await axios.patch(`/api/inventory/suppliers/${id}/`, clean(change))
    toast.addToast('거래처를 수정했습니다.', 'success')
    editForm.value = null
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '거래처 수정 중 오류가 발생했습니다.'), 'error', 5000)
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
