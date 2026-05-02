import { ref } from 'vue';
import { useRouter } from 'vue-router';
import api from '../api/auth';

export const useAuthStore = () => {
  const isAuthenticated = ref(!!localStorage.getItem('access_token'));
  const router = useRouter();

  async function login(username, password) {
    console.log('DEBUG FRONTEND LOGIN:', { username, password_length: password?.length });
    try {
      const response = await api.post('/auth/login', { username, password });
      console.log('DEBUG LOGIN SUCCESS:', response.data);
      localStorage.setItem('access_token', response.data.access_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
      isAuthenticated.value = true;
      console.log('DEBUG: Redirecting to /dashboard/bots');
      router.push('/dashboard/bots');
    } catch (error) {
      console.log('DEBUG LOGIN ERROR:', error.response?.data || error.message);
      throw error;
    }
  }

  function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    isAuthenticated.value = false;
    router.push('/login');
  }

  return { isAuthenticated, login, logout };
};
