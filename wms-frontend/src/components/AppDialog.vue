<template>
  <div v-if="d" class="modal-overlay z-[2500] print:hidden" @keydown.esc.prevent="cancel">
    <form class="modal" :class="d.large ? 'w-[760px]' : 'w-[420px]'" role="dialog" aria-modal="true" @submit.prevent="ok">
      <div class="modal-header" :class="{ 'bg-danger!': d.danger, 'text-3xl! py-4! px-6!': d.large }">{{ d.title || defaultTitle }}</div>
      <div class="modal-content whitespace-pre-line" :class="d.large ? 'text-3xl leading-snug p-8!' : ''">
        {{ d.message }}
        <input v-if="d.kind === 'prompt'" ref="inputRef" v-model="value" class="field w-full mt-2.5 whitespace-normal"
          :placeholder="d.placeholder || ''" :maxlength="d.maxlength || 100" />
        <select v-if="d.kind === 'select'" ref="inputRef" v-model="value" class="field field-lg w-full mt-2.5">
          <option :value="null" disabled>선택하세요</option>
          <option v-for="option in d.options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </div>
      <div class="modal-footer">
        <button ref="okRef" type="submit" :class="okClass"
          :disabled="(d.kind === 'prompt' && !value?.trim()) || (d.kind === 'select' && value === null)">
          {{ d.okText || '확인' }}
        </button>
        <button v-if="d.kind !== 'alert'" ref="cancelRef" type="button" :class="d.large ? 'work-btn w-72' : 'btn btn-lg'" @click="cancel">
          {{ d.cancelText || '취소' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useDialogStore } from '../stores/dialogStore'

const store = useDialogStore()
const d = computed(() => store.current)
const value = ref(null)
const inputRef = ref(null)
const okRef = ref(null)
const cancelRef = ref(null)

// 현장 화면용(large)은 장갑을 껴도 누르기 쉬운 큰 버튼을 씁니다.
const okClass = computed(() => d.value.large
  ? ['work-btn w-72', d.value.danger ? 'work-btn-danger' : 'work-btn-primary']
  : ['btn btn-lg', d.value.danger ? 'btn-danger' : 'btn-primary'])
const defaultTitle = computed(() => ({ alert: '알림', confirm: '확인', prompt: '입력', select: '선택' }[d.value?.kind]))

const ok = () => {
  const { kind } = d.value
  if (kind === 'prompt') return store.close(value.value?.trim() || null)
  if (kind === 'select') return store.close(value.value)
  store.close(kind === 'confirm' ? true : undefined)
}
const cancel = () => store.close(d.value?.kind === 'confirm' ? false : d.value?.kind === 'alert' ? undefined : null)

// 열릴 때 입력칸이나 기본 버튼에 커서를 둡니다. Enter는 그 버튼을, Esc는 취소를 누릅니다.
watch(d, async (current) => {
  if (!current) return
  value.value = current.kind === 'prompt' ? (current.value || '') : current.kind === 'select' ? (current.value ?? null) : null
  await nextTick()
  if (inputRef.value) inputRef.value.focus()
  else (current.focusCancel ? cancelRef.value : okRef.value)?.focus()
})
</script>
