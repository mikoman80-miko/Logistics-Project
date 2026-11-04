<template>
  <div class="erp-login-bg">
    <div class="erp-login-box">
      <div class="login-header">
        <h1>WMS 물류관리시스템 로그인</h1>
      </div>
      <form @submit.prevent="handleLogin" class="login-body">
        <table class="login-table">
          <tbody>
            <tr>
              <th>사원번호</th>
              <td><input v-model="username" type="text" class="field w-full" required autofocus /></td>
            </tr>
            <tr>
              <th>비밀번호</th>
              <td><input v-model="password" type="password" class="field w-full" required /></td>
            </tr>
          </tbody>
        </table>
        <div v-if="errorMessage" class="alert alert-danger">※ {{ errorMessage }}</div>
        <button type="submit" class="btn btn-primary btn-lg btn-block" :disabled="isLoading">
          {{ isLoading ? '인증 중...' : '시스템 접속' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'; 
import { useAuthStore } from '../stores/auth';

const authStore = useAuthStore(); 

// 개발 PC의 wms-frontend/.env.local에 값이 있을 때만 미리 채웁니다.
const username = ref(import.meta.env.VITE_DEV_LOGIN_ID || '');
const password = ref(import.meta.env.VITE_DEV_LOGIN_PW || '');
const errorMessage = ref(''); 
const isLoading = ref(false);

const handleLogin = async () => {
  isLoading.value = true; 
  errorMessage.value = '';
  const result = await authStore.login(username.value, password.value);
  if (!result.success) errorMessage.value = result.message;
  isLoading.value = false;
};
</script>

<style scoped>
.erp-login-bg { width: 100%; height: 100vh; background: #d3d7dc; display: flex; justify-content: center; align-items: center; }
.erp-login-box { background: #fff; border: 1px solid #555; width: 350px; box-shadow: 2px 2px 5px rgba(0,0,0,0.2); }
.login-header { background: #2f353a; color: #fff; padding: 12px 15px; border-bottom: 2px solid #00529b; }
.login-header h1 { margin: 0; font-size: 14px; font-weight: bold; }
.login-body { padding: 20px; }
.login-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
.login-table th { width: 80px; text-align: left; font-size: 12px; color: #333; padding: 5px 0; }
.login-table td { padding: 5px 0; }
</style>