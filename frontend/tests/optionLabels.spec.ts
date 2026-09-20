/**
 * 选项显示标号（CH-001，规格 6.6 / UI-UX 规范 2.2）。
 *
 * 试用反馈原话："题目选项乱序，预期选项 ABCD，实际显示 BACD"
 */

import { describe, expect, it } from 'vitest'

import { keyForLabel, labelForIndex, toDisplayOptions } from '@/lib/optionLabels'

const SHUFFLED = [
  { key: 'B', text: '选项B的内容' },
  { key: 'A', text: '选项A的内容' },
  { key: 'C', text: '选项C的内容' },
  { key: 'D', text: '选项D的内容' },
]

describe('labelForIndex', () => {
  it('按位置生成 A、B、C…', () => {
    expect(labelForIndex(0)).toBe('A')
    expect(labelForIndex(1)).toBe('B')
    expect(labelForIndex(2)).toBe('C')
    expect(labelForIndex(3)).toBe('D')
  })

  it('超过 26 项后继续用 AA、AB 表示', () => {
    expect(labelForIndex(25)).toBe('Z')
    expect(labelForIndex(26)).toBe('AA')
    expect(labelForIndex(27)).toBe('AB')
  })

  it('非法下标返回空串，不抛异常', () => {
    expect(labelForIndex(-1)).toBe('')
    expect(labelForIndex(Number.NaN)).toBe('')
  })
})

describe('toDisplayOptions —— 单选/多选', () => {
  it('标号按显示位置排成 A B C D，即使原始标识是乱序的', () => {
    const display = toDisplayOptions('single', SHUFFLED)

    expect(display.map((o) => o.label)).toEqual(['A', 'B', 'C', 'D'])
    // 内部仍然带着原始标识，顺序未变
    expect(display.map((o) => o.key)).toEqual(['B', 'A', 'C', 'D'])
  })

  it('内容与标号的对应关系正确（标号是位置，内容是该位置的选项）', () => {
    const display = toDisplayOptions('multi', SHUFFLED)

    expect(display[0]).toEqual({ label: 'A', key: 'B', text: '选项B的内容' })
    expect(display[1]).toEqual({ label: 'B', key: 'A', text: '选项A的内容' })
  })

  it('两、三项选项也连续编号', () => {
    expect(
      toDisplayOptions('single', [
        { key: 'C', text: 'c' },
        { key: 'A', text: 'a' },
      ]).map((o) => o.label),
    ).toEqual(['A', 'B'])
  })

  it('空选项不报错', () => {
    expect(toDisplayOptions('single', [])).toEqual([])
    expect(toDisplayOptions('single', undefined)).toEqual([])
    expect(toDisplayOptions('single', null)).toEqual([])
  })
})

describe('toDisplayOptions —— 判断题', () => {
  it('判断题不显示 A/B，标号保持「对 / 错」', () => {
    const display = toDisplayOptions('judge', [
      { key: '对', text: '正确' },
      { key: '错', text: '错误' },
    ])

    expect(display.map((o) => o.label)).toEqual(['对', '错'])
    expect(display.map((o) => o.key)).toEqual(['对', '错'])
  })
})

describe('keyForLabel', () => {
  it('由显示标号反查原始标识（用于提交）', () => {
    const display = toDisplayOptions('single', SHUFFLED)

    // 考生点第 1 项（显示 A），提交的必须是原始标识 B
    expect(keyForLabel(display, 'A')).toBe('B')
    expect(keyForLabel(display, 'B')).toBe('A')
    expect(keyForLabel(display, 'D')).toBe('D')
  })

  it('不存在的标号返回 undefined', () => {
    expect(keyForLabel(toDisplayOptions('single', SHUFFLED), 'Z')).toBeUndefined()
  })
})
