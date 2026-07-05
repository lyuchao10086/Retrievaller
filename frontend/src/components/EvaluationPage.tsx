import { Activity, BarChart3, CheckCircle2 } from "lucide-react"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Progress } from "./ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { evaluationRows, metricCards } from "@/data/mockData"

const dimensions = [
  { label: "Faithfulness", value: 92 },
  { label: "Answer Relevance", value: 88 },
  { label: "Context Precision", value: 86 },
  { label: "Context Recall", value: 85 },
  { label: "Citation Accuracy", value: 90 }
]

export default function EvaluationPage() {
  return (
    <section>
      <PageHeader
        title="系统评估"
        description="围绕忠实度、相关性、上下文召回和引用准确率评估 RAG 系统，判断回答是否真实、忠实、准确。"
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metricCards.map((metric) => (
          <Card key={metric.key}>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-muted-foreground">{metric.label}</CardTitle>
              <CardDescription>{metric.key}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-3 flex items-end gap-2">
                <span className="text-3xl font-bold">{metric.value}%</span>
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
            <CardDescription>用进度条模拟柱状图展示各维度分数</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {dimensions.map((item) => (
              <div key={item.label}>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="font-medium">{item.label}</span>
                  <span className="text-muted-foreground">{item.value}%</span>
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
          <CardTitle>评估样本表格</CardTitle>
          <CardDescription>测试问题、标准答案、模型回答和人工评价</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>测试问题</TableHead>
                <TableHead>标准答案</TableHead>
                <TableHead>模型回答</TableHead>
                <TableHead>检索上下文</TableHead>
                <TableHead>忠实度评分</TableHead>
                <TableHead>引用是否正确</TableHead>
                <TableHead>人工评价</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {evaluationRows.map((row) => (
                <TableRow key={row.question}>
                  <TableCell className="font-medium">{row.question}</TableCell>
                  <TableCell className="max-w-xs text-muted-foreground">{row.expected}</TableCell>
                  <TableCell className="max-w-xs text-muted-foreground">{row.answer}</TableCell>
                  <TableCell className="font-mono text-xs">{row.context}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={row.faithfulness} className="w-24" />
                      <span>{row.faithfulness}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.citation === "正确" ? "success" : "warning"}>{row.citation}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.human === "通过" ? "success" : "warning"}>{row.human}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  )
}
