/**
 * 题型展示与校验的共享定义。
 */

import type { QuestionType } from '@/api/client'

export const QUESTION_TYPES: { value: QuestionType; label: string }[] = [
  { value: 'single', label: '单选题' },
  { value: 'multi', label: '多选题' },
  { value: 'judge', label: '判断题' },
]

/** 题型中文标签。 */
export function typeLabel(type: string): string {
  return QUESTION_TYPES.find((item) => item.value === type)?.label ?? type
}

/** 该题型是否为多选题（多选才允许多个正确答案）。 */
export function isMulti(type: QuestionType): boolean {
  return type === 'multi'
}

/** 判断题的固定选项。 */
export const JUDGE_OPTIONS = [
  { key: '对', text: '正确' },
  { key: '错', text: '错误' },
]
