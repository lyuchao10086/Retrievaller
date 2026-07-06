import { useEffect, useMemo, useState } from "react"
import {
  BookOpen,
  ChevronRight,
  Edit3,
  FileSearch,
  FileText,
  Grid2X2,
  History,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Pin,
  Search,
  Settings,
  Share2,
  Trash2,
  TriangleAlert,
  UploadCloud,
  UserRound
} from "lucide-react"
import retrievallerAvatar from "@/assets/retrievaller-avatar.png"
import type { MenuKey } from "@/data/mockData"
import { cn } from "./ui/utils"

type SidebarProps = {
  active: MenuKey
  collapsed: boolean
  onChange: (key: MenuKey) => void
}

type HistoryItem = {
  id: string
  title: string
  pinned: boolean
}

const initialHistories: HistoryItem[] = [
  { id: "main", title: "主对话", pinned: true },
  { id: "ppt", title: "论文汇报PPT生成", pinned: false },
  { id: "turkish-name", title: "土耳其名字生成", pinned: false },
  { id: "prelu-flow", title: "PReLUGradReduce算子流程图", pinned: false },
  { id: "noble-logo", title: "QQ飞车NOBLE赛车车标", pinned: false },
  { id: "hallucination-image", title: "大模型幻觉图片生成", pinned: false },
  { id: "self-rag", title: "Self-RAG：结合检索与自我反思", pinned: false },
  { id: "paper-ppt", title: "生成论文汇报PPT", pinned: false },
  { id: "model-io", title: "模型输入到输出流程", pinned: false },
  { id: "pagerank", title: "PageRank算法实现（杂志评分）", pinned: false },
  { id: "video", title: "生成30秒视频", pinned: false }
]

