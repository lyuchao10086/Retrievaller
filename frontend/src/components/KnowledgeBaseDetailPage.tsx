import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import {
  ArrowLeft,
  ChevronDown,
  CheckCircle2,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Trash2,
  X
} from "lucide-react"
import { ApiError } from "@/api/client"
import { deleteDocument, listDocuments, processDocument, renameDocument, uploadDocument } from "@/api/documentApi"
import { listQaRecords } from "@/api/ragApi"
import type { DocumentRecord } from "@/types/document"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import ConfirmDialog from "./ui/ConfirmDialog"
import {
  buildDocumentRecallCounts,
  filterDocuments,
  formatCompactCount,
  getDocumentAvailabilityLabel,
  getDocumentStatusLabel,
  isDocumentRetrievable
} from "./knowledgeBaseDetailUtils"
import { cn } from "./ui/utils"

type Props = {
  knowledgeBase: KnowledgeBase
  onBack: () => void
  onChunkSettings?: (document: DocumentRecord) => void
}

export default function KnowledgeBaseDetailPage({ knowledgeBase, onBack, onChunkSettings }: Props) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [recallCounts, setRecallCounts] = useState<Record<string, number>>({})
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DocumentRecord | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [renameTarget, setRenameTarget] = useState<DocumentRecord | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [renameLoading, setRenameLoading] = useState(false)
  const [workingDocumentId, setWorkingDocumentId] = useState<string | null>(null)
  const [workingAction, setWorkingAction] = useState<"process" | null>(null)
  const [menuPosition, setMenuPosition] = useState<{ x: number; y: number; flipUp: boolean } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const menuButtonRefs = useRef<Map<string, HTMLButtonElement>>(new Map())
  const menuRef = useRef<HTMLDivElement>(null)

  const showError = (unknownError: unknown) => {
    setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
  }

  // Auto-dismiss success message after 2 seconds
  useEffect(() => {
    if (!message) return
    const timer = setTimeout(() => setMessage(""), 2000)
    return () => clearTimeout(timer)
  }, [message])

  const refresh = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLoading(true)
      setError("")
    }
    try {
      const [documentData, qaRecordsResult] = await Promise.allSettled([
        listDocuments(knowledgeBase.id),
        listQaRecords()
      ])

      if (documentData.status === "fulfilled") {
        setDocuments(documentData.value)
      } else {
        throw documentData.reason
      }

      if (qaRecordsResult.status === "fulfilled") {
        setRecallCounts(buildDocumentRecallCounts(qaRecordsResult.value, knowledgeBase.id))
      } else {
        setRecallCounts({})
      }
    } catch (unknownError) {
      if (!options?.silent) showError(unknownError)
    } finally {
      if (!options?.silent) setLoading(false)
    }
  }, [knowledgeBase.id])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!documents.some((document) => isProcessingDocument(document.status))) return
    const timer = window.setInterval(() => {
      void refresh({ silent: true })
    }, 3000)
    return () => window.clearInterval(timer)
  }, [documents, refresh])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      const isMenuButton = menuButtonRefs.current.get(openMenuId ?? "")?.contains(target)
      const isMenuContent = menuRef.current?.contains(target)
      if (openMenuId && !isMenuButton && !isMenuContent) {
        setOpenMenuId(null)
        setMenuPosition(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [openMenuId])

  // Focus rename input when dialog opens
  useEffect(() => {
    if (renameTarget) {
      setRenameValue(renameTarget.file_name)
      // Defer focus to next tick so the input is rendered
      requestAnimationFrame(() => renameInputRef.current?.focus())
    }
  }, [renameTarget])

  const filteredDocuments = useMemo(
    () => filterDocuments(documents, query),
    [documents, query]
  )

  const addFiles = async (incoming: FileList | null) => {
    if (!incoming?.length) return
    const files = Array.from(incoming).filter(isSupportedTextFile)
    if (files.length === 0) {
      setError("当前仅支持上传 TXT、MD、MARKDOWN 文本文件")
      return
    }
    setUploading(true)
    setError("")
    setMessage("")
    try {
      for (const file of files) {
        await uploadDocument(knowledgeBase.id, file)
      }
      await refresh()
      setMessage("文件已上传，可点击开始处理；处理完成后即可用于问答检索")
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  const confirmDeleteDocument = async () => {
    if (!deleteTarget) return
    setDeleteLoading(true)
    setError("")
    setMessage("")
    try {
      await deleteDocument(knowledgeBase.id, deleteTarget.id)
      setDeleteTarget(null)
      setMessage("文件已删除")
      await refresh()
    } catch (unknownError) {
      showError(unknownError)
      await refresh({ silent: true })
    } finally {
      setDeleteLoading(false)
    }
  }

  const confirmBatchDelete = async () => {
    if (selectedIds.size === 0) return
    setDeleteLoading(true)
    setError("")
    setMessage("")
    try {
      for (const id of Array.from(selectedIds)) {
        await deleteDocument(knowledgeBase.id, id)
      }
      const count = selectedIds.size
      setSelectedIds(new Set())
      setDeleteTarget(null)
      setMessage(`已删除 ${count} 个文件`)
      await refresh()
    } catch (unknownError) {
      showError(unknownError)
      await refresh({ silent: true })
    } finally {
      setDeleteLoading(false)
    }
  }

  const confirmRename = async () => {
    if (!renameTarget || !renameValue.trim()) return
    setRenameLoading(true)
    setError("")
    try {
      await renameDocument(knowledgeBase.id, renameTarget.id, renameValue.trim())
      setRenameTarget(null)
      setMessage("重命名成功")
      await refresh()
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setRenameLoading(false)
    }
  }

  const submitDocumentProcessing = async (document: DocumentRecord) => {
    setWorkingDocumentId(document.id)
    setWorkingAction("process")
    setError("")
    setMessage("")
    try {
      await processDocument(knowledgeBase.id, document.id)
      setMessage("已提交后台处理，请稍候")
      await refresh()
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setWorkingDocumentId(null)
      setWorkingAction(null)
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredDocuments.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredDocuments.map((d) => d.id)))
    }
  }

  const allSelected = filteredDocuments.length > 0 && selectedIds.size === filteredDocuments.length
  const someSelected = selectedIds.size > 0

  return (
    <section className="min-h-full bg-white px-2 py-1 sm:px-0">
      <div className="flex items-start justify-between gap-4 px-3 pt-2 sm:px-0">
        <div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBack}
              className="flex h-7 w-7 items-center justify-center rounded-md text-[#7a8495] transition hover:bg-[#f2f4f7] hover:text-[#111]"
              title="返回知识库"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <h2 className="text-base font-semibold text-[#0f172a]">{knowledgeBase.name}</h2>
          </div>
          <div className="mt-6 flex h-8 w-[250px] max-w-[calc(100vw-3rem)] items-center gap-2 rounded-lg bg-[#f2f4f7] px-3 text-[#9aa3b2]">
            <Search className="h-4 w-4" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索"
              className="min-w-0 flex-1 bg-transparent text-sm text-[#1f2937] outline-none placeholder:text-[#9aa3b2]"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="text-[#a7b0bd] transition hover:text-[#4b5563]"
                title="清空搜索"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
        <div className="mt-[52px] flex items-center gap-2">
          {someSelected && (
            <button
              type="button"
              onClick={() => setDeleteTarget({ id: "__batch__" } as DocumentRecord)}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 text-sm font-medium text-red-600 transition hover:bg-red-100"
            >
              <Trash2 className="h-4 w-4" />
              删除 ({selectedIds.size})
            </button>
          )}
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[#64748b] transition hover:bg-[#f2f4f7] disabled:opacity-50"
            title="刷新"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </button>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            <Plus className="h-4 w-4" />
            添加文件
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".txt,.md,.markdown,text/plain,text/markdown"
            multiple
            className="hidden"
            onChange={(event) => void addFiles(event.target.files)}
          />
        </div>
      </div>

      {(message || error) && (
        <div className="mt-5 grid gap-2 px-3 sm:px-0">
          {message && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {message}
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>
      )}

      <div className="mt-8 overflow-x-auto">
        <table className="min-w-[1120px] w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[#edf0f4] text-left text-xs font-medium text-[#637083]">
              <th className="w-8 px-3 py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  aria-label="全选"
                  className="h-4 w-4 rounded border-[#d0d7de] text-blue-600 focus:ring-blue-500"
                />
              </th>
              <th className="w-8 px-0 py-3">
                <span className="sr-only">序号</span>
              </th>
              <th className="px-3 py-3 font-medium">名称</th>
              <th className="w-28 px-3 py-3 font-medium">字符数</th>
              <th className="w-32 px-3 py-3 font-medium">
                <span className="inline-flex items-center gap-1">
                  召回次数
                  <ChevronDown className="h-3 w-3" />
                </span>
              </th>
              <th className="w-40 px-3 py-3 font-medium">
                <span className="inline-flex items-center gap-1">
                  上传时间
                  <ChevronDown className="h-3 w-3" />
                </span>
              </th>
              <th className="w-36 px-3 py-3 font-medium">状态</th>
              <th className="w-56 px-3 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && documents.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-16 text-center text-sm text-[#94a3b8]">
                  加载中...
                </td>
              </tr>
            ) : filteredDocuments.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-16 text-center text-sm text-[#94a3b8]">
                  {query ? "没有匹配的文件" : "当前知识库暂无文件"}
                </td>
              </tr>
            ) : (
              filteredDocuments.map((document, index) => {
                const availability = getDocumentAvailabilityLabel(document.status)
                const retrievable = isDocumentRetrievable(document.status)
                const isSelected = selectedIds.has(document.id)
                const isWorking = workingDocumentId === document.id
                const actionDisabled = workingDocumentId !== null
                return (
                  <tr
                    key={document.id}
                    className={cn(
                      "border-b border-[#f1f3f6] text-[#1f2937] transition",
                      isSelected ? "bg-blue-50/60" : "hover:bg-[#fafbfc]"
                    )}
                  >
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(document.id)}
                        aria-label={`选择 ${document.file_name}`}
                        className="h-4 w-4 rounded border-[#d0d7de] text-blue-600 focus:ring-blue-500"
                      />
                    </td>
                    <td className="px-0 py-3 text-xs text-[#64748b]">{index + 1}</td>
                    <td className="px-3 py-3">
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-2">
                          <FileTypeBadge fileName={document.file_name} fileType={document.file_type} />
                          <span className="truncate font-medium text-[#172033]" title={document.file_name}>
                            {document.file_name}
                          </span>
                        </div>
                        {document.status === "failed" && document.error_message && (
                          <div className="mt-1 max-w-[360px] truncate text-xs text-red-500" title={document.error_message}>
                            {document.error_message}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-[#334155]">{formatCompactCount(document.file_size)}</td>
                    <td className="px-3 py-3 text-[#334155]">{recallCounts[document.id] ?? 0}</td>
                    <td className="px-3 py-3 text-[#334155]">{formatTableDate(document.created_at)}</td>
                    <td className="px-3 py-3">
                      <span
                        className="inline-flex items-center gap-1.5 text-sm text-[#1f2937]"
                        title={availability}
                      >
                        <span className={cn("h-2 w-2 rounded-full", retrievable ? "bg-emerald-500" : "bg-amber-400")} />
                        {getDocumentStatusLabel(document.status)}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-3">
                        <DocumentActionButton
                          document={document}
                          isWorking={isWorking}
                          disabled={actionDisabled}
                          workingAction={isWorking ? workingAction : null}
                          onProcess={() => void submitDocumentProcessing(document)}
                        />
                        <span
                          role="switch"
                          aria-checked={retrievable}
                          aria-label={retrievable ? "已入库，可用于问答检索" : "尚未入库，暂不可检索"}
                          title={retrievable ? "已入库，可用于问答检索" : "尚未完成分段与向量入库，暂不可检索"}
                          className={cn(
                            "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition",
                            retrievable ? "bg-blue-600" : "bg-[#cbd5e1]"
                          )}
                        >
                          <span
                            className={cn(
                              "block h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
                              retrievable ? "translate-x-4" : "translate-x-0.5"
                            )}
                          />
                        </span>
                        <button
                          type="button"
                          ref={(el) => {
                            if (el) {
                              menuButtonRefs.current.set(document.id, el)
                            } else {
                              menuButtonRefs.current.delete(document.id)
                            }
                          }}
                          onClick={() => {
                            const isOpen = openMenuId === document.id
                            if (!isOpen) {
                              const btn = menuButtonRefs.current.get(document.id)
                              if (btn) {
                                const rect = btn.getBoundingClientRect()
                                const menuHeight = 130
                                const shouldFlipUp = rect.bottom + menuHeight > window.innerHeight
                                setMenuPosition({
                                  x: rect.right,
                                  y: shouldFlipUp ? rect.top - menuHeight : rect.bottom + 4,
                                  flipUp: shouldFlipUp
                                })
                              }
                            } else {
                              setMenuPosition(null)
                            }
                            setOpenMenuId(isOpen ? null : document.id)
                          }}
                          className="flex h-7 w-7 items-center justify-center rounded-md text-[#64748b] transition hover:bg-[#eef2f7] hover:text-[#111]"
                          title="更多操作"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Dropdown menu rendered via portal to escape table overflow clipping */}
      {openMenuId && menuPosition && createPortal(
        (() => {
          const menuDoc = documents.find((d) => d.id === openMenuId)
          if (!menuDoc) return null
          return (
            <div
              ref={menuRef}
              className="fixed z-[9999] w-36 rounded-lg border border-[#e7e7e7] bg-white py-1 shadow-lg"
              style={{
                left: `${menuPosition.x}px`,
                top: `${menuPosition.y}px`,
                transform: "translateX(-100%)"
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setOpenMenuId(null)
                  setMenuPosition(null)
                  setRenameTarget(menuDoc)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#334155] transition hover:bg-[#f5f7fa]"
              >
                <Pencil className="h-3.5 w-3.5" />
                重命名
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpenMenuId(null)
                  setMenuPosition(null)
                  onChunkSettings?.(menuDoc)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#334155] transition hover:bg-[#f5f7fa]"
              >
                <Settings2 className="h-3.5 w-3.5" />
                分段设置（草稿）
              </button>
              <div className="my-1 border-t border-[#f0f0f0]" />
              <button
                type="button"
                onClick={() => {
                  setOpenMenuId(null)
                  setMenuPosition(null)
                  setDeleteTarget(menuDoc)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-500 transition hover:bg-red-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除
              </button>
            </div>
          )
        })(),
        document.body
      )}

      {/* Single document delete dialog */}
      <ConfirmDialog
        open={deleteTarget !== null && deleteTarget.id !== "__batch__"}
        title="要删除该文件吗？"
        description={deleteTarget && deleteTarget.id !== "__batch__" ? `确认删除文件「${deleteTarget.file_name}」？此操作不可撤销。` : ""}
        confirmLabel="确认删除"
        cancelLabel="取消"
        danger
        loading={deleteLoading}
        onConfirm={() => void confirmDeleteDocument()}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Batch delete dialog */}
      <ConfirmDialog
        open={deleteTarget !== null && deleteTarget.id === "__batch__"}
        title="确认批量删除？"
        description={`将删除选中的 ${selectedIds.size} 个文件，此操作不可撤销。`}
        confirmLabel="确认删除"
        cancelLabel="取消"
        danger
        loading={deleteLoading}
        onConfirm={() => void confirmBatchDelete()}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Rename dialog */}
      {renameTarget && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setRenameTarget(null)} />
          <div className="relative z-10 w-full max-w-[420px] rounded-2xl border border-[#e7e7e7] bg-white p-6 shadow-[0_20px_60px_rgba(15,23,42,0.18)]">
            <button
              type="button"
              onClick={() => setRenameTarget(null)}
              className="absolute right-4 top-4 flex h-7 w-7 items-center justify-center rounded-lg text-[#999] transition hover:bg-[#f4f4f4]"
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-lg font-semibold text-[#1f1f1f]">重命名文件</h3>
            <p className="mt-2 text-sm leading-6 text-[#666]">
              将「{renameTarget.file_name}」重命名为：
            </p>
            <input
              ref={renameInputRef}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  void confirmRename()
                }
                if (e.key === "Escape") {
                  setRenameTarget(null)
                }
              }}
              className="mt-4 w-full rounded-lg border border-[#ddd] px-3 py-2 text-sm text-[#1f2937] outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              placeholder="输入新文件名"
            />
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRenameTarget(null)}
                disabled={renameLoading}
                className="rounded-lg border border-[#ddd] px-4 py-2 text-sm text-[#555] transition hover:bg-[#f5f5f5] disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void confirmRename()}
                disabled={renameLoading || !renameValue.trim()}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
              >
                {renameLoading ? "处理中..." : "确认"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function DocumentActionButton({
  document,
  isWorking,
  disabled,
  workingAction,
  onProcess
}: {
  document: DocumentRecord
  isWorking: boolean
  disabled: boolean
  workingAction: "process" | null
  onProcess: () => void
}) {
  if (
    document.status === "uploaded" ||
    document.status === "failed" ||
    document.status === "parsed" ||
    document.status === "chunked"
  ) {
    const label = document.status === "failed"
      ? "重试处理"
      : document.status === "uploaded"
        ? "开始处理"
        : "继续处理"
    return (
      <button
        type="button"
        onClick={onProcess}
        disabled={disabled}
        className={cn(
          "inline-flex h-7 min-w-[84px] items-center justify-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
          document.status === "failed"
            ? "border-red-200 bg-red-50 text-red-600 hover:bg-red-100"
            : "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100"
        )}
      >
        {isWorking && workingAction === "process" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Settings2 className="h-3.5 w-3.5" />}
        {isWorking && workingAction === "process" ? "提交中" : label}
      </button>
    )
  }

  if (isProcessingDocument(document.status)) {
    const label = document.status === "parsing"
      ? "解析中"
      : document.status === "chunking"
        ? "分段中"
        : "向量中"
    return (
      <span className="inline-flex h-7 min-w-[84px] items-center justify-center gap-1.5 rounded-md bg-amber-50 px-2.5 text-xs font-medium text-amber-700">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {label}
      </span>
    )
  }

  if (document.status === "embedded") {
    return (
      <span className="inline-flex h-7 min-w-[84px] items-center justify-center gap-1.5 rounded-md bg-emerald-50 px-2.5 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" />
        可检索
      </span>
    )
  }

  return (
    <span className="inline-flex h-7 min-w-[84px] items-center justify-center rounded-md bg-slate-50 px-2.5 text-xs text-slate-500">
      待处理
    </span>
  )
}

function isProcessingDocument(status: string) {
  return status === "parsing" || status === "chunking" || status === "embedding"
}

function FileTypeBadge({ fileName, fileType }: { fileName: string; fileType?: string | null }) {
  const extension = getFileExtension(fileName, fileType)
  return (
    <span className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-[3px] bg-blue-500 px-0.5 text-[8px] font-bold leading-none text-white">
      {extension}
    </span>
  )
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

function getFileExtension(fileName: string, fileType?: string | null) {
  const fromName = fileName.split(".").pop()
  const extension = (fromName && fromName !== fileName ? fromName : fileType || "FILE").toUpperCase()
  if (extension === "MARKDOWN") return "MD"
  return extension.slice(0, 3)
}

function formatTableDate(value?: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, "0")
  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  ].join(" ")
}
