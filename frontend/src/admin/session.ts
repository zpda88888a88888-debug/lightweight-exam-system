/**
 * 管理端会话：超管 token 存 localStorage（刷新不掉登录）。
 */

import { reactive } from 'vue'

const ADMIN_TOKEN_KEY = 'exam.admin.token.v1'

export const adminSession = reactive({
  token: '',
  username: '',
})

export function persistAdminToken(username = ''): void {
  try {
    localStorage.setItem(ADMIN_TOKEN_KEY, JSON.stringify({ token: adminSession.token, username }))
  } catch {
    /* 忽略隐私模式 */
  }
}

export function restoreAdminToken(): void {
  try {
    const raw = localStorage.getItem(ADMIN_TOKEN_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as { token?: string; username?: string }
    if (parsed.token) {
      adminSession.token = parsed.token
      adminSession.username = parsed.username ?? ''
    }
  } catch {
    /* 数据损坏按未登录处理 */
  }
}

export function clearAdminToken(): void {
  adminSession.token = ''
  try {
    localStorage.removeItem(ADMIN_TOKEN_KEY)
  } catch {
    /* 忽略 */
  }
}

export function isAdminLoggedIn(): boolean {
  return Boolean(adminSession.token)
}
