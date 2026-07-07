export type Evaluation = {
  id: string
  qa_record_id: string
  faithfulness_score: number
  relevance_score: number
  citation_score: number
  completeness_score: number
  hallucination: boolean
  overall_score: number
  reason: string
  created_at: string
}

export type EvaluationListResponse = {
  items: Evaluation[]
}
