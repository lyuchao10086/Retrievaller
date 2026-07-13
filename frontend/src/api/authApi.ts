import { request } from "./client"
import type { AuthPayload, TokenResponse } from "@/types/auth"

export function register(payload: AuthPayload) {
  return request<TokenResponse>("/api/auth/register", { method: "POST", body: payload })
}

export function login(payload: AuthPayload) {
  return request<TokenResponse>("/api/auth/login", { method: "POST", body: payload })
}
