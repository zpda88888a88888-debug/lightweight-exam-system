/**
 * 后端 API 客户端（与 backend/app/routers 一一对应）。
 *
 * 约定：
 *   - 统一解包后端的 `{ detail: "..." }` 错误体，抛 ApiError，便于界面直接展示中文提示。
 *   - 所有时间字段保持后端原始字符串（naive UTC），由 lib/time.ts 显式按 UTC 解析。
 */

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

// ---------------------------------------------------------------- 类型

export interface ExamBrief {
  id: number
  title: string
  start_at: string
  end_at: string
}

export interface Option {
  key: string
  text: string
}

export type QuestionType = 'single' | 'multi' | 'judge'

export interface PaperQuestion {
  id: number
  type: QuestionType
  stem: string
  options: Option[]
}

export interface PaperResponse {
  exam: ExamBrief
  questions: PaperQuestion[]
}

export interface AttemptResponse {
  attempt_id: number
  end_at: string
}

export interface SubmitResponse {
  ok: boolean
  attempt_id: number
  score: number
  status: 'submitted' | 'timeout_submitted'
  submitted_at: string
}

export interface AdminLoginResponse {
  token: string
}

export interface QuestionStats {
  last_drawn_exam_id: number | null
  last_drawn_exam_title: string | null
  last_drawn_at: string | null
  answer_count: number
  correct_count: number
  /** null 表示从未被作答（界面显示"暂无"，不是 0%） */
  correct_rate: number | null
}

export interface QuestionOut {
  id: number
  type: QuestionType
  stem: string
  options: Option[]
  answer: string[]
  score: number
  tags: string[]
  analysis: string
  updated_at: string
  /** 题库列表接口返回；单题增改时为 null */
  stats?: QuestionStats | null
}

export interface ExamSettings {
  rules: { tag: string; count: number }[]
}

export interface ExamOut {
  id: number
  title: string
  recruitment_no: string
  status: 'draft' | 'published' | 'archived'
  external_status: 'draft' | 'upcoming' | 'running' | 'ended' | 'archived'
  start_at: string
  end_at: string
  pass_ratio: number
  settings: ExamSettings
  created_at: string
  published_at: string | null
}

export type ParticipationStatus =
  | 'not_started'
  | 'in_progress'
  | 'submitted'
  | 'timeout_submitted'

export interface CandidateRow {
  user_id: number
  phone: string
  name: string
  id_card: string
  invite_code: string | null
  /** 参与状态：谁没来 / 谁正在考试 / 谁已交卷 */
  status: ParticipationStatus
  started_at: string | null
  submitted_at: string | null
  score: number | null
}

export interface StatsQuestionRow {
  question_id: number
  seq: number
  wrong_rate: number
  full_score: number
}

export interface StatsResponse {
  exam_id: number
  total_candidates: number
  attempt_count: number
  absent_count: number
  average_score: number
  pass_ratio: number
  pass_line: number | null
  pass_count: number
  pass_rate: number
  questions: StatsQuestionRow[]
}

export interface ResultRow {
  user_id: number
  phone: string
  name: string
  id_card: string
  invite_code: string | null
  started_at: string | null
  submitted_at: string | null
  score: number | null
  is_pass: boolean
  switch_count: number
  switch_log: string[]
  status: string
}

export interface ResultsResponse {
  exam_id: number
  rows: ResultRow[]
}

export interface RosterImportResponse {
  users_created: number
  users_updated: number
  linked: number
  total_rows: number
}

export interface TagCount {
  tag: string
  question_count: number
}

/** 管理端试卷快照中的题目（含正确答案，仅管理端可见）。 */
export interface AdminPaperQuestion {
  seq: number
  question_id: number
  type: QuestionType
  stem: string
  options: Option[]
  answer: string[]
  score: number
  analysis: string
}

/** 考试与试卷的对应关系（只读）。 */
export interface AdminPaper {
  exam: ExamOut
  questions: AdminPaperQuestion[]
  total_score: number
  question_count: number
}

export interface PublishResponse {
  exam_id: number
  question_count: number
  total_score: number
}

// ---------------------------------------------------------------- 请求封装

