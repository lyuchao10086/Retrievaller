import { request } from "./client"
import type {
  KnowledgeBase,
  KnowledgeBaseConfig,
  KnowledgeBaseConfigUpdatePayload,
  KnowledgeBaseCreatePayload,
  KnowledgeBaseUpdatePayload
} from "@/types/knowledgeBase"

export function listKnowledgeBases() {
  return request<KnowledgeBase[]>("/api/knowledge-bases")
}

export function createKnowledgeBase(payload: KnowledgeBaseCreatePayload) {
  return request<KnowledgeBase>("/api/knowledge-bases", {
    method: "POST",
    body: payload
  })
}

export function getKnowledgeBase(kbId: string) {
  return request<KnowledgeBase>(`/api/knowledge-bases/${kbId}`)
}

export function updateKnowledgeBase(kbId: string, payload: KnowledgeBaseUpdatePayload) {
  return request<KnowledgeBase>(`/api/knowledge-bases/${kbId}`, {
    method: "PUT",
    body: payload
  })
}

export function deleteKnowledgeBase(kbId: string) {
  return request<KnowledgeBase>(`/api/knowledge-bases/${kbId}`, {
    method: "DELETE"
  })
}

export function getKnowledgeBaseConfig(kbId: string) {
  return request<KnowledgeBaseConfig>(`/api/knowledge-bases/${kbId}/config`)
}

export function updateKnowledgeBaseConfig(
  kbId: string,
  payload: KnowledgeBaseConfigUpdatePayload
) {
  return request<KnowledgeBaseConfig>(`/api/knowledge-bases/${kbId}/config`, {
    method: "PUT",
    body: payload
  })
}
