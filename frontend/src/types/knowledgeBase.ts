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
