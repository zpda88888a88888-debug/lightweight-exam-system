/**
 * 切屏记录：监听 visibilitychange，记录次数与时间点。
 *
 * 规格依据：spec 4.2 / 架构 9.9 —— 切屏只记录，**不中断考试**。
 * 交卷时把 count 与 log 一并上报。
 */

export interface SwitchTrackerOptions {
  /** 注入时钟，便于测试断言确定时间点 */
  now?: () => Date
  /** 每次切屏后的回调 */
  onSwitch?: (count: number, at: string) => void
  /** 监听目标，默认 document */
  target?: Document
}

export interface SwitchTracker {
  readonly count: number
  readonly log: string[]
  start: () => void
  stop: () => void
}

export function createSwitchTracker(options: SwitchTrackerOptions = {}): SwitchTracker {
  const now = options.now ?? (() => new Date())
  const target = options.target ?? document

  let count = 0
  const log: string[] = []
  let started = false
  /** 上一次是否已处于隐藏态：避免同一次切屏被多条事件重复计数 */
  let alreadyHidden = false

  const handler = () => {
    if (target.hidden) {
      if (alreadyHidden) return
      alreadyHidden = true
      count += 1
      const at = now().toISOString()
      log.push(at)
      options.onSwitch?.(count, at)
    } else {
      alreadyHidden = false
    }
  }

  return {
    get count() {
      return count
    },
    get log() {
      return log
    },
    start() {
      if (started) return
      started = true
      // 若页面在加载时本就是隐藏的，不把初始状态算作一次切屏
      alreadyHidden = target.hidden
      target.addEventListener('visibilitychange', handler)
    },
    stop() {
      if (!started) return
      started = false
      target.removeEventListener('visibilitychange', handler)
    },
  }
}
