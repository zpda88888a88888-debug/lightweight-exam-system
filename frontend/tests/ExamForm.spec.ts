/**
 * 考试表单（CH-004 及格比例说明、CH-005 标签封闭选项）。
 *
 * 试用反馈原话：
 *   "及格比例，页面增加说明"
 *   "组卷规则（按标签抽题），把标签都展示出来，让管理员通过封闭选项选择"
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listExamsMock, listTagsMock, createExamMock, pushMock } = vi.hoisted(() => ({
  listExamsMock: vi.fn(),
  listTagsMock: vi.fn(),
  createExamMock: vi.fn(),
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
    createExam: createExamMock,
    updateExam: vi.fn(),
    deleteExam: vi.fn(),
    publishExam: vi.fn(),
    archiveExam: vi.fn(),
  },
}))

import { adminSession } from '@/admin/session'
import ExamsView from '@/admin/views/ExamsView.vue'

const TAGS = [
  { tag: '安全生产', question_count: 3 },
  { tag: '法律法规', question_count: 5 },
]

async function openCreateForm() {
  const wrapper = mount(ExamsView)
  await flushPromises()

  const newButton = wrapper.findAll('button').find((b) => b.text().includes('新建考试'))!
  await newButton.trigger('click')
  await flushPromises()

  return { wrapper, modal: wrapper.find('.modal') }
}

beforeEach(() => {
  adminSession.token = 'test-token'
  listExamsMock.mockReset().mockResolvedValue([])
  listTagsMock.mockReset().mockResolvedValue(TAGS)
  createExamMock.mockReset().mockResolvedValue({})
  pushMock.mockReset()
})

describe('及格比例说明（CH-004）', () => {
  it('表单展示及格线口径说明', async () => {
    const { modal } = await openCreateForm()
    const text = modal.text()

    expect(text).toContain('同分并列者全部通过')
    expect(text).toContain('分母为')
    expect(text).toContain('缺考不计入')
  })

  it('说明文案随所选比例变化', async () => {
    const { modal } = await openCreateForm()

    await modal.find('#e-ratio').setValue('80')
    await flushPromises()

    expect(modal.text()).toContain('前 80%')
  })
})

describe('组卷规则标签封闭选项（CH-005）', () => {
  it('标签来自题库接口，且显示可用题数', async () => {
    const { modal } = await openCreateForm()

    const options = modal
      .find('select.rule-tag')
      .findAll('option')
      .map((option) => option.text())

    expect(options[0]).toContain('请选择标签')
    expect(options.some((t) => t.includes('安全生产') && t.includes('可用 3 题'))).toBe(true)
    expect(options.some((t) => t.includes('法律法规') && t.includes('可用 5 题'))).toBe(true)
  })

  it('标签是选择而非自由输入（不存在文本输入框）', async () => {
    const { modal } = await openCreateForm()

    const ruleRow = modal.find('.rule-row')
    expect(ruleRow.find('select.rule-tag').exists()).toBe(true)
    // 规则行里不应再有手打标签的 input（题数输入框仍是 input）
    const inputs = ruleRow.findAll('input')
    expect(inputs).toHaveLength(1)
    expect(inputs[0].classes()).toContain('rule-count')
  })

  it('抽题数超过可用题数时即时提示', async () => {
    const { modal } = await openCreateForm()

    await modal.find('select.rule-tag').setValue('安全生产')
    await modal.find('input.rule-count').setValue(10)
    await flushPromises()

    expect(modal.text()).toContain('超出可用 3 题')
  })

  it('抽题数在可用范围内时不提示超量', async () => {
    const { modal } = await openCreateForm()

    await modal.find('select.rule-tag').setValue('安全生产')
    await modal.find('input.rule-count').setValue(2)
    await flushPromises()

    expect(modal.text()).not.toContain('超出可用')
  })

  it('超量时保存被拦截，且不发起请求', async () => {
    const { modal } = await openCreateForm()

    await modal.find('#e-title').setValue('测试考试')
    await modal.find('#e-no').setValue('ZP-TEST')
    await modal.find('select.rule-tag').setValue('安全生产')
    await modal.find('input.rule-count').setValue(99)
    await flushPromises()

    await modal.findAll('button').find((b) => b.text() === '保存')!.trigger('click')
    await flushPromises()

    expect(modal.text()).toContain('无法抽取')
    expect(createExamMock).not.toHaveBeenCalled()
  })

  it('合法配置可以提交，且携带所选标签', async () => {
    const { modal } = await openCreateForm()

    await modal.find('#e-title').setValue('测试考试')
    await modal.find('#e-no').setValue('ZP-TEST')
    await modal.find('select.rule-tag').setValue('法律法规')
    await modal.find('input.rule-count').setValue(4)
    await flushPromises()

    await modal.findAll('button').find((b) => b.text() === '保存')!.trigger('click')
    await flushPromises()

    expect(createExamMock).toHaveBeenCalledTimes(1)
    const payload = createExamMock.mock.calls[0][1] as {
      settings: { rules: { tag: string; count: number }[] }
    }
    expect(payload.settings.rules).toEqual([{ tag: '法律法规', count: 4 }])
  })

  it('题库为空时给出可操作的提示', async () => {
    listTagsMock.mockResolvedValue([])
    const { modal } = await openCreateForm()

    expect(modal.text()).toContain('先在「题库管理」给题目打标签')
  })
})
