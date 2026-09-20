<script setup lang="ts">
/**
 * 答题页。
 *
 * 规格依据：spec 4.2 / 4.3、架构 9.1、9.4、9.5、9.7、9.9
 *   - 一页到底滚动答题，顶部固定倒计时（基于 end_at）。
 *   - 答案实时存 IndexedDB，刷新/断网/崩溃可恢复。
 *   - 切屏记录次数与时间点（不中断考试）。
 *   - 到截止时间自动交卷；提前交卷提示未答题数。
 *   - 提交失败自动重试 3 次（2s/4s/8s），仍失败显示「重试提交」并保留答案。
 *   - 考试中零后端交互：只有交卷一次请求。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { PaperQuestion } from '@/api/client'
import { answerStore } from '@/lib/answerStore'
import { toSubmitPayload, toggleAnswer, unansweredCount } from '@/lib/answers'
import { toDisplayOptions } from '@/lib/optionLabels'
import { typeLabel } from '@/lib/questionTypes'
import { submitWithRetry } from '@/lib/retry'
import { createSwitchTracker } from '@/lib/switchTracker'
import { formatDuration, remainingSeconds } from '@/lib/time'
import { session } from '../session'
import AnswerSheet from '../components/AnswerSheet.vue'

const router = useRouter()

const now = ref(new Date())
const submitting = ref(false)
const submitted = ref(false)
const submitError = ref('')
const retryHint = ref('')
const manualRetryVisible = ref(false)
const savedHint = ref('')
const showSheet = ref(false)
const showConfirm = ref(false)
const pendingUnanswered = ref(0)
const autoSubmitNotice = ref(false)

const tracker = createSwitchTracker()

let tickTimer: ReturnType<typeof setInterval> | undefined

const questions = computed(() => session.questions)

/**
 * 选项显示标号（CH-001）：标号按显示位置排成 A、B、C、D，
 * 内部仍持有服务端返回的原始标识用于提交。
 */
const displayOptions = computed(() => {
  const map = new Map<number, ReturnType<typeof toDisplayOptions>>()
  for (const question of questions.value) {
    map.set(question.id, toDisplayOptions(question.type, question.options))
  }
  return map
})

function optionsOf(questionId: number) {
  return displayOptions.value.get(questionId) ?? []
}

/** 剩余秒数：以服务端 end_at 为准，前端倒计时只是展示 */
const remaining = computed(() => remainingSeconds(session.exam?.end_at, now.value))
const urgent = computed(() => remaining.value > 0 && remaining.value <= 300)

const answeredTotal = computed(
  () => questions.value.length - unansweredCount(questions.value, session.answers),
)

/** 快照为普通对象：Vue 响应式 Proxy 无法被 IndexedDB 结构化克隆 */
function snapshotAnswers() {
  return JSON.parse(JSON.stringify(session.answers)) as typeof session.answers
}

/**
 * 立即写入 IndexedDB。
 *
 * 这里刻意**不做防抖**：防抖会留下一个「刚作答就刷新/崩溃 → 答案丢失」的窗口
 * （本项目的 E2E 就复现过）。一次 IndexedDB 写入开销极小，
 * 而答案不丢失是 spec 4.2 的硬要求，因此每次变更都直接落盘。
 */
async function saveNow() {
  if (session.attemptId === null) return
  try {
    const at = await answerStore.save(session.attemptId, snapshotAnswers())
    savedHint.value = `已保存 ${new Date(at).toLocaleTimeString('zh-CN', { hour12: false })}`
  } catch {
    // 本地保存失败不阻塞答题（例如隐私模式）；交卷仍会提交内存中的答案
    savedHint.value = '本地保存失败'
  }
}

function isSelected(questionId: number, key: string): boolean {
  return (session.answers[questionId] ?? []).includes(key)
}

function selectOption(question: PaperQuestion, key: string) {
  if (submitted.value) return
  session.answers[question.id] = toggleAnswer(
    question.type,
    session.answers[question.id],
    key,
  )
  void saveNow()
}

