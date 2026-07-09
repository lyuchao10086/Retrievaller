export type DocumentStatus =
  | "uploaded"
  | "parsing"
  | "parsed"
  | "chunked"
  | "embedding"
  | "embedded"
  | "failed"
  | "deleted"
  | string

export type DocumentRecord = {
  id: string
  user_id: string
  knowledge_base_id: string
  file_name: string
  file_type: string
  file_size: number
  storage_bucket?: string | null
  storage_object_key?: string | null
  status: DocumentStatus
  error_message?: string | null
  parsed_bucket?: string | null
  parsed_object_key?: string | null
  task_id?: string | null
  created_at: string
  updated_at: string
}

export type ParseTaskResponse = {
  message: string
  document_id: string
  task_id: string
  status: DocumentStatus
}

export type ChunkSettingsPayload = {
  separator?: string | null
  chunk_size: number
  chunk_overlap: number
  replace_consecutive_whitespace: boolean
  remove_urls_and_emails: boolean
}

export type ParsedSection = {
  level?: number
  title?: string | null
  content?: string | null
  chapter?: string | null
  section?: string | null
  subsection?: string | null
}

export type ParsedDocument = {
  document_id?: string
  knowledge_base_id?: string
  file_name?: string
  file_type?: string
  parser?: string
  sections?: ParsedSection[]
  [key: string]: unknown
}

export type EmbeddingStatus = {
  document_id: string
  status: string
  total_chunks: number
  embedded_chunks: number
  pending_chunks: number
}
