// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// 👇 방금 만든 Tailwind CSS 파일을 불러옵니다!
import './assets/tailwind.css' 

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')