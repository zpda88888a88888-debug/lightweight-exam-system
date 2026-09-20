/**
 * 提交失败自动重试。
 *
 * 规格依据：测试方案 6.12 / 架构 9.5
 *   前端保留全部答案 → 自动重试 3 次（间隔 2s / 4s / 8s）
 *   → 仍失败则显示「重试提交」按钮 → 服务端幂等保证重复提交安全。
 */

/** 默认重试间隔（毫秒）：2s / 4s / 8s */
export const RETRY_DELAYS: readonly number[] = [2000, 4000, 8000]

export interface RetryOutcome<T> {
  ok: boolean
  value?: T
  error?: unknown
  /** 实际尝试次数（首次 + 重试） */
  attempts: number
}

export interface RetryOptions {
  /** 自定义重试间隔序列 */
  delays?: readonly number[]
  /** 注入的休眠函数（测试用假定时器时替换，避免真实等待） */
  sleep?: (ms: number) => Promise<void>
  /** 每次重试前的回调：(第几次重试, 错误, 本次间隔) */
  onRetry?: (attempt: number, error: unknown, delay: number) => void
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/**
 * 执行带重试的提交任务。
 *
 * 首次失败后按 `delays` 依次重试；全部失败返回 `ok: false`，
 * 调用方据此展示手动重试入口（不丢失本地答案）。
 */
export async function submitWithRetry<T>(
  task: () => Promise<T>,
  options: RetryOptions = {},
): Promise<RetryOutcome<T>> {
  const delays = options.delays ?? RETRY_DELAYS
  const sleep = options.sleep ?? defaultSleep

  let attempts = 0
  let lastError: unknown

  for (let index = 0; index <= delays.length; index += 1) {
    attempts += 1
    try {
      const value = await task()
      return { ok: true, value, attempts }
    } catch (error) {
      lastError = error
      if (index < delays.length) {
        const delay = delays[index]
        options.onRetry?.(index + 1, error, delay)
        await sleep(delay)
      }
    }
  }

  return { ok: false, error: lastError, attempts }
}
