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

      <div class="p-4 border-t flex gap-2 items-center">
        <input type="file" ref="fileInput" @change="handleFileUpload" class="hidden" multiple />
        <button @click="onFileButtonClick" class="px-4 py-2 border rounded hover:bg-gray-50" title="Прикрепить файл">
          📎
        </button>
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
const files = ref([])
const fileInput = ref(null)

function onFileButtonClick() {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

function handleFileUpload(event) {
  var newFiles = Array.from(event.target.files)
  files.value = files.value.concat(newFiles)
  event.target.value = ''
}

async function sendMessage() {
  if (!selectedBot.value || !query.value.trim()) return

  var userMsg = query.value
  var fileNames = files.value.map(function(f) { return f.name })
  messages.value.push({
    role: 'user',
    content: userMsg + (fileNames.length ? ' [Files: ' + fileNames.join(', ') + ']' : '')
  })
  query.value = ''
  var currentFiles = files.value.slice()
  files.value = []

  try {
    var formData = new FormData()
    formData.append('bot_id', selectedBot.value)
    formData.append('query', userMsg)
    formData.append('thread_id', threadId.value)
    currentFiles.forEach(function(file) {
      formData.append('files', file, file.name)
    })

    var response = await api.post('/chat', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    messages.value.push({ role: 'assistant', content: response.data.answer })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: 'Ошибка отправки сообщения' })
  }
}

async function loadBots() {
  var response = await api.get('/bots')
  bots.value = response.data.filter(function(b) { return b.is_active })
  if (route.query.bot) {
    selectedBot.value = Number(route.query.bot)
  }
}

onMounted(loadBots)
</script>
