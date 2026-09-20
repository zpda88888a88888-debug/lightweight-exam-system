/**
 * 考试对外状态的展示映射（对应后端 architecture 9.2 的惰性状态）。
 */

export type ExternalStatus = 'draft' | 'upcoming' | 'running' | 'ended' | 'archived'

const LABELS: Record<string, string> = {
  draft: '草稿',
  upcoming: '未开始',
  running: '进行中',
  ended: '已结束',
  archived: '已归档',
}

const CLASSES: Record<string, string> = {
  draft: 'status-draft',
  upcoming: 'status-upcoming',
  running: 'status-running',
  ended: 'status-ended',
  archived: 'status-archived',
}

export function examStatusLabel(status: string): string {
  return LABELS[status] ?? status
}

export function examStatusClass(status: string): string {
  return CLASSES[status] ?? 'status-draft'
}

/** 仅草稿可编辑/删除/发布/导入名单/生成邀请码（发布即冻结）。 */
export function isDraft(status: string): boolean {
  return status === 'draft'
}

/** 仅已发布可归档。 */
export function canArchive(status: string): boolean {
  return status === 'published'
}
