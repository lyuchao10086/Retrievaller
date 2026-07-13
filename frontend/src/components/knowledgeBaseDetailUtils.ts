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

const documentStatusLabels: Record<string, string> = {
  uploaded: "已上传，待处理",
  parsing: "解析中",
  parsed: "已解析，待分段",
  chunking: "分段创建中",
  chunked: "已分段，待向量化",
  embedding: "向量生成中",
  embedded: "已入库，可检索",
  failed: "处理失败",
  deleting: "删除清理中，可重试",
  deleted: "已删除"
}

export type DocumentStatusTone = "success" | "warning" | "processing" | "destructive" | "secondary"

export function getDocumentStatusLabel(status: string) {
  return documentStatusLabels[status] ?? status
}

export function getDocumentStatusTone(status: string): DocumentStatusTone {
  if (status === "embedded") return "success"
  if (status === "parsing" || status === "chunking" || status === "embedding" || status === "deleting") return "processing"
  if (status === "failed") return "destructive"
  if (status === "deleted") return "secondary"
  return "warning"
}

export function isDocumentRetrievable(status: string) {
  return status === "embedded"
}

export function getDocumentAvailabilityLabel(status: string) {
  if (status === "embedded") return "可检索"
  if (status === "failed" || status === "deleting" || status === "deleted") return "不可用"
  if (status === "parsing" || status === "chunking" || status === "embedding") return "处理中"
  return "待处理"
}
