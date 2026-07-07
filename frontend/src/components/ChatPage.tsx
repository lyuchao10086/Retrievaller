import { FormEvent, useEffect, useMemo, useState } from "react"
import { ArrowUp, Bot, Database, PanelLeftClose, PanelLeftOpen, Plus, Share2, Sparkles, UserRound } from "lucide-react"
import { ApiError } from "@/api/client"
import { evaluateQaRecord } from "@/api/evaluationApi"
import { listKnowledgeBases } from "@/api/knowledgeBaseApi"
import { answerQuestionAcrossKnowledgeBases } from "@/api/ragApi"
import type { Evaluation } from "@/types/evaluation"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import type { MultiRagSource } from "@/types/rag"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Input } from "./ui/input"
import { Textarea } from "./ui/textarea"

type Message = {
  role: "user" | "assistant"
  content: string
  sources?: MultiRagSource[]
  qaRecordId?: string | null
  evaluation?: Evaluation
  evaluationLoading?: boolean
  evaluationError?: string
}

const suggestions = [
  "总结当前知识库中的核心结论",
  "请根据知识库回答制度流程问题",
  "这个文档主要讲了什么？",
  "列出回答中的引用来源",
  "根据当前知识库资料能确定什么？",
  "检索到的原文依据有哪些？",
  "请用条理化方式回答这个问题",
  "如果资料不足，请说明无法确定"
]

type ChatPageProps = {
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
}

export default function ChatPage({ sidebarCollapsed, onToggleSidebar }: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState("")
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([])
  const [topK, setTopK] = useState(5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const selectedKnowledgeBases = useMemo(
    () => knowledgeBases.filter((item) => selectedKbIds.includes(item.id)),
    [knowledgeBases, selectedKbIds]
  )
  const selectedKnowledgeBaseText = useMemo(
    () =>
      selectedKnowledgeBases.length > 0
        ? selectedKnowledgeBases.map((item) => item.name).join("、")
        : "请至少选择一个知识库",
    [selectedKnowledgeBases]
  )

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

    try {
      const response = await answerQuestionAcrossKnowledgeBases({
        query: trimmed,
        knowledge_base_ids: selectedKbIds,
        top_k: topK
      })
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          qaRecordId: response.qa_record_id
        }
      ])
    } catch (unknownError) {
      setError(readErrorMessage(unknownError))
      setMessages((current) => current.filter((_, index) => index !== current.length - 1))
    } finally {
      setLoading(false)
    }
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
    <section className="relative flex h-full min-h-screen flex-col bg-white">
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
          <p className="mt-1 text-[11px] text-[#9aa3b2]">请选择一个或多个知识库作为检索范围。</p>
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

      <div className="scrollbar-thin flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-5xl flex-col px-6">
          {error && (
            <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center pb-36 pt-16">
              <h2 className="text-center text-3xl font-bold tracking-normal text-[#111]">有什么我能帮你的吗？</h2>
              <div className="mt-4 flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-sm text-blue-700">
                <Database className="h-4 w-4" />
                检索范围：{selectedKnowledgeBaseText}
              </div>
              <div className="mt-8 flex max-w-5xl flex-wrap justify-center gap-3">
                {suggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setQuestion(item)}
                    className="rounded-xl bg-[#f5f5f5] px-4 py-3 text-sm text-[#222] transition hover:bg-[#eeeeee]"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex-1 space-y-6 py-8 pb-48">
              {messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div
                    className={
                      message.role === "user"
                        ? "max-w-[78%] rounded-2xl bg-[#f4f4f4] p-4 text-[#111]"
                        : "max-w-[82%] rounded-2xl border border-[#eeeeee] bg-white p-4 shadow-sm"
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

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-white via-white to-white/0 px-6 pb-4 pt-14">
        <form onSubmit={sendQuestion} className="pointer-events-auto mx-auto max-w-[820px]">
          <div className="rounded-[26px] border border-blue-200/80 bg-white/95 p-3 shadow-[0_18px_50px_rgba(37,99,235,0.12)] backdrop-blur transition focus-within:border-blue-400 focus-within:shadow-[0_22px_60px_rgba(37,99,235,0.18)]">
            <div className="flex min-h-[78px] items-start gap-3">
              <Textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="向选中的知识库提问..."
                className="min-h-[58px] resize-none border-0 bg-transparent px-2 py-2 text-[15px] leading-7 text-[#1f1f1f] shadow-none placeholder:text-[#9aa3b2] focus-visible:ring-0"
              />
              <Button
                size="icon"
                className="mt-1 h-9 w-9 shrink-0 rounded-full bg-blue-600 shadow-[0_8px_18px_rgba(37,99,235,0.28)] transition hover:bg-blue-700 disabled:bg-[#d9d9d9] disabled:shadow-none"
                aria-label="发送"
                disabled={loading}
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium text-[#1f1f1f] transition hover:bg-[#f4f6fb]"
                aria-label="多知识库问答"
              >
                <Plus className="h-5 w-5" />
                <span className="hidden sm:inline">多知识库</span>
              </button>
              <KnowledgeBaseSelector
                knowledgeBases={knowledgeBases}
                selectedKbIds={selectedKbIds}
                onToggle={(kbId) => {
                  setSelectedKbIds((current) =>
                    current.includes(kbId)
                      ? current.filter((item) => item !== kbId)
                      : [...current, kbId]
                  )
                }}
              />
              <label className="flex h-9 items-center gap-2 rounded-full border border-[#e5e7eb] px-3 text-sm text-[#1f1f1f]">
                top_k
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(event) => setTopK(clampTopK(Number(event.target.value)))}
                  className="h-7 w-16 border-0 px-1 text-center shadow-none focus-visible:ring-0"
                />
              </label>
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
  onToggle
}: {
  knowledgeBases: KnowledgeBase[]
  selectedKbIds: string[]
  onToggle: (kbId: string) => void
}) {
  if (knowledgeBases.length === 0) {
    return (
      <div className="flex h-9 items-center rounded-full border border-[#e5e7eb] px-3 text-sm text-[#9aa3b2]">
        暂无知识库
      </div>
    )
  }

  return (
    <div className="flex max-h-20 max-w-full flex-wrap gap-2 overflow-y-auto rounded-2xl border border-[#e5e7eb] bg-white px-3 py-2">
      {knowledgeBases.map((knowledgeBase) => (
        <label
          key={knowledgeBase.id}
          className="flex h-7 items-center gap-2 rounded-full bg-[#f6f7fb] px-3 text-xs text-[#1f1f1f]"
        >
          <input
            type="checkbox"
            checked={selectedKbIds.includes(knowledgeBase.id)}
            onChange={() => onToggle(knowledgeBase.id)}
            className="h-3.5 w-3.5 accent-blue-600"
          />
          <span className="max-w-[160px] truncate">{knowledgeBase.name}</span>
        </label>
      ))}
    </div>
  )
}

function formatSource(source: MultiRagSource["source"]) {
  const fileSource = [source.file_name, source.chapter, source.section, source.subsection]
    .filter(Boolean)
    .join(" - ")
  return [source.knowledge_base_name, fileSource].filter(Boolean).join(" / ")
}

function clampTopK(value: number) {
  if (Number.isNaN(value)) return 5
  return Math.min(20, Math.max(1, value))
}

function readErrorMessage(unknownError: unknown) {
  return unknownError instanceof ApiError ? unknownError.detail : String(unknownError)
}
