import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ArrowLeft,
  ChevronDown,
  FileText,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X
} from "lucide-react"
import { ApiError } from "@/api/client"
import { deleteDocument, listDocuments, uploadDocument } from "@/api/documentApi"
import { listQaRecords } from "@/api/ragApi"
import type { DocumentRecord } from "@/types/document"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import ConfirmDialog from "./ui/ConfirmDialog"
import {
  buildDocumentRecallCounts,
  filterDocuments,
  formatCompactCount,
  getDocumentAvailabilityLabel
} from "./knowledgeBaseDetailUtils"
import { cn } from "./ui/utils"

type Props = {
  knowledgeBase: KnowledgeBase
  onBack: () => void
}

export default function KnowledgeBaseDetailPage({ knowledgeBase, onBack }: Props) {
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
  const inputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const showError = (unknownError: unknown) => {
    setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
  }

  const refresh = useCallback(async () => {
    setLoading(true)
    setError("")
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
      showError(unknownError)
    } finally {
      setLoading(false)
    }
  }, [knowledgeBase.id])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpenMenuId(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const filteredDocuments = useMemo(
    () => filterDocuments(documents, query),
    [documents, query]
  )

  const addFiles = async (incoming: FileList | null) => {
    if (!incoming?.length) return
    setUploading(true)
    setError("")
    setMessage("")
    try {
      for (const file of Array.from(incoming)) {
        await uploadDocument(knowledgeBase.id, file)
      }
      setMessage("文件已添加")
      await refresh()
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
    } finally {
      setDeleteLoading(false)
    }
  }

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
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="hidden h-9 w-9 items-center justify-center rounded-lg text-[#64748b] transition hover:bg-[#f2f4f7] disabled:opacity-50 sm:flex"
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
        <table className="min-w-[980px] w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[#edf0f4] text-left text-xs font-medium text-[#637083]">
              <th className="w-8 px-3 py-3">
                <span className="sr-only">选择</span>
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
              <th className="w-28 px-3 py-3 font-medium">状态</th>
              <th className="w-24 px-3 py-3 font-medium">操作</th>
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
                const available = availability === "可用"
                return (
                  <tr key={document.id} className="border-b border-[#f1f3f6] text-[#1f2937] transition hover:bg-[#fafbfc]">
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        aria-label={`选择 ${document.file_name}`}
                        className="h-4 w-4 rounded border-[#d0d7de] text-blue-600 focus:ring-blue-500"
                      />
                    </td>
                    <td className="px-0 py-3 text-xs text-[#64748b]">{index + 1}</td>
                    <td className="px-3 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <FileTypeBadge fileName={document.file_name} fileType={document.file_type} />
                        <span className="truncate font-medium text-[#172033]" title={document.file_name}>
                          {document.file_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-[#334155]">{formatCompactCount(document.file_size)}</td>
                    <td className="px-3 py-3 text-[#334155]">{recallCounts[document.id] ?? 0}</td>
                    <td className="px-3 py-3 text-[#334155]">{formatTableDate(document.created_at)}</td>
                    <td className="px-3 py-3">
                      <span className="inline-flex items-center gap-1.5 text-sm text-[#1f2937]">
                        <span className={cn("h-2 w-2 rounded-full", available ? "bg-emerald-500" : "bg-amber-400")} />
                        {availability}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-3">
                        <span
                          role="switch"
                          aria-checked={available}
                          className={cn(
                            "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition",
                            available ? "bg-blue-600" : "bg-[#cbd5e1]"
                          )}
                        >
                          <span
                            className={cn(
                              "block h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
                              available ? "translate-x-4" : "translate-x-0.5"
                            )}
                          />
                        </span>
                        <div className="relative" ref={openMenuId === document.id ? menuRef : undefined}>
                          <button
                            type="button"
                            onClick={() => setOpenMenuId(openMenuId === document.id ? null : document.id)}
                            className="flex h-7 w-7 items-center justify-center rounded-md text-[#64748b] transition hover:bg-[#eef2f7] hover:text-[#111]"
                            title="更多操作"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                          {openMenuId === document.id && (
                            <div className="absolute right-0 top-8 z-50 w-32 rounded-lg border border-[#e7e7e7] bg-white py-1 shadow-lg">
                              <button
                                type="button"
                                onClick={() => {
                                  setOpenMenuId(null)
                                  setDeleteTarget(document)
                                }}
                                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-500 transition hover:bg-red-50"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                删除
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="要删除该文件吗？"
        description={deleteTarget ? `确认删除文件「${deleteTarget.file_name}」？此操作不可撤销。` : ""}
        confirmLabel="确认删除"
        cancelLabel="取消"
        danger
        loading={deleteLoading}
        onConfirm={() => void confirmDeleteDocument()}
        onCancel={() => setDeleteTarget(null)}
      />
    </section>
  )
}

function FileTypeBadge({ fileName, fileType }: { fileName: string; fileType?: string | null }) {
  const extension = getFileExtension(fileName, fileType)
  return (
    <span className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-[3px] bg-blue-500 px-0.5 text-[8px] font-bold leading-none text-white">
      {extension}
    </span>
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
