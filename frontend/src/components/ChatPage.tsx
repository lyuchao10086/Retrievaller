import { FormEvent, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import {
  ArrowUp,
  Bot,
  Database,
  Globe2,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  Share2,
  Sparkles,
  StopCircle,
  UserRound
} from "lucide-react"
import { ApiError } from "@/api/client"
import { evaluateQaRecord } from "@/api/evaluationApi"
import { listKnowledgeBases } from "@/api/knowledgeBaseApi"
import { answerQuestionAcrossKnowledgeBases, createRagSuggestions } from "@/api/ragApi"
import type { Evaluation } from "@/types/evaluation"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import type { MultiRagSource } from "@/types/rag"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Textarea } from "./ui/textarea"
import { cn } from "./ui/utils"

const DEFAULT_SUGGESTIONS = [
  "总结默认知识库中的核心结论",
  "这个文档主要讲了什么？",
  "列出回答中的引用来源",
  "检索到的原文依据有哪些？",
  "根据当前知识库资料能确定什么？",
  "请用条理化方式回答这个问题",
  "如果资料不足，请说明无法确定",
  "当前知识库里有哪些关键流程？"
]

const DEFAULT_TOP_K = 5
const TOP_K_STORAGE_KEY = "retrievaller.defaultTopK"

type Message = {
  role: "user" | "assistant"
  content: string
  sources?: MultiRagSource[]
  qaRecordId?: string | null
  evaluation?: Evaluation
  evaluationLoading?: boolean
  evaluationError?: string
}

type ChatPageProps = {
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
}

