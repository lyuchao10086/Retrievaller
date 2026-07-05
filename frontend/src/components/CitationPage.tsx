import { useState } from "react"
import { CheckCircle2, FileSearch, Link2, ShieldCheck } from "lucide-react"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { citations } from "@/data/mockData"
import { cn } from "./ui/utils"

export default function CitationPage() {
  const [selected, setSelected] = useState(citations[0])

  return (
    <section>
      <PageHeader
        title="引用来源"
        description="集中展示 RAG 回答中的证据链，强调答案不是凭空生成，而是来自可追溯、可核验的文档片段。"
      />

      <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>引用来源列表</CardTitle>
            <CardDescription>问题、回答摘要、引用文档与命中情况</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {citations.map((item) => (
              <button
                key={item.chunk}
                type="button"
                onClick={() => setSelected(item)}
                className={cn(
                  "w-full rounded-lg border bg-white p-4 text-left transition hover:border-primary hover:bg-blue-50/40",
                  selected.chunk === item.chunk && "border-primary bg-blue-50/60"
                )}
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-slate-900">{item.question}</p>
                  <Badge variant={item.hit ? "success" : "warning"}>{item.hit ? "命中正确段落" : "需人工复核"}</Badge>
                </div>
                <p className="text-sm leading-6 text-muted-foreground">{item.summary}</p>
                <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
                  <span>文档：{item.doc}</span>
                  <span>页码：{item.page}</span>
                  <span className="font-mono text-xs">Chunk：{item.chunk}</span>
                  <span>相似度：{item.score}</span>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileSearch className="h-5 w-5 text-primary" />
              文档溯源详情
            </CardTitle>
            <CardDescription>查看原文证据、OCR 置信度与生成参与情况</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg border bg-gradient-to-br from-white to-blue-50 p-4">
              <div className="mb-3 flex items-center gap-2">
                <Link2 className="h-4 w-4 text-primary" />
                <span className="font-semibold">原始文档名</span>
              </div>
              <p className="text-sm text-muted-foreground">{selected.doc}</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <InfoTile label="原始页码" value={selected.page} />
              <InfoTile label="OCR 置信度" value={selected.confidence} />
              <InfoTile label="检索分数" value={selected.score.toString()} />
              <InfoTile label="参与生成" value={selected.used ? "是" : "否"} />
            </div>
            <div className="rounded-lg border p-4">
              <div className="mb-3 flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                原始文本
              </div>
              <p className="text-sm leading-7 text-slate-700">{selected.text}</p>
            </div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                证据链校验
              </div>
              <p className="mt-2 text-sm leading-6 text-emerald-700">
                系统保留了文档名、页码、Chunk ID、检索分数与 OCR 置信度，可用于回答复核和人工审计。
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-white p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-semibold">{value}</p>
    </div>
  )
}
