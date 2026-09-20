/**
 * 答题页组件测试（测试方案 6.12 的关键路径）。
 *
 * 覆盖：
 *   - 渲染题目与选项
 *   - 选择答案写入 IndexedDB
 *   - 组件重建后答案恢复（刷新不丢答案）
 *   - 单选替换 / 多选切换
 *   - 提前交卷提示未答题数
 *   - 提交失败保留答案并显示「重试提交」
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { submitMock, replaceMock } = vi.hoisted(() => ({
  submitMock: vi.fn(),
  replaceMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  useRoute: () => ({ params: {} }),
}))

vi.mock('@/api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 500
    detail = ''
  },
  api: {
    submit: submitMock,
    getPaper: vi.fn(),
    createAttempt: vi.fn(),
    join: vi.fn(),
  },
}))

// 重试间隔置空：只验证组件对「最终失败」的处理，退避调度由 retry.spec.ts 覆盖
vi.mock('@/lib/retry', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/retry')>()
  return {
    ...actual,
    submitWithRetry: (task: () => Promise<unknown>, options: Record<string, unknown> = {}) =>
      actual.submitWithRetry(task, { ...options, delays: [] }),
  }
})

import { answerStore } from '@/lib/answerStore'
import { session } from '@/candidate/session'
import ExamView from '@/candidate/views/ExamView.vue'

const ATTEMPT_ID = 42

function setupSession(answers: Record<number, string[]> = {}) {
  session.token = 'test-token'
  session.exam = {
    id: 1,
    title: '测试考试',
    start_at: '2026-09-19T09:00:00',
    end_at: '2099-09-19T11:00:00',
  }
  session.attemptId = ATTEMPT_ID
  session.answers = answers
  session.questions = [
    {
      id: 101,
      type: 'single',
      stem: '单选题题干',
      options: [
        { key: 'A', text: '选项A' },
        { key: 'B', text: '选项B' },
      ],
    },
    {
      id: 102,
      type: 'multi',
      stem: '多选题题干',
      options: [
        { key: 'A', text: '选项A' },
        { key: 'B', text: '选项B' },
        { key: 'C', text: '选项C' },
      ],
    },
  ]
}

function optionInputs(wrapper: ReturnType<typeof mount>, questionId: number) {
  return wrapper.findAll(`input[name="q-${questionId}"]`)
}

async function mountExam() {
  const wrapper = mount(ExamView, { attachTo: document.body })
  // onMounted 里的 IndexedDB 读取是异步的：flushPromises 只清微任务，
  // 需要让出一个宏任务让 IDB 回调跑完，否则断言会早于答案恢复。
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 20))
  await flushPromises()
  return wrapper
}

beforeEach(async () => {
  submitMock.mockReset()
  replaceMock.mockReset()
  await answerStore.clear(ATTEMPT_ID)
  setupSession()
})

describe('ExamView 渲染', () => {
  it('渲染全部题目、题型标签与选项', async () => {
    const wrapper = await mountExam()

    expect(wrapper.text()).toContain('单选题题干')
    expect(wrapper.text()).toContain('多选题题干')
    expect(wrapper.text()).toContain('单选题')
    expect(wrapper.text()).toContain('多选题')
    expect(optionInputs(wrapper, 101)).toHaveLength(2)
    expect(optionInputs(wrapper, 102)).toHaveLength(3)

    wrapper.unmount()
  })

  it('倒计时基于 end_at 显示', async () => {
    const wrapper = await mountExam()
    // end_at 是 2099 年，必然显示一个远大于 0 的时长
    expect(wrapper.text()).toMatch(/\d{2}:\d{2}:\d{2}/)
    wrapper.unmount()
  })
})

describe('ExamView 答案持久化', () => {
  it('选择答案后写入 IndexedDB', async () => {
    const wrapper = await mountExam()

    await optionInputs(wrapper, 101)[1].setValue(true)
    // 答案不做防抖：变更后应很快落盘（这里只让出一个宏任务）
    await new Promise((resolve) => setTimeout(resolve, 50))

    const stored = await answerStore.load(ATTEMPT_ID)
    expect(stored[101]).toEqual(['B'])

    wrapper.unmount()
  })

  it('组件重建后从 IndexedDB 恢复答案（刷新不丢答案）', async () => {
    // 预置本地已保存的答案
    await answerStore.save(ATTEMPT_ID, { 101: ['A'], 102: ['A', 'C'] })

    const wrapper = await mountExam()

    const singleInputs = optionInputs(wrapper, 101)
    expect((singleInputs[0].element as HTMLInputElement).checked).toBe(true)
    expect((singleInputs[1].element as HTMLInputElement).checked).toBe(false)

    const multiInputs = optionInputs(wrapper, 102)
    expect((multiInputs[0].element as HTMLInputElement).checked).toBe(true)
    expect((multiInputs[1].element as HTMLInputElement).checked).toBe(false)
    expect((multiInputs[2].element as HTMLInputElement).checked).toBe(true)

    wrapper.unmount()
  })

  it('本地无答案时从空白开始且不报错（换设备/清缓存）', async () => {
    const wrapper = await mountExam()

    const inputs = optionInputs(wrapper, 101)
    expect(inputs.every((i) => (i.element as HTMLInputElement).checked === false)).toBe(true)
    expect(wrapper.text()).not.toContain('本地保存失败')

    wrapper.unmount()
  })
})

describe('ExamView 选择语义', () => {
  it('单选题再选其他项时替换（不会出现两个选中）', async () => {
    const wrapper = await mountExam()

    const inputs = optionInputs(wrapper, 101)
    await inputs[0].setValue(true)
    await inputs[1].setValue(true)

    expect((inputs[0].element as HTMLInputElement).checked).toBe(false)
    expect((inputs[1].element as HTMLInputElement).checked).toBe(true)

    wrapper.unmount()
  })

  it('多选题可累加与取消', async () => {
    const wrapper = await mountExam()
    const inputs = optionInputs(wrapper, 102)

    await inputs[0].setValue(true)
    await inputs[1].setValue(true)
    expect((inputs[0].element as HTMLInputElement).checked).toBe(true)
    expect((inputs[1].element as HTMLInputElement).checked).toBe(true)

    await inputs[0].setValue(false)
    expect((inputs[0].element as HTMLInputElement).checked).toBe(false)

    wrapper.unmount()
  })

  it('答题进度正确显示已答题数', async () => {
    const wrapper = await mountExam()
    expect(wrapper.text()).toContain('已答 0 / 2')

    await optionInputs(wrapper, 101)[0].setValue(true)
    await flushPromises()

    expect(wrapper.text()).toContain('已答 1 / 2')

    wrapper.unmount()
  })
})

describe('ExamView 交卷', () => {
  it('提前交卷时提示未答题数', async () => {
    const wrapper = await mountExam()

    await optionInputs(wrapper, 101)[0].setValue(true)
    await flushPromises()

    // 点击顶部「交卷」
    const submitButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '交卷')!
    await submitButton.trigger('click')

    expect(wrapper.text()).toContain('还有')
    expect(wrapper.text()).toContain('1')

    wrapper.unmount()
  })

  it('交卷成功后跳转到完成页并清除本地答案', async () => {
    submitMock.mockResolvedValue({
      ok: true,
      attempt_id: ATTEMPT_ID,
      score: 10,
      status: 'submitted',
      submitted_at: '2026-09-19T10:00:00',
    })

    const wrapper = await mountExam()
    await optionInputs(wrapper, 101)[0].setValue(true)
    await flushPromises()

    // 先打开确认框，再查询弹窗内的按钮（弹窗渲染前按钮不存在）
    await wrapper.findAll('button').find((b) => b.text() === '交卷')!.trigger('click')
    await flushPromises()

    const confirmButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '确认交卷')!
    await confirmButton.trigger('click')
    await flushPromises()

    expect(submitMock).toHaveBeenCalledTimes(1)
    expect(replaceMock).toHaveBeenCalledWith('/done')

    const stored = await answerStore.load(ATTEMPT_ID)
    expect(stored).toEqual({})

    wrapper.unmount()
  })

  it('提交失败时保留答案并显示「重试提交」按钮', async () => {
    submitMock.mockRejectedValue(new Error('网络错误'))

    const wrapper = await mountExam()
    await optionInputs(wrapper, 101)[1].setValue(true)
    await new Promise((resolve) => setTimeout(resolve, 50))

    await wrapper.findAll('button').find((b) => b.text() === '交卷')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '确认交卷')!.trigger('click')
    await flushPromises()

    // 显示失败提示与手动重试入口
    expect(wrapper.text()).toContain('答案已保存在本机')
    expect(wrapper.findAll('button').some((b) => b.text() === '重试提交')).toBe(true)

    // 答案未被丢弃
    const stored = await answerStore.load(ATTEMPT_ID)
    expect(stored[101]).toEqual(['B'])

    // 仍然停留在答题页
    expect(replaceMock).not.toHaveBeenCalledWith('/done')

    wrapper.unmount()
  })

  it('截止时间到达时自动交卷（无需考生点击）', async () => {
    submitMock.mockResolvedValue({
      ok: true,
      attempt_id: ATTEMPT_ID,
      score: 0,
      status: 'timeout_submitted',
      submitted_at: '2026-09-19T10:00:00',
    })

    // 让考试已经截止（end_at 在过去）
    session.exam!.end_at = '2020-01-01T00:00:00'

    const wrapper = await mountExam()
    // 倒计时每秒 tick 一次，等它跑过一轮
    await new Promise((resolve) => setTimeout(resolve, 1300))
    await flushPromises()

    expect(submitMock).toHaveBeenCalledTimes(1)
    expect(replaceMock).toHaveBeenCalledWith('/done')
    // 自动交卷不需要人工确认弹窗
    expect(wrapper.text()).not.toContain('确认交卷')

    wrapper.unmount()
  })
})

describe('ExamView 选项标号（CH-001）', () => {
  const SHUFFLED_QUESTION = {
    id: 201,
    type: 'single' as const,
    stem: '乱序单选题',
    options: [
      { key: 'B', text: '第二项内容' },
      { key: 'A', text: '第一项内容' },
      { key: 'D', text: '第四项内容' },
      { key: 'C', text: '第三项内容' },
    ],
  }

  it('标号按显示位置排成 A B C D，不再跟随被打乱的原始标识', async () => {
    session.questions = [SHUFFLED_QUESTION]
    const wrapper = await mountExam()

    const labels = wrapper.findAll('.option-key').map((node) => node.text())
    expect(labels).toEqual(['A', 'B', 'C', 'D'])

    // 内容顺序未被改动：显示 A 的那一项内容仍是原始 B 选项的文本
    const texts = wrapper.findAll('.option-text').map((node) => node.text())
    expect(texts).toEqual(['第二项内容', '第一项内容', '第四项内容', '第三项内容'])

    wrapper.unmount()
  })

  it('判断题标号保持「对 / 错」，不显示 A/B', async () => {
    session.questions = [
      {
        id: 202,
        type: 'judge' as const,
        stem: '判断题',
        options: [
          { key: '对', text: '正确' },
          { key: '错', text: '错误' },
        ],
      },
    ]
    const wrapper = await mountExam()

    expect(wrapper.findAll('.option-key').map((n) => n.text())).toEqual(['对', '错'])

    wrapper.unmount()
  })

  it('提交的是原始标识而非显示标号', async () => {
    submitMock.mockResolvedValue({
      ok: true,
      attempt_id: ATTEMPT_ID,
      score: 10,
      status: 'submitted',
      submitted_at: '2026-09-19T10:00:00',
    })
    session.questions = [SHUFFLED_QUESTION]

    const wrapper = await mountExam()
    // 点显示为 A 的第一项（原始标识是 B）
    await optionInputs(wrapper, 201)[0].setValue(true)
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text() === '交卷')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '确认交卷')!.trigger('click')
    await flushPromises()

    const payload = submitMock.mock.calls[0][2] as {
      answers: { question_id: number; answer: string[] }[]
    }
    expect(payload.answers).toEqual([{ question_id: 201, answer: ['B'] }])

    wrapper.unmount()
  })
})
