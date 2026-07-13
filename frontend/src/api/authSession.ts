import type { AuthSession, TokenResponse } from "@/types/auth"

const AUTH_SESSION_STORAGE_KEY = "retrievaller.auth-session"
export const AUTH_SESSION_EXPIRED_EVENT = "retrievaller:auth-session-expired"

export function readAuthSession(): AuthSession | null {
  try {
    const rawValue = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY)
    const value = rawValue ? JSON.parse(rawValue) : null
    if (
      !value ||
      typeof value.accessToken !== "string" ||
      typeof value.username !== "string" ||
      typeof value.userId !== "string" ||
      typeof value.expiresIn !== "number"
    ) {
      return null
    }
    return value as AuthSession
  } catch {
    return null
  }
}

export function saveAuthSession(response: TokenResponse): AuthSession {
  const session: AuthSession = {
    accessToken: response.access_token,
    expiresIn: response.expires_in,
    userId: response.user_id,
    username: response.username
  }
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session))
  return session
}

export function clearAuthSession(notify = false) {
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
  if (notify) window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT))
}
