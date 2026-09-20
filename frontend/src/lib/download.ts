/**
 * 前端下载工具。
 *
 * 导出接口需要 Authorization 头，无法直接用 <a href> 下载，
 * 因此先 fetch 文本再生成 Blob 触发下载。
 */

export function downloadText(
  filename: string,
  text: string,
  mime = 'text/csv;charset=utf-8',
): void {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

/** 生成带时间戳的文件名，避免覆盖。 */
export function timestampedName(prefix: string, extension: string): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}`
  return `${prefix}-${stamp}.${extension}`
}
