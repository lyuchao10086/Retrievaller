import { request } from "./client"

export type HealthResponse = {
  backend?: HealthDependencyStatus
  dependencies?: Record<string, HealthDependencyStatus>
}

export type HealthDependencyStatus = {
  status?: "ok" | "warning" | "error" | string
  code?: string
  detail?: string
  hint?: string
  error?: string
  model?: string
  provider?: string
  broker?: string
  backend?: string
}

export type SystemConfigResponse = {
  app?: {
    name?: string
    env?: string
  }
  llm?: {
    provider?: string
    base_url?: string
    local_llm_model?: string
  }
  embedding?: {
    provider?: string
    model_name?: string
    dimension?: number
    embedding_model_name?: string
    embedding_dimension?: number
  }
  storage?: {
    documents_bucket?: string
    parsed_results_bucket?: string
    milvus_collection?: string
  }
  document_processing?: {
    mode?: string
    supported_file_types?: string[]
    default_chunk_size?: number
    default_chunk_overlap?: number
  }
  evaluation?: {
    provider?: string
    base_url?: string
    model?: string
    configured?: boolean
  }
  rerank?: {
    configured?: boolean
    model_name?: string
    reason?: string
  }
}

export function getHealth() {
  return request<HealthResponse>("/health")
}

export function getSystemConfig() {
  return request<SystemConfigResponse>("/api/system/config")
}
