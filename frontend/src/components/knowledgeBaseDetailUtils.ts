export type RecallSource = {
  document_id?: string
  knowledge_base_id?: string
}

export type RecallRecord = {
  sources_json?: RecallSource[]
}

export function filterDocuments<T extends { file_name: string; file_type?: string | null }>(
  documents: T[],
  query: string
) {
  const normalizedQuery = query.trim().toLowerCase()
  if (!normalizedQuery) return documents

  return documents.filter((document) => {
    const fileName = document.file_name.toLowerCase()
    const fileType = (document.file_type ?? "").toLowerCase()
    return fileName.includes(normalizedQuery) || fileType.includes(normalizedQuery)
  })
}

export function buildDocumentRecallCounts(records: RecallRecord[], knowledgeBaseId: string) {
  return records.reduce<Record<string, number>>((counts, record) => {
    for (const source of record.sources_json ?? []) {
      if (source.knowledge_base_id !== knowledgeBaseId || !source.document_id) continue
      counts[source.document_id] = (counts[source.document_id] ?? 0) + 1
    }
    return counts
  }, {})
}

export function formatCompactCount(value: number) {
  if (value < 1000) return String(value)
  const compact = value / 1000
  return `${compact >= 10 ? compact.toFixed(1) : compact.toFixed(2)}`.replace(/\.0+$/, "").replace(/(\.\d)0$/, "$1") + "k"
}

export function getDocumentAvailabilityLabel(status: string) {
  if (status === "failed" || status === "deleted") return "不可用"
  if (status === "parsing" || status === "embedding") return "处理中"
  return "可用"
}
