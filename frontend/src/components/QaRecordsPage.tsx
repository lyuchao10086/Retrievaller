import { useEffect, useMemo, useState } from "react"
import { Eye, FileSearch, RefreshCw, ShieldCheck, Sparkles, Trash2 } from "lucide-react"
import { ApiError } from "@/api/client"
import { evaluateQaRecord, getQaRecordEvaluation } from "@/api/evaluationApi"
import { deleteQaRecord, listQaRecords } from "@/api/ragApi"
import type { Evaluation } from "@/types/evaluation"
import type { MultiRagSource, QaRecord } from "@/types/rag"
import PageHeader from "./PageHeader"
import ConfirmDialog from "./ui/ConfirmDialog"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"

type DialogState =
  | { kind: "sources"; record: QaRecord }
  | { kind: "evaluation"; evaluation: Evaluation }
  | null

export default function QaRecordsPage() {
  const [records, setRecords] = useState<QaRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [workingId, setWorkingId] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [dialog, setDialog] = useState<DialogState>(null)
  const [deleteTarget, setDeleteTarget] = useState<QaRecord | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const totalSources = useMemo(
    () => records.reduce((sum, record) => sum + (record.sources_json?.length ?? 0), 0),
    [records]
  )

  async function refreshRecords() {
    setLoading(true)
    setError("")
    try {
      setRecords(await listQaRecords())
    } catch (unknownError) {
      setError(readErrorMessage(unknownError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshRecords()
  }, [])

  async function submitEvaluation(record: QaRecord) {
    setWorkingId(record.id)
    setError("")
    setMessage("")
    try {
      const evaluation = await evaluateQaRecord(record.id)
      setDialog({ kind: "evaluation", evaluation })
      setMessage("评估完成")
    } catch (unknownError) {
      setError(readErrorMessage(unknownError))
    } finally {
      setWorkingId(null)
    }
  }

  async function viewEvaluation(record: QaRecord) {
    setWorkingId(record.id)
    setError("")
    setMessage("")
    try {
      const evaluation = await getQaRecordEvaluation(record.id)
      setDialog({ kind: "evaluation", evaluation })
    } catch (unknownError) {
      if (unknownError instanceof ApiError && unknownError.status === 404) {
        setError("该问答记录尚未评估")
      } else {
        setError(readErrorMessage(unknownError))
      }
    } finally {
      setWorkingId(null)
    }
  }

  async function removeRecord(record: QaRecord) {
    setDeleteTarget(record)
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setDeleteLoading(true)
    setError("")
    setMessage("")
    try {
      await deleteQaRecord(deleteTarget.id)
      setRecords((current) => current.filter((item) => item.id !== deleteTarget.id))
      setDialog((current) => (current?.kind === "sources" && current.record.id === deleteTarget.id ? null : current))
      setMessage("问答记录已删除")
    } catch (unknownError) {
      setError(readErrorMessage(unknownError))
    } finally {
      setDeleteLoading(false)
      setDeleteTarget(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="问答记录与评估"
        description="查看 RAG 问答历史，检查引用来源，并调用 DeepSeek 评估答案忠实性。"
      />

      {(message || error) && (
        <div className="mb-4 grid gap-2">
          {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}
          {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        </div>
      )}

      <div className="mb-5 grid gap-4 md:grid-cols-3">
        <MetricCard label="问答记录" value={records.length} />
        <MetricCard label="引用来源" value={totalSources} />
        <MetricCard label="评估方式" value="DeepSeek" />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>最近问答记录</CardTitle>
            <CardDescription>默认展示当前用户最近 50 条记录</CardDescription>
          </div>
          <Button variant="outline" onClick={() => void refreshRecords()} disabled={loading}>
            <RefreshCw className="h-4 w-4" />
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <EmptyBlock icon={RefreshCw} text="正在加载问答记录..." />
          ) : records.length === 0 ? (
            <EmptyBlock icon={FileSearch} text="暂无问答记录" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>问题</TableHead>
                  <TableHead>答案</TableHead>
                  <TableHead>知识库</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell className="max-w-[260px] font-medium">
                      <div className="line-clamp-3">{record.question}</div>
                      <div className="mt-1 font-mono text-xs text-muted-foreground">{record.id}</div>
                    </TableCell>
                    <TableCell className="max-w-[380px] text-muted-foreground">
                      <div className="max-h-24 overflow-auto whitespace-pre-wrap text-sm leading-6">{record.answer}</div>
                    </TableCell>
                    <TableCell className="max-w-[220px]">
                      <div className="flex flex-wrap gap-1">
                        {record.knowledge_base_ids.map((kbId) => (
                          <Badge key={kbId} variant="secondary" className="font-mono">{kbId}</Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={record.sources_json.length > 0 ? "processing" : "secondary"}>
                        {record.sources_json.length} 条
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDate(record.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button size="sm" variant="outline" onClick={() => setDialog({ kind: "sources", record })}>
                          <Eye className="h-4 w-4" />
                          查看来源
                        </Button>
                        <Button size="sm" onClick={() => void submitEvaluation(record)} disabled={workingId === record.id}>
                          <Sparkles className="h-4 w-4" />
                          评估答案
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => void viewEvaluation(record)} disabled={workingId === record.id}>
                          <ShieldCheck className="h-4 w-4" />
                          评估结果
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void removeRecord(record)} disabled={workingId === record.id}>
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {dialog && <RecordDialog dialog={dialog} onClose={() => setDialog(null)} />}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="要删除该问答记录吗？"
        description={deleteTarget ? `确认删除问答记录「${deleteTarget.title || deleteTarget.question}」？此操作不可撤销。` : ""}
        confirmLabel="确认删除"
        cancelLabel="取消"
        danger
        loading={deleteLoading}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </section>
  )
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  )
}

function EmptyBlock({ icon: Icon, text }: { icon: typeof FileSearch; text: string }) {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center text-muted-foreground">
      <Icon className="h-8 w-8" />
      <div className="text-sm">{text}</div>
    </div>
  )
}

function RecordDialog({ dialog, onClose }: { dialog: DialogState; onClose: () => void }) {
  if (!dialog) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="flex max-h-[86vh] w-full max-w-5xl flex-col rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <div className="text-sm font-semibold">
              {dialog.kind === "sources" ? "引用来源" : "DeepSeek 评估结果"}
            </div>
            <div className="text-xs text-muted-foreground">
              {dialog.kind === "sources" ? dialog.record.question : dialog.evaluation.qa_record_id}
            </div>
          </div>
          <Button variant="ghost" onClick={onClose}>关闭</Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-5">
          {dialog.kind === "sources" ? (
            <SourcesPanel sources={dialog.record.sources_json} />
          ) : (
            <EvaluationPanel evaluation={dialog.evaluation} />
          )}
        </div>
      </div>
    </div>
  )
}

function SourcesPanel({ sources }: { sources: MultiRagSource[] }) {
  if (sources.length === 0) {
    return <EmptyBlock icon={FileSearch} text="该记录没有返回引用来源" />
  }

  return (
    <div className="space-y-3">
      {sources.map((source, index) => (
        <div key={`${source.chunk_id}-${index}`} className="rounded-lg border bg-blue-50/40 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="font-semibold">来源 {index + 1}</div>
            <Badge variant="processing">score {formatScore(source.score)}</Badge>
          </div>
          <div className="text-sm leading-7 text-slate-700">
            <div>来源：{formatSource(source)}</div>
            <div className="font-mono text-xs text-muted-foreground">Chunk ID：{source.chunk_id}</div>
          </div>
          <div className="mt-3 max-h-40 overflow-auto rounded-lg bg-white/80 p-3 text-sm leading-6 text-muted-foreground">
            {source.content}
          </div>
        </div>
      ))}
    </div>
  )
}

function EvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  const rows = [
    ["忠实性", evaluation.faithfulness_score],
    ["相关性", evaluation.relevance_score],
    ["引用正确性", evaluation.citation_score],
    ["完整性", evaluation.completeness_score],
    ["综合分", evaluation.overall_score]
  ] as const

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {rows.map(([label, score]) => (
          <div key={label} className="rounded-lg border p-4">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-2 text-2xl font-semibold">{score}/5</div>
          </div>
        ))}
      </div>
      <div className="rounded-lg border p-4">
        <div className="text-xs text-muted-foreground">是否幻觉</div>
        <Badge className="mt-2" variant={evaluation.hallucination ? "destructive" : "success"}>
          {evaluation.hallucination ? "存在幻觉" : "未发现明显幻觉"}
        </Badge>
      </div>
      <div className="rounded-lg border p-4">
        <div className="mb-2 text-sm font-semibold">评估理由</div>
        <p className="whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{evaluation.reason}</p>
      </div>
    </div>
  )
}

function formatSource(source: MultiRagSource) {
  const info = source.source ?? {}
  const fileSource = [
    info.file_name,
    info.chapter,
    info.section,
    info.subsection
  ].filter(Boolean).join(" - ")
  return [info.knowledge_base_name, fileSource].filter(Boolean).join(" / ")
}

function formatScore(value?: number) {
  if (typeof value !== "number") return "-"
  return value.toFixed(4)
}

function formatDate(value?: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function readErrorMessage(unknownError: unknown) {
  return unknownError instanceof ApiError ? unknownError.detail : String(unknownError)
}
