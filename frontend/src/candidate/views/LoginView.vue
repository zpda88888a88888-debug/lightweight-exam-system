<script setup lang="ts">
/** 考生登录页：手机号 + 邀请码。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { persistSession, session } from '../session'

const router = useRouter()

const phone = ref('')
const inviteCode = ref('')
const error = ref('')
const loading = ref(false)

async function onSubmit() {
  error.value = ''

  if (!/^1\d{10}$/.test(phone.value)) {
    error.value = '请输入正确的 11 位手机号'
    return
  }
  if (!/^\d{6}$/.test(inviteCode.value)) {
    error.value = '请输入 6 位数字邀请码'
    return
  }

  loading.value = true
  try {
    const data = await api.join(phone.value, inviteCode.value)
    session.token = data.token
    session.exam = data.exam
    session.attemptId = null
    session.questions = []
    session.answers = {}
    session.submitted = null
    persistSession()
    await router.push('/waiting')
  } catch (err) {
    // 后端已给出明确中文提示：考试未开始 / 考试已结束 / 你已交卷，考试结束 / 手机号或邀请码错误
    error.value =
      err instanceof ApiError ? err.detail : '网络异常，请检查网络后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="center-page">
    <div class="card login-card">
      <h1 class="login-title">在线考试</h1>
      <p class="muted login-sub">请输入手机号与邀请码进入考试</p>

      <div v-if="error" class="alert alert-error" role="alert">{{ error }}</div>

      <form @submit.prevent="onSubmit">
        <div class="field">
          <label for="phone">手机号</label>
          <input
            id="phone"
            v-model.trim="phone"
            class="input"
            type="tel"
            inputmode="numeric"
            autocomplete="tel"
            placeholder="11 位手机号"
            maxlength="11"
          />
        </div>

        <div class="field">
          <label for="invite">邀请码</label>
          <input
            id="invite"
            v-model.trim="inviteCode"
            class="input"
            inputmode="numeric"
            placeholder="6 位数字邀请码"
            maxlength="6"
          />
        </div>

        <button class="btn btn-primary btn-lg login-submit" type="submit" :disabled="loading">
          {{ loading ? '验证中…' : '进入考试' }}
        </button>
      </form>

      <p class="muted login-hint">邀请码由考试管理员线下分发</p>
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
  font-size: 22px;
  text-align: center;
}

.login-sub {
  margin: 0 0 20px;
  text-align: center;
  font-size: 14px;
}

.login-submit {
  width: 100%;
  margin-top: 6px;
}

.login-hint {
  margin: 16px 0 0;
  text-align: center;
  font-size: 12px;
}
</style>
