<template>
  <div class="modal-overlay z-[2400]" @keydown.esc="$emit('close')">
    <form class="work-dialog" @submit.prevent="submit">
      <div class="text-3xl font-bold">작업자 전환</div>
      <div class="text-2xl text-muted">다음 작업자의 사원증을 스캔하세요. 이후 처리는 그 사람 이름으로 기록됩니다.</div>
      <input ref="inputRef" v-model="code" type="password" class="work-scan" autocomplete="off" spellcheck="false" placeholder="사원증 스캔" />
      <div v-if="error" class="text-2xl font-bold text-danger">{{ error }}</div>
      <div class="grid grid-cols-2 gap-4">
        <button type="submit" class="work-btn work-btn-primary" :disabled="isBusy">확인 (Enter)</button>
        <button type="button" class="work-btn" @click="$emit('close')">닫기 (Esc)</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { useDialogStore } from '../../stores/dialogStore'
import { useToastStore } from '../../stores/toastStore'

// 사원증 코드는 화면에 그대로 보이지 않게 password 칸으로 받습니다.
const emit = defineEmits(['close'])
const authStore = useAuthStore()
const dialog = useDialogStore()
const toast = useToastStore()
const code = ref('')
const error = ref('')
const isBusy = ref(false)
const inputRef = ref(null)

const submit = async () => {
  const value = code.value.trim()
  code.value = ''
  if (!value) return
  isBusy.value = true
  const result = await authStore.loginWithBadge(value)
  isBusy.value = false
  if (!result.success) {
    error.value = result.message
    inputRef.value?.focus()
    return
  }
  toast.addToast(`${result.name} 님으로 바뀌었습니다.`, 'success')
  emit('close')
}

onMounted(() => {
  dialog.block()
  inputRef.value?.focus()
})
onUnmounted(dialog.unblock)
</script>
