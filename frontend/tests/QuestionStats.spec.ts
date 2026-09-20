/**
 * 题库统计展示（CH-008）。
 *
 * 试用反馈原话：
 *   "题库管理新增统计功能，能看到每个题目上次被随机抽中的考试名称和时间，
 *    累计答题正确率"
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listQuestionsMock, exportQuestionsMock, downloadTextMock } = vi.hoisted(() => ({
  listQuestionsMock: vi.fn(),
  exportQuestionsMock: vi.fn(),
  downloadTextMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/lib/download', () => ({
  downloadText: downloadTextMock,
  timestampedName: (prefix: string, ext: string) => `${prefix}.${ext}`,
}))

vi.mock('@/api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 500
    detail = ''
    constructor(status: number, detail: string) {
      super(detail)
      this.status = status
      this.detail = detail
    }
  },
  api: {
    listQuestions: listQuestionsMock,
    exportQuestions: exportQuestionsMock,
    createQuestion: vi.fn(),
    updateQuestion: vi.fn(),
    deleteQuestion: vi.fn(),
    importQuestions: vi.fn(),
  },
}))

import { adminSession } from '@/admin/session'
import QuestionsView from '@/admin/views/QuestionsView.vue'

function question(id: number, stem: string, stats: unknown) {
  return {
    id,
    type: 'single' as const,
    stem,
    options: [
      { key: 'A', text: '对' },
      { key: 'B', text: '错' },
    ],
    answer: ['A'],
    score: 10,
    tags: ['标签'],
    analysis: '',
    updated_at: '2026-09-19T10:00:00',
    stats,
  }
}

const DRAWN = question(1, '被抽中过的题', {
  last_drawn_exam_id: 7,
  last_drawn_exam_title: '安全生产考试',
  last_drawn_at: '2026-09-19T10:00:00',
  answer_count: 8,
  correct_count: 6,
  correct_rate: 0.75,
})

const NEVER_DRAWN = question(2, '从未被抽中的题', {
  last_drawn_exam_id: null,
  last_drawn_exam_title: null,
  last_drawn_at: null,
  answer_count: 0,
  correct_count: 0,
  correct_rate: null,
})

const DRAWN_NO_ANSWERS = question(3, '被抽中但无人作答', {
  last_drawn_exam_id: 7,
  last_drawn_exam_title: '安全生产考试',
  last_drawn_at: '2026-09-19T10:00:00',
  answer_count: 0,
  correct_count: 0,
  correct_rate: null,
})

beforeEach(() => {
  adminSession.token = 'test-token'
  listQuestionsMock.mockReset().mockResolvedValue([DRAWN, NEVER_DRAWN, DRAWN_NO_ANSWERS])
  exportQuestionsMock.mockReset().mockResolvedValue('ID,题型,题干\n')
  downloadTextMock.mockReset()
})

describe('题库统计列（CH-008）', () => {
  it('表头包含「上次被抽中」与「累计正确率」', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const headers = wrapper.findAll('thead th').map((th) => th.text())
    expect(headers).toContain('上次被抽中')
    expect(headers).toContain('累计正确率')
  })

  it('显示上次被抽中的考试名称与时间', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const row = wrapper.findAll('tbody tr').find((tr) => tr.text().includes('被抽中过的题'))!
    expect(row.text()).toContain('安全生产考试')
    // 时间以本地可读格式展示
    expect(row.find('.drawn-time').text()).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })

  it('累计正确率按百分比展示，并给出样本量', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const row = wrapper.findAll('tbody tr').find((tr) => tr.text().includes('被抽中过的题'))!
    expect(row.text()).toContain('75%')
    expect(row.text()).toContain('（6/8）')
  })

  it('从未被抽中时显示「暂无」而不是空白或 0%', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const row = wrapper.findAll('tbody tr').find((tr) => tr.text().includes('从未被抽中的题'))!
    expect(row.text()).toContain('暂无')
    expect(row.text()).not.toContain('0%')
  })

  it('被抽中但从未被作答时，正确率显示「暂无」而考试名称照常显示', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const row = wrapper.findAll('tbody tr').find((tr) => tr.text().includes('被抽中但无人作答'))!
    expect(row.text()).toContain('安全生产考试')
    expect(row.text()).toContain('暂无')
    // 不能显示成 0%，否则会被误读为"没人做对"
    expect(row.text()).not.toContain('0%')
  })

  it('统计缺失（字段为 null）时不报错，按「暂无」渲染', async () => {
    listQuestionsMock.mockResolvedValue([question(9, '无统计字段', null)])
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const row = wrapper.findAll('tbody tr').find((tr) => tr.text().includes('无统计字段'))!
    expect(row.text()).toContain('暂无')
  })

  it('筛选后仍展示统计（后端在列表接口一并返回）', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    await wrapper.find('#f-keyword').setValue('被抽中过的题')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()

    expect(listQuestionsMock).toHaveBeenLastCalledWith('test-token', {
      type: undefined,
      tag: undefined,
      keyword: '被抽中过的题',
    })
  })
})

describe('题库导出（CH-011）', () => {
  it('提供「导出题库 CSV」按钮并调用导出接口', async () => {
    const wrapper = mount(QuestionsView)
    await flushPromises()

    const button = wrapper.findAll('button').find((b) => b.text() === '导出题库 CSV')
    expect(button).toBeTruthy()

    await button!.trigger('click')
    await flushPromises()

    expect(exportQuestionsMock).toHaveBeenCalledWith('test-token')
    expect(downloadTextMock).toHaveBeenCalledWith('题库.csv', expect.any(String))
  })

  it('导出失败时展示后端原因，不静默吞掉', async () => {
    const { ApiError } = await import('@/api/client')
    exportQuestionsMock.mockRejectedValue(new ApiError(500, '导出炸了'))

    const wrapper = mount(QuestionsView)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '导出题库 CSV')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('导出炸了')
  })
})
