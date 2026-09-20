/**
 * 考试列表查询与操作列（CH-006 / CH-007）。
 *
 * 试用反馈原话：
 *   "考试管理应该增加查询功能，考试多了之后，支持按状态、选聘编号、
 *    开考时间、名称（模糊查询）查询列表"
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listExamsMock, listTagsMock, pushMock } = vi.hoisted(() => ({
  listExamsMock: vi.fn(),
  listTagsMock: vi.fn(),
  pushMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@/api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 500
    detail = ''
  },
  api: {
    listExams: listExamsMock,
    listTags: listTagsMock,
    createExam: vi.fn(),
    updateExam: vi.fn(),
    deleteExam: vi.fn(),
    publishExam: vi.fn(),
    archiveExam: vi.fn(),
  },
}))

import { adminSession } from '@/admin/session'
import ExamsView from '@/admin/views/ExamsView.vue'

const DRAFT = {
  id: 1,
  title: '草稿考试',
  recruitment_no: 'ZP-DRAFT',
  status: 'draft' as const,
  external_status: 'draft' as const,
  start_at: '2026-09-19T09:00:00',
  end_at: '2026-09-19T11:00:00',
  pass_ratio: 60,
  settings: { rules: [] },
  created_at: '2026-09-19T08:00:00',
  published_at: null,
}

const PUBLISHED = {
  ...DRAFT,
  id: 2,
  title: '已发布考试',
  recruitment_no: 'ZP-PUB',
  status: 'published' as const,
  external_status: 'running' as const,
}

beforeEach(() => {
  adminSession.token = 'test-token'
  listExamsMock.mockReset().mockResolvedValue([DRAFT, PUBLISHED])
  listTagsMock.mockReset().mockResolvedValue([])
  pushMock.mockReset()
})

describe('查询条件（CH-006）', () => {
  it('提供状态、选聘编号、名称、开考时间起止五个条件', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    expect(wrapper.find('#q-status').exists()).toBe(true)
    expect(wrapper.find('#q-no').exists()).toBe(true)
    expect(wrapper.find('#q-title').exists()).toBe(true)
    expect(wrapper.find('#q-from').attributes('type')).toBe('date')
    expect(wrapper.find('#q-to').attributes('type')).toBe('date')

    const statusOptions = wrapper.findAll('#q-status option').map((o) => o.text())
    expect(statusOptions).toEqual(['全部', '草稿', '未开始', '进行中', '已结束', '已归档'])
  })

  it('首次加载不带任何查询条件', async () => {
    mount(ExamsView)
    await flushPromises()

    expect(listExamsMock).toHaveBeenCalledWith('test-token', {
      status: undefined,
      recruitment_no: undefined,
      title: undefined,
      start_from: undefined,
      start_to: undefined,
    })
  })

  it('按名称模糊查询会作为参数下发', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    await wrapper.find('#q-title').setValue('已发布')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()

    expect(listExamsMock).toHaveBeenLastCalledWith(
      'test-token',
      expect.objectContaining({ title: '已发布' }),
    )
  })

  it('按状态查询会作为参数下发', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    await wrapper.find('#q-status').setValue('draft')
    await flushPromises()

    expect(listExamsMock).toHaveBeenLastCalledWith(
      'test-token',
      expect.objectContaining({ status: 'draft' }),
    )
  })

  it('开考时间按本地日期换算为 UTC 区间下发', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    await wrapper.find('#q-from').setValue('2026-09-19')
    await wrapper.find('#q-to').setValue('2026-09-19')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()

    const args = listExamsMock.mock.calls.at(-1)![1]
    expect(args.start_from).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/)
    expect(args.start_to).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/)
    // 起始 < 截止，覆盖整天
    expect(args.start_from < args.start_to).toBe(true)
  })

  it('有查询条件时出现「清除」，点击后清空并重新加载', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    expect(wrapper.findAll('button').some((b) => b.text() === '清除')).toBe(false)

    await wrapper.find('#q-title').setValue('草稿')
    await flushPromises()
    const clearButton = wrapper.findAll('button').find((b) => b.text() === '清除')!
    await clearButton.trigger('click')
    await flushPromises()

    expect((wrapper.find('#q-title').element as HTMLInputElement).value).toBe('')
    expect(listExamsMock.mock.calls.at(-1)![1].title).toBeUndefined()
  })

  it('查询无结果时给出空态与清除入口', async () => {
    listExamsMock.mockResolvedValue([])
    const wrapper = mount(ExamsView)
    await flushPromises()

    // 无过滤条件 → 常规空态
    expect(wrapper.text()).toContain('暂无考试，请先新建')

    await wrapper.find('#q-title').setValue('不存在')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('没有符合查询条件的考试')
  })
})

describe('操作列按状态区分（CH-007）', () => {
  it('草稿：编辑 / 发布 / 名单与邀请码 / 删除', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    const row = wrapper.findAll('tr').find((tr) => tr.text().includes('ZP-DRAFT'))!
    const texts = row.findAll('button').map((b) => b.text())

    expect(texts).toEqual(['编辑', '发布', '名单与邀请码', '删除'])
  })

  it('已发布：成绩/统计 / 查看试卷 / 归档', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    const row = wrapper.findAll('tr').find((tr) => tr.text().includes('ZP-PUB'))!
    const texts = row.findAll('button').map((b) => b.text())

    expect(texts).toEqual(['成绩/统计', '查看试卷', '归档'])
  })

  it('「名单与邀请码」跳转到考生管理并带上场次 id', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    const row = wrapper.findAll('tr').find((tr) => tr.text().includes('ZP-DRAFT'))!
    await row.findAll('button').find((b) => b.text() === '名单与邀请码')!.trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      name: 'admin-candidates',
      query: { exam: String(DRAFT.id) },
    })
  })

  it('「成绩/统计」进入考试详情', async () => {
    const wrapper = mount(ExamsView)
    await flushPromises()

    const row = wrapper.findAll('tr').find((tr) => tr.text().includes('ZP-PUB'))!
    await row.findAll('button').find((b) => b.text() === '成绩/统计')!.trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      name: 'admin-exam-detail',
      params: { id: PUBLISHED.id },
    })
  })
})
