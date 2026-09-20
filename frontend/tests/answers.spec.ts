/**
 * 答案选择与未答题计数（测试方案 6.12：提前交卷提示未答题数）。
 */

import { describe, expect, it } from 'vitest'

import {
  answeredCount,
  isAnswered,
  toSubmitPayload,
  toggleAnswer,
  unansweredCount,
} from '@/lib/answers'

describe('toggleAnswer — 单选/判断', () => {
  it('点选后选中该项', () => {
    expect(toggleAnswer('single', [], 'B')).toEqual(['B'])
  })

  it('再点其他项则替换（单选只能一个答案）', () => {
    expect(toggleAnswer('single', ['B'], 'C')).toEqual(['C'])
  })

  it('再点已选中的项保持选中（不会变成空）', () => {
    expect(toggleAnswer('single', ['B'], 'B')).toEqual(['B'])
  })

  it('判断题与单选语义一致', () => {
    expect(toggleAnswer('judge', [], '对')).toEqual(['对'])
    expect(toggleAnswer('judge', ['对'], '错')).toEqual(['错'])
  })
})

describe('toggleAnswer — 多选', () => {
  it('点选累加', () => {
    expect(toggleAnswer('multi', [], 'A')).toEqual(['A'])
    expect(toggleAnswer('multi', ['A'], 'B')).toEqual(['A', 'B'])
  })

  it('再点已选项则取消', () => {
    expect(toggleAnswer('multi', ['A', 'B'], 'A')).toEqual(['B'])
  })

  it('取消到空是合法状态（多选不选得 0 分）', () => {
    expect(toggleAnswer('multi', ['A'], 'A')).toEqual([])
  })

  it('不修改传入数组（纯函数）', () => {
    const original = ['A']
    toggleAnswer('multi', original, 'B')
    expect(original).toEqual(['A'])
  })
})

describe('isAnswered', () => {
  it('非空数组视为已作答', () => {
    expect(isAnswered(['A'])).toBe(true)
  })

  it('空数组、undefined、null 视为未作答', () => {
    expect(isAnswered([])).toBe(false)
    expect(isAnswered(undefined)).toBe(false)
    expect(isAnswered(null)).toBe(false)
  })
})

describe('answeredCount / unansweredCount', () => {
  const questions = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }]

  it('统计已答与未答题数', () => {
    const answers = { 1: ['A'], 3: ['A', 'B'] }
    expect(answeredCount(questions, answers)).toBe(2)
    expect(unansweredCount(questions, answers)).toBe(2)
  })

  it('全部未答时未答数为题目总数', () => {
    expect(unansweredCount(questions, {})).toBe(4)
  })

  it('全部已答时未答数为 0', () => {
    const answers = { 1: ['A'], 2: ['B'], 3: ['C'], 4: ['对'] }
    expect(unansweredCount(questions, answers)).toBe(0)
  })

  it('空答案数组不计入已答', () => {
    expect(answeredCount([{ id: 1 }], { 1: [] })).toBe(0)
  })
})

describe('toSubmitPayload', () => {
  it('按试卷顺序输出，未答题以空数组提交', () => {
    const questions = [{ id: 11 }, { id: 22 }]
    const payload = toSubmitPayload(questions, { 11: ['A', 'B'] })

    expect(payload).toEqual([
      { question_id: 11, answer: ['A', 'B'] },
      { question_id: 22, answer: [] },
    ])
  })

  it('提交的是原始选项标识，与显示顺序无关', () => {
    const payload = toSubmitPayload([{ id: 1 }], { 1: ['D'] })
    expect(payload[0].answer).toEqual(['D'])
  })
})
