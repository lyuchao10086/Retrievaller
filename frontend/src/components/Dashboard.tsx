import { ArrowRight } from "lucide-react"
import PageHeader from "./PageHeader"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Progress } from "./ui/progress"
import { pipelineSteps, stats } from "@/data/mockData"

export default function Dashboard() {
  return (
    <section>
      <PageHeader
        title="项目概览"
        description="从文档上传、PaddleOCR 解析、LangChain Retriever 构建，到带引用来源的 RAG 问答与质量评估，一屏掌握完整链路。"
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.label}>
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">{stat.label}</CardTitle>
                <Icon className="h-5 w-5 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stat.value}</div>
                <p className="mt-2 text-xs text-muted-foreground">{stat.hint}</p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>文档智能解析 Pipeline</CardTitle>
          <CardDescription>文档 → OCR → 文本 → 向量库 → 检索 → 生成回答 → 引用来源 → 评估</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {pipelineSteps.map((step, index) => {
              const Icon = step.icon
              return (
                <div key={step.title} className="relative rounded-lg border bg-white p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md bg-blue-50 text-primary">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-semibold">{step.title}</p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{step.desc}</p>
                    </div>
                  </div>
                  {index < pipelineSteps.length - 1 && (
                    <ArrowRight className="absolute -right-2 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-slate-300 xl:block" />
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      <div className="mt-5 grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader>
            <CardTitle>系统目标</CardTitle>
            <CardDescription>面向个人与团队的可追溯智能文档知识库</CardDescription>
          </CardHeader>
          <CardContent className="text-sm leading-7 text-slate-700">
            该系统用于将 PDF、图片、扫描件等非结构化文档转化为可检索、可问答、可评估的知识库。系统通过
            PaddleOCR 提取文档文本，利用 LangChain 构建检索器，并基于 RAG 技术实现带引用来源的智能问答。
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>今日质量快照</CardTitle>
            <CardDescription>最近 256 次问答的综合表现</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              ["OCR 平均置信度", 94],
              ["Retriever 命中率", 87],
              ["引用可追溯率", 91]
            ].map(([label, value]) => (
              <div key={label as string}>
                <div className="mb-2 flex justify-between text-sm">
                  <span>{label}</span>
                  <span className="font-semibold">{value}%</span>
                </div>
                <Progress value={value as number} />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