function jumpTo(index: number) {
  showSheet.value = false
  nextTick(() => {
    document.getElementById(`question-${index}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  })
}

function openConfirm() {
  pendingUnanswered.value = unansweredCount(questions.value, session.answers)
  showConfirm.value = true
}

async function performSubmit(reason: 'manual' | 'timeout') {
  const attemptId = session.attemptId
  if (attemptId === null || submitting.value || submitted.value) return

  submitting.value = true
  submitError.value = ''
  retryHint.value = ''
  manualRetryVisible.value = false
  showConfirm.value = false

  const outcome = await submitWithRetry(
    () =>
      api.submit(attemptId, session.token, {
        answers: toSubmitPayload(questions.value, session.answers),
        switch_count: tracker.count,
        switch_log: [...tracker.log],
      }),
    {
      onRetry: (attempt, _error, delay) => {
        retryHint.value = `提交失败，正在第 ${attempt} 次自动重试（${delay / 1000} 秒后）…`
      },
    },
  )

  submitting.value = false

  if (outcome.ok && outcome.value) {
    submitted.value = true
    stopTimers()
    // 交卷成功即清除本地答案，避免残留
    try {
      await answerStore.clear(attemptId)
    } catch {
      /* 忽略清理失败 */
    }
    session.submitted = outcome.value
    await router.replace('/done')
    return
  }

  // 全部重试失败：保留本地答案，暴露手动重试入口（spec 7.2）
  manualRetryVisible.value = true
  submitError.value =
    reason === 'timeout'
      ? '已到截止时间，自动交卷失败。答案已保存在本机，请点击「重试提交」。'
      : '交卷失败，答案已保存在本机，请点击「重试提交」。'
  retryHint.value = ''
}

function stopTimers() {
  if (tickTimer) clearInterval(tickTimer)
  tickTimer = undefined
  tracker.stop()
}

onMounted(async () => {
  // 未登录（例如直接输入地址）→ 回到等待页
  if (!session.exam || !session.token) {
    await router.replace('/waiting')
    return
  }

  // 刷新后内存中的试卷会丢失：自动重新拉取。
  // 试卷顺序与选项乱序都由服务端按考生种子确定，因此内容与刷新前一致。
  if (session.questions.length === 0) {
    try {
      const paper = await api.getPaper(session.exam.id, session.token)
      session.exam = paper.exam
      session.questions = paper.questions
    } catch {
      // 考试已结束/已归档/未开始等：交回等待页展示原因
      await router.replace('/waiting')
      return
    }
  }

  // 恢复本地答案（换设备/清缓存时为空白，不报错）。
  // 用「内存优先」合并而不是直接覆盖：IndexedDB 读取是异步的，
  // 若考生在读取完成前就已答题，直接覆盖会把这几秒内的作答丢掉。
  if (session.attemptId !== null) {
    try {
      const stored = await answerStore.load(session.attemptId)
      session.answers = { ...stored, ...session.answers }
    } catch {
      session.answers = { ...session.answers }
    }
  }

  tracker.start()

  tickTimer = setInterval(() => {
    now.value = new Date()
    if (remaining.value <= 0 && !submitted.value) {
      // 截止时间到：自动交卷（不再询问）
      autoSubmitNotice.value = true
      void performSubmit('timeout')
    }
  }, 1000)
})

onBeforeUnmount(() => {
  stopTimers()
})
</script>

<template>
  <div class="exam">
    <!-- 顶部固定栏：倒计时 + 进度 + 交卷 -->
    <header class="exam-bar">
      <div class="exam-bar-left">
        <span class="exam-title">{{ session.exam?.title ?? '考试' }}</span>
        <span class="muted exam-progress">已答 {{ answeredTotal }} / {{ questions.length }}</span>
      </div>

      <div class="exam-bar-right">
        <button class="btn btn-sm sheet-toggle" type="button" @click="showSheet = true">
          答题卡
        </button>
        <div class="clock" :class="{ 'clock-urgent': urgent }">
          <span class="clock-label">剩余</span>
          <span class="clock-value">{{ formatDuration(remaining) }}</span>
        </div>
        <button
          class="btn btn-primary btn-sm"
          type="button"
          :disabled="submitting"
          @click="openConfirm"
        >
          交卷
        </button>
      </div>
    </header>

    <main class="exam-body">
      <!-- 提交状态提示 -->
      <div v-if="autoSubmitNotice && submitting" class="alert alert-warning">
        考试已到截止时间，正在自动交卷…
      </div>
      <div v-if="retryHint" class="alert alert-warning">{{ retryHint }}</div>
      <div v-if="submitError" class="alert alert-error">
        <div>{{ submitError }}</div>
        <button
          v-if="manualRetryVisible"
          class="btn btn-danger btn-sm"
          style="margin-top: 10px"
          type="button"
          :disabled="submitting"
          @click="performSubmit('manual')"
        >
          重试提交
        </button>
      </div>

      <p v-if="savedHint" class="muted save-hint">{{ savedHint }}</p>

      <!-- 一页到底 -->
      <section
        v-for="(question, index) in questions"
        :id="`question-${index}`"
        :key="question.id"
        class="card question"
      >
        <div class="question-head">
          <span class="question-no">{{ index + 1 }}</span>
          <span class="tag">{{ typeLabel(question.type) }}</span>
          <span v-if="(session.answers[question.id] ?? []).length === 0" class="tag tag-blank">
            未作答
          </span>
        </div>

        <p class="question-stem">{{ question.stem }}</p>

        <div class="options">
          <label
            v-for="option in optionsOf(question.id)"
            :key="option.key"
            class="option"
            :class="{ 'is-selected': isSelected(question.id, option.key) }"
          >
            <input
              :type="question.type === 'multi' ? 'checkbox' : 'radio'"
              :name="`q-${question.id}`"
              :checked="isSelected(question.id, option.key)"
              @change="selectOption(question, option.key)"
            />
            <span class="option-key">{{ option.label }}</span>
            <span class="option-text">{{ option.text }}</span>
          </label>
        </div>
      </section>

      <div class="exam-footer">
        <button class="btn btn-primary btn-lg" type="button" :disabled="submitting" @click="openConfirm">
          交卷
        </button>
      </div>
    </main>

    <!-- 答题卡抽屉 -->
    <div v-if="showSheet" class="modal-mask" @click.self="showSheet = false">
      <div class="modal sheet-modal">
        <AnswerSheet :questions="questions" :answers="session.answers" @jump="jumpTo" />
        <div class="modal-actions">
          <button class="btn" type="button" @click="showSheet = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 交卷确认（提示未答题数） -->
    <div v-if="showConfirm" class="modal-mask" @click.self="showConfirm = false">
      <div class="modal">
        <h3>确认交卷</h3>
        <p v-if="pendingUnanswered > 0">
          还有 <strong class="danger-text">{{ pendingUnanswered }}</strong> 题未答，交卷后不可再修改。
        </p>
        <p v-else>题目已全部作答，交卷后不可再修改。</p>
        <div class="modal-actions">
          <button class="btn" type="button" :disabled="submitting" @click="showConfirm = false">
            继续答题
          </button>
          <button
            class="btn btn-primary"
            type="button"
            :disabled="submitting"
            @click="performSubmit('manual')"
          >
            {{ submitting ? '提交中…' : '确认交卷' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.exam {
  min-height: 100vh;
  padding-bottom: 24px;
}

.exam-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--c-border);
}

.exam-bar-left {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.exam-title {
  font-weight: 600;
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.exam-progress {
  font-size: 12px;
}

.exam-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.clock {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius);
  background: var(--c-primary-weak);
  color: #1e40af;
}

.clock-urgent {
  background: var(--c-danger-weak);
  color: #991b1b;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.62;
  }
}

.clock-label {
  font-size: 11px;
}

.clock-value {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-size: 15px;
}

.exam-body {
  max-width: 760px;
  margin: 0 auto;
  padding: 16px 14px;
}

.save-hint {
  margin: 0 0 10px;
  font-size: 12px;
  text-align: right;
}

.question {
  padding: 16px;
  margin-bottom: 14px;
  scroll-margin-top: 74px;
}

.question-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.question-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--c-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.tag-blank {
  background: var(--c-warning-weak);
  color: #92400e;
}

.question-stem {
  margin: 0 0 14px;
  font-size: 15.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  background: var(--c-surface);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.option:hover {
  border-color: var(--c-primary);
}

.option.is-selected {
  border-color: var(--c-primary);
  background: var(--c-primary-weak);
}

.option input {
  margin-top: 3px;
  accent-color: var(--c-primary);
  flex: none;
}

.option-key {
  flex: none;
  font-weight: 600;
  min-width: 16px;
}

.option-text {
  flex: 1;
  word-break: break-word;
}

.exam-footer {
  padding: 10px 0 30px;
  display: flex;
  justify-content: center;
}

.sheet-toggle {
  white-space: nowrap;
}

.sheet-modal {
  max-width: 480px;
}

.danger-text {
  color: var(--c-danger);
}

@media (min-width: 1100px) {
  .exam-body {
    max-width: 820px;
  }
}
</style>
