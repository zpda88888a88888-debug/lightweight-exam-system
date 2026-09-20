/**
 * 时间工具：服务端时间解析、倒计时、时长格式化。
 *
 * ⚠️ 关键：后端以 **naive UTC** 序列化时间（无时区标记，如 "2026-09-19T11:00:00"）。
 * `new Date("2026-09-19T11:00:00")` 会按**本地时区**解析，在东八区会偏差 8 小时，
 * 导致倒计时严重错误。因此这里一律显式按 UTC 解析。
 */

/** 匹配结尾的时区标记：Z、+08:00、+0800 */
const TIMEZONE_SUFFIX = /(?:Z|[+-]\d{2}:?\d{2})$/i
/** 仅日期，无时间部分 */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

/**
 * 解析服务端时间字符串为 Date。
 *
 * - 无时区标记 → 视为 UTC（补 Z）
 * - 已有时区标记 → 按其偏移解析
 * - 仅日期 → 视为该日 UTC 零点
 *
 * @returns 解析失败返回 null（调用方据此降级，不抛异常）
 */
export function parseServerTime(value: string | Date | null | undefined): Date | null {
  if (value === null || value === undefined) return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }

  const text = String(value).trim()
  if (!text) return null

  // 兼容 "YYYY-MM-DD HH:MM:SS" 这种以空格分隔的写法
  let normalized = text.replace(' ', 'T')

  if (!TIMEZONE_SUFFIX.test(normalized)) {
    normalized = DATE_ONLY.test(normalized) ? `${normalized}T00:00:00Z` : `${normalized}Z`
  }

  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

/**
 * 剩余秒数（基于 end_at 计算，已过期返回 0）。
 *
 * 统一截止时间意味着晚进少考：无论何时进入，剩余时间都以 end_at 为准。
 */
export function remainingSeconds(
  endAt: string | Date | null | undefined,
  now: Date = new Date(),
): number {
  const end = parseServerTime(endAt)
  if (!end) return 0
  const diff = end.getTime() - now.getTime()
  return diff <= 0 ? 0 : Math.floor(diff / 1000)
}

/** 格式化为 HH:MM:SS（超过 24 小时按小时累计）。 */
export function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(Number.isFinite(totalSeconds) ? totalSeconds : 0))
  const hours = Math.floor(safe / 3600)
  const minutes = Math.floor((safe % 3600) / 60)
  const seconds = safe % 60
  return [hours, minutes, seconds].map((v) => String(v).padStart(2, '0')).join(':')
}

/** 格式化为本地可读时间（用于等待页/管理端展示）。 */
export function formatLocal(value: string | Date | null | undefined): string {
  const parsed = parseServerTime(value)
  if (!parsed) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  )
}

/**
 * Date → 后端接受的 naive UTC ISO 字符串（无时区标记，秒精度）。
 *
 * ⚠️ 必须去掉 `Z`：后端模型使用无时区的 datetime，
 * 若发送带时区的字符串，数据库里会混入 aware datetime，
 * 与 `now()` 的 naive UTC 比较时会抛异常。
 */
export function toServerIso(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, '')
}

/** `<input type="datetime-local">` 的值（本地时间）→ 后端 naive UTC ISO。 */
export function localInputToServer(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return toServerIso(date)
}

/** 后端 naive UTC ISO → `<input type="datetime-local">` 的值（本地时间）。 */
export function serverToLocalInput(value: string | Date | null | undefined): string {
  const date = parseServerTime(value)
  if (!date) return ''
  return dateToLocalInput(date)
}

/**
 * Date → `<input type="datetime-local">` 的值（按本地时间直接格式化）。
 *
 * 与 serverToLocalInput 的区别：本函数不做时区换算，
 * 用于「默认填当前本地时间」这类场景。
 */
export function dateToLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** 解析 `<input type="date">` 的 "YYYY-MM-DD"，按本地时区构造 Date。 */
function parseLocalDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (!match) return null
  const [, y, m, d] = match
  const date = new Date(Number(y), Number(m) - 1, Number(d))
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * `<input type="date">` 的**起始日** → 后端 naive UTC ISO。
 *
 * 管理端按"开考时间"筛选时，用户选的是本地日历日；
 * 这里把它换算成该日本地 00:00:00 对应的 UTC 时刻，
 * 与库里存的 naive UTC 才能正确比较。
 */
export function localDateStartToServer(value: string): string {
  const date = parseLocalDate(value)
  if (!date) return ''
  date.setHours(0, 0, 0, 0)
  return toServerIso(date)
}

/** `<input type="date">` 的**截止日** → 后端 naive UTC ISO（该日本地 23:59:59）。 */
export function localDateEndToServer(value: string): string {
  const date = parseLocalDate(value)
  if (!date) return ''
  date.setHours(23, 59, 59, 0)
  return toServerIso(date)
}
