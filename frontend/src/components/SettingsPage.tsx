import { useState } from "react"
import { Eye, EyeOff, Gauge, HardDrive, KeyRound, ScanText, Search } from "lucide-react"
import PageHeader from "./PageHeader"
import { Button } from "./ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Input } from "./ui/input"
import { Label } from "./ui/label"
import { Select } from "./ui/select"
import { Slider } from "./ui/slider"
import { Switch } from "./ui/switch"

export default function SettingsPage() {
  const [showKey, setShowKey] = useState(false)
  const [temperature, setTemperature] = useState(0.2)
  const [gpu, setGpu] = useState(true)
  const [preprocess, setPreprocess] = useState(true)
  const [rerank, setRerank] = useState(true)

  return (
    <section>
      <PageHeader
        title="设置"
        description="集中配置 LLM、OCR、存储和检索默认参数，为后续接入 FastAPI 后端保留清晰的数据结构。"
      />

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-primary" />
              模型配置
            </CardTitle>
            <CardDescription>LLM 调用参数</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="LLM 模型名称">
              <Select defaultValue="gpt">
                <option value="gpt">gpt-4o-mini</option>
                <option value="qwen">Qwen2.5</option>
                <option value="glm">GLM-4</option>
              </Select>
            </Field>
            <Field label="API Key">
              <div className="flex gap-2">
                <Input type={showKey ? "text" : "password"} defaultValue="sk-xxxxxxxxxxxxxxxx" />
                <Button type="button" variant="outline" size="icon" onClick={() => setShowKey(!showKey)} aria-label="切换 API Key 显示">
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </Field>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <Label>Temperature</Label>
                <span className="text-sm font-semibold">{temperature.toFixed(2)}</span>
              </div>
              <Slider min={0} max={1} step={0.01} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
            </div>
            <Field label="Max Tokens">
              <Input type="number" defaultValue={2048} />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ScanText className="h-5 w-5 text-primary" />
              OCR 配置
            </CardTitle>
            <CardDescription>PaddleOCR 运行参数</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="OCR 语言">
              <Select defaultValue="mixed">
                <option value="zh">中文</option>
                <option value="en">英文</option>
                <option value="mixed">中英混合</option>
              </Select>
            </Field>
            <ToggleRow label="是否启用 GPU" checked={gpu} onChange={setGpu} />
            <ToggleRow label="图片预处理开关" checked={preprocess} onChange={setPreprocess} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-primary" />
              存储配置
            </CardTitle>
            <CardDescription>文件、OCR 文本、向量库与日志路径</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="原始文件存储路径"><Input defaultValue="/data/storage/raw/" /></Field>
            <Field label="OCR 文本存储路径"><Input defaultValue="/data/storage/ocr_text/" /></Field>
            <Field label="向量数据库路径"><Input defaultValue="/data/vectorstore/faiss/" /></Field>
            <Field label="日志存储路径"><Input defaultValue="/data/logs/retrievaller/" /></Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5 text-primary" />
              检索配置
            </CardTitle>
            <CardDescription>Retriever 默认行为</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="默认 Top-K"><Input type="number" defaultValue={5} /></Field>
            <Field label="默认检索方式">
              <Select defaultValue="similarity">
                <option value="similarity">相似度检索</option>
                <option value="mmr">MMR</option>
                <option value="hybrid">Hybrid Search</option>
              </Select>
            </Field>
            <ToggleRow label="是否启用 Rerank" checked={rerank} onChange={setRerank} />
            <div className="rounded-lg border bg-blue-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-blue-700">
                <Gauge className="h-4 w-4" />
                默认阈值建议
              </div>
              <p className="mt-2 text-sm leading-6 text-blue-700">制度类知识库建议 Score Threshold 不低于 0.7，并默认开启引用来源展示。</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <span className="text-sm font-medium">{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} label={label} />
    </div>
  )
}
