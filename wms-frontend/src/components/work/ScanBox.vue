<template>
  <form @submit.prevent="submit">
    <input ref="inputRef" v-model="value" class="work-scan" type="text" :placeholder="placeholder"
      :disabled="locked" autocomplete="off" spellcheck="false" @blur="keepFocus" />
  </form>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import { useDialogStore } from '../../stores/dialogStore'

const props = defineProps({
  placeholder: { type: String, default: '스캔 대기 중...' },
  paused: { type: Boolean, default: false },
})
const emit = defineEmits(['scan'])

const { feedback, fail } = useWorkFeedback()
const inputRef = ref(null)
const value = ref('')
const dialog = useDialogStore()
// 오류 화면이나 확인 팝업이 떠 있으면 스캔을 받지 않고, 커서도 가져오지 않습니다.
const locked = computed(() => props.paused || feedback.value?.type === 'error' || !!dialog.current || dialog.blockers > 0)

const focus = () => { if (!locked.value) inputRef.value?.focus() }

// 마우스를 눌러도 다음 스캔을 놓치지 않도록 입력창으로 돌아옵니다.
let timer = null
const keepFocus = () => {
  clearTimeout(timer)
  timer = setTimeout(focus, 150)
}

const submit = () => {
  const code = value.value.trim()
  value.value = ''
  if (!code) return
  // 한글 입력 상태로 스캔하면 바코드가 한글로 들어옵니다.
  if (/[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(code)) {
    fail('한글로 입력되었습니다. 키보드의 [한/영] 키를 눌러 영문으로 바꾼 뒤 다시 스캔하세요.')
    return
  }
  emit('scan', code)
}

watch(locked, async (isLocked) => {
  if (!isLocked) {
    await nextTick()
    focus()
  }
})

onMounted(focus)
onBeforeUnmount(() => clearTimeout(timer))
</script>
