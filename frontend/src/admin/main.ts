/**
 * 管理端入口：独立页面（admin.html），与考生端构建产物共用后端 API。
 */

import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'

import '@/styles/app.css'
import App from './App.vue'
import CandidatesView from './views/CandidatesView.vue'
import ExamDetailView from './views/ExamDetailView.vue'
import ExamsView from './views/ExamsView.vue'
import LoginView from './views/LoginView.vue'
import PaperDetailView from './views/PaperDetailView.vue'
import PapersView from './views/PapersView.vue'
import QuestionsView from './views/QuestionsView.vue'
import { isAdminLoggedIn, restoreAdminToken } from './session'

const router = createRouter({
  // 管理端是独立入口（admin.html）：用 hash 模式，
  // 这样纯静态托管 + 任意刷新路径都可用，无需服务器 rewrite 配置。
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: { name: 'admin-exams' } },
    { path: '/login', name: 'admin-login', component: LoginView },
    { path: '/exams', name: 'admin-exams', component: ExamsView },
    { path: '/exams/:id', name: 'admin-exam-detail', component: ExamDetailView, props: true },
    { path: '/candidates', name: 'admin-candidates', component: CandidatesView },
    { path: '/papers', name: 'admin-papers', component: PapersView },
    { path: '/papers/:id', name: 'admin-paper-detail', component: PaperDetailView, props: true },
    { path: '/questions', name: 'admin-questions', component: QuestionsView },
    { path: '/:pathMatch(.*)*', redirect: { name: 'admin-exams' } },
  ],
})

// 管理端页面挂在 /admin.html
restoreAdminToken()

router.beforeEach((to) => {
  if (to.name !== 'admin-login' && !isAdminLoggedIn()) {
    return { name: 'admin-login' }
  }
  if (to.name === 'admin-login' && isAdminLoggedIn()) {
    return { name: 'admin-exams' }
  }
  return true
})

createApp(App).use(router).mount('#admin-app')
