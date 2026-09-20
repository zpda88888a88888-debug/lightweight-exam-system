/**
 * 名单参与状态（CH-010）。
 *
 * 用于回答"谁在考试、谁没来"：
 *   未登录   —— 从未用邀请码登录过（没有 attempt）
 *   答题中   —— 已登录并开始答题，尚未交卷（这才是"正在考试"）
 *   已交卷   —— 截止前正常提交
 *   超时交卷 —— 到达截止时间后才提交
 */

import type { CandidateRow } from '@/api/client'

export type ParticipationStatus =
  | 'not_started'
  | 'in_progress'
  | 'submitted'
  | 'timeout_submitted'

export const PARTICIPATION_OPTIONS: { value: ParticipationStatus; label: string }[] = [
  { value: 'not_started', label: '未登录' },
  { value: 'in_progress', label: '答题中' },
  { value: 'submitted', label: '已交卷' },
  { value: 'timeout_submitted', label: '超时交卷' },
]

const LABELS: Record<string, string> = Object.fromEntries(
  PARTICIPATION_OPTIONS.map((item) => [item.value, item.label]),
)

const CLASSES: Record<string, string> = {
  not_started: 'p-not-started',
  in_progress: 'p-in-progress',
  submitted: 'p-submitted',
  timeout_submitted: 'p-timeout',
}

export function participationLabel(status: string): string {
  return LABELS[status] ?? status
}

export function participationClass(status: string): string {
  return CLASSES[status] ?? 'p-not-started'
}

export interface ParticipationSummary {
  total: number
  not_started: number
  in_progress: number
  submitted: number
  timeout_submitted: number
  /** 已产生最终成绩的人数（已交卷 + 超时交卷） */
  finished: number
}

/**
 * 统计各状态人数。
 *
 * 注意：必须对**全量名单**统计，而不是当前筛选后的子集，
 * 否则"未登录 0 人"这种结论会随着筛选条件变化而失真。
 */
export function summarizeParticipation(rows: CandidateRow[]): ParticipationSummary {
  const summary: ParticipationSummary = {
    total: rows.length,
    not_started: 0,
    in_progress: 0,
    submitted: 0,
    timeout_submitted: 0,
    finished: 0,
  }
  for (const row of rows) {
    if (row.status === 'not_started') summary.not_started += 1
    else if (row.status === 'in_progress') summary.in_progress += 1
    else if (row.status === 'submitted') summary.submitted += 1
    else if (row.status === 'timeout_submitted') summary.timeout_submitted += 1
  }
  summary.finished = summary.submitted + summary.timeout_submitted
  return summary
}

/** 按状态筛选（空值表示全部）。 */
export function filterByStatus(
  rows: CandidateRow[],
  status: ParticipationStatus | '',
): CandidateRow[] {
  if (!status) return rows
  return rows.filter((row) => row.status === status)
}
