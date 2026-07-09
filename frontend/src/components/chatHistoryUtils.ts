import type { MultiRagSource, QaRecord } from "@/types/rag"

export type RestoredChatMessage = {
  role: "user" | "assistant"
  content: string
  sources?: MultiRagSource[]
  qaRecordId?: string | null
}

export function restoreMessagesFromQaRecord(record: QaRecord): RestoredChatMessage[] {
  return [
    {
      role: "user",
      content: record.question
    },
    {
      role: "assistant",
      content: record.answer,
      sources: record.sources_json,
      qaRecordId: record.id
    }
  ]
}
