import { useEffect, useMemo, useState } from "react"
import { Activity, BarChart3, CheckCircle2 } from "lucide-react"
import { ApiError } from "@/api/client"
import { listEvaluations } from "@/api/evaluationApi"
import type { Evaluation } from "@/types/evaluation"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Progress } from "./ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { buildEvaluationDimensions, buildEvaluationMetrics } from "./evaluationUtils"

export default function EvaluationPage() {
  const [evaluations, setEvaluations] = useState<Evaluation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const metrics = useMemo(() => buildEvaluationMetrics(evaluations), [evaluations])
  const dimensions = useMemo(() => buildEvaluationDimensions(evaluations), [evaluations])

  useEffect(() => {
    let active = true

    async function loadEvaluations() {
      setLoading(true)
      setError("")
      try {
        const response = await listEvaluations()
        if (active) setEvaluations(response.items)
      } catch (unknownError) {
        if (active) setError(readErrorMessage(unknownError))
      } finally {
        if (active) setLoading(false)
      }
    }

    void loadEvaluations()
    return () => {
      active = false
    }
  }, [])

  return (
    <section>
      <PageHeader
        title="系统评估"
        description="汇总已保存的 RAG 问答评估结果；单条评估请在“问答记录与评估”页面发起。"
      />

      {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <Card key={metric.key}>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-muted-foreground">{metric.label}</CardTitle>
              <CardDescription>{metric.key}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-3 flex items-end gap-2">
                <span className="text-3xl font-bold">{loading ? "..." : `${metric.value}%`}</span>
                <CheckCircle2 className="mb-1 h-5 w-5 text-emerald-600" />
              </div>
              <Progress value={metric.value} />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-primary" />
              评估维度分布
            </CardTitle>
            <CardDescription>{loading ? "正在加载已保存的评估结果" : `基于 ${evaluations.length} 条已保存评估结果`}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {dimensions.map((item) => (
              <div key={item.label}>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="font-medium">{item.label}</span>
                  <span className="text-muted-foreground">{loading ? "..." : `${item.value}%`}</span>
                </div>
                <Progress value={item.value} className="h-3" />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              评估说明
            </CardTitle>
            <CardDescription>面向知识库问答质量的核心判据</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {[
              ["Faithfulness", "回答是否完全由检索上下文支持。"],
              ["Answer Relevance", "回答是否直接回应用户问题。"],
              ["Context Precision", "召回上下文中有效信息的占比。"],
              ["Context Recall", "标准答案所需证据是否被召回。"],
              ["Citation Accuracy", "引用页码、Chunk 与原文是否匹配。"]
            ].map(([title, desc]) => (
              <div key={title} className="rounded-lg border bg-white p-4">
                <p className="font-semibold">{title}</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{desc}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>已保存评估结果</CardTitle>
          <CardDescription>每条记录对应一次已完成的 QA 问答评估</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>QA 记录 ID</TableHead>
                <TableHead>综合分</TableHead>
                <TableHead>忠实性</TableHead>
                <TableHead>回答相关性</TableHead>
                <TableHead>引用正确性</TableHead>
                <TableHead>完整性</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>创建时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-muted-foreground">正在加载评估结果...</TableCell></TableRow>
              ) : evaluations.length === 0 ? (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-muted-foreground">暂无已保存的评估结果</TableCell></TableRow>
              ) : evaluations.map((evaluation) => (
                <TableRow key={evaluation.id}>
                  <TableCell className="font-mono text-xs">{evaluation.qa_record_id}</TableCell>
                  <TableCell className="font-medium">{evaluation.overall_score}/5</TableCell>
                  <TableCell>{evaluation.faithfulness_score}/5</TableCell>
                  <TableCell>{evaluation.relevance_score}/5</TableCell>
                  <TableCell>{evaluation.citation_score}/5</TableCell>
                  <TableCell>{evaluation.completeness_score}/5</TableCell>
                  <TableCell><Badge variant="success">已完成</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDate(evaluation.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  )
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false })
}

function readErrorMessage(unknownError: unknown) {
  return unknownError instanceof ApiError ? unknownError.detail : "加载评估结果失败"
}
