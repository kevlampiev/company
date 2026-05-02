<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="max-w-md w-full bg-white p-8 rounded-lg shadow">
      <h2 class="text-2xl font-bold mb-6 text-center">Вход в систему</h2>
      <form @submit.prevent="handleLogin">
        <div class="mb-4">
          <label class="block text-sm font-medium mb-2">Логин</label>
          <input v-model="username" type="text" class="w-full px-3 py-2 border rounded-lg" required />
        </div>
        <div class="mb-6">
          <label class="block text-sm font-medium mb-2">Пароль</label>
          <input v-model="password" type="password" class="w-full px-3 py-2 border rounded-lg" required />
        </div>
        <button type="submit" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700">
          Войти
        </button>
        <p v-if="error" class="text-red-500 mt-2 text-sm">{{ error }}</p>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const username = ref('')
const password = ref('')
const error = ref('')
const router = useRouter()
const auth = useAuthStore()

async function handleLogin() {
  try {
    await auth.login(username.value, password.value)
    router.push('/dashboard/bots')
  } catch (e) {
    error.value = 'Ошибка входа'
  }
}
</script>
