import { request } from "./client"
import type { ChunkRecord } from "@/types/chunk"
import type {
  ChunkSettingsPayload,
  DocumentRecord,
  EmbeddingStatus,
  ParsedDocument,
  ParseTaskResponse
} from "@/types/document"

export function uploadDocument(kbId: string, file: File, chunkSettings?: ChunkSettingsPayload) {
  const form = new FormData()
  form.append("file", file)
  if (chunkSettings) {
    form.append("chunk_settings", JSON.stringify(chunkSettings))
  }
  return request<DocumentRecord>(`/api/knowledge-bases/${kbId}/documents/upload`, {
    method: "POST",
    body: form
  })
}

export function listDocuments(kbId: string) {
  return request<DocumentRecord[]>(`/api/knowledge-bases/${kbId}/documents`)
}

export function getDocument(kbId: string, documentId: string) {
  return request<DocumentRecord>(`/api/knowledge-bases/${kbId}/documents/${documentId}`)
}

export function deleteDocument(kbId: string, documentId: string) {
  return request<DocumentRecord>(`/api/knowledge-bases/${kbId}/documents/${documentId}`, {
    method: "DELETE"
  })
}

export function parseDocument(kbId: string, documentId: string) {
  return request<ParseTaskResponse>(
    `/api/knowledge-bases/${kbId}/documents/${documentId}/parse`,
    { method: "POST" }
  )
}

export function processDocument(
  kbId: string,
  documentId: string,
  chunkSettings?: ChunkSettingsPayload
) {
  return request<ParseTaskResponse>(
    `/api/knowledge-bases/${kbId}/documents/${documentId}/process`,
    {
      method: "POST",
      ...(chunkSettings ? { body: chunkSettings } : {})
    }
  )
}

export function getParsedDocument(kbId: string, documentId: string) {
  return request<ParsedDocument>(`/api/knowledge-bases/${kbId}/documents/${documentId}/parsed`)
}

export function createChunks(kbId: string, documentId: string) {
  return request<ChunkRecord[]>(`/api/knowledge-bases/${kbId}/documents/${documentId}/chunks`, {
    method: "POST"
  })
}

export function listChunks(kbId: string, documentId: string) {
  return request<ChunkRecord[]>(`/api/knowledge-bases/${kbId}/documents/${documentId}/chunks`)
}

export function embedDocument(kbId: string, documentId: string) {
  return request<EmbeddingStatus>(`/api/knowledge-bases/${kbId}/documents/${documentId}/embed`, {
    method: "POST"
  })
}

export function getEmbeddingStatus(kbId: string, documentId: string) {
  return request<EmbeddingStatus>(
    `/api/knowledge-bases/${kbId}/documents/${documentId}/embedding-status`
  )
}

export function renameDocument(kbId: string, documentId: string, fileName: string) {
  return request<DocumentRecord>(
    `/api/knowledge-bases/${kbId}/documents/${documentId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_name: fileName })
    }
  )
}
