import { useState } from "react"
import { ArrowLeft, Save } from "lucide-react"
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

  const update = <K extends keyof ChunkSettings>(key: K, value: ChunkSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2400)
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
            当前配置仅为预设草稿，暂未接入后端处理流程。文档处理链路接入后，这些参数将用于切分与清洗。
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
              配置已暂存于当前页面，尚未提交到后端。
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex flex-shrink-0 items-center justify-end border-t border-[#e8e8e8] px-6 py-4">
        <button
          type="button"
          onClick={handleSave}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="h-3.5 w-3.5" />
          保存配置草稿
        </button>
      </div>
    </section>
  )
}
