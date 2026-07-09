import { useCallback, useEffect, useMemo, useState } from "react"
import { ArrowRight, Database, GitBranch, Layers3, Plus, RefreshCw, Save, Trash2 } from "lucide-react"
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
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  updateKnowledgeBase
} from "@/api/knowledgeBaseApi"
import { listDocuments } from "@/api/documentApi"
import type { ChunkRecord } from "@/types/chunk"
import type { DocumentRecord, EmbeddingStatus } from "@/types/document"
import type { KnowledgeBase } from "@/types/knowledgeBase"
import { getDocumentStatusLabel } from "./knowledgeBaseDetailUtils"

export default function KnowledgeBasePage() {
  const flow = ["原始文本", "文本清洗", "文档切分", "Embedding", "向量存储", "Retriever"]
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbId, setSelectedKbId] = useState("")
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [selectedDocumentId, setSelectedDocumentId] = useState("")
  const [chunks, setChunks] = useState<ChunkRecord[]>([])
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus | null>(null)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const selectedKb = useMemo(
    () => knowledgeBases.find((knowledgeBase) => knowledgeBase.id === selectedKbId) ?? null,
    [knowledgeBases, selectedKbId]
  )
  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId]
  )

  const showError = (unknownError: unknown) => {
    setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
  }

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

  const refreshDocuments = useCallback(async (kbId = selectedKbId) => {
    if (!kbId) {
      setDocuments([])
      setSelectedDocumentId("")
      return
    }
    try {
      const data = await listDocuments(kbId)
      setDocuments(data)
      setSelectedDocumentId((current) => current || data[0]?.id || "")
    } catch (unknownError) {
      showError(unknownError)
    }
  }, [selectedKbId])

  useEffect(() => {
    void refreshKnowledgeBases()
  }, [refreshKnowledgeBases])

  useEffect(() => {
    if (!selectedKb) {
      setName("")
      setDescription("")
      return
    }
    setName(selectedKb.name)
    setDescription(selectedKb.description ?? "")
    setChunks([])
    setEmbeddingStatus(null)
    void refreshDocuments(selectedKb.id)
  }, [selectedKb, refreshDocuments])

  const submitCreate = async () => {
    if (!name.trim()) return
    setLoading(true)
    setError("")
    try {
      const created = await createKnowledgeBase({
        name: name.trim(),
        description: description.trim() || null
      })
      setMessage("知识库已创建")
      await refreshKnowledgeBases()
      setSelectedKbId(created.id)
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setLoading(false)
    }
  }

  const submitUpdate = async () => {
    if (!selectedKb || !name.trim()) return
    setLoading(true)
    setError("")
    try {
      await updateKnowledgeBase(selectedKb.id, {
        name: name.trim(),
        description: description.trim() || null
      })
      setMessage("知识库已更新")
      await refreshKnowledgeBases()
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setLoading(false)
    }
  }

  const submitDelete = async () => {
    if (!selectedKb) return
    setDeleteConfirmOpen(true)
  }

  const confirmDelete = async () => {
    if (!selectedKb) return
    setDeleteLoading(true)
    setError("")
    try {
      await deleteKnowledgeBase(selectedKb.id)
      setMessage("知识库已删除")
      setSelectedKbId("")
      setSelectedDocumentId("")
      setChunks([])
      await refreshKnowledgeBases()
    } catch (unknownError) {
      showError(unknownError)
    } finally {
      setDeleteLoading(false)
      setDeleteConfirmOpen(false)
    }
  }

  return (
    <section>
      <PageHeader
        title="知识库构建"
        description="查看知识库与文档状态；Chunk、Embedding 与向量入库操作仍是待接入入口。"
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
            <CardTitle>知识库配置</CardTitle>
            <CardDescription>主题知识库与当前文档处理对象</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>当前知识库</Label>
              <Select value={selectedKbId} onChange={(event) => setSelectedKbId(event.target.value)}>
                <option value="">新建知识库</option>
                {knowledgeBases.map((knowledgeBase) => (
                  <option key={knowledgeBase.id} value={knowledgeBase.id}>
                    {knowledgeBase.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>知识库状态</Label>
              <Input readOnly value={selectedKb?.status ?? "new"} />
            </div>
            <div className="space-y-2">
              <Label>知识库名称</Label>
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：课题组论文库" />
            </div>
            <div className="space-y-2">
              <Label>知识库描述</Label>
              <Input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="可选" />
            </div>
            <div className="space-y-2">
              <Label>当前文档</Label>
              <Select value={selectedDocumentId} onChange={(event) => setSelectedDocumentId(event.target.value)}>
                <option value="">请选择文档</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.file_name} ({getDocumentStatusLabel(document.status)})
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Embedding 模型</Label>
              <Input readOnly value="quentinz/bge-large-zh-v1.5:latest" />
            </div>
            <div className="flex flex-wrap gap-2 md:col-span-2">
              <Button onClick={() => void submitCreate()} disabled={loading || !name.trim()}>
                <Plus className="h-4 w-4" />
                创建知识库
              </Button>
              <Button variant="outline" onClick={() => void submitUpdate()} disabled={loading || !selectedKb}>
                <Save className="h-4 w-4" />
                保存修改
              </Button>
              <Button variant="outline" onClick={() => void refreshKnowledgeBases()} disabled={loading}>
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
              <Button variant="destructive" onClick={() => void submitDelete()} disabled={loading || !selectedKb}>
                <Trash2 className="h-4 w-4" />
                删除
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>构建流程图</CardTitle>
            <CardDescription>流程示意，仅用于展示后续接入方向</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-3">
              {flow.map((item, index) => (
                <div key={item} className="relative rounded-lg border bg-gradient-to-br from-white to-blue-50 p-4">
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-primary text-white">
                    {index < 2 ? <GitBranch className="h-5 w-5" /> : index < 4 ? <Layers3 className="h-5 w-5" /> : <Database className="h-5 w-5" />}
                  </div>
                  <p className="font-semibold">{item}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Step {index + 1}</p>
                  {index < flow.length - 1 && <ArrowRight className="absolute -right-2 top-1/2 hidden h-4 w-4 text-slate-300 md:block" />}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>切片预览表格</CardTitle>
            <CardDescription>Chunk、Embedding 与向量状态操作待接入正式处理流程</CardDescription>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" disabled>
              文档切分（待接入）
            </Button>
            <Button variant="outline" disabled>
              查看 Chunk（待接入）
            </Button>
            <Button disabled>
              Embedding（待接入）
            </Button>
            <Button variant="outline" disabled>
              向量状态（待接入）
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            当前页面不触发后端切分、Embedding 或 Milvus 入库请求，避免误认为构建链路已完成接入。
          </div>
          {embeddingStatus && (
            <div className="mb-4 grid gap-3 rounded-lg border bg-blue-50/50 p-4 text-sm md:grid-cols-4">
              <span>document_status: <b>{embeddingStatus.status}</b></span>
              <span>total_chunks: <b>{embeddingStatus.total_chunks}</b></span>
              <span>embedded_chunks: <b>{embeddingStatus.embedded_chunks}</b></span>
              <span>pending_chunks: <b>{embeddingStatus.pending_chunks}</b></span>
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Chunk ID</TableHead>
                <TableHead>来源文档</TableHead>
                <TableHead>章节</TableHead>
                <TableHead>文本片段</TableHead>
                <TableHead>Embedding 状态</TableHead>
                <TableHead>入库状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {chunks.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                    {selectedDocumentId ? "构建处理入口待接入，当前不展示真实 Chunk 预览" : "请选择一个文档"}
                  </TableCell>
                </TableRow>
              ) : (
                chunks.map((chunk) => (
                  <TableRow key={chunk.id}>
                    <TableCell className="font-mono text-xs">{chunk.id}</TableCell>
                    <TableCell>{selectedDocument?.file_name ?? chunk.document_id}</TableCell>
                    <TableCell>
                      <div className="text-sm">{chunk.chapter || "-"}</div>
                      <div className="text-xs text-muted-foreground">{chunk.section || chunk.subsection || "-"}</div>
                    </TableCell>
                    <TableCell className="max-w-md text-muted-foreground">
                      <div className="max-h-20 overflow-auto">{chunk.content}</div>
                    </TableCell>
                    <TableCell><Badge variant={chunk.status === "embedded" ? "success" : "warning"}>{chunk.status}</Badge></TableCell>
                    <TableCell><Badge variant={chunk.vector_id ? "success" : "secondary"}>{chunk.vector_id ? "已入库" : "待入库"}</Badge></TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <ConfirmDialog
        open={deleteConfirmOpen}
        title="要删除知识库吗？"
        description={selectedKb ? `确认删除知识库「${selectedKb.name}」？此操作不可撤销，知识库下的所有文档和向量数据将被永久删除。` : ""}
        confirmLabel="确认删除"
        cancelLabel="取消"
        danger
        loading={deleteLoading}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </section>
  )
}
