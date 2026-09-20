<script setup lang="ts">
/**
 * 等待页：显示考试名称、开考时间、截止时间；
 * 到开考时间后出现「开始考试」按钮；点击后创建 attempt 并拉取试卷。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, api } from '@/api/client'
import { answerStore } from '@/lib/answerStore'
import { formatDuration, formatLocal, remainingSeconds } from '@/lib/time'
import { session, persistSession } from '../session'

const router = useRouter()

const now = ref(new Date())
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

const startAt = computed(() => session.exam?.start_at ?? null)
const endAt = computed(() => session.exam?.end_at ?? null)

/** 距开考的剩余秒数 */
const secondsToStart = computed(() => remainingSeconds(startAt.value, now.value))
/** 距截止的剩余秒数（晚进少考） */
const secondsToEnd = computed(() => remainingSeconds(endAt.value, now.value))

const started = computed(() => secondsToStart.value <= 0)
const ended = computed(() => secondsToEnd.value <= 0)

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date()
  }, 1000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

async function onStart() {
  if (!session.exam) return
  error.value = ''
  loading.value = true
  try {
    // 创建 attempt（后端幂等：重复调用返回同一个 attempt_id）
    const attempt = await api.createAttempt(session.exam.id, session.token)
    session.attemptId = attempt.attempt_id
    // 关键：立即持久化 attemptId，否则刷新后守卫看不到 attempt，
    // 会被退回等待页，无法直接恢复答题。
    persistSession()

    // 拉取试卷（服务端已按考生种子乱序选项）
    const paper = await api.getPaper(session.exam.id, session.token)
    session.exam = paper.exam
    session.questions = paper.questions

    // 从 IndexedDB 恢复本地答案（刷新/断网/崩溃后继续）
    session.answers = await answerStore.load(attempt.attempt_id)

    await router.push('/exam')
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : '无法开始考试，请检查网络后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="center-page">
    <div class="card waiting-card">
      <h1 class="waiting-title">{{ session.exam?.title ?? '考试' }}</h1>

      <div v-if="error" class="alert alert-error">{{ error }}</div>

      <dl class="waiting-meta">
        <div>
          <dt>开考时间</dt>
          <dd>{{ formatLocal(startAt) }}</dd>
        </div>
        <div>
          <dt>截止时间</dt>
          <dd>{{ formatLocal(endAt) }}</dd>
        </div>
      </dl>

      <div v-if="ended" class="alert alert-error" style="margin-bottom: 0">
        考试已结束，无法进入。
      </div>

      <template v-else-if="!started">
        <div class="countdown-box">
          <div class="muted">距开考还有</div>
          <div class="countdown-value">{{ formatDuration(secondsToStart) }}</div>
        </div>
        <button class="btn btn-lg waiting-btn" disabled>开始考试</button>
        <p class="muted waiting-hint">到开考时间后按钮自动可用</p>
      </template>

      <template v-else>
        <div class="alert alert-info">
          考试进行中，距截止还有 <strong>{{ formatDuration(secondsToEnd) }}</strong>
          <br />
          <span class="muted">晚进入不会补时，倒计时按统一截止时间计算。</span>
        </div>
        <button class="btn btn-primary btn-lg waiting-btn" :disabled="loading" @click="onStart">
          {{ loading ? '加载试卷中…' : '开始考试' }}
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.waiting-card {
  width: 100%;
  max-width: 440px;
  padding: 26px 24px;
}

.waiting-title {
  margin: 0 0 18px;
  font-size: 20px;
  text-align: center;
}

.waiting-meta {
  margin: 0 0 20px;
  display: grid;
  gap: 10px;
}

.waiting-meta > div {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed var(--c-border);
}

.waiting-meta dt {
  color: var(--c-text-weak);
  font-size: 13px;
}

.waiting-meta dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.countdown-box {
  text-align: center;
  padding: 16px 0 20px;
}

.countdown-value {
  font-size: 34px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 1px;
  color: var(--c-primary);
}

.waiting-btn {
  width: 100%;
}

.waiting-hint {
  margin: 10px 0 0;
  text-align: center;
  font-size: 12px;
}
</style>
