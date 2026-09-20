/**
 * 提交失败自动重试（测试方案 6.12：自动重试 3 次，间隔 2s / 4s / 8s；
 * 3 次失败后显示手动重试按钮）。
 *
 * 测试用注入的 sleep 与假定时器，不等待真实时间（规避风险 R9）。
 */

import { describe, expect, it, vi } from 'vitest'

import { RETRY_DELAYS, submitWithRetry } from '@/lib/retry'

describe('RETRY_DELAYS', () => {
  it('间隔为 2s / 4s / 8s', () => {
    expect([...RETRY_DELAYS]).toEqual([2000, 4000, 8000])
  })
})

describe('submitWithRetry', () => {
  it('首次成功时不重试，只调用一次', async () => {
    const task = vi.fn().mockResolvedValue({ ok: true })
    const sleep = vi.fn().mockResolvedValue(undefined)

    const outcome = await submitWithRetry(task, { sleep })

    expect(task).toHaveBeenCalledTimes(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(outcome.ok).toBe(true)
    expect(outcome.value).toEqual({ ok: true })
    expect(outcome.attempts).toBe(1)
  })

  it('失败后自动重试 3 次，共尝试 4 次', async () => {
    const task = vi.fn().mockRejectedValue(new Error('网络错误'))
    const sleep = vi.fn().mockResolvedValue(undefined)

    const outcome = await submitWithRetry(task, { sleep })

    expect(task).toHaveBeenCalledTimes(4)
    expect(outcome.ok).toBe(false)
    expect(outcome.attempts).toBe(4)
  })

  it('重试间隔依次为 2000 / 4000 / 8000 毫秒', async () => {
    const task = vi.fn().mockRejectedValue(new Error('网络错误'))
    const delays: number[] = []
    const sleep = vi.fn(async (ms: number) => {
      delays.push(ms)
    })

    await submitWithRetry(task, { sleep })

    expect(delays).toEqual([2000, 4000, 8000])
  })

  it('中途成功则停止重试并返回结果', async () => {
    const task = vi
      .fn()
      .mockRejectedValueOnce(new Error('第一次失败'))
      .mockRejectedValueOnce(new Error('第二次失败'))
      .mockResolvedValue({ score: 30 })
    const delays: number[] = []
    const sleep = vi.fn(async (ms: number) => {
      delays.push(ms)
    })

    const outcome = await submitWithRetry(task, { sleep })

    expect(task).toHaveBeenCalledTimes(3)
    expect(delays).toEqual([2000, 4000])
    expect(outcome.ok).toBe(true)
    expect(outcome.value).toEqual({ score: 30 })
  })

  it('全部失败时返回最后一次错误，供 UI 显示「重试提交」按钮', async () => {
    const lastError = new Error('最后一次失败')
    const task = vi
      .fn()
      .mockRejectedValueOnce(new Error('一'))
      .mockRejectedValueOnce(new Error('二'))
      .mockRejectedValueOnce(new Error('三'))
      .mockRejectedValue(lastError)
    const sleep = vi.fn().mockResolvedValue(undefined)

    const outcome = await submitWithRetry(task, { sleep })

    expect(outcome.ok).toBe(false)
    expect(outcome.error).toBe(lastError)
  })

  it('每次重试前回调 onRetry，便于界面提示第几次重试', async () => {
    const task = vi.fn().mockRejectedValue(new Error('失败'))
    const sleep = vi.fn().mockResolvedValue(undefined)
    const onRetry = vi.fn()

    await submitWithRetry(task, { sleep, onRetry })

    expect(onRetry).toHaveBeenCalledTimes(3)
    expect(onRetry.mock.calls.map((c) => c[0])).toEqual([1, 2, 3])
    expect(onRetry.mock.calls.map((c) => c[2])).toEqual([2000, 4000, 8000])
  })

  it('支持自定义重试间隔（便于测试与后续调整）', async () => {
    const task = vi.fn().mockRejectedValue(new Error('失败'))
    const delays: number[] = []
    const sleep = vi.fn(async (ms: number) => {
      delays.push(ms)
    })

    await submitWithRetry(task, { sleep, delays: [1, 2] })

    expect(task).toHaveBeenCalledTimes(3)
    expect(delays).toEqual([1, 2])
  })
})
