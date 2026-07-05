import { ArrowRight, Database, GitBranch, Layers3 } from "lucide-react"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Input } from "./ui/input"
import { Label } from "./ui/label"
import { Select } from "./ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { chunks } from "@/data/mockData"

export default function KnowledgeBasePage() {
  const flow = ["原始文本", "文本清洗", "文档切分", "Embedding", "向量存储", "Retriever"]

  return (
    <section>
      <PageHeader
        title="知识库构建"
        description="配置 Chunk 策略、Embedding 模型、向量数据库与检索方式，模拟 LangChain Retriever 的完整构建过程。"
      />

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>知识库配置</CardTitle>
            <CardDescription>文本切分与检索参数</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Chunk Size</Label>
              <Input type="number" defaultValue={500} />
            </div>
            <div className="space-y-2">
              <Label>Chunk Overlap</Label>
              <Input type="number" defaultValue={50} />
            </div>
            <div className="space-y-2">
              <Label>Embedding 模型</Label>
              <Select defaultValue="bge">
                <option value="bge">bge-small-zh</option>
                <option value="ada">text-embedding-ada</option>
                <option value="m3e">m3e-base</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>向量数据库</Label>
              <Select defaultValue="faiss">
                <option value="faiss">FAISS</option>
                <option value="chroma">Chroma</option>
                <option value="milvus">Milvus</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>检索方式</Label>
              <Select defaultValue="similarity">
                <option value="similarity">相似度检索</option>
                <option value="mmr">MMR</option>
                <option value="hybrid">Hybrid Search</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Top-K</Label>
              <Input type="number" defaultValue={5} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>构建流程图</CardTitle>
            <CardDescription>从 OCR 文本到 Retriever 的转换链路</CardDescription>
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
        <CardHeader>
          <CardTitle>切片预览表格</CardTitle>
          <CardDescription>Chunk、来源页码、Embedding 与入库状态</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Chunk ID</TableHead>
                <TableHead>来源文档</TableHead>
                <TableHead>页码</TableHead>
                <TableHead>文本片段</TableHead>
                <TableHead>Embedding 状态</TableHead>
                <TableHead>入库状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {chunks.map((chunk) => (
                <TableRow key={chunk.id}>
                  <TableCell className="font-mono text-xs">{chunk.id}</TableCell>
                  <TableCell>{chunk.doc}</TableCell>
                  <TableCell>{chunk.page}</TableCell>
                  <TableCell className="max-w-md text-muted-foreground">{chunk.text}</TableCell>
                  <TableCell><Badge variant={chunk.embedding === "已生成" ? "success" : "warning"}>{chunk.embedding}</Badge></TableCell>
                  <TableCell><Badge variant={chunk.stored === "已入库" ? "success" : "secondary"}>{chunk.stored}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  )
}
