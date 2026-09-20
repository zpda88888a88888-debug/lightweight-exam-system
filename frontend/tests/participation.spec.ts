/**
 * 名单参与状态（CH-010）。
 *
 * 试用反馈原话：
 *   "考生管理除了导入信息，生成邀请码之外，提供状态查询功能，看谁在考试，谁没来"
 */

import { describe, expect, it } from 'vitest'

import type { CandidateRow } from '@/api/client'
import {
  filterByStatus,
  participationClass,
  participationLabel,
  summarizeParticipation,
} from '@/lib/participation'

function candidate(userId: number, status: CandidateRow['status']): CandidateRow {
  return {
    user_id: userId,
    phone: `1380000000${userId}`,
    name: `考生${userId}`,
    id_card: `1101011990010100${userId}`,
    invite_code: '123456',
    status,
    started_at: status === 'not_started' ? null : '2026-09-19T10:00:00',
    submitted_at: status === 'submitted' || status === 'timeout_submitted' ? '2026-09-19T10:30:00' : null,
    score: status === 'submitted' || status === 'timeout_submitted' ? 80 : null,
  }
}

describe('状态标签', () => {
  it('四种状态都有中文标签', () => {
    expect(participationLabel('not_started')).toBe('未登录')
    expect(participationLabel('in_progress')).toBe('答题中')
    expect(participationLabel('submitted')).toBe('已交卷')
    expect(participationLabel('timeout_submitted')).toBe('超时交卷')
  })

  it('未知状态原样返回，不吞错', () => {
    expect(participationLabel('weird')).toBe('weird')
  })

  it('每种状态有对应的样式类（便于区分颜色）', () => {
    const classes = [
      participationClass('not_started'),
      participationClass('in_progress'),
      participationClass('submitted'),
      participationClass('timeout_submitted'),
    ]
    expect(new Set(classes).size).toBe(4)
  })
})

describe('summarizeParticipation', () => {
  it('统计各状态人数与已完成人数', () => {
    const rows = [
      candidate(1, 'not_started'),
      candidate(2, 'not_started'),
      candidate(3, 'in_progress'),
      candidate(4, 'submitted'),
      candidate(5, 'timeout_submitted'),
    ]

    const summary = summarizeParticipation(rows)
    expect(summary.total).toBe(5)
    expect(summary.not_started).toBe(2)
    expect(summary.in_progress).toBe(1)
    expect(summary.submitted).toBe(1)
    expect(summary.timeout_submitted).toBe(1)
    // 「已产生成绩」把正常交卷与超时交卷都算上
    expect(summary.finished).toBe(2)
  })

  it('空名单返回全 0，不报错', () => {
    const summary = summarizeParticipation([])
    expect(summary.total).toBe(0)
    expect(summary.finished).toBe(0)
    expect(summary.not_started).toBe(0)
  })

  it('各状态人数之和等于总人数', () => {
    const rows = [
      candidate(1, 'not_started'),
      candidate(2, 'in_progress'),
      candidate(3, 'submitted'),
    ]
    const s = summarizeParticipation(rows)
    expect(s.not_started + s.in_progress + s.submitted + s.timeout_submitted).toBe(s.total)
  })
})

describe('filterByStatus', () => {
  const rows = [
    candidate(1, 'not_started'),
    candidate(2, 'in_progress'),
    candidate(3, 'submitted'),
    candidate(4, 'not_started'),
  ]

  it('空值返回全部（"全部"选项）', () => {
    expect(filterByStatus(rows, '')).toHaveLength(4)
  })

  it('按「没来的」筛选', () => {
    const missing = filterByStatus(rows, 'not_started')
    expect(missing.map((r) => r.user_id)).toEqual([1, 4])
  })

  it('按「正在考试的」筛选', () => {
    expect(filterByStatus(rows, 'in_progress').map((r) => r.user_id)).toEqual([2])
  })

  it('无匹配返回空数组', () => {
    expect(filterByStatus(rows, 'timeout_submitted')).toEqual([])
  })
})
