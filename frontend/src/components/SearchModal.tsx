import { useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { MessageSquare, RotateCcw, Search } from "lucide-react"
import { cn } from "./ui/utils"

type SearchModalProps = {
  open: boolean
  onClose: () => void
  histories: Array<{ id: string; title: string; pinned: boolean; createdAt?: string }>
  onNewChat: () => void
  onSelectHistory: (id: string) => void
}

function formatRelativeTime(dateStr: string) {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    const hours = date.getHours().toString().padStart(2, "0")
    const minutes = date.getMinutes().toString().padStart(2, "0")
    return `${hours}:${minutes}`
  }
  if (diffDays === 1) return "昨天"
  if (diffDays < 7) return `${diffDays}天前`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}个月前`
  return `${Math.floor(diffDays / 365)}年前`
}

export default function SearchModal({ open, onClose, histories, onNewChat, onSelectHistory }: SearchModalProps) {
  const [query, setQuery] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQuery("")
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [open, onClose])

  const filteredHistories = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return histories
    return histories.filter((h) => h.title.toLowerCase().includes(q))
  }, [histories, query])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-[10000] flex items-start justify-center pt-[15vh]">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-[520px] rounded-2xl border border-[#e7e7e7] bg-white shadow-[0_20px_60px_rgba(15,23,42,0.18)]">
        {/* Search Input */}
        <div className="flex items-center gap-3 border-b border-[#f0f0f0] px-5 py-4">
          <Search className="h-5 w-5 shrink-0 text-[#999]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索历史对话..."
            className="min-w-0 flex-1 bg-transparent text-[15px] text-[#1f1f1f] outline-none placeholder:text-[#bbb]"
          />
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[#999] transition hover:bg-[#f4f4f4] hover:text-[#666]"
          >
            <span className="text-sm">✕</span>
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[60vh] overflow-y-auto px-3 py-3">
          {/* Quick Create */}
          {!query && (
            <div className="mb-3">
              <div className="mb-2 px-2 text-xs text-[#999]">快捷创建</div>
              <button
                type="button"
                onClick={() => {
                  onNewChat()
                  onClose()
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-[#1f1f1f] transition hover:bg-[#f5f5f5]"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#f4f4f4]">
                  <RotateCcw className="h-4 w-4 text-[#666]" />
                </div>
                <span className="flex-1 text-left">新对话</span>
              </button>
            </div>
          )}

          {/* Recent Conversations */}
          <div>
            <div className="mb-2 px-2 text-xs text-[#999]">
              {query ? "搜索结果" : "最近对话"}
            </div>
            {filteredHistories.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-[#bbb]">
                {query ? "没有匹配的历史对话" : "暂无历史对话"}
              </div>
            ) : (
              <div className="space-y-0.5">
                {filteredHistories.map((history) => (
                  <button
                    key={history.id}
                    type="button"
                    onClick={() => {
                      onSelectHistory(history.id)
                      onClose()
                    }}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition hover:bg-[#f5f5f5]",
                      history.pinned && "bg-[#fafbff]"
                    )}
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#f4f4f4]">
                      <MessageSquare className="h-4 w-4 text-[#888]" />
                    </div>
                    <span className="min-w-0 flex-1 truncate text-left text-[#1f1f1f]">{history.title}</span>
                    {history.createdAt && (
                      <span className="shrink-0 text-xs text-[#bbb]">{formatRelativeTime(history.createdAt)}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
