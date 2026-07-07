export type RagAnswerRequest = {
  query: string
  top_k?: number
}

export type RagSourceInfo = {
  file_name: string
  chapter?: string | null
  section?: string | null
  subsection?: string | null
}

export type MultiRagSourceInfo = RagSourceInfo & {
  knowledge_base_name: string
}

export type RagSource = {
  chunk_id: string
  document_id: string
  score: number
  content: string
  source: RagSourceInfo
}

export type MultiRagSource = {
  chunk_id: string
  document_id: string
  knowledge_base_id: string
  score: number
  content: string
  source: MultiRagSourceInfo
}

export type RagAnswerResponse = {
  query: string
  knowledge_base_id: string
  top_k: number
  answer: string
  sources: RagSource[]
}

export type MultiRagAnswerRequest = {
  query: string
  knowledge_base_ids: string[]
  top_k?: number
}

export type MultiRagAnswerResponse = {
  qa_record_id?: string | null
  query: string
  knowledge_base_ids: string[]
  top_k: number
  answer: string
  sources: MultiRagSource[]
}

export type QaRecord = {
  id: string
  question: string
  answer: string
  knowledge_base_ids: string[]
  sources_json: MultiRagSource[]
  created_at: string
  updated_at?: string | null
}
