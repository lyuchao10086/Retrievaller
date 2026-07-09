import type { MultiRagSource } from "@/types/rag"

export function formatQaRecordSource(source: MultiRagSource) {
  const info = source.source ?? {}
  const fileSource = [
    info.file_name,
    info.chapter,
    info.section,
    info.subsection
  ].filter(Boolean).join(" - ")
  const formatted = [info.knowledge_base_name, fileSource].filter(Boolean).join(" / ")
  return formatted || source.knowledge_base_id || "-"
}

export function formatQaRecordSourceScore(value?: number) {
  if (typeof value !== "number") return "-"
  return value.toFixed(4)
}

export function formatKnowledgeBaseIds(ids: string[]) {
  return ids.length > 0 ? ids.join(", ") : "-"
}

export function formatQaRecordDate(value?: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
