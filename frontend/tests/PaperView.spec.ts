/**
 * 试卷管理（CH-002）。
 *
 * 试用反馈原话："管理端应该有试卷管理模块，现在管理端无法查看考试和试卷的对应关系"
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listExamsMock, getAdminPaperMock, pushMock } = vi.hoisted(() => ({
  listExamsMock: vi.fn(),
  getAdminPaperMock: vi.fn(),
  pushMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
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
    listExams: listExamsMock,
    getAdminPaper: getAdminPaperMock,
  },
}))

import { ApiError } from '@/api/client'
import { adminSession } from '@/admin/session'
import PaperDetailView from '@/admin/views/PaperDetailView.vue'
import PapersView from '@/admin/views/PapersView.vue'

const PUBLISHED_EXAM = {
  id: 1,
  title: '安全生产考试',
  recruitment_no: 'ZP-001',
  status: 'published' as const,
  external_status: 'running' as const,
  start_at: '2026-09-19T09:00:00',
  end_at: '2026-09-19T11:00:00',
  pass_ratio: 60,
  settings: { rules: [{ tag: '安全生产', count: 2 }] },
  created_at: '2026-09-19T08:00:00',
  published_at: '2026-09-19T08:30:00',
}

const DRAFT_EXAM = {
  ...PUBLISHED_EXAM,
  id: 2,
  title: '未发布的考试',
  recruitment_no: 'ZP-002',
  status: 'draft' as const,
  external_status: 'draft' as const,
  published_at: null,
}

const PAPER = {
  exam: PUBLISHED_EXAM,
  question_count: 2,
  total_score: 25,
  questions: [
    {
      seq: 0,
      question_id: 11,
      type: 'single' as const,
      stem: '我国安全生产方针是？',
      options: [
        { key: 'A', text: '安全第一' },
        { key: 'B', text: '生产第一' },
      ],
      answer: ['A'],
      score: 10,
      analysis: '依据安全生产法',
    },
    {
      seq: 1,
      question_id: 12,
      type: 'multi' as const,
      stem: '属于特种作业的有？',
      options: [
        { key: 'A', text: '电工' },
        { key: 'B', text: '焊接' },
        { key: 'C', text: '文秘' },
      ],
      answer: ['A', 'B'],
      score: 15,
      analysis: '',
    },
  ],
}


/** 详情页模板里用了 <router-link>，测试环境需 stub 掉 */
function mountDetail(id: string) {
  return mount(PaperDetailView, {
    props: { id },
    global: { stubs: { 'router-link': true } },
  })
}

beforeEach(() => {
  adminSession.token = 'test-token'
  listExamsMock.mockReset().mockResolvedValue([PUBLISHED_EXAM, DRAFT_EXAM])
  getAdminPaperMock.mockReset().mockResolvedValue(PAPER)
  pushMock.mockReset()
})

describe('PapersView 列表', () => {
  it('展示考试与试卷的对应关系（题数、总分）', async () => {
    const wrapper = mount(PapersView)
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('安全生产考试')
    expect(text).toContain('ZP-001')
    // 题数与总分来自试卷快照
    expect(text).toContain('25')
    expect(text).toContain('60%')
  })

  it('草稿考试不出现在试卷列表中（草稿没有试卷）', async () => {
    const wrapper = mount(PapersView)
    await flushPromises()

    expect(wrapper.text()).not.toContain('未发布的考试')
    expect(getAdminPaperMock).toHaveBeenCalledTimes(1)
    expect(getAdminPaperMock).toHaveBeenCalledWith('test-token', 1)
  })

  it('说明试卷是只读快照', async () => {
    const wrapper = mount(PapersView)
    await flushPromises()

    expect(wrapper.text()).toContain('发布时生成的快照')
    expect(wrapper.text()).toContain('不可修改')
  })

  it('无已发布考试时给出可操作的下一步', async () => {
    listExamsMock.mockResolvedValue([DRAFT_EXAM])
    const wrapper = mount(PapersView)
    await flushPromises()

    expect(wrapper.text()).toContain('暂无已发布的考试')
    expect(wrapper.text()).toContain('发布')
  })

  it('点「查看试卷」跳转到试卷详情', async () => {
    const wrapper = mount(PapersView)
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text() === '查看试卷')!.trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      name: 'admin-paper-detail',
      params: { id: PUBLISHED_EXAM.id },
    })
  })
})

describe('PaperDetailView 详情', () => {
  it('渲染题目、选项与正确答案标记', async () => {
    const wrapper = mountDetail('1')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('我国安全生产方针是？')
    expect(text).toContain('属于特种作业的有？')
    expect(text).toContain('单选题')
    expect(text).toContain('多选题')
    // 选项与分值
    expect(text).toContain('安全第一')
    expect(text).toContain('10 分')
    expect(text).toContain('15 分')
    // 正确答案被标记
    expect(wrapper.findAll('.option.is-correct')).toHaveLength(3) // A + A、B
    expect(text).toContain('正确答案')
  })

  it('显示试卷总分与题数', async () => {
    const wrapper = mountDetail('1')
    await flushPromises()

    expect(wrapper.text()).toContain('25')
    expect(wrapper.text()).toContain('及格比例')
  })

  it('明确标注只读，且不提供任何改题入口', async () => {
    const wrapper = mountDetail('1')
    await flushPromises()

    expect(wrapper.text()).toContain('只读')
    const buttonTexts = wrapper.findAll('button').map((b) => b.text())
    expect(buttonTexts.some((t) => t.includes('编辑'))).toBe(false)
    expect(buttonTexts.some((t) => t.includes('换题'))).toBe(false)
    expect(buttonTexts.some((t) => t.includes('保存'))).toBe(false)
  })

  it('草稿考试：展示后端返回的「尚未发布」原因', async () => {
    getAdminPaperMock.mockRejectedValue(new ApiError(409, '该考试尚未发布，暂无试卷'))

    const wrapper = mountDetail('2')
    await flushPromises()

    expect(wrapper.text()).toContain('该考试尚未发布，暂无试卷')
    expect(wrapper.findAll('.question')).toHaveLength(0)
  })

  it('显示解析（管理端可见）', async () => {
    const wrapper = mountDetail('1')
    await flushPromises()

    expect(wrapper.text()).toContain('依据安全生产法')
  })
})
