import { FileText, Image, ScanLine } from "lucide-react"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Label } from "./ui/label"
import { Progress } from "./ui/progress"
import { Select } from "./ui/select"
import { Switch } from "./ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { ocrTasks } from "@/data/mockData"
import { useState } from "react"

export default function OCRPage() {
  const [layout, setLayout] = useState(true)
  const [tables, setTables] = useState(true)
  const [formula, setFormula] = useState(false)
  const [images, setImages] = useState(true)

  return (
    <section>
      <PageHeader
        title="OCR 解析（演示）"
        description="OCR 后端尚未接入，当前页面仅展示未来能力样例，不会提交真实识别任务。"
      />

      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
        当前 OCR 配置、任务列表和结果预览均为演示数据；PDF、图片识别与 PaddleOCR 调用待后续接入。
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
        <Card>
          <CardHeader>
            <CardTitle>OCR 配置</CardTitle>
            <CardDescription>演示参数，当前不可提交到后端</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label>OCR 引擎</Label>
              <Select defaultValue="paddle" disabled>
                <option value="paddle">PaddleOCR</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>语言模型</Label>
              <Select defaultValue="mixed" disabled>
                <option value="zh">中文</option>
                <option value="en">英文</option>
                <option value="mixed">中英混合</option>
              </Select>
            </div>
            {[
              ["是否启用版面分析", layout, setLayout],
              ["是否识别表格", tables, setTables],
              ["是否识别公式", formula, setFormula],
              ["是否保留图片区域", images, setImages]
            ].map(([label, checked, setter]) => (
              <div key={label as string} className="flex items-center justify-between rounded-lg border p-4">
                <span className="text-sm font-medium">{label as string}</span>
                <Switch checked={checked as boolean} onCheckedChange={setter as (v: boolean) => void} label={label as string} disabled />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>OCR 任务列表</CardTitle>
            <CardDescription>演示识别进度、置信度与处理状态</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>文档名</TableHead>
                  <TableHead>页数</TableHead>
                  <TableHead>识别进度</TableHead>
                  <TableHead>平均置信度</TableHead>
                  <TableHead>耗时</TableHead>
                  <TableHead>状态</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ocrTasks.map((task) => (
                  <TableRow key={task.doc}>
                    <TableCell className="font-medium">{task.doc}</TableCell>
                    <TableCell>{task.pages}</TableCell>
                    <TableCell className="min-w-[160px]">
                      <div className="flex items-center gap-2">
                        <Progress value={task.progress} />
                        <span className="w-10 text-xs text-muted-foreground">{task.progress}%</span>
                      </div>
                    </TableCell>
                    <TableCell>{task.confidence}</TableCell>
                    <TableCell>{task.duration}</TableCell>
                    <TableCell>
                      <Badge variant={task.status === "已完成" ? "success" : task.status === "需复核" ? "warning" : "processing"}>
                        {task.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>OCR 结果预览</CardTitle>
          <CardDescription>左侧为模拟预览，右侧为演示文本与关键结果高亮</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="min-h-[420px] rounded-lg border bg-slate-100 p-6">
              <div className="mx-auto h-full max-w-sm rounded-lg border bg-white p-6 shadow-sm">
                <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <FileText className="h-4 w-4 text-primary" />
                  LangChain技术文档.pdf / 第 6 页
                </div>
                <div className="space-y-3">
                  <div className="h-4 w-4/5 rounded bg-slate-200" />
                  <div className="h-4 w-full rounded bg-slate-200" />
                  <div className="h-4 w-11/12 rounded bg-blue-100" />
                  <div className="mt-6 grid grid-cols-2 gap-3">
                    <div className="flex h-28 items-center justify-center rounded border border-dashed text-slate-400">
                      <Image className="h-8 w-8" />
                    </div>
                    <div className="space-y-2">
                      <div className="h-3 rounded bg-slate-200" />
                      <div className="h-3 rounded bg-slate-200" />
                      <div className="h-3 w-2/3 rounded bg-slate-200" />
                    </div>
                  </div>
                  <div className="mt-6 h-24 rounded border border-blue-200 bg-blue-50" />
                </div>
              </div>
            </div>
            <div className="rounded-lg border bg-white p-5">
              <div className="mb-4 flex items-center gap-2">
                <ScanLine className="h-5 w-5 text-primary" />
                <span className="font-semibold">提取文本</span>
                <Badge variant="success">置信度 96.2%</Badge>
              </div>
              <p className="text-sm leading-8 text-slate-700">
                本文档主要介绍了基于 <mark className="rounded bg-blue-100 px-1 text-blue-700">LangChain</mark> 的
                <mark className="mx-1 rounded bg-violet-100 px-1 text-violet-700">Retriever 构建方法</mark>，包括文本切分、
                Embedding 生成、向量数据库存储以及相似度检索流程。系统在问答阶段会根据用户问题召回相关 Chunk，
                并结合 RAG 技术生成答案，同时展示文档名、页码、Chunk ID 和相似度分数等引用来源。
              </p>
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                {["版面块 12", "表格 2", "图片区域 4"].map((item) => (
                  <div key={item} className="rounded-lg border bg-slate-50 p-3 text-center text-sm font-medium">{item}</div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
