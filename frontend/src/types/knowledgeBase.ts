export type KnowledgeBaseStatus = "active" | "deleted" | string

export type KnowledgeBase = {
  id: string
  user_id: string
  name: string
  description: string | null
  status: KnowledgeBaseStatus
  created_at: string
  updated_at: string
}

export type KnowledgeBaseCreatePayload = {
  name: string
  description?: string | null
}

export type KnowledgeBaseUpdatePayload = {
  name?: string
  description?: string | null
}

export type ProcessingConfig = {
  separator: string | null
  chunk_size: number
  chunk_overlap: number
  replace_consecutive_whitespace: boolean
  remove_urls_and_emails: boolean
  embedding_model_name: string
}

export type RetrievalConfig = {
  top_k: number
  similarity_threshold: number
  rerank_enabled: boolean
  rerank_model_name: string
  rerank_candidate_count: number
}

export type GenerationConfig = {
  llm_model_name: string
  temperature: number
  max_tokens: number
}

export type KnowledgeBaseConfig = {
  knowledge_base_id: string
  processing: ProcessingConfig
  retrieval: RetrievalConfig
  generation: GenerationConfig
  version: number
  created_at: string | null
  updated_at: string | null
}

export type KnowledgeBaseConfigUpdatePayload = {
  processing?: Partial<ProcessingConfig>
  retrieval?: Partial<RetrievalConfig>
  generation?: Partial<GenerationConfig>
}
