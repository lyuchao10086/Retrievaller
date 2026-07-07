import { request } from "./client"

export type HealthResponse = {
  backend?: { status?: string }
  dependencies?: Record<string, { status?: string; error?: string }>
}

export function getHealth() {
  return request<HealthResponse>("/health")
}
