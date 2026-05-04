<template>
  <div class="min-h-screen bg-gray-50 p-8">
    <div class="max-w-4xl mx-auto bg-white rounded-lg shadow">
      <div class="p-4 border-b flex items-center gap-4">
        <button @click="router.push('/dashboard/bots')" class="text-blue-600 hover:underline">&larr; К списку ботов</button>
        <select v-model="selectedBot" class="px-3 py-2 border rounded">
          <option :value="null">Выберите бота</option>
          <option v-for="bot in bots" :key="bot.id" :value="bot.id">{{ bot.name }}</option>
        </select>
      </div>

      <div class="h-96 overflow-y-auto p-4 space-y-4">
        <div v-for="(msg, i) in messages" :key="i" :class="msg.role === 'user' ? 'text-right' : 'text-left'">
          <div :class="msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100'" class="inline-block px-4 py-2 rounded-lg max-w-lg">
            {{ msg.content }}
          </div>
        </div>
      </div>

      <div class="p-4 border-t flex gap-2">
        <input v-model="query" @keyup.enter="sendMessage" class="flex-1 px-3 py-2 border rounded-lg" placeholder="Введите сообщение..." />
        <button @click="sendMessage" class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">Отправить</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api/auth'

const route = useRoute()
const router = useRouter()

const bots = ref([])
const selectedBot = ref(null)
const query = ref('')
const messages = ref([])
const threadId = ref('thread_' + Date.now())

async function loadBots() {
  const { data } = await api.get('/bots')
  bots.value = data.filter(b => b.is_active)
  if (route.query.bot) {
    selectedBot.value = Number(route.query.bot)
  }
}

async function sendMessage() {
  if (!selectedBot.value || !query.value.trim()) return

  const userMsg = query.value
  messages.value.push({ role: 'user', content: userMsg })
  query.value = ''

  try {
    const { data } = await api.post('/chat', {
      bot_id: selectedBot.value,
      query: userMsg,
      thread_id: threadId.value
    })
    messages.value.push({ role: 'assistant', content: data.answer })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: 'Ошибка отправки сообщения' })
  }
}

onMounted(loadBots)
</script>
