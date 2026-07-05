import { FormEvent, useMemo, useState } from "react"
import { ArrowUp, Bot, Globe2, PanelLeftClose, PanelLeftOpen, Plus, Share2, UserRound } from "lucide-react"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Textarea } from "./ui/textarea"
import { citations } from "@/data/mockData"

type Message = {
  role: "user" | "assistant"
  content: string
}

const suggestions = [
  "总结上传文档中的核心结论",
  "请根据知识库回答制度流程问题",
  "帮我提取扫描件中的表格信息",
  "第六章主要讲了什么？",
  "列出回答中的引用来源和页码",
  "评估这次回答是否忠实于原文",
  "如何构建 LangChain Retriever？",
  "比较不同文档中的相同条款"
]

type ChatPageProps = {
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
}

export default function ChatPage({ sidebarCollapsed, onToggleSidebar }: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState("")
  const [webSearchEnabled, setWebSearchEnabled] = useState(false)
  const [topK] = useState(5)
  const [showCitations] = useState(true)

  const activeCitations = useMemo(() => citations.slice(0, Math.min(2, topK)), [topK])

  const sendQuestion = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return
    setMessages((current) => [
      ...current,
      { role: "user", content: trimmed },
      {
        role: "assistant",
        content:
          "已基于当前知识库检索到相关文档片段。综合 OCR 文本、Retriever 返回的上下文和引用证据，答案会优先依据原文生成；当证据不足时，系统会提示需要补充文档或降低检索阈值。"
      }
    ])
    setQuestion("")
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
          <h1 className="text-sm font-semibold text-[#111]">新对话</h1>
          <p className="mt-1 text-[11px] text-[#c8c8c8]">AI 生成可能有误 请核实</p>
        </div>
        <div className="group absolute right-6 top-1/2 -translate-y-1/2">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#c8c8c8] transition hover:bg-[#f4f4f4] hover:text-[#111]"
            aria-label="分享对话"
            onClick={() => alert("已模拟生成 PDF 分享链接")}
          >
            <Share2 className="h-4 w-4" />
          </button>
          <div className="pointer-events-none absolute left-1/2 top-[calc(100%+6px)] -translate-x-1/2 whitespace-nowrap rounded-md bg-black px-2 py-1 text-xs text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
            分享对话
          </div>
        </div>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-5xl flex-col px-6">
          {messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center pb-36 pt-16">
              <h2 className="text-center text-3xl font-bold tracking-normal text-[#111]">有什么我能帮你的吗？</h2>
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
            <div className="flex-1 space-y-6 py-8 pb-36">
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
                    <p className="text-sm leading-7">{message.content}</p>
                    {message.role === "assistant" && showCitations && (
                      <div className="mt-4 space-y-3">
                        {activeCitations.map((source, sourceIndex) => (
                          <div key={source.chunk} className="rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-sm text-slate-700">
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <span className="font-semibold">引用来源 {sourceIndex + 1}</span>
                              <Badge variant="processing">相似度 {source.score}</Badge>
                            </div>
                            <p>文档：{source.doc}</p>
                            <p>页码：{source.page}</p>
                            <p>Chunk ID：{source.chunk}</p>
                            <p className="mt-2 leading-6 text-muted-foreground">原文片段：“{source.text}”</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
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
                placeholder="发消息或按住空格说话..."
                className="min-h-[58px] resize-none border-0 bg-transparent px-2 py-2 text-[15px] leading-7 text-[#1f1f1f] shadow-none placeholder:text-[#9aa3b2] focus-visible:ring-0"
              />
              <Button
                size="icon"
                className="mt-1 h-9 w-9 shrink-0 rounded-full bg-blue-600 shadow-[0_8px_18px_rgba(37,99,235,0.28)] transition hover:bg-blue-700 disabled:bg-[#d9d9d9] disabled:shadow-none"
                aria-label="发送"
                disabled={!question.trim()}
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
            </div>
            <div className="mt-1 flex items-center gap-3">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium text-[#1f1f1f] transition hover:bg-[#f4f6fb]"
                  aria-label="添加附件"
                >
                  <Plus className="h-5 w-5" />
                  <span className="hidden sm:inline">附件</span>
                </button>
                <button
                  type="button"
                  className={`flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium transition ${
                    webSearchEnabled
                      ? "bg-blue-50 text-blue-600 hover:bg-blue-100"
                      : "text-[#1f1f1f] hover:bg-[#f4f6fb]"
                  }`}
                  aria-label="联网搜索"
                  aria-pressed={webSearchEnabled}
                  onClick={() => setWebSearchEnabled((enabled) => !enabled)}
                >
                  <Globe2 className="h-5 w-5" />
                  <span className="hidden sm:inline">{webSearchEnabled ? "搜索" : "联网"}</span>
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </section>
  )
}
