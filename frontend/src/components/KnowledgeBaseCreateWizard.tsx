import { useRef, useState } from "react"
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Loader2,
  Sparkles,
  UploadCloud,
  X
} from "lucide-react"
import { ApiError } from "@/api/client"
import { createKnowledgeBase, updateKnowledgeBaseConfig } from "@/api/knowledgeBaseApi"
import { uploadDocument } from "@/api/documentApi"
import { cn } from "./ui/utils"
import { NumberInput, RadioGroup, Section, TextInput, Toggle } from "./ui/ChunkSettingsComponents"

type ChunkingMethod = "character" | "sentence" | "paragraph" | "recursive" | "semantic"

const chunkingMethods: { value: ChunkingMethod; label: string; disabled?: boolean }[] = [
  { value: "character", label: "按字符" },
  { value: "sentence", label: "按句子（后续支持）", disabled: true },
  { value: "paragraph", label: "按段落（后续支持）", disabled: true },
  { value: "recursive", label: "递归分割（后续支持）", disabled: true },
  { value: "semantic", label: "语义分割（后续支持）", disabled: true },
]

const steps = [
  { key: "source", label: "选择数据源" },
  { key: "chunk", label: "文本分段与清洗" },
  { key: "finish", label: "创建并上传" }
] as const

type WizardProps = {
  onBack: () => void
}

