/**
 * 切屏记录（测试方案 6.11 / spec 4.2：切屏时记录次数和时间点，不中断考试）。
 *
 * 约定：监听 visibilitychange，仅在「变为隐藏」这一跳变时计数一次，
 * 避免同一次切屏触发多条事件导致重复计数。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createSwitchTracker } from '@/lib/switchTracker'

// document.hidden 在同一文件的用例之间会互相影响，必须重置
beforeEach(() => {
  Object.defineProperty(document, 'hidden', { value: false, configurable: true })
})

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { value: hidden, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('createSwitchTracker', () => {
  it('从 0 次开始，日志为空', () => {
    const tracker = createSwitchTracker()
    expect(tracker.count).toBe(0)
    expect(tracker.log).toEqual([])
  })

  it('进入隐藏态 → 计数 +1 并追加 ISO8601 时间点', () => {
    const tracker = createSwitchTracker()
    tracker.start()

    setHidden(true)

    expect(tracker.count).toBe(1)
    expect(tracker.log).toHaveLength(1)
    expect(tracker.log[0]).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    tracker.stop()
  })

  it('时间点可序列化为 JSON（交卷时随请求上报）', () => {
    const tracker = createSwitchTracker()
    tracker.start()
    setHidden(true)
    tracker.stop()

    const serialized = JSON.stringify(tracker.log)
    expect(JSON.parse(serialized)).toEqual(tracker.log)
  })

  it('多次切屏累计次数与时间点', () => {
    const tracker = createSwitchTracker()
    tracker.start()

    setHidden(true)
    setHidden(false)
    setHidden(true)
    setHidden(false)
    setHidden(true)

    expect(tracker.count).toBe(3)
    expect(tracker.log).toHaveLength(3)
    tracker.stop()
  })

  it('停留在隐藏态时重复事件不重复计数', () => {
    const tracker = createSwitchTracker()
    tracker.start()

    setHidden(true)
    setHidden(true)
    setHidden(true)

    expect(tracker.count).toBe(1)
    tracker.stop()
  })

  it('stop 之后不再计数', () => {
    const tracker = createSwitchTracker()
    tracker.start()
    setHidden(true)
    tracker.stop()

    setHidden(false)
    setHidden(true)

    expect(tracker.count).toBe(1)
  })

  it('重复 start 不会重复注册监听（避免计数翻倍）', () => {
    const tracker = createSwitchTracker()
    tracker.start()
    tracker.start()

    setHidden(true)

    expect(tracker.count).toBe(1)
    tracker.stop()
  })

  it('支持注入时钟，便于断言确定的时间点', () => {
    const fixed = new Date(Date.UTC(2026, 8, 19, 10, 1, 23))
    const tracker = createSwitchTracker({ now: () => fixed })
    tracker.start()

    setHidden(true)

    expect(tracker.log[0]).toBe('2026-09-19T10:01:23.000Z')
    tracker.stop()
  })

  it('切屏不中断考试：回调被调用且 tracker 保持可用', () => {
    const onSwitch = vi.fn()
    const tracker = createSwitchTracker({ onSwitch })
    tracker.start()

    setHidden(true)

    expect(onSwitch).toHaveBeenCalledTimes(1)
    expect(tracker.count).toBe(1)
    tracker.stop()
  })
})
