<template>
  <div class="min-h-screen bg-gray-50 p-8">
    <div class="max-w-6xl mx-auto">
      <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold">Управление ботами</h1>
        <div class="flex gap-2">
          <select ref="demoSelect" @change="addDemoBot($event.target.value)" class="px-4 py-2 border rounded-lg">
            <option value="">+ Добавить демо-бота</option>
            <option value="lawyer">Юрист (DeepSeek)</option>
            <option value="accountant">Бухгалтер (Qwen)</option>
            <option value="economist">Экономист (GPT-4)</option>
            <option value="manager">Менеджер (Claude)</option>
          </select>
          <button @click="showModal = true" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
            + Создать вручную
          </button>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-100">
            <tr>
              <th class="px-4 py-3 text-left">Имя</th>
              <th class="px-4 py-3 text-left">Область</th>
              <th class="px-4 py-3 text-left">Провайдер</th>
              <th class="px-4 py-3 text-left">Модель</th>
              <th class="px-4 py-3 text-left">Статус</th>
              <th class="px-4 py-3 text-left">Связь</th>
              <th class="px-4 py-3 text-left">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bot in bots" :key="bot.id" class="border-t" :class="bot.connection_error ? 'bg-gray-100 opacity-60' : ''">
              <td class="px-4 py-3">{{ bot.name }}</td>
              <td class="px-4 py-3">{{ bot.area }}</td>
              <td class="px-4 py-3">{{ bot.provider }}</td>
              <td class="px-4 py-3">{{ bot.model }}</td>
              <td class="px-4 py-3">
                <span :class="bot.is_active ? 'text-green-600' : 'text-red-600'">
                  {{ bot.is_active ? 'Вкл' : 'Выкл' }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="bot.connection_error" class="text-red-600 text-sm">Ошибка</span>
                <span v-else-if="bot.connection_tested" class="text-green-600 text-sm">OK</span>
                <span v-else class="text-gray-400 text-sm">не пров.</span>
              </td>
              <td class="px-4 py-3 space-x-2">
                <button @click="editBot(bot)" class="text-blue-600 hover:underline">Ред.</button>
                <button @click="generateKey(bot)" class="text-green-600 hover:underline">Ключ</button>
                <button @click="openChat(bot.id)" class="text-purple-600 hover:underline">Чат</button>
                <button @click="deleteBot(bot.id)" class="text-red-600 hover:underline">Удал.</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal for add/edit bot -->
    <div v-if="showModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
      <div class="bg-white p-6 rounded-lg w-full max-w-2xl">
        <h3 class="text-xl font-bold mb-4">{{ editingBot ? 'Редактировать' : 'Добавить' }} бота</h3>
        <form @submit.prevent="saveBot">
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-sm mb-1">Имя</label>
              <input v-model="form.name" class="w-full px-3 py-2 border rounded" required />
            </div>
            <div>
              <label class="block text-sm mb-1">Область</label>
              <input v-model="form.area" class="w-full px-3 py-2 border rounded" required />
            </div>
            <div>
              <label class="block text-sm mb-1">Провайдер</label>
              <select v-model="form.provider" class="w-full px-3 py-2 border rounded">
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="qwen">Qwen (Alibaba)</option>
                <option value="groq">Groq</option>
                <option value="openrouter">OpenRouter</option>
              </select>
            </div>
            <div>
              <label class="block text-sm mb-1">Модель</label>
              <input v-model="form.model" class="w-full px-3 py-2 border rounded" required />
            </div>
          </div>
          <div class="mb-4">
            <label class="block text-sm mb-1">API ключ</label>
            <input v-model="form.api_key" type="password" class="w-full px-3 py-2 border rounded" />
          </div>
          <div class="mb-4">
            <label class="block text-sm mb-1">Системный промпт</label>
            <textarea v-model="form.system_prompt" rows="4" class="w-full px-3 py-2 border rounded"></textarea>
          </div>
          <div class="flex items-center gap-4 mb-4">
            <label class="flex items-center gap-2">
              <input v-model="form.is_active" type="checkbox" /> Активен
            </label>
            <label class="flex items-center gap-2">
              <input v-model="form.use_rag" type="checkbox" /> Использовать RAG
            </label>
          </div>
          <div class="flex justify-end gap-2">
            <button type="button" @click="closeModal" class="px-4 py-2 border rounded">Отмена</button>
            <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded">Сохранить</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/auth'

const router = useRouter()

const bots = ref([])
const showModal = ref(false)
const editingBot = ref(null)
const demoSelect = ref(null)
const form = ref({
  name: '', area: '', provider: 'deepseek', model: '',
  api_key: '', system_prompt: '', is_active: true, use_rag: false
})

const demoBots = {
  lawyer: {
    name: 'Юрист',
    area: 'Право',
    provider: 'deepseek',
    model: 'deepseek-chat',
    system_prompt: 'Вы - опытный юрист. Отвечайте на вопросы по российскому законодательству, опираясь на актуальные нормативные акты. Будьте точны и объективны.'
  },
  accountant: {
    name: 'Бухгалтер',
    area: 'Бухучет',
    provider: 'qwen',
    model: 'qwen-turbo',
    system_prompt: 'Вы - профессиональный бухгалтер. Помогайте с вопросами налогообложения, отчетности и финансового учета по РФ. Давайте точные рекомендации.'
  },
  economist: {
    name: 'Экономист',
    area: 'Экономика',
    provider: 'openai',
    model: 'gpt-4o-mini',
    system_prompt: 'Вы - опытный экономист. Анализируйте экономические тренды, давайте прогнозы и рекомендации по финансовым стратегиям.'
  },
  manager: {
    name: 'Менеджер',
    area: 'Управление',
    provider: 'anthropic',
    model: 'claude-3-haiku',
    system_prompt: 'Вы - опытный менеджер проектов. Помогайте с планированием, организацией командной работы, управлением рисками и достижением целей.'
  }
}

async function loadBots() {
  try {
    const { data } = await api.get('/bots')
    bots.value = data
  } catch (e) {
    console.log('DEBUG ERROR loading bots:', e.response?.data || e.message)
  }
}

async function addDemoBot(type) {
  if (!type) return
  const demo = demoBots[type]
  if (!demo) return

  try {
    const { data } = await api.post('/bots', {
      name: demo.name,
      area: demo.area,
      provider: demo.provider,
      model: demo.model,
      system_prompt: demo.system_prompt,
      is_active: true,
      use_rag: false
    })
    bots.value.push(data)
    if (demoSelect.value) demoSelect.value.value = ''
  } catch (e) {
    console.log('DEBUG ERROR adding demo bot:', e.response?.data || e.message)
  }
}

async function saveBot() {
  try {
    let savedBot
    if (editingBot.value) {
      const { data } = await api.put(`/bots/${editingBot.value.id}`, form.value)
      const idx = bots.value.findIndex(b => b.id === editingBot.value.id)
      if (idx !== -1) bots.value[idx] = data
      savedBot = data
    } else {
      const { data } = await api.post('/bots', form.value)
      bots.value.push(data)
      savedBot = data
    }
    closeModal()
    if (savedBot && form.value.api_key) {
      try {
        const { data: testResult } = await api.post(`/bots/${savedBot.id}/test`)
        savedBot.connection_tested = true
        savedBot.connection_error = !testResult.success
      } catch {
        savedBot.connection_error = true
      }
    }
  } catch (e) {
    console.log('DEBUG ERROR saving bot:', e.response?.data || e.message)
  }
}

function editBot(bot) {
  editingBot.value = bot
  form.value = { ...bot, api_key: '' }
  showModal.value = true
}

async function deleteBot(id) {
  if (confirm('Удалить бота?')) {
    try {
      await api.delete(`/bots/${id}`)
      bots.value = bots.value.filter(b => b.id !== id)
    } catch (e) {
      console.log('DEBUG ERROR deleting bot:', e.response?.data || e.message)
    }
  }
}

async function generateKey(bot) {
  try {
    const { data } = await api.post(`/bots/${bot.id}/generate-claw-key`)
    alert(`Ключ: ${data.token}\n\n${data.message}`)
  } catch (e) {
    console.log('DEBUG ERROR generating key:', e.response?.data || e.message)
  }
}

function openChat(botId) {
  router.push({ path: '/chat', query: { bot: botId } })
}

function closeModal() {
  showModal.value = false
  editingBot.value = null
  form.value = { name: '', area: '', provider: 'deepseek', model: '', api_key: '', system_prompt: '', is_active: true, use_rag: false }
}

onMounted(loadBots)
</script>