export default function ChatPage({ sidebarCollapsed, onToggleSidebar }: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState("")
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([])
  const [onlineSearch, setOnlineSearch] = useState(false)
  const [suggestions, setSuggestions] = useState(DEFAULT_SUGGESTIONS)
  const [kbPickerOpen, setKbPickerOpen] = useState(false)
  const [kbPickerPosition, setKbPickerPosition] = useState({ left: 0, bottom: 0, width: 360 })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const formRef = useRef<HTMLFormElement | null>(null)
  const kbTriggerRef = useRef<HTMLDivElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const selectedKnowledgeBases = useMemo(
    () => knowledgeBases.filter((item) => selectedKbIds.includes(item.id)),
    [knowledgeBases, selectedKbIds]
  )
  const selectedKnowledgeBaseText = useMemo(
    () => {
      if (selectedKnowledgeBases.length === 0) {
        return "暂无选择，请先选择知识库"
      }
      return selectedKnowledgeBases.map((item) => item.name).join("、")
    },
    [selectedKnowledgeBases]
  )
  const noKbSelected = selectedKnowledgeBases.length === 0

  useEffect(() => {
    let ignore = false

    async function loadKnowledgeBases() {
      try {
        const data = await listKnowledgeBases()
        if (ignore) return
        setKnowledgeBases(data)
        setSelectedKbIds((current) => (current.length > 0 ? current : data[0] ? [data[0].id] : []))
      } catch (unknownError) {
        if (!ignore) setError(readErrorMessage(unknownError))
      }
    }

    void loadKnowledgeBases()
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    let ignore = false

    async function loadSuggestions() {
      if (selectedKnowledgeBases.length === 0) {
        setSuggestions([
          "联网检索这个问题的最新资料",
          "请说明资料不足时如何处理",
          "先帮我梳理问题背景",
          "给出可验证的信息来源"
        ])
        return
      }

      try {
        const response = await createRagSuggestions({
          knowledge_base_names: selectedKnowledgeBases.map((item) => item.name),
          count: 8
        })
        if (!ignore && response.suggestions.length > 0) {
          setSuggestions(response.suggestions)
        }
      } catch {
        if (!ignore) setSuggestions(DEFAULT_SUGGESTIONS)
      }
    }

    void loadSuggestions()
    return () => {
      ignore = true
    }
  }, [selectedKnowledgeBases])

  const updateKbPickerPosition = () => {
    const triggerRect = kbTriggerRef.current?.getBoundingClientRect()
    if (!triggerRect) return

    // Measure text to compute dynamic width based on longest KB name
    const canvas = document.createElement("canvas")
    const ctx = canvas.getContext("2d")
    let maxTextWidth = 0
    if (ctx) {
      ctx.font = "500 14px system-ui, sans-serif"
      for (const kb of knowledgeBases) {
        const nameWidth = ctx.measureText(kb.name).width
        let descWidth = 0
        if (kb.description) {
          ctx.font = "12px system-ui, sans-serif"
          descWidth = ctx.measureText(kb.description).width
          ctx.font = "500 14px system-ui, sans-serif"
        }
        maxTextWidth = Math.max(maxTextWidth, nameWidth, descWidth)
      }
    }
    // icon(24) + gap(8) + text + checkmark(16) + gap(8) + padding(24)
    const contentWidth = Math.ceil(maxTextWidth) + 80
    const pickerWidth = Math.max(220, Math.min(contentWidth, window.innerWidth - 32))

    setKbPickerPosition({
      left: triggerRect.left,
      bottom: Math.max(16, window.innerHeight - triggerRect.top + 8),
      width: pickerWidth,
    })
  }

  useEffect(() => {
    if (!kbPickerOpen) return

    updateKbPickerPosition()
    window.addEventListener("resize", updateKbPickerPosition)
    window.addEventListener("scroll", updateKbPickerPosition, true)

    const closePicker = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      if (target.closest("[data-kb-picker]")) return
      if (target.closest("[data-kb-picker-trigger]")) return
      setKbPickerOpen(false)
    }

    window.addEventListener("click", closePicker)
    return () => {
      window.removeEventListener("resize", updateKbPickerPosition)
      window.removeEventListener("scroll", updateKbPickerPosition, true)
      window.removeEventListener("click", closePicker)
    }
  }, [kbPickerOpen])

  const sendQuestion = async (event: FormEvent) => {
    event.preventDefault()
    const trimmed = question.trim()
    if (loading) return
    if (!trimmed) {
      setError("请输入问题")
      return
    }
    if (selectedKbIds.length === 0) {
      setError("请至少选择一个知识库")
      return
    }

    setError("")
    setLoading(true)
    setMessages((current) => [
      ...current.map((message) =>
        message.role === "assistant"
          ? {
              ...message,
              evaluation: undefined,
              evaluationLoading: false,
              evaluationError: undefined
            }
          : message
      ),
      { role: "user", content: trimmed }
    ])
    setQuestion("")

    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const response = await answerQuestionAcrossKnowledgeBases(
        {
          query: trimmed,
          knowledge_base_ids: selectedKbIds,
          top_k: readDefaultTopK()
        },
        controller.signal
      )
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          qaRecordId: response.qa_record_id
        }
      ])
      window.dispatchEvent(new Event("retrievaller:qa-records-updated"))
    } catch (unknownError) {
      if (unknownError instanceof DOMException && unknownError.name === "AbortError") {
        setMessages((current) =>
          current.map((message, index) =>
            index === current.length - 1 && message.role === "user"
              ? { ...message, content: `${message.content}\n\n[已中断]` }
              : message
          )
        )
      } else {
        setError(readErrorMessage(unknownError))
        setMessages((current) => current.filter((_, index) => index !== current.length - 1))
      }
    } finally {
      abortControllerRef.current = null
      setLoading(false)
    }
  }

  const stopQuestion = () => {
    abortControllerRef.current?.abort()
  }

  const evaluateMessage = async (messageIndex: number, qaRecordId: string) => {
    setMessages((current) =>
      current.map((message, index) =>
        index === messageIndex
          ? { ...message, evaluationLoading: true, evaluationError: undefined }
          : message
      )
    )

    try {
      const evaluation = await evaluateQaRecord(qaRecordId)
      setMessages((current) =>
        current.map((message, index) =>
          index === messageIndex
            ? { ...message, evaluation, evaluationLoading: false, evaluationError: undefined }
            : message
        )
      )
    } catch (unknownError) {
      setMessages((current) =>
        current.map((message, index) =>
          index === messageIndex
            ? {
                ...message,
                evaluationLoading: false,
                evaluationError: readErrorMessage(unknownError)
              }
            : message
        )
      )
    }
  }

  return (
    <section className="relative flex h-full min-h-screen min-w-0 flex-col overflow-x-hidden bg-white">
      <header className="relative flex h-14 shrink-0 items-center justify-center border-b border-[#eeeeee]">
        <button
          type="button"
          className="absolute left-5 flex h-8 w-8 items-center justify-center rounded-lg text-[#111] transition hover:bg-[#f4f4f4]"
          aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
          onClick={onToggleSidebar}
        >
          {sidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
        <div className="text-center">
          <h1 className="text-sm font-semibold text-[#111]">知识库问答</h1>
          <p className="mt-1 text-[11px] text-[#9aa3b2]">请选择一个或多个知识库作为检索范围，无知识库则联网</p>
        </div>
        <div className="group absolute right-6 top-1/2 -translate-y-1/2">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#c8c8c8] transition hover:bg-[#f4f4f4] hover:text-[#111]"
            aria-label="分享对话"
            onClick={() => alert("当前阶段暂不保存聊天历史")}
          >
            <Share2 className="h-4 w-4" />
          </button>
          <div className="pointer-events-none absolute left-1/2 top-[calc(100%+6px)] -translate-x-1/2 whitespace-nowrap rounded-md bg-black px-2 py-1 text-xs text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
            当前阶段不保存历史
          </div>
        </div>
      </header>

      <div className="scrollbar-thin min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-5xl min-w-0 flex-col px-4 sm:px-6">
          {error && (
            <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {messages.length === 0 ? (
            <div className="flex w-full min-w-0 flex-1 flex-col items-center justify-center pb-36 pt-16">
              <h2 className="text-center text-2xl font-bold tracking-normal text-[#111] sm:text-3xl">有什么我能帮你的吗？</h2>
              <div className={cn(
                "mt-4 flex max-w-full items-center gap-2 rounded-full border px-4 py-2 text-sm transition",
                selectedKnowledgeBases.length > 0
                  ? "border-blue-100 bg-blue-50 text-blue-700"
                  : "border-[#e0e0e0] bg-[#f5f5f5] text-[#999]"
              )}>
                <Database className="h-4 w-4 shrink-0" />
                <span className="min-w-0 truncate">知识库：{selectedKnowledgeBaseText}</span>
              </div>
              {!noKbSelected && (
                <div className="mt-8 flex w-full max-w-5xl flex-wrap justify-center gap-3">
                  {suggestions.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setQuestion(item)}
                      className="max-w-full rounded-xl bg-[#f5f5f5] px-4 py-3 text-sm text-[#222] transition hover:bg-[#eeeeee] sm:max-w-[calc(50%-0.75rem)] lg:max-w-full"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="min-w-0 flex-1 space-y-6 py-8 pb-48">
              {messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div
                    className={
                      message.role === "user"
                        ? "max-w-full rounded-2xl bg-[#f4f4f4] p-4 text-[#111] sm:max-w-[78%]"
                        : "max-w-full rounded-2xl border border-[#eeeeee] bg-white p-4 shadow-sm sm:max-w-[82%]"
                    }
                  >
                    <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                      {message.role === "user" ? <UserRound className="h-4 w-4" /> : <Bot className="h-4 w-4 text-blue-600" />}
                      {message.role === "user" ? "用户问题" : "AI 回答"}
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p>
                    {message.role === "assistant" && (
                      <>
                        <AnswerEvaluation
                          message={message}
                          messageIndex={index}
                          onEvaluate={evaluateMessage}
                        />
                        <SourceList sources={message.sources ?? []} />
                      </>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-2xl border border-[#eeeeee] bg-white p-4 text-sm text-muted-foreground shadow-sm">
                    正在检索选中的知识库并调用本地 Qwen3...
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 min-w-0 overflow-x-hidden bg-gradient-to-t from-white via-white to-white/0 px-4 pb-4 pt-14 sm:px-6">
        <form ref={formRef} onSubmit={sendQuestion} className="pointer-events-auto relative mx-auto w-full max-w-[820px] min-w-0">
          {kbPickerOpen && (
            <KnowledgeBaseSelector
              knowledgeBases={knowledgeBases}
              selectedKbIds={selectedKbIds}
              position={kbPickerPosition}
              onToggle={(kbId) => {
                setSelectedKbIds((current) =>
                  current.includes(kbId)
                    ? current.filter((item) => item !== kbId)
                    : [...current, kbId]
                )
              }}
            />
          )}
          <div className={cn(
            "rounded-[26px] border bg-white/95 p-3 shadow-[0_18px_50px_rgba(37,99,235,0.12)] backdrop-blur transition",
            noKbSelected
              ? "border-[#e8e8e8] shadow-none"
              : "border-blue-200/80 focus-within:border-blue-400 focus-within:shadow-[0_22px_60px_rgba(37,99,235,0.18)]"
          )}>
            <div className="flex min-h-[52px] items-start gap-3">
              <Textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    formRef.current?.requestSubmit()
                  }
                }}
                placeholder={noKbSelected ? "请先选择知识库..." : "向选中的知识库提问..."}
                disabled={noKbSelected}
                className="min-h-[42px] resize-none border-0 bg-transparent px-2 py-2 text-[15px] leading-7 text-[#1f1f1f] shadow-none placeholder:text-[#9aa3b2] focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <div className="mt-1 flex items-center gap-2">
              <ToolIconButton icon={<Paperclip className="h-5 w-5" />} label="添加附件" disabled />
              <ToolIconButton
                icon={<Globe2 className="h-5 w-5" />}
                label="联网检索"
                active={onlineSearch}
                disabled={noKbSelected}
                onClick={() => setOnlineSearch((v) => !v)}
              />
              <div ref={kbTriggerRef}>
                <ToolIconButton
                  icon={<Database className="h-5 w-5" />}
                  label="选择知识库"
                  active={selectedKnowledgeBases.length > 0 || kbPickerOpen}
                  dataAttribute="kb-picker-trigger"
                  onClick={() => {
                    updateKbPickerPosition()
                    setKbPickerOpen((value) => !value)
                  }}
                />
              </div>
              <div className="flex-1" />
              {question.trim() && !noKbSelected && (
                <Button
                  size="icon"
                  className="h-9 w-9 shrink-0 rounded-full bg-blue-600 shadow-[0_8px_18px_rgba(37,99,235,0.28)] transition hover:bg-blue-700"
                  aria-label={loading ? "中断" : "发送"}
                  type={loading ? "button" : "submit"}
                  onClick={loading ? stopQuestion : undefined}
                >
                  {loading ? <StopCircle className="h-4 w-4" /> : <ArrowUp className="h-4 w-4" />}
                </Button>
              )}
            </div>
          </div>
        </form>
      </div>
    </section>
  )
}

function SourceList({ sources }: { sources: MultiRagSource[] }) {
  if (sources.length === 0) {
    return (
      <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm text-muted-foreground">
        未返回引用来源。
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-3">
      {sources.map((source, sourceIndex) => (
        <div key={source.chunk_id} className="rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-sm text-slate-700">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold">引用来源 {sourceIndex + 1}</span>
            <Badge variant="processing">score {source.score.toFixed(4)}</Badge>
          </div>
          <p>来源：{formatSource(source.source)}</p>
          <p className="mt-1 text-xs text-muted-foreground">知识库 ID：{source.knowledge_base_id}</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">Chunk ID：{source.chunk_id}</p>
          <div className="mt-2 max-h-32 overflow-auto rounded-lg bg-white/70 p-3 leading-6 text-muted-foreground">
            {source.content}
          </div>
        </div>
      ))}
    </div>
  )
}

function AnswerEvaluation({
  message,
  messageIndex,
  onEvaluate
}: {
  message: Message
  messageIndex: number
  onEvaluate: (messageIndex: number, qaRecordId: string) => Promise<void>
}) {
  if (!message.qaRecordId) return null

  return (
    <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          记录 ID：<span className="font-mono">{message.qaRecordId}</span>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void onEvaluate(messageIndex, message.qaRecordId as string)}
          disabled={message.evaluationLoading}
        >
          <Sparkles className="h-4 w-4" />
          {message.evaluationLoading ? "正在调用 DeepSeek 评估..." : "立即评估"}
        </Button>
      </div>
      {message.evaluationError && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700">
          {message.evaluationError}
        </div>
      )}
      {message.evaluation && <EvaluationPanel evaluation={message.evaluation} />}
    </div>
  )
}

function EvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  const scores = [
    ["忠实性", evaluation.faithfulness_score],
    ["相关性", evaluation.relevance_score],
    ["引用正确性", evaluation.citation_score],
    ["完整性", evaluation.completeness_score],
    ["综合分", evaluation.overall_score]
  ] as const

  return (
    <div className="mt-4 space-y-3 rounded-xl border border-blue-100 bg-blue-50/50 p-4">
      <div className="flex items-center gap-2 font-semibold text-slate-800">
        <Sparkles className="h-4 w-4 text-blue-600" />
        DeepSeek 评估结果
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {scores.map(([label, score]) => (
          <div key={label} className="rounded-lg bg-white/80 p-3">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 text-lg font-semibold">{score}/5</div>
          </div>
        ))}
      </div>
      <div>
        <span className="text-sm font-medium">是否幻觉：</span>
        <Badge variant={evaluation.hallucination ? "destructive" : "success"}>
          {evaluation.hallucination ? "存在幻觉" : "未发现明显幻觉"}
        </Badge>
      </div>
      <div className="text-sm leading-7 text-muted-foreground">
        <span className="font-medium text-slate-700">评估理由：</span>
        {evaluation.reason}
      </div>
    </div>
  )
}

function KnowledgeBaseSelector({
  knowledgeBases,
  selectedKbIds,
  position,
  onToggle
}: {
  knowledgeBases: KnowledgeBase[]
  selectedKbIds: string[]
  position: { left: number; bottom: number; width: number }
  onToggle: (kbId: string) => void
}) {
  if (typeof document === "undefined") return null

  const baseStyle = {
    left: position.left,
    bottom: position.bottom,
    width: position.width
  }

  if (knowledgeBases.length === 0) {
    return createPortal(
      <div
        data-kb-picker
        className="fixed z-[9999] rounded-2xl border border-[#e5e7eb] bg-white p-3 text-sm text-[#9aa3b2] shadow-[0_18px_40px_rgba(15,23,42,0.12)]"
        style={baseStyle}
      >
        暂无知识库
      </div>,
      document.body
    )
  }

  return createPortal(
    <div
      data-kb-picker
      className="fixed z-[9999] rounded-2xl border border-[#e7e7e7] bg-white py-2 shadow-[0_18px_40px_rgba(15,23,42,0.12)]"
      style={baseStyle}
    >
      {knowledgeBases.map((knowledgeBase) => {
        const isSelected = selectedKbIds.includes(knowledgeBase.id)
        return (
          <button
            key={knowledgeBase.id}
            type="button"
            onClick={() => onToggle(knowledgeBase.id)}
            className={cn(
              "flex w-full items-center gap-2 px-3 py-1.5 text-left transition hover:bg-[#f5f5f5]",
              isSelected && "bg-blue-50/50"
            )}
          >
            <div className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded-md",
              isSelected ? "bg-blue-100 text-blue-600" : "bg-[#f0f0f0] text-[#888]"
            )}>
              <Database className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className={cn(
                "text-sm font-medium",
                isSelected ? "text-blue-700" : "text-[#1f1f1f]"
              )}>
                {knowledgeBase.name}
              </div>
              {knowledgeBase.description && (
                <div className="truncate text-xs text-[#999]">
                  {knowledgeBase.description}
                </div>
              )}
            </div>
            {isSelected && (
              <svg className="h-4 w-4 shrink-0 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            )}
          </button>
        )
      })}
    </div>,
    document.body
  )
}

function ToolIconButton({
  icon,
  label,
  active,
  disabled,
  dataAttribute,
  onClick
}: {
  icon: React.ReactNode
  label: string
  active?: boolean
  disabled?: boolean
  dataAttribute?: string
  onClick?: () => void
}) {
  const dataProps = dataAttribute ? { [`data-${dataAttribute}`]: true } : {}

  return (
    <div className="group relative">
      <button
        type="button"
        {...dataProps}
        disabled={disabled}
        onClick={onClick}
        aria-label={label}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full text-[#1f1f1f] transition hover:bg-[#f4f6fb] disabled:cursor-not-allowed disabled:text-[#b8b8b8]",
          active && "bg-blue-50 text-blue-700"
        )}
      >
        {icon}
      </button>
      <div className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-md bg-black px-2 py-1 text-xs text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
        {label}
      </div>
    </div>
  )
}

function formatSource(source: MultiRagSource["source"]) {
  const fileSource = [source.file_name, source.chapter, source.section, source.subsection]
    .filter(Boolean)
    .join(" - ")
  return [source.knowledge_base_name, fileSource].filter(Boolean).join(" / ")
}

function readDefaultTopK() {
  return clampTopK(Number(window.localStorage.getItem(TOP_K_STORAGE_KEY)))
}

function clampTopK(value: number) {
  if (Number.isNaN(value)) return DEFAULT_TOP_K
  return Math.min(20, Math.max(1, value))
}

function readErrorMessage(unknownError: unknown) {
  return unknownError instanceof ApiError ? unknownError.detail : String(unknownError)
}
