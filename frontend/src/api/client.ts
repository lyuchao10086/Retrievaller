const DEFAULT_API_BASE_URL = "http://localhost:8089"
const AUTH_SESSION_STORAGE_KEY = "retrievaller.auth-session"
const AUTH_SESSION_EXPIRED_EVENT = "retrievaller:auth-session-expired"

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || DEFAULT_API_BASE_URL

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown>
  signal?: AbortSignal
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const accessToken = readAccessToken()
  if (accessToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${accessToken}`)
  }
  let body = options.body as BodyInit | undefined

  if (body && !(body instanceof FormData) && typeof body !== "string") {
    headers.set("Content-Type", "application/json")
    body = JSON.stringify(body)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body,
    signal: options.signal
  })

  if (!response.ok) {
    if (response.status === 401) {
      window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
      window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT))
    }
    throw new ApiError(response.status, await readErrorDetail(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

function readAccessToken(): string | null {
  try {
    const rawValue = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY)
    const value = rawValue ? JSON.parse(rawValue) : null
    return value && typeof value.accessToken === "string" ? value.accessToken : null
  } catch {
    return null
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    if (typeof payload.detail === "string") return payload.detail
    return JSON.stringify(payload.detail ?? payload)
  } catch {
    return response.statusText || "Request failed"
  }
}
