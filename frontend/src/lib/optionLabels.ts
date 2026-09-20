/**
 * 选项显示标号（CH-001）。
 *
 * 背景：选项内容按考生独立乱序（防抄答案，spec 6.6），但早期实现把**标号**也跟着
 * 打乱了，考生会看到"第一项标号是 B"这种令人困惑的显示。
 *
 * 规则（spec 6.6 / UI-UX 规范 §2.2）：
 *   - 显示标号一律按**显示位置**重新编号：第 1 项 A、第 2 项 B …
 *   - 内部仍持有服务端返回的**原始选项标识**，提交时按显示位置映射回原始标识；
 *     服务端判分只认原始标识。
 *   - 判断题不打乱，标号就用原始标识（对 / 错），不显示 A/B。
 */

import type { Option, QuestionType } from '@/api/client'

export interface DisplayOption {
  /** 展示给考生的标号：单选/多选为位置字母，判断题为「对 / 错」 */
  label: string
  /** 提交给服务端的原始选项标识 */
  key: string
  text: string
}

/** 位置序号 → 标号字母：0→A，25→Z，26→AA（支持超过 26 个选项的极端情况） */
export function labelForIndex(index: number): string {
  if (!Number.isFinite(index) || index < 0) return ''
  let value = Math.floor(index)
  let label = ''
  do {
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26) - 1
  } while (value >= 0)
  return label
}

/**
 * 构造带显示标号的选项列表。
 *
 * 注意：输入的 options 已经是服务端按考生种子乱序后的顺序，
 * 这里只负责"把标号按位置重新排好"，不改变内容顺序。
 */
export function toDisplayOptions(
  questionType: QuestionType,
  options: Option[] | undefined | null,
): DisplayOption[] {
  const list = options ?? []
  return list.map((option, index) => ({
    label: questionType === 'judge' ? option.key : labelForIndex(index),
    key: option.key,
    text: option.text,
  }))
}

/** 由显示标号反查原始选项标识（点击标号时需要）。 */
export function keyForLabel(displayOptions: DisplayOption[], label: string): string | undefined {
  return displayOptions.find((item) => item.label === label)?.key
}