export interface ClientOptions {
  baseUrl?: string
  fetchImpl?: typeof fetch
}

interface RequestOptions {
  method?: string
  token?: string | null
  body?: unknown
  rawBody?: BodyInit
  contentType?: string
  signal?: AbortSignal
}

export function createApiClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? '').replace(/\/$/, '')
  const doFetch = options.fetchImpl ?? globalThis.fetch

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = {}
    let body: BodyInit | undefined

    if (options.rawBody !== undefined) {
      body = options.rawBody
      headers['Content-Type'] = options.contentType ?? 'application/json'
    } else if (options.body !== undefined) {
      body = JSON.stringify(options.body)
      headers['Content-Type'] = 'application/json'
    }

    if (options.token) {
      headers.Authorization = `Bearer ${options.token}`
    }

    const response = await doFetch(`${baseUrl}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body,
      signal: options.signal,
    })

    if (!response.ok) {
      let detail = `请求失败（HTTP ${response.status}）`
      try {
        const payload = (await response.json()) as { detail?: unknown }
        if (typeof payload.detail === 'string') {
          detail = payload.detail
        } else if (Array.isArray(payload.detail)) {
          // FastAPI 校验错误体
          detail = payload.detail
            .map((item) => (item as { msg?: string }).msg ?? '')
            .filter(Boolean)
            .join('；')
        }
      } catch {
        /* 保留默认提示 */
      }
      throw new ApiError(response.status, detail)
    }

    if (response.status === 204) return undefined as T

    const contentType = response.headers.get('Content-Type') ?? ''
    if (contentType.includes('application/json')) {
      return (await response.json()) as T
    }
    return (await response.text()) as unknown as T
  }

  return {
    // ---------------- 考生端 ----------------
    join: (phone: string, inviteCode: string) =>
      request<{ token: string; exam: ExamBrief }>('/api/auth/join', {
        method: 'POST',
        body: { phone, invite_code: inviteCode },
      }),

    createAttempt: (examId: number, token: string) =>
      request<AttemptResponse>(`/api/exams/${examId}/attempts`, { method: 'POST', token }),

    getPaper: (examId: number, token: string) =>
      request<PaperResponse>(`/api/exams/${examId}/paper`, { token }),

    submit: (
      attemptId: number,
      token: string,
      payload: {
        answers: { question_id: number; answer: string[] }[]
        switch_count: number
        switch_log: string[]
      },
    ) =>
      request<SubmitResponse>(`/api/attempts/${attemptId}/submit`, {
        method: 'POST',
        token,
        body: payload,
      }),

    // ---------------- 管理端：登录 ----------------
    adminLogin: (username: string, password: string) =>
      request<AdminLoginResponse>('/api/admin/login', {
        method: 'POST',
        body: { username, password },
      }),

    // ---------------- 管理端：题库 ----------------
    listQuestions: (token: string, filters: { type?: string; tag?: string; keyword?: string } = {}) => {
      const query = new URLSearchParams()
      if (filters.type) query.set('type', filters.type)
      if (filters.tag) query.set('tag', filters.tag)
      if (filters.keyword) query.set('keyword', filters.keyword)
      const suffix = query.toString() ? `?${query}` : ''
      return request<QuestionOut[]>(`/api/admin/questions${suffix}`, { token })
    },

    createQuestion: (
      token: string,
      payload: {
        type: QuestionType
        stem: string
        options: Option[]
        answer: string[]
        score: number
        tags: string[]
        analysis?: string
      },
    ) => request<QuestionOut>('/api/admin/questions', { method: 'POST', token, body: payload }),

    updateQuestion: (
      token: string,
      id: number,
      payload: {
        type: QuestionType
        stem: string
        options: Option[]
        answer: string[]
        score: number
        tags: string[]
        analysis?: string
      },
    ) => request<QuestionOut>(`/api/admin/questions/${id}`, { method: 'PUT', token, body: payload }),

    deleteQuestion: (token: string, id: number) =>
      request<{ ok: boolean }>(`/api/admin/questions/${id}`, { method: 'DELETE', token }),

    exportQuestions: (token: string) => request<string>('/api/admin/questions/export', { token }),

    importQuestions: (
      token: string,
      questions: {
        id?: number
        type: QuestionType
        stem: string
        options: Option[]
        answer: string[]
        score: number
        tags: string[]
        analysis?: string
      }[],
    ) =>
      request<{ created: number; updated: number; total: number }>(
        '/api/admin/questions/import',
        { method: 'POST', token, body: { questions } },
      ),

    // ---------------- 管理端：题库标签 ----------------
    listTags: (token: string) => request<TagCount[]>('/api/admin/tags', { token }),

    // ---------------- 管理端：试卷管理（只读快照） ----------------
    getAdminPaper: (token: string, examId: number) =>
      request<AdminPaper>(`/api/admin/exams/${examId}/paper`, { token }),

    // ---------------- 管理端：考试 ----------------
    listExams: (
      token: string,
      filters: {
        status?: string
        recruitment_no?: string
        title?: string
        start_from?: string
        start_to?: string
      } = {},
    ) => {
      const query = new URLSearchParams()
      if (filters.status) query.set('status', filters.status)
      if (filters.recruitment_no) query.set('recruitment_no', filters.recruitment_no)
      if (filters.title) query.set('title', filters.title)
      if (filters.start_from) query.set('start_from', filters.start_from)
      if (filters.start_to) query.set('start_to', filters.start_to)
      const suffix = query.toString() ? `?${query}` : ''
      return request<ExamOut[]>(`/api/admin/exams${suffix}`, { token })
    },

    createExam: (
      token: string,
      payload: {
        title: string
        recruitment_no: string
        start_at: string
        end_at: string
        pass_ratio: number
        settings: ExamSettings
      },
    ) => request<ExamOut>('/api/admin/exams', { method: 'POST', token, body: payload }),

    updateExam: (
      token: string,
      id: number,
      payload: {
        title: string
        recruitment_no: string
        start_at: string
        end_at: string
        pass_ratio: number
        settings: ExamSettings
      },
    ) => request<ExamOut>(`/api/admin/exams/${id}`, { method: 'PUT', token, body: payload }),

    deleteExam: (token: string, id: number) =>
      request<{ ok: boolean }>(`/api/admin/exams/${id}`, { method: 'DELETE', token }),

    publishExam: (token: string, id: number) =>
      request<PublishResponse>(`/api/admin/exams/${id}/publish`, { method: 'POST', token }),

    archiveExam: (token: string, id: number) =>
      request<ExamOut>(`/api/admin/exams/${id}/archive`, { method: 'POST', token }),

    // ---------------- 管理端：名单与邀请码 ----------------
    listCandidates: (token: string, examId: number) =>
      request<CandidateRow[]>(`/api/admin/exams/${examId}/candidates`, { token }),

    importCandidates: (token: string, examId: number, csvText: string) =>
      request<RosterImportResponse>(`/api/admin/exams/${examId}/candidates/import`, {
        method: 'POST',
        token,
        rawBody: new TextEncoder().encode(csvText),
        contentType: 'text/csv; charset=utf-8',
      }),

    generateInvites: (token: string, examId: number, confirm: boolean) =>
      request<{ generated: number }>(`/api/admin/exams/${examId}/candidates/generate`, {
        method: 'POST',
        token,
        body: { confirm },
      }),

    exportInviteCodes: (token: string, examId: number) =>
      request<string>(`/api/admin/exams/${examId}/candidates/export`, { token }),

    // ---------------- 管理端：成绩与统计 ----------------
    getResults: (token: string, examId: number) =>
      request<ResultsResponse>(`/api/admin/exams/${examId}/results`, { token }),

    exportResults: (token: string, examId: number) =>
      request<string>(`/api/admin/exams/${examId}/results/export`, { token }),

    getStats: (token: string, examId: number) =>
      request<StatsResponse>(`/api/admin/exams/${examId}/stats`, { token }),
  }
}

export type ApiClient = ReturnType<typeof createApiClient>

/** 应用级默认客户端（同源，开发期由 Vite 代理到后端）。 */
export const api = createApiClient()
