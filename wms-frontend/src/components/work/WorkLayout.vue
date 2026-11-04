<template>
  <div class="work-screen">
    <header class="work-header">
      <div class="flex items-center gap-6">
        <button v-if="showHome" class="work-header-btn" @click="router.push('/work')">◀ 처음으로</button>
        <h1 class="m-0 text-4xl font-bold">{{ title }}</h1>
      </div>
      <div class="flex items-center gap-4 text-2xl">
        <span>{{ authStore.user?.name }}</span>
        <button v-if="isAdmin" class="work-header-btn" @click="router.push('/today')">관리 화면</button>
        <button class="work-header-btn" @click="switchOpen = true">작업자 전환</button>
        <button class="work-header-btn" @click="passwordOpen = true">비밀번호</button>
        <button class="work-header-btn" @click="authStore.logout()">로그아웃</button>
      </div>
    </header>

    <main class="work-body">
      <slot />
    </main>

    <PasswordChangeModal v-if="passwordOpen" large @close="passwordOpen = false" />
    <BadgeSwitchDialog v-if="switchOpen" @close="switchOpen = false" />

    <div v-if="feedback?.type === 'ok'" class="work-toast-ok">✔ {{ feedback.message }}</div>
    <div v-if="feedback?.type === 'error'" class="work-error" @click="dismiss">
      <div class="text-[110px] leading-none">✖</div>
      <div class="text-6xl font-bold leading-snug text-center max-w-[1400px] break-keep">{{ feedback.message }}</div>
      <button class="work-error-btn">확인 (스페이스바)</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useWorkFeedback } from '../../composables/useWorkFeedback'
import PasswordChangeModal from '../PasswordChangeModal.vue'
import BadgeSwitchDialog from './BadgeSwitchDialog.vue'

defineProps({
  title: { type: String, required: true },
  showHome: { type: Boolean, default: true },
})

const router = useRouter()
const authStore = useAuthStore()
const { feedback, dismiss } = useWorkFeedback()
const isAdmin = computed(() => authStore.user?.role === '관리자')
const passwordOpen = ref(false)
const switchOpen = ref(false)

// 스캐너는 끝에 Enter를 보내므로, 오류 확인은 Enter가 아닌 스페이스바로 받습니다.
const onKeydown = (event) => {
  if (feedback.value?.type !== 'error') return
  event.preventDefault()
  if (event.code === 'Space') dismiss()
}

onMounted(() => window.addEventListener('keydown', onKeydown, true))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown, true)
  dismiss()
})
</script>
