import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const routes = [
  {
    path: '/login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true }
  },
  {
    path: '/dashboard/bots',
    component: () => import('../views/DashboardBots.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/chat',
    component: () => import('../views/ChatView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard/bots'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, from, next) => {
  const auth = useAuthStore();
  const isAuth = !!localStorage.getItem('access_token');

  console.log('DEBUG ROUTER:', {
    to: to.path,
    from: from.path,
    isAuth,
    requiresAuth: to.meta.requiresAuth,
    guest: to.meta.guest
  });

  if (to.meta.requiresAuth && !isAuth) {
    console.log('DEBUG: Redirecting to login (not authenticated)');
    next('/login');
  } else if (to.meta.guest && isAuth) {
    console.log('DEBUG: Redirecting to dashboard (already logged in)');
    next('/dashboard/bots');
  } else {
    next();
  }
});

export default router;
