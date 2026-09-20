<script setup lang="ts">
/** 管理端登录页：账号 + 密码（环境变量配置的单超管）。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { adminSession, persistAdminToken } from '../session'

const router = useRouter()

const username = ref('admin')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function onSubmit() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入账号与密码'
    return
  }
  loading.value = true
  try {
    const data = await api.adminLogin(username.value, password.value)
    adminSession.token = data.token
    adminSession.username = username.value
    persistAdminToken(username.value)
    await router.push({ name: 'admin-exams' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '网络异常，请检查后端服务是否已启动'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="center-page">
    <div class="card login-card">
      <h1 class="login-title">考试管理后台</h1>
      <p class="muted login-sub">请使用管理员账号登录</p>

      <div v-if="error" class="alert alert-error">{{ error }}</div>

      <form @submit.prevent="onSubmit">
        <div class="field">
          <label for="username">账号</label>
          <input id="username" v-model.trim="username" class="input" autocomplete="username" />
        </div>

        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            class="input"
            type="password"
            autocomplete="current-password"
          />
        </div>

        <button class="btn btn-primary btn-lg login-submit" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </form>

      <p class="muted login-hint">账号密码由后端环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 配置</p>
    </div>
  </div>
</template>

<style scoped>
.login-card {
  width: 100%;
  max-width: 400px;
  padding: 28px 24px;
}

.login-title {
  margin: 0 0 4px;
  font-size: 21px;
  text-align: center;
}

.login-sub {
  margin: 0 0 20px;
  text-align: center;
  font-size: 14px;
}

.login-submit {
  width: 100%;
}

.login-hint {
  margin: 16px 0 0;
  text-align: center;
  font-size: 12px;
}
</style>