export default function KnowledgeBaseCreateWizard({ onBack }: WizardProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [chunkSize, setChunkSize] = useState(500)
  const [chunkOverlap, setChunkOverlap] = useState(50)
  const [separator, setSeparator] = useState("\\n\\n")
  const [chunkingMethod, setChunkingMethod] = useState<ChunkingMethod>("character")
  const [respectSentenceBoundary, setRespectSentenceBoundary] = useState(false)
  const [respectWordBoundary, setRespectWordBoundary] = useState(false)
  const [replaceConsecutiveWhitespace, setReplaceConsecutiveWhitespace] = useState(false)
  const [removeUrlsAndEmails, setRemoveUrlsAndEmails] = useState(false)
  const [minChunkSize, setMinChunkSize] = useState(100)
  const [parentChildChunks, setParentChildChunks] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")
  const [created, setCreated] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const goNext = () => {
    if (currentStep < steps.length - 1) setCurrentStep((s) => s + 1)
  }

  const goPrev = () => {
    if (currentStep > 0) setCurrentStep((s) => s - 1)
  }

  const addFiles = (incoming: FileList | null) => {
    if (!incoming?.length) return
    setFiles((prev) => [...prev, ...Array.from(incoming).filter(isSupportedTextFile)])
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleCreate = async () => {
    setCreating(true)
    setCreateError("")
    try {
      const kb = await createKnowledgeBase({
        name: name.trim(),
        description: description.trim() || null
      })
      await updateKnowledgeBaseConfig(kb.id, {
        processing: {
          separator: separator || null,
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
          replace_consecutive_whitespace: replaceConsecutiveWhitespace,
          remove_urls_and_emails: removeUrlsAndEmails
        }
      })
      for (const file of files) {
        await uploadDocument(kb.id, file)
      }
      setCreated(true)
    } catch (unknownError) {
      setCreateError(
        unknownError instanceof ApiError ? unknownError.detail : String(unknownError)
      )
    } finally {
      setCreating(false)
    }
  }

  return (
    <section className="min-h-full bg-white">
      {/* Compact top navigation bar */}
      <div className="flex items-center justify-between border-b border-[#e8e8e8] px-6 py-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-[#555] transition hover:text-[#1f1f1f]"
        >
          <ArrowLeft className="h-4 w-4" />
          知识库
        </button>

        <div className="flex items-center gap-3">
          {steps.map((step, index) => {
            const isActive = index === currentStep
            const isDone = index < currentStep
            return (
              <div key={step.key} className="flex items-center gap-3">
                {isActive ? (
                  <>
                    <span className="rounded-full bg-blue-600 px-2.5 py-0.5 text-xs font-semibold text-white">
                      STEP {index + 1}
                    </span>
                    <span className="text-sm font-medium text-[#1f1f1f]">{step.label}</span>
                  </>
                ) : (
                  <>
                    <span className="flex h-5 w-5 items-center justify-center rounded-full text-xs text-[#bbb]">
                      {isDone ? <Check className="h-3 w-3 text-blue-500" /> : index + 1}
                    </span>
                    <span className={cn("text-sm", isDone ? "text-blue-500" : "text-[#bbb]")}>
                      {step.label}
                    </span>
                  </>
                )}
                {index < steps.length - 1 && (
                  <div className="h-px w-6 bg-[#ddd]" />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Created success state */}
      {created ? (
        <div className="mx-6 mt-10">
          <div className="flex flex-col items-center rounded-xl border border-emerald-200 bg-emerald-50/50 py-16">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100">
              <Check className="h-7 w-7 text-emerald-600" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-[#1f1f1f]">知识库创建成功</h3>
            <p className="mt-1 text-sm text-[#888]">
              「{name}」已创建{files.length > 0 ? `，${files.length} 个文档已上传` : ""}
            </p>
            {files.length > 0 && (
              <p className="mt-2 text-xs text-[#999]">
                文档当前仅作为原始文件上传；分段、清洗与向量入库尚未在此流程中执行。
              </p>
            )}
            <button
              type="button"
              onClick={onBack}
              className="mt-6 rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
            >
              返回知识库
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Step content */}
          <div className="mx-6 mt-6 max-w-3xl">
            <div className="max-h-[calc(100vh-220px)] overflow-y-auto rounded-xl border border-[#e8e8e8] bg-white p-6">
              {currentStep === 0 && (
                <StepSource
                  files={files}
                  addFiles={addFiles}
                  removeFile={removeFile}
                  inputRef={inputRef}
                />
              )}
              {currentStep === 1 && (
                <StepChunk
                  chunkSize={chunkSize}
                  setChunkSize={setChunkSize}
                  chunkOverlap={chunkOverlap}
                  setChunkOverlap={setChunkOverlap}
                  separator={separator}
                  setSeparator={setSeparator}
                  chunkingMethod={chunkingMethod}
                  setChunkingMethod={setChunkingMethod}
                  respectSentenceBoundary={respectSentenceBoundary}
                  setRespectSentenceBoundary={setRespectSentenceBoundary}
                  respectWordBoundary={respectWordBoundary}
                  setRespectWordBoundary={setRespectWordBoundary}
                  replaceConsecutiveWhitespace={replaceConsecutiveWhitespace}
                  setReplaceConsecutiveWhitespace={setReplaceConsecutiveWhitespace}
                  removeUrlsAndEmails={removeUrlsAndEmails}
                  setRemoveUrlsAndEmails={setRemoveUrlsAndEmails}
                  minChunkSize={minChunkSize}
                  setMinChunkSize={setMinChunkSize}
                  parentChildChunks={parentChildChunks}
                  setParentChildChunks={setParentChildChunks}
                />
              )}
              {currentStep === 2 && (
                <StepFinish
                  name={name}
                  setName={setName}
                  description={description}
                  setDescription={setDescription}
                  files={files}
                  chunkSize={chunkSize}
                  chunkOverlap={chunkOverlap}
                  separator={separator}
                  chunkingMethod={chunkingMethod}
                  respectSentenceBoundary={respectSentenceBoundary}
                  respectWordBoundary={respectWordBoundary}
                  replaceConsecutiveWhitespace={replaceConsecutiveWhitespace}
                  removeUrlsAndEmails={removeUrlsAndEmails}
                  minChunkSize={minChunkSize}
                  parentChildChunks={parentChildChunks}
                  creating={creating}
                  error={createError}
                />
              )}
            </div>
          </div>

          {/* Footer navigation */}
          <div className="mx-6 mt-5 flex items-center justify-between">
            <button
              type="button"
              onClick={currentStep === 0 ? onBack : goPrev}
              className="flex items-center gap-1.5 rounded-lg border border-[#ddd] px-4 py-2 text-sm text-[#555] transition hover:bg-[#f5f5f5]"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              {currentStep === 0 ? "取消" : "上一步"}
            </button>
            {currentStep < steps.length - 1 ? (
              currentStep === 0 && files.length === 0 ? (
                <button
                  type="button"
                  onClick={() => setCurrentStep(2)}
                  className="flex items-center gap-1.5 rounded-lg border border-[#ddd] bg-white px-5 py-2 text-sm font-medium text-[#555] transition hover:bg-[#f5f5f5]"
                >
                  跳过
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={goNext}
                  className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
                >
                  下一步
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              )
            ) : (
              <button
                type="button"
                onClick={() => void handleCreate()}
                disabled={creating || name.trim().length === 0}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-5 py-2 text-sm font-medium text-white transition",
                  creating || name.trim().length === 0
                    ? "cursor-not-allowed bg-blue-300"
                    : "bg-blue-600 hover:bg-blue-700"
                )}
              >
                {creating ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    创建中...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5" />
                    创建知识库
                  </>
                )}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  )
}

/* ─── Step 0: Data Source ─── */
function StepSource({
  files,
  addFiles,
  removeFile,
  inputRef
}: {
  files: File[]
  addFiles: (f: FileList | null) => void
  removeFile: (i: number) => void
  inputRef: React.RefObject<HTMLInputElement>
}) {
  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-base font-semibold text-[#1f1f1f]">选择数据源</h4>
        <p className="mt-1 text-sm text-[#999]">
          上传文档到知识库，也可以跳过此步稍后再上传。
        </p>
      </div>

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          addFiles(e.dataTransfer.files)
        }}
        className="flex w-full flex-col items-center rounded-xl border-2 border-dashed border-[#d4d4d4] bg-[#fafafa] py-12 transition hover:border-blue-400 hover:bg-blue-50/30"
      >
        <UploadCloud className="h-10 w-10 text-[#bbb]" />
        <p className="mt-3 text-sm font-medium text-[#555]">拖拽文件到此处，或点击上传</p>
        <p className="mt-1 text-xs text-[#aaa]">当前支持 TXT、MD、MARKDOWN 文本文档</p>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".txt,.md,.markdown,text/plain,text/markdown"
        multiple
        className="hidden"
        onChange={(e) => addFiles(e.target.files)}
      />

      {files.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-[#666]">
            已选择 {files.length} 个文件
          </div>
          <div className="space-y-1.5">
            {files.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center justify-between rounded-lg border border-[#eee] bg-white px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-blue-500" />
                  <span className="text-sm text-[#333]">{file.name}</span>
                  <span className="text-xs text-[#aaa]">{formatBytes(file.size)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="text-[#ccc] transition hover:text-red-400"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── Step 1: Chunk Config ─── */
function StepChunk({
  chunkSize,
  setChunkSize,
  chunkOverlap,
  setChunkOverlap,
  separator,
  setSeparator,
  chunkingMethod,
  setChunkingMethod,
  respectSentenceBoundary,
  setRespectSentenceBoundary,
  respectWordBoundary,
  setRespectWordBoundary,
  replaceConsecutiveWhitespace,
  setReplaceConsecutiveWhitespace,
  removeUrlsAndEmails,
  setRemoveUrlsAndEmails,
  minChunkSize,
  setMinChunkSize,
  parentChildChunks,
  setParentChildChunks,
}: {
  chunkSize: number
  setChunkSize: (v: number) => void
  chunkOverlap: number
  setChunkOverlap: (v: number) => void
  separator: string
  setSeparator: (v: string) => void
  chunkingMethod: ChunkingMethod
  setChunkingMethod: (v: ChunkingMethod) => void
  respectSentenceBoundary: boolean
  setRespectSentenceBoundary: (v: boolean) => void
  respectWordBoundary: boolean
  setRespectWordBoundary: (v: boolean) => void
  replaceConsecutiveWhitespace: boolean
  setReplaceConsecutiveWhitespace: (v: boolean) => void
  removeUrlsAndEmails: boolean
  setRemoveUrlsAndEmails: (v: boolean) => void
  minChunkSize: number
  setMinChunkSize: (v: number) => void
  parentChildChunks: boolean
  setParentChildChunks: (v: boolean) => void
}) {
  return (
    <div>
      <div>
        <h4 className="text-base font-semibold text-[#1f1f1f]">文本分段与清洗</h4>
        <p className="mt-1 text-sm text-[#999]">
          基础选项会保存到本知识库，并在后续处理文档时用于切分与清洗。
        </p>
        <p className="mt-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-700">
          分隔符、分段大小、重叠长度、连续空白替换和 URL/邮箱删除会在创建时保存。标注“后续支持”的选项暂未接入。
        </p>
      </div>

      {/* 基础 */}
      <Section title="基础">
        <div>
          <TextInput
            label="分隔符"
            hint="优先按此分隔符切分文本，默认按双换行"
            value={separator}
            onChange={setSeparator}
            placeholder="\\n\\n"
            mono
          />
          <NumberInput
            label="分段最大长度（字符数）"
            hint="每个文本块的最大字符数，建议 200-1000"
            value={chunkSize}
            onChange={setChunkSize}
            min={100}
            max={5000}
          />
          <NumberInput
            label="分段重叠长度（字符数）"
            hint="相邻文本块的重叠字符数，有助于保持上下文连贯"
            value={chunkOverlap}
            onChange={setChunkOverlap}
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
            value={chunkingMethod}
            onChange={(v) => setChunkingMethod(v as ChunkingMethod)}
          />
          <Toggle
            label="尊重句子边界"
            hint="避免在句子中间切断，保持句子完整性"
            checked={respectSentenceBoundary}
            onChange={setRespectSentenceBoundary}
            disabled
          />
          <Toggle
            label="尊重词边界"
            hint="避免在单词中间切断（对英文等语言重要）"
            checked={respectWordBoundary}
            onChange={setRespectWordBoundary}
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
            checked={replaceConsecutiveWhitespace}
            onChange={setReplaceConsecutiveWhitespace}
          />
          <Toggle
            label="删除 URL 和电子邮件地址"
            hint="移除文本中的 URL 链接和电子邮件地址"
            checked={removeUrlsAndEmails}
            onChange={setRemoveUrlsAndEmails}
          />
        </div>
      </Section>

      {/* 高级 */}
      <Section title="高级" defaultOpen={false}>
        <div>
          <NumberInput
            label="最小分段大小（字符数）"
            hint="低于此值的文本块会与下一段合并，避免过短片段"
            value={minChunkSize}
            onChange={setMinChunkSize}
            min={0}
            max={500}
            disabled
          />
          <Toggle
            label="父子块关系"
            hint="建立层级块关系，父块用于粗检索，子块用于精检索"
            checked={parentChildChunks}
            onChange={setParentChildChunks}
            disabled
          />
        </div>
      </Section>
    </div>
  )
}

/* ─── Step 2: Basic Info + Review & Create ─── */
const chunkingMethodLabels: Record<ChunkingMethod, string> = {
  character: "按字符",
  sentence: "按句子",
  paragraph: "按段落",
  recursive: "递归分割",
  semantic: "语义分割",
}

function StepFinish({
  name,
  setName,
  description,
  setDescription,
  files,
  chunkSize,
  chunkOverlap,
  separator,
  chunkingMethod,
  respectSentenceBoundary,
  respectWordBoundary,
  replaceConsecutiveWhitespace,
  removeUrlsAndEmails,
  minChunkSize,
  parentChildChunks,
  creating,
  error
}: {
  name: string
  setName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  files: File[]
  chunkSize: number
  chunkOverlap: number
  separator: string
  chunkingMethod: ChunkingMethod
  respectSentenceBoundary: boolean
  respectWordBoundary: boolean
  replaceConsecutiveWhitespace: boolean
  removeUrlsAndEmails: boolean
  minChunkSize: number
  parentChildChunks: boolean
  creating: boolean
  error: string
}) {
  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-base font-semibold text-[#1f1f1f]">确认并创建</h4>
        <p className="mt-1 text-sm text-[#999]">
          填写知识库名称并检查信息，确认无误后创建知识库并上传原始文件。
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Name & Description */}
      <div className="space-y-4 rounded-lg border border-[#eee] bg-[#fafafa] p-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-[#333]">
            知识库名称 <span className="text-red-400">*</span>
          </label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：课题组论文库、产品手册知识库"
            className="w-full rounded-lg border border-[#ddd] bg-white px-3 py-2.5 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-[#333]">描述</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="可选，简要描述知识库的用途和内容范围"
            rows={2}
            className="w-full resize-none rounded-lg border border-[#ddd] bg-white px-3 py-2.5 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
        </div>
      </div>

      {/* Config summary */}
      <div className="space-y-3">
        <SummaryRow label="文档数量" value={`${files.length} 个`} />
        {files.length > 0 && (
          <div className="rounded-lg border border-[#eee] bg-[#fafafa] px-3 py-2">
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-2 py-0.5 text-xs text-[#555]">
                <FileText className="h-3 w-3 text-blue-400" />
                {f.name}
              </div>
            ))}
          </div>
        )}
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
          以下基础配置会保存到知识库；已上传文件将在点击“开始处理”后使用它们。
        </div>
        <SummaryRow label="分段方式" value={chunkingMethodLabels[chunkingMethod]} />
        <SummaryRow label="分隔符" value={separator || "（默认）"} />
        <SummaryRow label="分段大小" value={`${chunkSize} 字符`} />
        <SummaryRow label="分段重叠" value={`${chunkOverlap} 字符`} />
        <SummaryRow label="最小分段大小" value={`${minChunkSize} 字符（后续支持）`} />
        <SummaryRow label="尊重句子边界" value={respectSentenceBoundary ? "是（后续支持）" : "否（后续支持）"} />
        <SummaryRow label="尊重词边界" value={respectWordBoundary ? "是（后续支持）" : "否（后续支持）"} />
        <SummaryRow label="替换连续空白" value={replaceConsecutiveWhitespace ? "是" : "否"} />
        <SummaryRow label="删除 URL 和邮箱" value={removeUrlsAndEmails ? "是" : "否"} />
        <SummaryRow label="父子块关系" value={parentChildChunks ? "启用（后续支持）" : "关闭（后续支持）"} />
      </div>

      {creating && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在创建知识库并上传原始文件，请稍候...
        </div>
      )}
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[#f0f0f0] pb-3">
      <span className="shrink-0 text-sm text-[#999]">{label}</span>
      <span className="text-right text-sm font-medium text-[#333]">{value}</span>
    </div>
  )
}

function formatBytes(value?: number | null) {
  if (value == null) return "-"
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function isSupportedTextFile(file: File) {
  const name = file.name.toLowerCase()
  const type = file.type.toLowerCase()
  return (
    name.endsWith(".txt") ||
    name.endsWith(".md") ||
    name.endsWith(".markdown") ||
    type === "text/plain" ||
    type === "text/markdown" ||
    type === "text/x-markdown"
  )
}
