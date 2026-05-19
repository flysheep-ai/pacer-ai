import { createRouter as createVueRouter, createMemoryHistory, createWebHistory } from 'vue-router'
import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export function createRouter(): Router {
  const mode = (import.meta as unknown as { env: { MODE: string } }).env.MODE
  const isTest = mode === 'test'
  const router = createVueRouter({
    history: isTest ? createMemoryHistory() : createWebHistory(),
    routes: [
      { path: '/', name: 'login', component: () => import('@/views/LoginView.vue') },
      { path: '/chat', name: 'chat', component: () => import('@/views/ChatView.vue') },
      { path: '/chat/:sid', name: 'chat-sid', component: () => import('@/views/ChatView.vue') },
      { path: '/:path(.*)*', redirect: '/' },
    ],
  })
  router.beforeEach((to) => {
    const auth = useAuthStore()
    if (auth.isAuthenticated && to.name === 'login') return { path: '/chat' }
    if (!auth.isAuthenticated && to.name !== 'login') return { path: '/' }
    return true
  })
  return router
}
