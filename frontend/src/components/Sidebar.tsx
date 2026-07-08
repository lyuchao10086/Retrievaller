import { useEffect, useMemo, useState } from "react"
import {
  BookOpen,
  ChevronRight,
  Edit3,
  Grid2X2,
  History,
  MoreHorizontal,
  Pencil,
  Pin,
  Search,
  Settings,
  Share2,
  Trash2,
  TriangleAlert,
  UserRound
} from "lucide-react"
import { ApiError } from "@/api/client"
import { deleteQaRecord, listQaRecords } from "@/api/ragApi"
import type { MenuKey } from "@/data/mockData"
import type { QaRecord } from "@/types/rag"
import { cn } from "./ui/utils"
import SearchModal from "./SearchModal"

type SidebarProps = {
  active: MenuKey
  collapsed: boolean
  onChange: (key: MenuKey) => void
}

type HistoryItem = {
  id: string
  title: string
  pinned: boolean
  createdAt?: string
}

const HIDDEN_HISTORY_IDS_STORAGE_KEY = "retrievaller_hidden_qa_record_ids"

export default function Sidebar({ active, collapsed, onChange }: SidebarProps) {
  const [moreMenuOpen, setMoreMenuOpen] = useState(false)
  const [moreFlyoutOpen, setMoreFlyoutOpen] = useState(false)
  const [moreButtonRect, setMoreButtonRect] = useState<{ x: number; y: number; h: number } | null>(null)
  const [searchModalOpen, setSearchModalOpen] = useState(false)
  const [histories, setHistories] = useState<HistoryItem[]>([])
  const [historyError, setHistoryError] = useState("")
  const [historyMenu, setHistoryMenu] = useState<{ id: string; x: number; y: number } | null>(null)

  const moreItems: Array<{ key: MenuKey; label: string; icon: typeof Settings }> = [
    { key: "settings", label: "设置", icon: Settings }
  ]

  const sortedHistories = useMemo(
    () => histories.sort((a, b) => Number(b.pinned) - Number(a.pinned)),
    [histories]
  )

  useEffect(() => {
    let ignore = false

    async function loadHistories() {
      try {
        const records = await listQaRecords()
        if (!ignore) {
          const hiddenIds = readHiddenHistoryIds()
          setHistories((current) => mergeHistoryPins(records, current).filter((history) => !hiddenIds.has(history.id)))
          setHistoryError("")
        }
      } catch (unknownError) {
        if (!ignore) setHistoryError(readErrorMessage(unknownError))
      }
    }

    void loadHistories()
    window.addEventListener("retrievaller:qa-records-updated", loadHistories)
    return () => {
      ignore = true
      window.removeEventListener("retrievaller:qa-records-updated", loadHistories)
    }
  }, [])

  useEffect(() => {
    if (!historyMenu && !moreMenuOpen && !moreFlyoutOpen) return

    const closeMenu = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      if (target.closest("[data-history-menu]")) return
      if (target.closest("[data-more-menu]")) return
      if (target.closest("[data-more-flyout]")) return
      if (target.closest("[data-more-trigger]")) return
      setHistoryMenu(null)
      setMoreMenuOpen(false)
      setMoreFlyoutOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHistoryMenu(null)
        setMoreMenuOpen(false)
        setMoreFlyoutOpen(false)
      }
    }

    window.addEventListener("click", closeMenu)
    window.addEventListener("keydown", closeOnEscape)
    return () => {
      window.removeEventListener("click", closeMenu)
      window.removeEventListener("keydown", closeOnEscape)
    }
  }, [historyMenu, moreMenuOpen])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault()
        setSearchModalOpen((v) => !v)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  async function deleteHistory(historyId: string) {
    try {
      await deleteQaRecord(historyId)
      hideHistoryId(historyId)
      setHistories((current) => current.filter((history) => history.id !== historyId))
      setHistoryError("")
    } catch (unknownError) {
      setHistoryError(readErrorMessage(unknownError))
    }
  }

  if (collapsed) {
    return null
  }

  return (
    <aside className="sticky top-0 z-40 hidden h-screen w-[280px] shrink-0 overflow-visible border-r border-[#e8e8e8] bg-[#f7f7f7] text-[#1f1f1f] lg:flex lg:flex-col">
      <div className="p-3">
        <button
          type="button"
          onClick={() => setSearchModalOpen(true)}
          className="mb-3 flex w-full items-center gap-2 rounded-lg border border-[#dedede] bg-[#f2f2f2] px-3 py-2 text-[#999] transition hover:border-[#d0d0d0] hover:bg-[#e9e9e9]"
        >
          <Search className="h-4 w-4" />
          <span className="min-w-0 flex-1 text-left text-sm">搜索...</span>
          <span className="text-xs">⌘ K</span>
        </button>

        <button
          type="button"
          className="mb-2 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition hover:bg-white"
          onClick={() => onChange("chat")}
        >
          <img src="/favicon.svg?v=search" alt="" className="h-7 w-7 rounded-lg object-cover" />
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
              active === "knowledge" || active === "kbCreate" ? "bg-white shadow-sm" : "hover:bg-white"
            )}
          >
            <BookOpen className="h-4 w-4" />
            知识库
          </button>

          <button
            type="button"
            data-more-trigger
            onClick={(event) => {
              setMoreMenuOpen((value) => !value)
              setMoreFlyoutOpen(false)
              const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
              setMoreButtonRect({ x: rect.right, y: rect.top, h: rect.height })
            }}
            onMouseEnter={(event) => {
              if (moreMenuOpen) return
              const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
              setMoreButtonRect({ x: rect.right, y: rect.top, h: rect.height })
              setMoreFlyoutOpen(true)
            }}
            onMouseLeave={() => setMoreFlyoutOpen(false)}
            className={cn(
              "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-sm font-medium transition hover:bg-[#eeeeee]",
              (moreMenuOpen || moreFlyoutOpen) && "bg-[#eeeeee]"
            )}
          >
            <span className={cn("flex items-center gap-2", moreMenuOpen && "text-[#999]")}>
              <Grid2X2 className="h-4 w-4" />
              {moreMenuOpen ? "收起" : "更多"}
            </span>
            <ChevronRight className={cn("h-4 w-4 text-[#999] transition", moreMenuOpen && "rotate-90")} />
          </button>

          {moreMenuOpen && (
            <div data-more-menu className="space-y-0.5">
              {moreItems.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => {
                      onChange(item.key)
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium transition",
                      active === item.key ? "bg-white shadow-sm font-semibold text-[#111]" : "text-[#444] hover:bg-white"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </button>
                )
              })}
            </div>
          )}

          {moreFlyoutOpen && moreButtonRect && (
            <div
              data-more-flyout
              className="fixed z-[9999] w-[160px] rounded-xl border border-[#e7e7e7] bg-white p-2 shadow-[0_10px_28px_rgba(15,23,42,0.10)]"
              style={{ left: moreButtonRect.x + 4, top: moreButtonRect.y }}
              onMouseEnter={() => setMoreFlyoutOpen(true)}
              onMouseLeave={() => setMoreFlyoutOpen(false)}
            >
              {moreItems.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => {
                      onChange(item.key)
                      setMoreFlyoutOpen(false)
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
          {sortedHistories.map((history) => (
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
                className="min-w-0 flex-1 truncate px-2 py-1.5 text-left"
              >
                {history.title}
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
          {historyError && (
            <div className="rounded-lg px-2 py-2 text-xs text-red-500">历史加载失败：{historyError}</div>
          )}
          {!historyError && sortedHistories.length === 0 && (
            <div className="rounded-lg px-2 py-2 text-xs text-[#999]">
              暂无历史对话
            </div>
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
              const historyId = historyMenu.id
              setHistoryMenu(null)
              void deleteHistory(historyId)
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

      <SearchModal
        open={searchModalOpen}
        onClose={() => setSearchModalOpen(false)}
        histories={sortedHistories}
        onNewChat={() => onChange("chat")}
        onSelectHistory={() => onChange("chat")}
      />
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

function mergeHistoryPins(records: QaRecord[], current: HistoryItem[]) {
  const pinnedById = new Map(current.map((history) => [history.id, history.pinned]))
  return records.map((record) => ({
    id: record.id,
    title: formatHistoryTitle(record),
    pinned: pinnedById.get(record.id) ?? false,
    createdAt: record.created_at
  }))
}

function readHiddenHistoryIds() {
  try {
    const rawValue = window.localStorage.getItem(HIDDEN_HISTORY_IDS_STORAGE_KEY)
    const parsedValue = rawValue ? JSON.parse(rawValue) : []
    return new Set(Array.isArray(parsedValue) ? parsedValue.map(String) : [])
  } catch {
    return new Set<string>()
  }
}

function hideHistoryId(historyId: string) {
  const hiddenIds = readHiddenHistoryIds()
  hiddenIds.add(historyId)
  window.localStorage.setItem(HIDDEN_HISTORY_IDS_STORAGE_KEY, JSON.stringify([...hiddenIds]))
}

function formatHistoryTitle(record: QaRecord) {
  const title = record.title && record.title !== "新对话" ? record.title : record.question
  const compact = title.trim().split(/\s+/).join(" ")
  return compact ? compact.slice(0, 24) : "新对话"
}

function readErrorMessage(unknownError: unknown) {
  return unknownError instanceof ApiError ? unknownError.detail : String(unknownError)
}
