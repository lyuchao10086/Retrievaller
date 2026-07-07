export type ChunkRecord = {
  id: string
  user_id: string
  knowledge_base_id: string
  document_id: string
  chunk_index: number
  title?: string | null
  content: string
  chapter?: string | null
  section?: string | null
  subsection?: string | null
  status: string
  vector_id?: string | null
  created_at: string
  updated_at: string
}
