/**
 * 考生管理（CH-007 / CH-009 / CH-010）。
 *
 * 相关试用反馈：
 *   "考生管理关联考试场次的时候，如果场次很多，下拉框不好选，参考考试管理的查询"
 *   "考生管理除了导入信息，生成邀请码之外，提供状态查询功能，看谁在考试，谁没来"
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  listExamsMock,
  listCandidatesMock,
  importCandidatesMock,
  generateInvitesMock,
  exportInviteCodesMock,
  replaceMock,
  routeQuery,
  downloadTextMock,
} = vi.hoisted(() => ({
  listExamsMock: vi.fn(),
  listCandidatesMock: vi.fn(),
  importCandidatesMock: vi.fn(),
  generateInvitesMock: vi.fn(),
  exportInviteCodesMock: vi.fn(),
  replaceMock: vi.fn(),
  routeQuery: {} as Record<string, string>,
  downloadTextMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  useRoute: () => ({ query: routeQuery }),
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
    listExams: listExamsMock,
    listCandidates: listCandidatesMock,
    importCandidates: importCandidatesMock,
    generateInvites: generateInvitesMock,
    exportInviteCodes: exportInviteCodesMock,
  },
}))

import { adminSession } from '@/admin/session'
import CandidatesView from '@/admin/views/CandidatesView.vue'

type Status = 'not_started' | 'in_progress' | 'submitted' | 'timeout_submitted'

function exam(id: number, title: string, no: string, status: 'draft' | 'published' = 'draft') {
  return {
    id,
    title,
    recruitment_no: no,
    status,
    external_status: status === 'draft' ? ('draft' as const) : ('running' as const),
    start_at: '2026-09-19T09:00:00',
    end_at: '2026-09-19T11:00:00',
    pass_ratio: 60,
    settings: { rules: [] },
    created_at: '2026-09-19T08:00:00',
    published_at: status === 'draft' ? null : '2026-09-19T08:30:00',
  }
}

function candidate(userId: number, name: string, status: Status, invite: string | null = '123456') {
  return {
    user_id: userId,
    phone: `1380000000${userId}`,
    name,
    id_card: `1101011990010100${userId}`,
    invite_code: invite,
    status,
    started_at: status === 'not_started' ? null : '2026-09-19T09:10:00',
    submitted_at:
      status === 'submitted' || status === 'timeout_submitted' ? '2026-09-19T09:40:00' : null,
    score: status === 'submitted' || status === 'timeout_submitted' ? 80 : null,
  }
}

const DRAFT_EXAM = exam(1, '草稿考试', 'ZP-DRAFT', 'draft')
const PUBLISHED_EXAM = exam(2, '已发布考试', 'ZP-PUB', 'published')

const ROSTER = [
  candidate(1, '张三', 'submitted'),
  candidate(2, '李四', 'in_progress'),
  candidate(3, '王五', 'not_started'),
  candidate(4, '赵六', 'timeout_submitted'),
]

function mountView() {
  return mount(CandidatesView)
}

beforeEach(() => {
  adminSession.token = 'test-token'
  for (const key of Object.keys(routeQuery)) delete routeQuery[key]
  listExamsMock.mockReset().mockResolvedValue([DRAFT_EXAM, PUBLISHED_EXAM])
  listCandidatesMock.mockReset().mockResolvedValue([])
  importCandidatesMock.mockReset().mockResolvedValue({
    users_created: 1, users_updated: 0, linked: 1, total_rows: 1,
  })
  generateInvitesMock.mockReset().mockResolvedValue({ generated: 1 })
  exportInviteCodesMock.mockReset().mockResolvedValue('csv')
  replaceMock.mockReset()
  downloadTextMock.mockReset()
})

describe('场次查询与选择（CH-009）', () => {
  it('用「查询 + 结果列表」而不是下拉框', async () => {
    const wrapper = mountView()
    await flushPromises()

    // 查询条件与考试管理一致
    expect(wrapper.find('#p-status').exists()).toBe(true)
    expect(wrapper.find('#p-no').exists()).toBe(true)
    expect(wrapper.find('#p-title').exists()).toBe(true)
    expect(wrapper.find('#p-from').attributes('type')).toBe('date')
    expect(wrapper.find('#p-to').attributes('type')).toBe('date')

    // 不再使用下拉框
    expect(wrapper.find('#exam-select').exists()).toBe(false)

    // 结果以可点击行呈现
    expect(wrapper.findAll('.exam-row')).toHaveLength(2)
  })

  it('首次加载不带查询条件', async () => {
    mountView()
    await flushPromises()

    expect(listExamsMock).toHaveBeenCalledWith('test-token', {
      status: undefined,
      recruitment_no: undefined,
      title: undefined,
      start_from: undefined,
      start_to: undefined,
    })
  })

  it('按名称 / 状态 / 编号查询会下发参数', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('#p-title').setValue('草稿')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(listExamsMock.mock.calls.at(-1)![1]).toMatchObject({ title: '草稿' })

    await wrapper.find('#p-status').setValue('draft')
    await flushPromises()
    expect(listExamsMock.mock.calls.at(-1)![1]).toMatchObject({ status: 'draft' })

    await wrapper.find('#p-no').setValue('ZP')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(listExamsMock.mock.calls.at(-1)![1]).toMatchObject({ recruitment_no: 'ZP' })
  })

  it('开考时间按本地日期换算为 UTC 区间', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('#p-from').setValue('2026-09-19')
    await wrapper.find('#p-to').setValue('2026-09-19')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()

    const args = listExamsMock.mock.calls.at(-1)![1]
    expect(args.start_from).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/)
    expect(args.start_to).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/)
    expect(args.start_from < args.start_to).toBe(true)
  })

  it('点选场次后收起选择器、记住场次并加载名单', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('.exam-row')[0].trigger('click')
    await flushPromises()

    expect(replaceMock).toHaveBeenCalledWith({ query: { exam: '1' } })
    expect(listCandidatesMock).toHaveBeenCalledWith('test-token', 1)
    // 选择器收起，改显示已选栏
    expect(wrapper.find('#p-title').exists()).toBe(false)
    expect(wrapper.text()).toContain('更换场次')
  })

  it('支持 ?exam=<id> 预选场次（从考试管理跳转）', async () => {
    routeQuery.exam = '2'
    const wrapper = mountView()
    await flushPromises()

    expect(listCandidatesMock).toHaveBeenCalledWith('test-token', 2)
    expect(wrapper.text()).toContain('已发布考试')
  })

  it('「更换场次」重新打开选择器', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.exam-row')[0].trigger('click')
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text() === '更换场次')!.trigger('click')
    await flushPromises()

    expect(wrapper.find('#p-title').exists()).toBe(true)
  })

  it('无匹配时区分「没有考试」与「查询无结果」', async () => {
    listExamsMock.mockResolvedValue([])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('还没有任何考试')

    await wrapper.find('#p-title').setValue('不存在')
    await wrapper.findAll('button').find((b) => b.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('没有符合查询条件的考试')

    // 有查询条件时出现「清除」
    expect(wrapper.findAll('button').some((b) => b.text() === '清除')).toBe(true)
  })
})

describe('参与状态查询（CH-010）', () => {
  async function mountSelected() {
    routeQuery.exam = '2'
    listCandidatesMock.mockResolvedValue(ROSTER)
    const wrapper = mountView()
    await flushPromises()
    return wrapper
  }

  it('汇总各状态人数，直接回答"谁在考试、谁没来"', async () => {
    const wrapper = await mountSelected()
    const text = wrapper.text()

    expect(text).toContain('名单 4 人')
    expect(text).toContain('已产生成绩 2 人')
    expect(text).toContain('未登录 1 人')

    const chips = wrapper.findAll('.chip').map((c) => c.text().replace(/\s+/g, ''))
    expect(chips).toEqual(['全部4', '未登录1', '答题中1', '已交卷1', '超时交卷1'])
  })

  it('名单表格显示每人的状态', async () => {
    const wrapper = await mountSelected()

    const rows = wrapper.findAll('tbody tr')
    const byName: Record<string, string> = {}
    for (const tr of rows) {
      byName[tr.findAll('td')[1].text()] = tr.find('.p-status').text()
    }

    expect(byName).toEqual({
      张三: '已交卷',
      李四: '答题中',
      王五: '未登录',
      赵六: '超时交卷',
    })
  })

  it('点状态标签可筛选名单', async () => {
    const wrapper = await mountSelected()

    await wrapper.findAll('.chip').find((c) => c.text().includes('答题中'))!.trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('李四')
    expect(rows[0].text()).not.toContain('张三')
  })

  it('筛选后各状态人数仍按全量统计（不因筛选而失真）', async () => {
    const wrapper = await mountSelected()

    await wrapper.findAll('.chip').find((c) => c.text().includes('未登录'))!.trigger('click')
    await flushPromises()

    // 表格只剩 1 人，但「全部」标签仍是 4
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    const allChip = wrapper.findAll('.chip').find((c) => c.text().includes('全部'))!
    expect(allChip.text().replace(/\s+/g, '')).toBe('全部4')
  })

  it('无该状态考生时给出空态', async () => {
    routeQuery.exam = '2'
    listCandidatesMock.mockResolvedValue([candidate(1, '张三', 'submitted')])
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('.chip').find((c) => c.text().includes('未登录'))!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('没有该状态的考生')
  })

  it('显示得分与交卷时间，未交卷时为「—」', async () => {
    const wrapper = await mountSelected()

    const rows = wrapper.findAll('tbody tr')
    const submitted = rows.find((tr) => tr.text().includes('张三'))!
    const notStarted = rows.find((tr) => tr.text().includes('王五'))!

    expect(submitted.text()).toContain('80')
    expect(notStarted.findAll('td')[6].text()).toBe('—')
    expect(notStarted.findAll('td')[7].text()).toBe('—')
  })
})

describe('草稿场次：可导入与生成邀请码', () => {
  async function mountDraft(roster = ROSTER) {
    routeQuery.exam = '1'
    listCandidatesMock.mockResolvedValue(roster)
    const wrapper = mountView()
    await flushPromises()
    return wrapper
  }

  it('展示导入名单入口并带所选场次 id', async () => {
    const wrapper = await mountDraft([])

    expect(wrapper.text()).toContain('导入考生名单')
    await wrapper.find('textarea').setValue('手机号,姓名,身份证号\n13800000001,张三,110101199001010011\n')
    await wrapper.findAll('button').find((b) => b.text().includes('导入到本场考试'))!.trigger('click')
    await flushPromises()

    expect(importCandidatesMock).toHaveBeenCalledWith('test-token', 1, expect.stringContaining('张三'))
  })

  it('空内容导入被拦截', async () => {
    const wrapper = await mountDraft([])
    await wrapper.findAll('button').find((b) => b.text().includes('导入到本场考试'))!.trigger('click')
    await flushPromises()

    expect(importCandidatesMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请粘贴 CSV 内容或选择文件')
  })

  it('已有邀请码时按钮为「重新生成」并提示旧码失效', async () => {
    const wrapper = await mountDraft()

    await wrapper.findAll('button').find((b) => b.text() === '重新生成邀请码')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('旧码立即失效')

    await wrapper.findAll('button').find((b) => b.text() === '确认生成')!.trigger('click')
    await flushPromises()
    expect(generateInvitesMock).toHaveBeenCalledWith('test-token', 1, true)
  })

  it('首次生成不出现"覆盖旧码"提示', async () => {
    const wrapper = await mountDraft([candidate(1, '张三', 'not_started', null)])

    expect(wrapper.findAll('button').some((b) => b.text() === '生成邀请码')).toBe(true)
    await wrapper.findAll('button').find((b) => b.text() === '生成邀请码')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧码立即失效')
  })

  it('导出邀请码 CSV', async () => {
    const wrapper = await mountDraft()
    await wrapper.findAll('button').find((b) => b.text() === '导出邀请码 CSV')!.trigger('click')
    await flushPromises()

    expect(exportInviteCodesMock).toHaveBeenCalledWith('test-token', 1)
    expect(downloadTextMock).toHaveBeenCalled()
  })

  it('名单为空时禁用生成与导出', async () => {
    const wrapper = await mountDraft([])
    const buttons = wrapper.findAll('button')
    expect(buttons.find((b) => b.text() === '生成邀请码')!.attributes('disabled')).toBeDefined()
    expect(buttons.find((b) => b.text() === '导出邀请码 CSV')!.attributes('disabled')).toBeDefined()
  })
})

describe('已发布场次：只读', () => {
  it('提示冻结、无导入入口、无生成按钮，但状态查询仍可用', async () => {
    routeQuery.exam = '2'
    listCandidatesMock.mockResolvedValue(ROSTER)
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('已冻结')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.findAll('button').some((b) => b.text().includes('生成邀请码'))).toBe(false)
    // 状态查询仍然可用（考试进行中时最需要看谁没来）
    expect(wrapper.findAll('.chip')).toHaveLength(5)
    expect(wrapper.findAll('tbody tr')).toHaveLength(4)
  })
})
