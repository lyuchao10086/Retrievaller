import { createPortal } from "react-dom"
import { useEffect, useMemo, useRef, useState } from "react"
import { Plus, Search, X, FileText, Database, MoreHorizontal, Pencil } from "lucide-react"
import { ApiError } from "@/api/client"
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  updateKnowledgeBase
} from "@/api/knowledgeBaseApi"
import { listDocuments } from "@/api/documentApi"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import { cn } from "./ui/utils"

type KbWithDocCount = KnowledgeBase & { docCount: number }

function formatRelativeTime(dateStr: string) {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return "几秒前"
  const diffMin = Math.floor(diffMs / (1000 * 60))
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  if (diffHours < 24) return `${diffHours}小时前`
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays === 1) return "昨天"
  if (diffDays < 7) return `${diffDays}天前`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}周前`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}个月前`
  return `${Math.floor(diffDays / 365)}年前`
}

export default function KnowledgeBaseGridPage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KbWithDocCount[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createDesc, setCreateDesc] = useState("")
  const [createLoading, setCreateLoading] = useState(false)
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editKb, setEditKb] = useState<KnowledgeBase | null>(null)
  const [editName, setEditName] = useState("")
  const [editDesc, setEditDesc] = useState("")
  const [editLoading, setEditLoading] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const loadKnowledgeBases = async () => {
    setLoading(true)
    setError("")
    try {
      const kbs = await listKnowledgeBases()
      // Fetch document counts in parallel
      const results = await Promise.allSettled(
        kbs.map(async (kb) => {
          try {
            const docs = await listDocuments(kb.id)
            return { ...kb, docCount: docs.length }
          } catch {
            return { ...kb, docCount: 0 }
          }
        })
      )
      setKnowledgeBases(
        results
          .filter((r): r is PromiseFulfilledResult<KbWithDocCount> => r.status === "fulfilled")
          .map((r) => r.value)
      )
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadKnowledgeBases()
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return knowledgeBases
    return knowledgeBases.filter(
      (kb) => kb.name.toLowerCase().includes(q) || (kb.description ?? "").toLowerCase().includes(q)
    )
  }, [knowledgeBases, query])

  const handleCreate = async () => {
    if (!createName.trim()) return
    setCreateLoading(true)
    setError("")
    try {
      await createKnowledgeBase({
        name: createName.trim(),
        description: createDesc.trim() || null
      })
      setCreateOpen(false)
      setCreateName("")
      setCreateDesc("")
      await loadKnowledgeBases()
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
    } finally {
      setCreateLoading(false)
    }
  }

  const handleDelete = async (kb: KnowledgeBase) => {
    if (!window.confirm(`确认删除知识库「${kb.name}」？`)) return
    try {
      await deleteKnowledgeBase(kb.id)
      await loadKnowledgeBases()
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
    }
  }

  const handleEdit = (kb: KnowledgeBase) => {
    setEditKb(kb)
    setEditName(kb.name)
    setEditDesc(kb.description ?? "")
    setEditOpen(true)
    setOpenMenuId(null)
  }

  const handleEditSubmit = async () => {
    if (!editKb || !editName.trim()) return
    setEditLoading(true)
    setError("")
    try {
      await updateKnowledgeBase(editKb.id, {
        name: editName.trim(),
        description: editDesc.trim() || null
      })
      setEditOpen(false)
      setEditKb(null)
      await loadKnowledgeBases()
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
    } finally {
      setEditLoading(false)
    }
  }

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpenMenuId(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <section className="min-h-full bg-white">
      {/* Header */}
      <div className="flex items-start justify-between px-6 pt-6 pb-4">
        <div>
          <h2 className="text-xl font-bold text-[#111]">知识库</h2>
          <div className="mt-3 flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-lg border border-[#dedede] bg-white px-3 py-1.5 text-[#999]">
              <Search className="h-4 w-4" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索知识库..."
                className="w-[200px] bg-transparent text-sm text-[#1f1f1f] outline-none placeholder:text-[#bbb]"
              />
              {query && (
                <button type="button" onClick={() => setQuery("")} className="text-[#bbb] hover:text-[#666]">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          创建
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-6 mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Grid */}
      <div className="px-6 pb-8">
        {loading ? (
          <div className="py-20 text-center text-sm text-[#999]">加载中...</div>
        ) : filtered.length === 0 ? (
          <div className="py-20 text-center text-sm text-[#999]">
            {query ? "没有匹配的知识库" : "暂无知识库，点击右上角创建"}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((kb) => (
              <div
                key={kb.id}
                className="group relative flex flex-col rounded-xl border border-[#e8e8e8] bg-white p-5 shadow-sm transition hover:border-[#d0d0d0] hover:shadow-md"
                style={{ minHeight: 150 }}
              >
                {/* Three-dot menu */}
                <div className="absolute right-3 top-3" ref={openMenuId === kb.id ? menuRef : undefined}>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setOpenMenuId(openMenuId === kb.id ? null : kb.id)
                    }}
                    className="flex h-6 w-6 items-center justify-center rounded-md text-[#ccc] opacity-0 transition hover:bg-[#f4f4f4] hover:text-[#666] group-hover:opacity-100"
                    title="更多操作"
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </button>
                  {openMenuId === kb.id && (
                    <div className="absolute right-0 top-8 z-50 w-44 rounded-lg border border-[#e7e7e7] bg-white py-1 shadow-lg">
                      <button
                        type="button"
                        onClick={() => handleEdit(kb)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#333] hover:bg-[#f5f5f5]"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        编辑
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setOpenMenuId(null)
                          void handleDelete(kb)
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-red-50"
                      >
                        <X className="h-3.5 w-3.5" />
                        删除
                      </button>
                    </div>
                  )}
                </div>

                {/* Icon + Name */}
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-orange-50">
                    <Database className="h-5 w-5 text-orange-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-[#1f1f1f]">{kb.name}</div>
                  </div>
                </div>

                {/* Description */}
                {kb.description && (
                  <p className="mt-3 line-clamp-1 text-xs leading-5 text-[#888]" title={kb.description}>
                    {kb.description}
                  </p>
                )}

                {/* Meta */}
                <div className="mt-auto flex items-center gap-3 text-xs text-[#999]">
                  <span className="flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5" />
                    {kb.docCount}
                  </span>
                  <span className="text-[#ddd]">/</span>
                  <span>更新于 {formatRelativeTime(kb.updated_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Modal */}
      {createOpen &&
        createPortal(
          <div className="fixed inset-0 z-[10000] flex items-center justify-center">
            <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setCreateOpen(false)} />
            <div className="relative z-10 w-full max-w-[420px] rounded-2xl border border-[#e7e7e7] bg-white p-6 shadow-[0_20px_60px_rgba(15,23,42,0.18)]">
              <div className="mb-5 flex items-center justify-between">
                <h3 className="text-base font-semibold text-[#1f1f1f]">创建知识库</h3>
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-[#999] transition hover:bg-[#f4f4f4]"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-[#333]">名称</label>
                  <input
                    autoFocus
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        void handleCreate()
                      }
                    }}
                    placeholder="例如：课题组论文库"
                    className="w-full rounded-lg border border-[#ddd] px-3 py-2 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-[#333]">描述</label>
                  <input
                    value={createDesc}
                    onChange={(e) => setCreateDesc(e.target.value)}
                    placeholder="可选"
                    className="w-full rounded-lg border border-[#ddd] px-3 py-2 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="rounded-lg border border-[#ddd] px-4 py-2 text-sm text-[#555] transition hover:bg-[#f5f5f5]"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={createLoading || !createName.trim()}
                  className={cn(
                    "rounded-lg px-4 py-2 text-sm font-medium text-white transition",
                    createLoading || !createName.trim()
                      ? "cursor-not-allowed bg-blue-300"
                      : "bg-blue-600 hover:bg-blue-700"
                  )}
                >
                  {createLoading ? "创建中..." : "创建"}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}

      {/* Edit Modal */}
      {editOpen && editKb &&
        createPortal(
          <div className="fixed inset-0 z-[10000] flex items-center justify-center">
            <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setEditOpen(false)} />
            <div className="relative z-10 w-full max-w-[420px] rounded-2xl border border-[#e7e7e7] bg-white p-6 shadow-[0_20px_60px_rgba(15,23,42,0.18)]">
              <div className="mb-5 flex items-center justify-between">
                <h3 className="text-base font-semibold text-[#1f1f1f]">编辑知识库</h3>
                <button
                  type="button"
                  onClick={() => setEditOpen(false)}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-[#999] transition hover:bg-[#f4f4f4]"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-[#333]">名称</label>
                  <input
                    autoFocus
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        void handleEditSubmit()
                      }
                    }}
                    placeholder="例如：课题组论文库"
                    className="w-full rounded-lg border border-[#ddd] px-3 py-2 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-[#333]">描述</label>
                  <input
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    placeholder="可选"
                    className="w-full rounded-lg border border-[#ddd] px-3 py-2 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditOpen(false)}
                  className="rounded-lg border border-[#ddd] px-4 py-2 text-sm text-[#555] transition hover:bg-[#f5f5f5]"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleEditSubmit()}
                  disabled={editLoading || !editName.trim()}
                  className={cn(
                    "rounded-lg px-4 py-2 text-sm font-medium text-white transition",
                    editLoading || !editName.trim()
                      ? "cursor-not-allowed bg-blue-300"
                      : "bg-blue-600 hover:bg-blue-700"
                  )}
                >
                  {editLoading ? "保存中..." : "保存"}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </section>
  )
}
