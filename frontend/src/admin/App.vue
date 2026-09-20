<script setup lang="ts">
/** 管理端根组件：未登录时只渲染登录页，登录后渲染带导航的布局。 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { adminSession, clearAdminToken } from './session'

const route = useRoute()
const router = useRouter()

const showLayout = computed(() => route.name !== 'admin-login')

function logout() {
  clearAdminToken()
  router.push({ name: 'admin-login' })
}
</script>

<template>
  <div v-if="!showLayout" class="admin-plain">
    <router-view />
  </div>

  <div v-else class="admin-shell">
    <aside class="admin-side">
      <div class="admin-brand">考试管理后台</div>
      <nav class="admin-nav">
        <router-link class="nav-item" :to="{ name: 'admin-exams' }">考试管理</router-link>
        <router-link class="nav-item" :to="{ name: 'admin-candidates' }">考生管理</router-link>
        <router-link class="nav-item" :to="{ name: 'admin-papers' }">试卷管理</router-link>
        <router-link class="nav-item" :to="{ name: 'admin-questions' }">题库管理</router-link>
      </nav>
      <div class="admin-side-foot">
        <a class="nav-item" href="/" target="_blank" rel="noopener">考生端入口 ↗</a>
      </div>
    </aside>

    <div class="admin-main">
      <header class="admin-header">
        <span class="muted">内网单机部署 · {{ adminSession.username || 'admin' }}</span>
        <span class="spacer"></span>
        <button class="btn btn-sm" type="button" @click="logout">退出登录</button>
      </header>
      <div class="admin-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-plain {
  min-height: 100vh;
}

.admin-shell {
  display: flex;
  min-height: 100vh;
}

.admin-side {
  width: 208px;
  flex: none;
  background: #101828;
  color: #cbd5e1;
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
}

.admin-brand {
  padding: 18px 16px;
  font-weight: 700;
  color: #fff;
  font-size: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.admin-nav {
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: block;
  padding: 9px 12px;
  border-radius: 8px;
  color: #cbd5e1;
  text-decoration: none;
  font-size: 14px;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.nav-item.router-link-active {
  background: var(--c-primary);
  color: #fff;
  font-weight: 600;
}

.admin-side-foot {
  margin-top: auto;
  padding: 10px 8px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.admin-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.admin-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.admin-content {
  padding: 20px;
  max-width: 1240px;
  width: 100%;
}
</style>
