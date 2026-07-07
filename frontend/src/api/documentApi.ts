import { request } from "./client"
import type { ChunkRecord } from "@/types/chunk"
import type {
  DocumentRecord,
  EmbeddingStatus,
  ParsedDocument,
  ParseTaskResponse
} from "@/types/document"

export function uploadDocument(kbId: string, file: File) {
  const form = new FormData()
  form.append("file", file)
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
