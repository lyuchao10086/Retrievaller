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
import { createKnowledgeBase } from "@/api/knowledgeBaseApi"
import { uploadDocument } from "@/api/documentApi"
import { cn } from "./ui/utils"

const steps = [
  { key: "source", label: "选择数据源" },
  { key: "chunk", label: "文本分段与清洗" },
  { key: "finish", label: "处理并完成" }
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
    setFiles((prev) => [...prev, ...Array.from(incoming)])
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
          <div className="mx-6 mt-6">
            <div className="rounded-xl border border-[#e8e8e8] bg-white p-6">
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
        <p className="mt-1 text-xs text-[#aaa]">支持 MD、PDF、DOCX、PNG 等格式</p>
      </button>
      <input
        ref={inputRef}
        type="file"
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
  setSeparator
}: {
  chunkSize: number
  setChunkSize: (v: number) => void
  chunkOverlap: number
  setChunkOverlap: (v: number) => void
  separator: string
  setSeparator: (v: string) => void
}) {
  return (
    <div className="space-y-5">
      <div>
        <h4 className="text-base font-semibold text-[#1f1f1f]">文本分段与清洗</h4>
        <p className="mt-1 text-sm text-[#999]">
          配置文档切分策略，决定如何将文档拆分为可检索的文本块。
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-[#333]">
            分段大小（字符数）
          </label>
          <input
            type="number"
            value={chunkSize}
            onChange={(e) => setChunkSize(Number(e.target.value) || 0)}
            min={100}
            max={5000}
            className="w-full rounded-lg border border-[#ddd] px-3 py-2.5 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
          <p className="mt-1 text-xs text-[#aaa]">每个文本块的最大字符数，建议 200-1000</p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-[#333]">
            分段重叠（字符数）
          </label>
          <input
            type="number"
            value={chunkOverlap}
            onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
            min={0}
            max={500}
            className="w-full rounded-lg border border-[#ddd] px-3 py-2.5 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
          <p className="mt-1 text-xs text-[#aaa]">相邻文本块的重叠字符数，有助于保持上下文连贯</p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-[#333]">
            分隔符
          </label>
          <input
            value={separator}
            onChange={(e) => setSeparator(e.target.value)}
            placeholder="\\n\\n"
            className="w-full rounded-lg border border-[#ddd] px-3 py-2.5 font-mono text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
          <p className="mt-1 text-xs text-[#aaa]">优先按此分隔符切分文本，默认按双换行</p>
        </div>
      </div>
    </div>
  )
}

/* ─── Step 2: Basic Info + Review & Create ─── */
function StepFinish({
  name,
  setName,
  description,
  setDescription,
  files,
  chunkSize,
  chunkOverlap,
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
  creating: boolean
  error: string
}) {
  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-base font-semibold text-[#1f1f1f]">确认并创建</h4>
        <p className="mt-1 text-sm text-[#999]">
          填写知识库名称并检查配置信息，确认无误后点击创建。
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
        <SummaryRow label="分段大小" value={`${chunkSize} 字符`} />
        <SummaryRow label="分段重叠" value={`${chunkOverlap} 字符`} />
      </div>

      {creating && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在创建知识库并上传文档，请稍候...
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
