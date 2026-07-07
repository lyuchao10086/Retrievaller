import { request } from "./client"
import type {
  MultiRagAnswerRequest,
  MultiRagAnswerResponse,
  QaRecord,
  RagSuggestionsRequest,
  RagSuggestionsResponse,
  RagAnswerRequest,
  RagAnswerResponse
} from "@/types/rag"

export function answerKnowledgeBaseQuestion(
  kbId: string,
  payload: RagAnswerRequest
) {
  return request<RagAnswerResponse>(`/api/knowledge-bases/${kbId}/rag/answer`, {
    method: "POST",
    body: payload
  })
}

export function answerQuestionAcrossKnowledgeBases(payload: MultiRagAnswerRequest) {
  return request<MultiRagAnswerResponse>("/api/rag/answer", {
    method: "POST",
    body: payload
  })
}

export function listQaRecords() {
  return request<QaRecord[]>("/api/rag/records")
}

export function createRagSuggestions(payload: RagSuggestionsRequest) {
  return request<RagSuggestionsResponse>("/api/rag/suggestions", {
    method: "POST",
    body: payload
  })
}
