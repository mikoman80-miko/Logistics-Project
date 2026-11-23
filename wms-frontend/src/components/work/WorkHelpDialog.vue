<template>
  <!-- 현장 화면 도움말: F1 또는 [도움말]로 열고 Esc로 닫습니다. -->
  <div class="modal-overlay z-[2300]" @click.self="$emit('close')">
    <div class="work-dialog w-[1200px]! max-h-[90vh] overflow-y-auto" role="dialog" aria-label="도움말">
      <div class="text-4xl font-bold">도움말 · {{ help.title }}</div>
      <section>
        <div class="text-3xl font-bold text-primary mb-3">순서</div>
        <ol class="m-0 pl-10 flex flex-col gap-2 text-3xl leading-snug">
          <li v-for="step in help.steps" :key="step">{{ step }}</li>
        </ol>
      </section>
      <section v-if="help.problems.length">
        <div class="text-3xl font-bold text-danger mb-3">이럴 때는</div>
        <div v-for="item in help.problems" :key="item.problem" class="py-3 border-t-2 border-line">
          <div class="text-3xl font-bold">{{ item.problem }}</div>
          <div class="text-2xl mt-1 leading-snug">→ {{ item.fix }}</div>
        </div>
      </section>
      <button ref="closeRef" class="work-btn work-btn-primary" @click="$emit('close')">닫기 (Esc)</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useDialogStore } from '../../stores/dialogStore'
import { helpFor } from '../../utils/workHelp'

const emit = defineEmits(['close'])
const route = useRoute()
const dialog = useDialogStore()
const help = computed(() => helpFor(route.name))
const closeRef = ref(null)

const onKeydown = (event) => {
  if (event.key === 'Escape') emit('close')
}

// 열려 있는 동안 스캔 칸이 포커스를 가져가지 않게 합니다.
onMounted(() => {
  dialog.block()
  closeRef.value?.focus({ preventScroll: true })  // 맨 위(순서)부터 보이게
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  dialog.unblock()
  window.removeEventListener('keydown', onKeydown)
})
</script>
