<template>
  <div class="page">
    <BadgeCardModal v-if="badge" :badge="badge" @close="badge = null" />
    <div class="panel p-2.5">
      <form class="toolbar" @submit.prevent="addUser">
        <label class="field-label">사원번호</label>
        <input v-model="form.username" class="field w-[140px]" maxlength="150" autocomplete="off" required />
        <label class="field-label ml-2">이름</label>
        <input v-model="form.name" class="field w-[120px]" maxlength="150" />
        <label class="field-label ml-2">권한</label>
        <select v-model="form.role" class="field w-[120px]">
          <option value="현장작업자">현장작업자</option>
          <option value="관리자">관리자</option>
        </select>
        <label class="field-label ml-2">첫 비밀번호</label>
        <input v-model="form.password" type="password" class="field w-[160px]" autocomplete="new-password" minlength="8" required />
        <button type="submit" class="btn btn-primary ml-2" :disabled="isSaving">사용자 등록</button>
      </form>
      <div class="mt-1.5 text-caption text-muted">첫 비밀번호는 본인에게 따로 알려 주고, 로그인 후 [비밀번호 변경]으로 바꾸게 안내하세요.</div>
    </div>

    <div class="panel flex-1 overflow-hidden">
      <div class="panel-header">
        <span class="panel-title">사용자 목록</span>
        <span>총 <strong>{{ users.length }}</strong>명</span>
      </div>
      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th width="130">사원번호</th>
              <th>이름</th>
              <th width="120">권한</th>
              <th width="140">마지막 로그인</th>
              <th width="80">상태</th>
              <th width="420">관리</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id" :class="{ 'row-muted': !user.is_active }">
              <td class="text-center font-mono font-bold">{{ user.username }}</td>
              <td>{{ user.name || '-' }} <span v-if="user.id === me" class="text-caption text-primary">(나)</span></td>
              <td class="text-center">
                <select class="field field-sm w-full" :value="user.role" :disabled="user.id === me || user.is_superuser" @change="change(user, { role: $event.target.value })">
                  <option value="관리자">관리자</option>
                  <option value="현장작업자">현장작업자</option>
                </select>
              </td>
              <td class="text-center">{{ user.last_login ? formatDateTime(user.last_login) : '로그인 기록 없음' }}</td>
              <td class="text-center font-bold" :class="user.is_active ? 'text-success' : 'text-muted'">{{ user.is_active ? '사용 중' : '사용 중지' }}</td>
              <td class="text-center whitespace-nowrap">
                <button class="btn btn-sm" :disabled="user.is_superuser && !iAmSuperuser" @click="rename(user)">이름 변경</button>
                <button class="btn btn-sm ml-1" :disabled="user.is_superuser && !iAmSuperuser" @click="resetPassword(user)">비밀번호 초기화</button>
                <button v-if="user.role === '현장작업자' && user.is_active" class="btn btn-sm ml-1" @click="issueBadge(user)">{{ user.has_badge ? '사원증 재발급' : '사원증 발급' }}</button>
                <button v-if="user.id !== me && !user.is_superuser" class="btn btn-sm ml-1" :class="{ 'btn-danger': user.is_active }"
                  @click="toggleActive(user)">{{ user.is_active ? '사용 중지' : '다시 사용' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../../stores/toastStore'
import { useDialogStore } from '../../stores/dialogStore'
import { useAuthStore } from '../../stores/auth'
import { apiErrorMessage } from '../../utils/apiError'
import { formatDateTime } from '../../utils/date'
import BadgeCardModal from '../../components/BadgeCardModal.vue'

const toast = useToastStore()
const dialog = useDialogStore()
const authStore = useAuthStore()
const users = ref([])
const badge = ref(null)
const isSaving = ref(false)
const emptyForm = () => ({ username: '', name: '', role: '현장작업자', password: '' })
const form = ref(emptyForm())

// 로그인한 계정 (자기 권한을 내리거나 사용 중지하지 못하게 합니다)
const meUser = computed(() => users.value.find(u => u.username === authStore.user?.name))
const me = computed(() => meUser.value?.id)
const iAmSuperuser = computed(() => !!meUser.value?.is_superuser)

const load = async () => {
  users.value = (await axios.get('/api/inventory/users/')).data
}

const addUser = async () => {
  isSaving.value = true
  try {
    await axios.post('/api/inventory/users/', form.value)
    toast.addToast(`[${form.value.username}] 사용자를 등록했습니다.`, 'success')
    form.value = emptyForm()
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '사용자 등록 중 오류가 발생했습니다.'), 'error', 6000)
  } finally {
    isSaving.value = false
  }
}

const change = async (user, body, message = '변경했습니다.') => {
  try {
    await axios.patch(`/api/inventory/users/${user.id}/`, body)
    toast.addToast(`[${user.username}] ${message}`, 'success')
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '변경 중 오류가 발생했습니다.'), 'error', 6000)
  }
  await load()
}

const rename = async (user) => {
  const name = await dialog.prompt(`[${user.username}] 새 이름을 입력하세요.`, { title: '이름 변경', value: user.name, okText: '변경', maxlength: 150 })
  if (name !== null) await change(user, { name }, '이름을 바꿨습니다.')
}

const toggleActive = async (user) => {
  if (user.is_active && !(await dialog.confirm(`[${user.username}] 계정을 사용 중지합니다.\n이 계정으로는 로그인할 수 없고, 처리 기록은 그대로 남습니다.`, { danger: true, okText: '사용 중지' }))) return
  await change(user, { is_active: !user.is_active }, user.is_active ? '사용 중지했습니다.' : '다시 사용합니다.')
}

const resetPassword = async (user) => {
  const password = await dialog.prompt(`[${user.username}] 새 비밀번호를 입력하세요. (8자 이상)`, { title: '비밀번호 초기화', okText: '초기화', maxlength: 128 })
  if (password === null) return
  try {
    const res = await axios.post(`/api/inventory/users/${user.id}/reset_password/`, { password })
    toast.addToast(res.data.message, 'success', 6000)
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '비밀번호 초기화 중 오류가 발생했습니다.'), 'error', 6000)
  }
}

const issueBadge = async (user) => {
  const message = user.has_badge
    ? `[${user.username}] 사원증을 다시 발급합니다.
지금 쓰는 사원증은 더 이상 쓸 수 없습니다.`
    : `[${user.username}] 사원증을 발급합니다. 발급 후 바로 인쇄하세요.`
  if (!(await dialog.confirm(message, { title: '사원증 발급', okText: '발급' }))) return
  try {
    const res = await axios.post(`/api/inventory/users/${user.id}/issue_badge/`)
    toast.addToast(res.data.message, 'success', 6000)
    badge.value = res.data
    await load()
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '사원증 발급 중 오류가 발생했습니다.'), 'error', 6000)
  }
}

onActivated(load)
</script>
