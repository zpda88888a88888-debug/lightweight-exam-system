/**
 * 答案选择逻辑（纯函数）。
 *
 * 规格依据：spec 4.2（可回头修改已答题目）、4.3（提前交卷提示未答题数）、6.1（题型判分）
 *
 * 单选/判断：点选即替换（不会出现取消到空，符合单选语义）。
 * 多选：点击切换选中/取消。
 * 提交时使用**原始选项标识**（A/B/C/D 或 对/错），与显示顺序无关。
 */

export type QuestionType = 'single' | 'multi' | 'judge'

export interface QuestionLike {
  id: number
  type: QuestionType
  stem: string
  options: { key: string; text: string }[]
}

export type Answers = Record<number, string[]>

/** 切换某个选项的选中状态，返回新的答案数组（不修改入参）。 */
export function toggleAnswer(
  questionType: QuestionType,
  current: string[] | undefined,
  key: string,
): string[] {
  const selected = current ?? []

  if (questionType === 'multi') {
    return selected.includes(key)
      ? selected.filter((item) => item !== key)
      : [...selected, key]
  }

  // 单选 / 判断：点选即替换；再次点击同一项保持选中
  return [key]
}

/** 是否已作答（有至少一个选项）。 */
export function isAnswered(answer: string[] | undefined | null): boolean {
  return Array.isArray(answer) && answer.length > 0
}

/** 已作答题数。 */
export function answeredCount(questions: { id: number }[], answers: Answers): number {
  return questions.reduce((total, q) => total + (isAnswered(answers[q.id]) ? 1 : 0), 0)
}

/** 未作答题数（提前交卷时要提示「还有 X 题未答」）。 */
export function unansweredCount(questions: { id: number }[], answers: Answers): number {
  return questions.length - answeredCount(questions, answers)
}

/** 构造交卷载荷：[{question_id, answer}]，只包含试卷内题目。 */
export function toSubmitPayload(
  questions: { id: number }[],
  answers: Answers,
): { question_id: number; answer: string[] }[] {
  return questions.map((q) => ({
    question_id: q.id,
    answer: answers[q.id] ?? [],
  }))
}