export default function Sidebar({ active, collapsed, onChange }: SidebarProps) {
  const [moreMenuOpen, setMoreMenuOpen] = useState(false)
  const [moreExpanded, setMoreExpanded] = useState(false)
  const [search, setSearch] = useState("")
  const [histories, setHistories] = useState<HistoryItem[]>(initialHistories)
  const [historyMenu, setHistoryMenu] = useState<{ id: string; x: number; y: number } | null>(null)

  const moreItems: Array<{ key: MenuKey; label: string; icon: typeof UploadCloud }> = [
    { key: "upload", label: "文档上传", icon: UploadCloud },
    { key: "ocr", label: "OCR 解析", icon: FileText },
    { key: "citations", label: "引用来源", icon: FileSearch },
    { key: "evaluation", label: "系统评估", icon: Grid2X2 },
    { key: "settings", label: "设置", icon: Settings }
  ]

  const query = search.trim().toLowerCase()
  const filteredHistories = useMemo(
    () =>
      histories
        .filter((history) => history.title.toLowerCase().includes(query))
        .sort((a, b) => Number(b.pinned) - Number(a.pinned)),
    [histories, query]
  )
  const filteredMoreItems = useMemo(
    () => moreItems.filter((item) => item.label.toLowerCase().includes(query)),
    [moreItems, query]
  )

  useEffect(() => {
    if (!historyMenu) return

    const closeMenu = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      if (target.closest("[data-history-menu]")) return
      setHistoryMenu(null)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setHistoryMenu(null)
    }

    window.addEventListener("click", closeMenu)
    window.addEventListener("keydown", closeOnEscape)
    return () => {
      window.removeEventListener("click", closeMenu)
      window.removeEventListener("keydown", closeOnEscape)
    }
  }, [historyMenu])

  if (collapsed) {
    return null
  }

  return (
    <aside className="sticky top-0 z-40 hidden h-screen w-[280px] shrink-0 overflow-visible border-r border-[#e8e8e8] bg-[#f7f7f7] text-[#1f1f1f] lg:flex lg:flex-col">
      <div className="p-3">
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-[#dedede] bg-[#f2f2f2] px-3 py-2 text-[#999] transition hover:border-[#d0d0d0] hover:bg-[#e9e9e9] focus-within:border-[#c8c8c8] focus-within:bg-white">
          <Search className="h-4 w-4" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && filteredMoreItems[0]) {
                onChange(filteredMoreItems[0].key)
              }
            }}
            placeholder="搜索..."
            className="min-w-0 flex-1 bg-transparent text-sm text-[#333] outline-none placeholder:text-[#999]"
          />
          <span className="text-xs">⌘ K</span>
        </div>

        <button
          type="button"
          className={cn(
            "mb-2 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition hover:bg-white",
            active === "dashboard" && "bg-white shadow-sm"
          )}
          onClick={() => onChange("dashboard")}
        >
          <img src={retrievallerAvatar} alt="" className="h-7 w-7 rounded-full object-cover" />
          <span className="flex-1 text-sm font-semibold">Retrievaller</span>
        </button>

        <nav className="space-y-1">
          <button
            type="button"
            onClick={() => onChange("chat")}
            className={cn(
              "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-sm font-medium transition",
              active === "chat" ? "bg-white shadow-sm" : "hover:bg-white"
            )}
          >
            <span className="flex items-center gap-2">
              <Edit3 className="h-4 w-4" />
              新对话
            </span>
            <span className="text-xs text-[#b8b8b8]">⇧ ⌘ K</span>
          </button>

          <button
            type="button"
            onClick={() => onChange("knowledge")}
            className={cn(
              "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium transition",
              active === "knowledge" ? "bg-white shadow-sm" : "hover:bg-white"
            )}
          >
            <BookOpen className="h-4 w-4" />
            知识库
          </button>

          {moreExpanded ? (
            <div className="space-y-1">
              <button
                type="button"
                onClick={() => setMoreExpanded(false)}
                className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-sm text-[#999] transition hover:bg-[#eeeeee] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <span className="flex items-center gap-2">
                  <Grid2X2 className="h-4 w-4 text-[#111]" />
                  收起
                </span>
                <ChevronRight className="h-4 w-4 rotate-90 text-[#999]" />
              </button>
              {(query ? filteredMoreItems : moreItems).map((item) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onChange(item.key)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition hover:bg-[#eeeeee]",
                      active === item.key ? "font-semibold text-[#111]" : "text-[#444]"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </button>
                )
              })}
              {query && filteredMoreItems.length === 0 && (
                <div className="px-3 py-2 text-xs text-[#999]">未找到匹配功能</div>
              )}
            </div>
          ) : (
            <div
              className="relative"
              onMouseEnter={() => setMoreMenuOpen(true)}
              onMouseLeave={() => setMoreMenuOpen(false)}
            >
              <button
                type="button"
                onClick={() => {
                  setMoreExpanded(true)
                  setMoreMenuOpen(false)
                }}
                className={cn(
                  "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-sm font-medium transition hover:bg-[#eeeeee]",
                  moreMenuOpen && "bg-[#eeeeee]"
                )}
              >
                <span className="flex items-center gap-2">
                  <Grid2X2 className="h-4 w-4" />
                  更多
                </span>
                <ChevronRight className="h-4 w-4 text-[#999]" />
              </button>

              {moreMenuOpen && (
                <div className="absolute left-[calc(100%+10px)] top-0 z-[9999] w-[190px] rounded-xl border border-[#e7e7e7] bg-white p-2 shadow-[0_12px_35px_rgba(15,23,42,0.14)]">
                  {(query ? filteredMoreItems : moreItems).map((item) => {
                    const Icon = item.icon
                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => {
                          onChange(item.key)
                          setMoreMenuOpen(false)
                        }}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition hover:bg-[#f5f5f5]",
                          active === item.key ? "font-semibold text-[#111]" : "text-[#444]"
                        )}
                      >
                        <Icon className="h-4 w-4" />
                        {item.label}
                      </button>
                    )
                  })}
                  {query && filteredMoreItems.length === 0 && (
                    <div className="px-3 py-2 text-xs text-[#999]">未找到匹配功能</div>
                  )}
                </div>
              )}
            </div>
          )}
        </nav>
      </div>

      <div className="mt-10 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        <div className="mb-3 flex items-center gap-2 px-2 text-xs text-[#999]">
          <History className="h-3.5 w-3.5" />
          历史对话
        </div>
        <div className="space-y-1">
          {filteredHistories.map((history) => (
            <div
              key={history.id}
              className={cn(
                "group flex w-full items-center rounded-lg text-sm text-[#3f3f3f] transition hover:bg-[#eeeeee]",
                historyMenu?.id === history.id && "bg-[#eeeeee]"
              )}
            >
              <button
                type="button"
                onClick={() => onChange("chat")}
                className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[#dddddd] bg-white text-[#9b9b9b]">
                  <MessageCircle className="h-3 w-3" />
                </span>
                <span className="min-w-0 flex-1 truncate">{history.title}</span>
              </button>
              <div className="relative mr-1 h-7 w-7 shrink-0">
                {history.pinned && (
                  <span
                    className={cn(
                      "absolute inset-0 flex items-center justify-center text-[#9b9b9b] transition-opacity group-hover:opacity-0",
                      historyMenu?.id === history.id && "opacity-0"
                    )}
                  >
                    <Pin className="h-3.5 w-3.5" />
                  </span>
                )}
                <button
                  type="button"
                  aria-label={`${history.title} 更多操作`}
                  data-history-menu
                  onClick={(event) => {
                    event.stopPropagation()
                    const rect = event.currentTarget.getBoundingClientRect()
                    setHistoryMenu(
                      historyMenu?.id === history.id
                        ? null
                        : {
                            id: history.id,
                            x: Math.min(rect.left - 2, window.innerWidth - 154),
                            y: Math.min(rect.bottom + 6, window.innerHeight - 238)
                          }
                    )
                  }}
                  className={cn(
                    "absolute inset-0 flex items-center justify-center rounded-lg bg-transparent text-[#9b9b9b] opacity-0 transition hover:bg-[#e2e2e2] hover:text-[#333] group-hover:opacity-100",
                    historyMenu?.id === history.id && "bg-[#e2e2e2] opacity-100"
                  )}
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
          {query && filteredHistories.length === 0 && (
            <div className="rounded-lg px-2 py-2 text-xs text-[#999]">没有匹配的历史对话</div>
          )}
        </div>
      </div>

      {historyMenu && (
        <div
          data-history-menu
          className="fixed z-[9999] w-[140px] rounded-xl border border-[#e7e7e7] bg-white p-2 shadow-[0_12px_35px_rgba(15,23,42,0.16)]"
          style={{ left: historyMenu.x, top: historyMenu.y }}
        >
          <HistoryMenuItem
            icon={<Pin className="h-4 w-4" />}
            label={histories.find((history) => history.id === historyMenu.id)?.pinned ? "取消置顶" : "置顶"}
            onClick={() => {
              setHistories((current) => {
                const next = current.map((history) =>
                  history.id === historyMenu.id ? { ...history, pinned: !history.pinned } : history
                )
                const selected = next.find((history) => history.id === historyMenu.id)
                if (!selected?.pinned) return next
                return [selected, ...next.filter((history) => history.id !== historyMenu.id)]
              })
              setHistoryMenu(null)
            }}
          />
          <HistoryMenuItem icon={<Share2 className="h-4 w-4" />} label="分享" disabled onClick={() => setHistoryMenu(null)} />
          <HistoryMenuItem icon={<Pencil className="h-4 w-4" />} label="重命名" onClick={() => setHistoryMenu(null)} />
          <HistoryMenuItem icon={<TriangleAlert className="h-4 w-4" />} label="举报" onClick={() => setHistoryMenu(null)} />
          <HistoryMenuItem
            icon={<Trash2 className="h-4 w-4" />}
            label="删除"
            danger
            onClick={() => {
              setHistories((current) => current.filter((history) => history.id !== historyMenu.id))
              setHistoryMenu(null)
            }}
          />
        </div>
      )}

      <button
        type="button"
        onClick={() => onChange("settings")}
        className="flex items-center gap-3 border-t border-[#e8e8e8] px-5 py-4 text-left transition hover:bg-white"
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-blue-600">
          <UserRound className="h-4 w-4" />
        </div>
        <span className="text-sm font-medium">用户662680</span>
        <ChevronRight className="ml-auto h-4 w-4 text-[#aaa]" />
      </button>
    </aside>
  )
}

function HistoryMenuItem({
  icon,
  label,
  disabled,
  danger,
  onClick
}: {
  icon: React.ReactNode
  label: string
  disabled?: boolean
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
        disabled && "cursor-not-allowed text-[#cfcfcf]",
        danger && "text-red-500 hover:bg-red-50",
        !disabled && !danger && "text-[#1f1f1f] hover:bg-[#f5f5f5]"
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}
