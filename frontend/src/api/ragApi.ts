import { request } from "./client"
import type {
  MultiRagAnswerRequest,
  MultiRagAnswerResponse,
  QaRecord,
  RagSuggestionsRequest,
  RagSuggestionsResponse
} from "@/types/rag"

export function answerQuestionAcrossKnowledgeBases(payload: MultiRagAnswerRequest, signal?: AbortSignal) {
  return request<MultiRagAnswerResponse>("/api/rag/answer", {
    method: "POST",
    body: payload,
    signal
  })
}

export function listQaRecords() {
  return request<QaRecord[]>("/api/rag/records")
}

export function deleteQaRecord(qaRecordId: string) {
  return request<QaRecord>(`/api/rag/records/${qaRecordId}`, {
    method: "DELETE"
  })
}

export function createRagSuggestions(payload: RagSuggestionsRequest) {
  return request<RagSuggestionsResponse>("/api/rag/suggestions", {
    method: "POST",
    body: payload
  })
}
