import { request } from "./client"
import type { Evaluation, EvaluationListResponse } from "@/types/evaluation"

export function evaluateQaRecord(qaRecordId: string) {
  return request<Evaluation>(`/api/evaluations/qa-records/${qaRecordId}`, {
    method: "POST"
  })
}

export function getQaRecordEvaluation(qaRecordId: string) {
  return request<Evaluation>(`/api/evaluations/qa-records/${qaRecordId}`)
}

export function listEvaluations() {
  return request<EvaluationListResponse>("/api/evaluations")
}
