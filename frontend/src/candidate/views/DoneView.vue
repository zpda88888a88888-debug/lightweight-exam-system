<script setup lang="ts">
/**
 * 交卷结果页。
 *
 * 规格依据：spec 4.2 / 架构 1「交卷后不立即出分，管理员导出 CSV 线下告知」。
 * 因此这里**不显示分数**，只确认交卷成功。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { clearSession } from '../session'

const router = useRouter()

// 进入本页即视为流程结束：清空本地会话，防止回退再次进入答题页
onMounted(() => {
  clearSession()
})

function goHome() {
  router.push('/')
}
</script>

<template>
  <div class="center-page">
    <div class="card done-card">
      <div class="done-icon">✓</div>
      <h1 class="done-title">交卷成功</h1>
      <p class="muted done-text">
        你的答案已提交，考试已结束。<br />
        成绩由考试管理员统一公布。
      </p>
      <p class="muted done-note">再次登录将被拒绝，请勿重复尝试。</p>
      <button class="btn btn-primary done-btn" @click="goHome">返回首页</button>
    </div>
  </div>
</template>

<style scoped>
.done-card {
  width: 100%;
  max-width: 420px;
  padding: 34px 24px;
  text-align: center;
}

.done-icon {
  width: 62px;
  height: 62px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: var(--c-success-weak);
  color: var(--c-success);
  font-size: 32px;
  line-height: 62px;
  border: 2px solid #bbf7d0;
}

.done-title {
  margin: 0 0 10px;
  font-size: 21px;
}

.done-text {
  margin: 0 0 14px;
  font-size: 14px;
}

.done-note {
  margin: 0 0 20px;
  font-size: 12px;
}

.done-btn {
  width: 100%;
}
</style>
