/**
 * 时间处理（测试方案 6.12：倒计时基于 end_at 计算）。
 *
 * 关键点：后端以 **naive UTC** 序列化时间（例如 "2026-09-19T11:00:00"，无时区标记）。
 * JavaScript 的 `new Date("2026-09-19T11:00:00")` 会按**本地时区**解析，
 * 在东八区会直接偏差 8 小时，导致倒计时错误。故必须显式按 UTC 解析。
 */

import { describe, expect, it } from 'vitest'

import { formatDuration, parseServerTime, remainingSeconds } from '@/lib/time'
import {
  localDateEndToServer,
  localDateStartToServer,
  localInputToServer,
  serverToLocalInput,
  toServerIso,
} from '@/lib/time'

describe('parseServerTime', () => {
  it('把后端 naive UTC 字符串按 UTC 解析，而不是本地时区', () => {
    const parsed = parseServerTime('2026-09-19T11:00:00')
    expect(parsed).not.toBeNull()
    expect(parsed!.getTime()).toBe(Date.UTC(2026, 8, 19, 11, 0, 0))
  })

  it('带 Z 的字符串原样解析', () => {
    expect(parseServerTime('2026-09-19T11:00:00Z')!.getTime()).toBe(
      Date.UTC(2026, 8, 19, 11, 0, 0),
    )
  })

  it('带偏移量的字符串按其偏移解析', () => {
    expect(parseServerTime('2026-09-19T19:00:00+08:00')!.getTime()).toBe(
      Date.UTC(2026, 8, 19, 11, 0, 0),
    )
  })

  it('接受 Date 实例', () => {
    const date = new Date(Date.UTC(2026, 8, 19, 11, 0, 0))
    expect(parseServerTime(date)!.getTime()).toBe(date.getTime())
  })

  it('非法输入返回 null 而不是 Invalid Date', () => {
    expect(parseServerTime('不是时间')).toBeNull()
    expect(parseServerTime('')).toBeNull()
    expect(parseServerTime(null)).toBeNull()
    expect(parseServerTime(undefined)).toBeNull()
  })
})

describe('remainingSeconds', () => {
  const now = new Date(Date.UTC(2026, 8, 19, 10, 0, 0))

  it('按 end_at 计算剩余秒数', () => {
    expect(remainingSeconds('2026-09-19T11:00:00', now)).toBe(3600)
  })

  it('已过期返回 0，不返回负数', () => {
    expect(remainingSeconds('2026-09-19T09:00:00', now)).toBe(0)
  })

  it('边界：恰好到点返回 0', () => {
    expect(remainingSeconds('2026-09-19T10:00:00', now)).toBe(0)
  })

  it('晚进少考：只剩 10 分钟时按剩余时间算', () => {
    const late = new Date(Date.UTC(2026, 8, 19, 10, 50, 0))
    expect(remainingSeconds('2026-09-19T11:00:00', late)).toBe(600)
  })

  it('无法解析的时间按 0 处理（不崩溃）', () => {
    expect(remainingSeconds('坏数据', now)).toBe(0)
  })
})

describe('formatDuration', () => {
  it('格式化为 HH:MM:SS', () => {
    expect(formatDuration(3661)).toBe('01:01:01')
    expect(formatDuration(3600)).toBe('01:00:00')
    expect(formatDuration(0)).toBe('00:00:00')
    expect(formatDuration(59)).toBe('00:00:59')
  })

  it('超过 24 小时仍按小时累计（长考试）', () => {
    expect(formatDuration(90000)).toBe('25:00:00')
  })

  it('负数与小数按 0 处理', () => {
    expect(formatDuration(-5)).toBe('00:00:00')
    expect(formatDuration(1.9)).toBe('00:00:01')
  })
})

describe('管理端时间转换（本地 ↔ 后端 naive UTC）', () => {
  it('toServerIso 输出无时区标记的 naive UTC（秒精度）', () => {
    expect(toServerIso(new Date(Date.UTC(2026, 8, 19, 11, 0, 0)))).toBe('2026-09-19T11:00:00')
  })

  it('toServerIso 结果不含 Z 或偏移量', () => {
    const iso = toServerIso(new Date())
    expect(iso).not.toContain('Z')
    expect(iso).not.toMatch(/[+-]\d{2}:\d{2}$/)
    expect(iso).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/)
  })

  it('localInputToServer 把本地时间换算为同一时刻的 UTC', () => {
    // 用本地构造的 Date 作为期望值，避免测试依赖运行时区
    const localValue = '2026-09-19T10:00'
    const expected = toServerIso(new Date(2026, 8, 19, 10, 0, 0))
    expect(localInputToServer(localValue)).toBe(expected)
  })

  it('serverToLocalInput 与 localInputToServer 互为逆运算', () => {
    const localValue = '2026-09-19T10:30'
    expect(serverToLocalInput(localInputToServer(localValue))).toBe(localValue)
  })

  it('serverToLocalInput 把卷面时间显示为本地时间', () => {
    const server = '2026-09-19T02:00:00'
    const localDate = new Date(Date.UTC(2026, 8, 19, 2, 0, 0))
    const pad = (n: number) => String(n).padStart(2, '0')
    const expected =
      `${localDate.getFullYear()}-${pad(localDate.getMonth() + 1)}-${pad(localDate.getDate())}` +
      `T${pad(localDate.getHours())}:${pad(localDate.getMinutes())}`
    expect(serverToLocalInput(server)).toBe(expected)
  })

  it('非法输入返回空字符串而不是崩溃', () => {
    expect(localInputToServer('')).toBe('')
    expect(serverToLocalInput('坏数据')).toBe('')
  })
})

describe('开考时间范围筛选的日期转换（CH-006）', () => {
  it('起始日换算为该日本地 00:00 对应的 UTC 时刻', () => {
    const expected = toServerIso(new Date(2026, 8, 19, 0, 0, 0))
    expect(localDateStartToServer('2026-09-19')).toBe(expected)
  })

  it('截止日换算为该日本地 23:59:59 对应的 UTC 时刻', () => {
    const expected = toServerIso(new Date(2026, 8, 19, 23, 59, 59))
    expect(localDateEndToServer('2026-09-19')).toBe(expected)
  })

  it('起止同日时，区间覆盖整天（起始 < 截止）', () => {
    const from = localDateStartToServer('2026-09-19')
    const to = localDateEndToServer('2026-09-19')
    expect(from < to).toBe(true)
  })

  it('空值与非法值返回空串（调用方据此不下发该条件）', () => {
    expect(localDateStartToServer('')).toBe('')
    expect(localDateEndToServer('')).toBe('')
    expect(localDateStartToServer('2026/09/19')).toBe('')
    expect(localDateEndToServer('坏数据')).toBe('')
  })
})
