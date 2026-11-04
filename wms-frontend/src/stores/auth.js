import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useToastStore } from './toastStore'

export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref(!!localStorage.getItem('access_token'))
  const user = ref(localStorage.getItem('username') ? {
    name: localStorage.getItem('username'),
    role: localStorage.getItem('user_role') || '현장작업자'
  } : null)
  const router = useRouter()

  if (isAuthenticated.value) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${localStorage.getItem('access_token')}`
  }

  // 로그아웃 함수 위로 끌어올림 (인터셉터에서 사용)
  const logout = () => {
    isAuthenticated.value = false
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('username')
    localStorage.removeItem('user_role')
    delete axios.defaults.headers.common['Authorization']
    router.push('/login')
  }

  // 동시에 여러 요청이 401을 받아도 토큰 갱신은 한 번만 합니다.
  let refreshing = null
  const refreshAccessToken = () => {
    if (!refreshing) {
      refreshing = axios.post('/api/token/refresh/', { refresh: localStorage.getItem('refresh_token') })
        .then((res) => {
          const newToken = res.data.access
          localStorage.setItem('access_token', newToken)
          axios.defaults.headers.common['Authorization'] = `Bearer ${newToken}`
          return newToken
        })
        .finally(() => { refreshing = null })
    }
    return refreshing
  }

  // 🌟 NEW: 토큰 자동 갱신(Refresh) 보안 로직
  axios.interceptors.response.use(
    (response) => response,
    async (error) => {
      const originalRequest = error.config
      // 조회 실패는 화면마다 처리하지 않으므로 여기서 한 번에 알립니다.
      if (originalRequest?.method === 'get' && (!error.response || error.response.status >= 500)) {
        useToastStore().addToast('서버에서 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.', 'error')
      }
      // 로그인/갱신 요청 자체의 실패는 세션 만료가 아니므로 그대로 돌려줍니다.
      const isTokenRequest = originalRequest?.url?.startsWith('/api/token/')
      // 401 에러이고, 아직 재시도하지 않은 요청이라면
      if (error.response && error.response.status === 401 && !originalRequest._retry && !isTokenRequest) {
        originalRequest._retry = true
        try {
          if (localStorage.getItem('refresh_token')) {
            const newToken = await refreshAccessToken()
            originalRequest.headers['Authorization'] = `Bearer ${newToken}`
            return axios(originalRequest) // 🌟 중단된 요청 재실행! (사용자는 에러를 모름)
          }
        } catch (refreshError) {
          console.error('토큰 갱신 실패')
        }
        if (isAuthenticated.value) {
          alert('보안을 위해 로그인 세션이 만료되었습니다. 다시 로그인해 주세요.')
          logout()
        }
      }
      return Promise.reject(error)
    }
  )

  // 로그인 결과(토큰과 권한)를 저장하고 권한별 첫 화면으로 보냅니다.
  const startSession = (data, username) => {
    // 권한은 서버의 계정 정보를 따릅니다. (메뉴 표시용이며, 실제 차단은 서버가 합니다)
    const role = data.role || '현장작업자'
    localStorage.setItem('access_token', data.access)
    if (data.refresh) localStorage.setItem('refresh_token', data.refresh)
    localStorage.setItem('username', username)
    localStorage.setItem('user_role', role)
    axios.defaults.headers.common['Authorization'] = `Bearer ${data.access}`
    isAuthenticated.value = true
    user.value = { name: username, role }
    router.push(role === '관리자' ? '/today' : '/work')
  }

  // 사원증 바코드로 로그인하거나, 현장 PC에서 작업자를 바꿉니다. (현장작업자 계정만)
  const loginWithBadge = async (code) => {
    try {
      const { data } = await axios.post('/api/token/badge/', { code })
      startSession(data, data.username)
      return { success: true, name: data.name || data.username }
    } catch (error) {
      const status = error.response?.status
      if (status === 429) return { success: false, message: '시도가 너무 많습니다. 잠시 후 다시 스캔하세요.' }
      if (status === 401 || status === 400) return { success: false, message: '등록되지 않았거나 쓸 수 없는 사원증입니다.' }
      return { success: false, message: '서버에 연결할 수 없습니다.' }
    }
  }

  const login = async (username, password) => {
    try {
      const response = await axios.post('/api/token/', { username, password })
      startSession(response.data, username)
      return { success: true }
    } catch (error) {
      console.error('로그인 실패:', error)
      const status = error.response?.status
      if (status === 429) return { success: false, message: '로그인 시도가 너무 많습니다. 잠시 후 다시 시도하십시오.' }
      if (status === 400 || status === 401) return { success: false, message: '사원번호 또는 비밀번호를 확인하십시오.' }
      return { success: false, message: '서버에 연결할 수 없습니다. 잠시 후 다시 시도하십시오.' }
    }
  }

  return { isAuthenticated, user, login, logout, loginWithBadge }
})
