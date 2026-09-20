/**
 * 考生端入口：路由与访问守卫。
 *
 * 守卫规则：
 *   - 未登录访问 /waiting、/exam → 回到登录页。
 *   - 已登录访问 / → 直接进入等待页（刷新后无需重新登录）。
 *   - 答题页要求已取到 attempt 与试卷。
 */

import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'

import '@/styles/app.css'
import App from './App.vue'
import DoneView from './views/DoneView.vue'
import ExamView from './views/ExamView.vue'
import LoginView from './views/LoginView.vue'
import WaitingView from './views/WaitingView.vue'
import { isLoggedIn, restoreSession, session } from './session'

const router = createRouter({
  // hash 模式：纯静态托管即可，刷新任意页面都不会 404，无需服务器 rewrite
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'login', component: LoginView },
    { path: '/waiting', name: 'waiting', component: WaitingView },
    { path: '/exam', name: 'exam', component: ExamView },
    { path: '/done', name: 'done', component: DoneView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

restoreSession()

router.beforeEach((to) => {
  const loggedIn = isLoggedIn()

  if (to.name === 'login') {
    // 刷新后仍在登录有效期：直接回到等待页
    return loggedIn && session.attemptId === null ? { name: 'waiting' } : true
  }

  if (!loggedIn) {
    return { name: 'login' }
  }

  // 刷新后 session.questions 会丢失（只持久化了 token/exam/attemptId），
  // 因此这里只要求已有 attempt；试卷由 ExamView 自动重新拉取。
  if (to.name === 'exam' && session.attemptId === null) {
    return { name: 'waiting' }
  }

  return true
})

createApp(App).use(router).mount('#app')
