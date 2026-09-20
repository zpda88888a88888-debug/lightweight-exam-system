/**
 * 考生会话状态。
 *
 * - token / 考试信息 / attemptId 存 localStorage：刷新、断网、崩溃后可恢复，
 *   并直接回到答题页，无需重新登录。
 * - 答案不在这里持久化：答案存在 IndexedDB（见 lib/answerStore.ts），
 *   因为答案量大且需要按 attempt 隔离。
 * - 换设备 / 换浏览器 / 清缓存时 localStorage 与 IndexedDB 同时为空，
 *   此时重新登录会拿到后端同一个 attempt，答案从空白继续（符合 spec 7.1）。
 */

import { reactive } from 'vue'

import type { ExamBrief, PaperQuestion, SubmitResponse } from '@/api/client'
import type { Answers } from '@/lib/answers'

const SESSION_KEY = 'exam.session.v1'

export interface PersistedSession {
  token: string
  exam: ExamBrief
  attemptId: number | null
}

export interface SessionState {
  token: string
  exam: ExamBrief | null
  attemptId: number | null
  questions: PaperQuestion[]
  answers: Answers
  submitted: SubmitResponse | null
  /** 是否已从 localStorage 恢复过 */
  restored: boolean
}

export const session = reactive<SessionState>({
  token: '',
  exam: null,
  attemptId: null,
  questions: [],
  answers: {},
  submitted: null,
  restored: false,
})

/** 把登录信息写入 localStorage（答案不写这里）。 */
export function persistSession(): void {
  if (!session.exam) return
  const payload: PersistedSession = {
    token: session.token,
    exam: session.exam,
    attemptId: session.attemptId,
  }
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload))
  } catch {
    // 隐私模式下 localStorage 可能不可用：不影响本次答题（答案在 IndexedDB）
  }
}

/** 从 localStorage 恢复登录信息。 */
export function restoreSession(): void {
  session.restored = true
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<PersistedSession>
    if (parsed.token && parsed.exam) {
      session.token = parsed.token
      session.exam = parsed.exam
      session.attemptId = parsed.attemptId ?? null
    }
  } catch {
    // 数据损坏时当作未登录处理，不阻塞进入登录页
  }
}

/** 清空会话（交卷成功或退出登录）。 */
export function clearSession(): void {
  session.token = ''
  session.exam = null
  session.attemptId = null
  session.questions = []
  session.answers = {}
  session.submitted = null
  try {
    localStorage.removeItem(SESSION_KEY)
  } catch {
    /* 忽略 */
  }
}

export function isLoggedIn(): boolean {
  return Boolean(session.token && session.exam)
}
