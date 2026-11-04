<template>
  <div class="modal-overlay z-[2400]" @keydown.esc="$emit('close')">
    <form class="modal" :class="large ? 'w-[760px] text-2xl' : 'w-[420px]'" @submit.prevent="submit">
      <div class="modal-header" :class="{ 'text-3xl! py-4! px-6!': large }">비밀번호 변경</div>
      <div class="modal-content flex flex-col gap-2.5" :class="{ 'p-8!': large }">
        <label class="field-label" :class="{ 'text-2xl!': large }">현재 비밀번호
          <input ref="firstRef" v-model="form.current" type="password" autocomplete="current-password" :class="inputClass" required />
        </label>
        <label class="field-label" :class="{ 'text-2xl!': large }">새 비밀번호
          <input v-model="form.next" type="password" autocomplete="new-password" minlength="8" :class="inputClass" required />
        </label>
        <label class="field-label" :class="{ 'text-2xl!': large }">새 비밀번호 확인
          <input v-model="form.confirm" type="password" autocomplete="new-password" :class="inputClass" required />
        </label>
        <div class="text-muted" :class="large ? 'text-xl' : 'text-caption'">8자 이상, 숫자만으로 된 비밀번호나 흔한 비밀번호는 쓸 수 없습니다.</div>
        <div v-if="error" class="alert alert-danger m-0">{{ error }}</div>
      </div>
      <div class="modal-footer">
        <button type="submit" :class="large ? 'work-btn work-btn-primary' : 'btn btn-primary btn-lg'" :disabled="isSaving">변경</button>
        <button type="button" :class="large ? 'work-btn' : 'btn btn-lg'" @click="$emit('close')">취소</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { useToastStore } from '../stores/toastStore'
import { useDialogStore } from '../stores/dialogStore'
import { apiErrorMessage } from '../utils/apiError'

// large: 현장 작업 화면용 큰 글씨
const props = defineProps({ large: { type: Boolean, default: false } })
const emit = defineEmits(['close'])
const toast = useToastStore()
const form = ref({ current: '', next: '', confirm: '' })
const error = ref('')
const isSaving = ref(false)
const firstRef = ref(null)
const inputClass = computed(() => ['field w-full mt-1', props.large ? 'field-lg text-2xl! h-14!' : ''])

const submit = async () => {
  error.value = ''
  if (form.value.next !== form.value.confirm) {
    error.value = '새 비밀번호와 확인이 다릅니다.'
    return
  }
  isSaving.value = true
  try {
    const res = await axios.post('/api/account/password/', { current_password: form.value.current, new_password: form.value.next })
    toast.addToast(res.data.message, 'success', 5000)
    emit('close')
  } catch (err) {
    error.value = err.response?.status === 429 ? '시도가 너무 많습니다. 잠시 후 다시 해 주세요.' : apiErrorMessage(err, '비밀번호를 바꾸지 못했습니다.')
  } finally {
    isSaving.value = false
  }
}

const dialog = useDialogStore()
onMounted(() => {
  dialog.block()
  firstRef.value?.focus()
})
onUnmounted(dialog.unblock)
</script>
