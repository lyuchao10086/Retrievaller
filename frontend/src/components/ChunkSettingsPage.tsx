import { useEffect, useState } from "react"
import { ArrowLeft, Save } from "lucide-react"
import { ApiError } from "@/api/client"
import { getKnowledgeBaseConfig, updateKnowledgeBaseConfig } from "@/api/knowledgeBaseApi"
import type { DocumentRecord } from "@/types/document"
import { NumberInput, RadioGroup, Section, TextInput, Toggle } from "./ui/ChunkSettingsComponents"

type Props = {
  document: DocumentRecord
  onBack: () => void
}

type ChunkingMethod = "character" | "sentence" | "paragraph" | "recursive" | "semantic"

interface ChunkSettings {
  // 基础
  separator: string
  chunkSize: number
  chunkOverlap: number
  // 分段
  chunkingMethod: ChunkingMethod
  respectSentenceBoundary: boolean
  respectWordBoundary: boolean
  // 清洗
  replaceConsecutiveWhitespace: boolean
  removeUrlsAndEmails: boolean
  // 高级
  minChunkSize: number
  parentChildChunks: boolean
}

const defaultSettings: ChunkSettings = {
  separator: "\\n\\n",
  chunkSize: 500,
  chunkOverlap: 50,
  chunkingMethod: "character",
  respectSentenceBoundary: false,
  respectWordBoundary: false,
  replaceConsecutiveWhitespace: false,
  removeUrlsAndEmails: false,
  minChunkSize: 100,
  parentChildChunks: false,
}

const chunkingMethods: { value: ChunkingMethod; label: string; disabled?: boolean }[] = [
  { value: "character", label: "按字符" },
  { value: "sentence", label: "按句子（后续支持）", disabled: true },
  { value: "paragraph", label: "按段落（后续支持）", disabled: true },
  { value: "recursive", label: "递归分割（后续支持）", disabled: true },
  { value: "semantic", label: "语义分割（后续支持）", disabled: true },
]

export default function ChunkSettingsPage({ document, onBack }: Props) {
  const [settings, setSettings] = useState<ChunkSettings>(defaultSettings)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false

    async function loadSettings() {
      setLoading(true)
      setError("")
      try {
        const config = await getKnowledgeBaseConfig(document.knowledge_base_id)
        if (cancelled) return
        setSettings((current) => ({
          ...current,
          separator: config.processing.separator ?? "",
          chunkSize: config.processing.chunk_size,
          chunkOverlap: config.processing.chunk_overlap,
          replaceConsecutiveWhitespace: config.processing.replace_consecutive_whitespace,
          removeUrlsAndEmails: config.processing.remove_urls_and_emails
        }))
      } catch (unknownError) {
        if (!cancelled) {
          setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadSettings()
    return () => {
      cancelled = true
    }
  }, [document.knowledge_base_id])

  const update = <K extends keyof ChunkSettings>(key: K, value: ChunkSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaved(false)
    setError("")
    try {
      await updateKnowledgeBaseConfig(document.knowledge_base_id, {
        processing: {
          separator: settings.separator || null,
          chunk_size: settings.chunkSize,
          chunk_overlap: settings.chunkOverlap,
          replace_consecutive_whitespace: settings.replaceConsecutiveWhitespace,
          remove_urls_and_emails: settings.removeUrlsAndEmails
        }
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2400)
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
    }
  }

  return (
    <section className="flex h-screen flex-col overflow-hidden bg-white -m-4 lg:-m-6">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center justify-between border-b border-[#e8e8e8] px-6 py-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-[#555] transition hover:text-[#1f1f1f]"
        >
          <ArrowLeft className="h-4 w-4" />
          返回
        </button>
        <div className="text-sm font-medium text-[#1f1f1f]">
          分段设置 - {document.file_name}
        </div>
        <div className="w-16" />
      </div>

      {/* Content - fixed container with internal scroll */}
      <div className="mx-6 mt-6 flex flex-1 overflow-hidden">
        <div className="flex w-full flex-col overflow-y-auto rounded-xl border border-[#e8e8e8] bg-white px-5 py-5">
          <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-700">
            分隔符、分段大小、重叠长度及两项清洗规则会保存到当前知识库，并在下次处理文档时生效。其余标注“后续支持”的选项暂未接入。
          </div>
          {/* 基础 */}
          <Section title="基础">
            <div>
              <TextInput
                label="分隔符"
                hint="优先按此分隔符切分文本，默认按双换行"
                value={settings.separator}
                onChange={(v) => update("separator", v)}
                placeholder="\\n\\n"
                mono
              />
              <NumberInput
                label="分段最大长度（字符数）"
                hint="每个文本块的最大字符数，建议 200-1000"
                value={settings.chunkSize}
                onChange={(v) => update("chunkSize", v)}
                min={100}
                max={5000}
              />
              <NumberInput
                label="分段重叠长度（字符数）"
                hint="相邻文本块的重叠字符数，有助于保持上下文连贯"
                value={settings.chunkOverlap}
                onChange={(v) => update("chunkOverlap", v)}
                min={0}
                max={500}
              />
            </div>
          </Section>

          {/* 分段 */}
          <Section title="分段">
            <div>
              <RadioGroup
                label="分段方式"
                hint="选择文本切分的策略"
                options={chunkingMethods}
                value={settings.chunkingMethod}
                onChange={(v) => update("chunkingMethod", v as ChunkingMethod)}
              />
              <Toggle
                label="尊重句子边界"
                hint="避免在句子中间切断，保持句子完整性"
                checked={settings.respectSentenceBoundary}
                onChange={(v) => update("respectSentenceBoundary", v)}
                disabled
              />
              <Toggle
                label="尊重词边界"
                hint="避免在单词中间切断（对英文等语言重要）"
                checked={settings.respectWordBoundary}
                onChange={(v) => update("respectWordBoundary", v)}
                disabled
              />
            </div>
          </Section>

          {/* 清洗 */}
          <Section title="清洗">
            <div>
              <Toggle
                label="替换连续空白字符"
                hint="将连续的空格、换行符和制表符合并为单个空格"
                checked={settings.replaceConsecutiveWhitespace}
                onChange={(v) => update("replaceConsecutiveWhitespace", v)}
              />
              <Toggle
                label="删除 URL 和电子邮件地址"
                hint="移除文本中的 URL 链接和电子邮件地址"
                checked={settings.removeUrlsAndEmails}
                onChange={(v) => update("removeUrlsAndEmails", v)}
              />
            </div>
          </Section>

          {/* 高级 */}
          <Section title="高级" defaultOpen={false}>
            <div>
              <NumberInput
                label="最小分段大小（字符数）"
                hint="低于此值的文本块会与下一段合并，避免过短片段"
                value={settings.minChunkSize}
                onChange={(v) => update("minChunkSize", v)}
                min={0}
                max={500}
                disabled
              />
              <Toggle
                label="父子块关系"
                hint="建立层级块关系，父块用于粗检索，子块用于精检索"
                checked={settings.parentChildChunks}
                onChange={(v) => update("parentChildChunks", v)}
                disabled
              />
            </div>
          </Section>

          {saved && (
            <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              已保存到当前知识库；已入库文档需要重新处理后才会使用新配置。
            </div>
          )}
          {error && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex flex-shrink-0 items-center justify-end border-t border-[#e8e8e8] px-6 py-4">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="h-3.5 w-3.5" />
          {loading ? "加载配置..." : "保存配置"}
        </button>
      </div>
    </section>
  )
}
