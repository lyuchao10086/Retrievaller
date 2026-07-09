import { useCallback, useEffect, useRef, useState } from "react"
import { FileJson, FilePlus2, FolderInput, RefreshCw, Trash2, UploadCloud } from "lucide-react"
import PageHeader from "./PageHeader"
import ConfirmDialog from "./ui/ConfirmDialog"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Input } from "./ui/input"
import { Label } from "./ui/label"
import { Select } from "./ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { ApiError } from "@/api/client"
import { listKnowledgeBases } from "@/api/knowledgeBaseApi"
import {
  deleteDocument,
  listDocuments,
  uploadDocument
} from "@/api/documentApi"
import type { DocumentRecord } from "@/types/document"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import { getDocumentStatusLabel, getDocumentStatusTone } from "./knowledgeBaseDetailUtils"

export default function UploadPage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbId, setSelectedKbId] = useState("")
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<DocumentRecord | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const showError = (unknownError: unknown) => {
    setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
  }

  const refreshDocuments = useCallback(async (kbId = selectedKbId) => {
    if (!kbId) {
      setDocuments([])
      return
    }
    setLoading(true)
    try {
      setDocuments(await listDocuments(kbId))
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setLoading(false)
    }
  }, [selectedKbId])

  const refreshKnowledgeBases = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listKnowledgeBases()
      setKnowledgeBases(data)
      setSelectedKbId((current) => current || data[0]?.id || "")
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshKnowledgeBases()
  }, [refreshKnowledgeBases])

  useEffect(() => {
    void refreshDocuments(selectedKbId)
  }, [selectedKbId, refreshDocuments])

  useEffect(() => {
    const hasParsingDocument = documents.some((document) => document.status === "parsing")
    if (!selectedKbId || !hasParsingDocument) return

    // parse 是 Celery 异步任务，前端只轮询当前知识库的文档列表。
    const timer = window.setInterval(() => void refreshDocuments(selectedKbId), 2000)
    return () => window.clearInterval(timer)
  }, [documents, selectedKbId, refreshDocuments])

  const addFiles = async (incoming: FileList | null) => {
    if (!incoming?.length || !selectedKbId) return
    const files = Array.from(incoming).filter(isSupportedTextFile)
    if (files.length === 0) {
      setError("当前仅支持上传 TXT、MD、MARKDOWN 文本文件")
      return
    }
    setError("")
    setMessage("")
    setLoading(true)
    try {
      for (const file of files) {
        await uploadDocument(selectedKbId, file)
      }
      setMessage("文件已上传，尚未完成分段与向量入库")
      await refreshDocuments(selectedKbId)
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setLoading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  const removeDocument = async (document: DocumentRecord) => {
    setDeleteTarget(document)
  }

  const confirmDeleteDocument = async () => {
    if (!deleteTarget) return
    setDeleteLoading(true)
    setError("")
    try {
      await deleteDocument(selectedKbId, deleteTarget.id)
      setMessage("文档已删除")
      await refreshDocuments(selectedKbId)
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setDeleteLoading(false)
      setDeleteTarget(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="文档上传"
        description="上传 TXT、MD、MARKDOWN 原始文件到知识库；分段、清洗与向量入库状态以后端实际接入能力为准。"
      />

      {(message || error) && (
        <div className="mb-4 grid gap-2">
          {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}
          {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>上传区域</CardTitle>
            <CardDescription>当前支持上传 TXT/MD 原始文件，分段与入库处理待接入</CardDescription>
          </CardHeader>
          <CardContent>
            <button
              type="button"
              disabled={!selectedKbId || loading}
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                void addFiles(event.dataTransfer.files)
              }}
              className="flex min-h-[260px] w-full flex-col items-center justify-center rounded-lg border-2 border-dashed border-blue-200 bg-blue-50/50 p-8 text-center transition hover:border-primary hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <UploadCloud className="h-12 w-12 text-primary" />
              <p className="mt-4 text-lg font-semibold">拖拽文件到此处，或点击上传</p>
              <p className="mt-2 text-sm text-muted-foreground">
                {selectedKbId ? "文件会保存到 MinIO；分段、清洗与向量入库暂未在上传时执行" : "请先选择或创建知识库"}
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {["TXT", "MD", "MARKDOWN"].map((type) => (
                  <Badge key={type} variant="purple">{type}</Badge>
                ))}
              </div>
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".txt,.md,.markdown,text/plain,text/markdown"
              multiple
              className="hidden"
              onChange={(e) => void addFiles(e.target.files)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>上传配置</CardTitle>
            <CardDescription>选择文档归属的主题知识库</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label>目标知识库</Label>
              <Select value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
                <option value="">请选择知识库</option>
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>{kb.name}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>后端对象存储路径</Label>
              <Input readOnly value="users/default_user/knowledge_bases/{kb_id}/raw/{document_id}/{file_name}" />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <p className="text-sm font-medium">分段与向量入库</p>
                <p className="text-xs text-muted-foreground">当前上传页不提交分段清洗配置；处理状态请以文档列表为准</p>
              </div>
              <Badge variant="secondary">待接入</Badge>
            </div>
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <p className="text-sm font-medium">支持的文件类型</p>
                <p className="text-xs text-muted-foreground">当前最小闭环只支持纯文本，不接收 PDF/DOCX/图片</p>
              </div>
              <Badge variant="secondary">TXT / MD</Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>文件列表</CardTitle>
            <CardDescription>展示文件状态与处理阶段</CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void refreshDocuments()}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
            <Button variant="outline" onClick={() => inputRef.current?.click()} disabled={!selectedKbId}>
              <FilePlus2 className="h-4 w-4" />
              添加文件
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文件名</TableHead>
                <TableHead>文件类型</TableHead>
                <TableHead>文件大小</TableHead>
                <TableHead>上传时间</TableHead>
                <TableHead>当前状态</TableHead>
                <TableHead>任务/错误</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                    {selectedKbId ? "当前知识库暂无文档" : "请选择知识库"}
                  </TableCell>
                </TableRow>
              ) : (
                documents.map((document) => (
                  <TableRow key={document.id}>
                    <TableCell className="font-medium">
                      <span className="flex items-center gap-2">
                        <FolderInput className="h-4 w-4 text-primary" />
                        {document.file_name}
                      </span>
                    </TableCell>
                    <TableCell>{document.file_type || "-"}</TableCell>
                    <TableCell>{formatBytes(document.file_size)}</TableCell>
                    <TableCell>{formatDate(document.created_at)}</TableCell>
                    <TableCell>
                      <Badge variant={getDocumentStatusTone(document.status)}>
                        {getDocumentStatusLabel(document.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[280px] text-xs text-muted-foreground">
                      {document.error_message || document.task_id || "-"}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        {document.status === "uploaded" && (
                          <Button size="sm" disabled title="后端解析、分段与向量入库流程待接入">
                            <FileJson className="h-4 w-4" />
                            解析待接入
                          </Button>
                        )}
                        {document.status === "parsed" && (
                          <Button size="sm" variant="outline" disabled title="解析结果查看待正式接入处理流程">
                            <FileJson className="h-4 w-4" />
                            解析结果待接入
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => void removeDocument(document)}>
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <ConfirmDialog
        open={deleteTarget !== null}
        title="要删除该文档吗？"
        description={deleteTarget ? `确认删除文档「${deleteTarget.file_name}」？此操作不可撤销。` : ""}
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

function formatDate(value?: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatBytes(value?: number | null) {
  if (value == null) return "-"
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
