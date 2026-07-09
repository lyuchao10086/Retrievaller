import { useEffect, useState } from "react"
import { Gauge, HardDrive, KeyRound, RefreshCw, ScanText, Search, Server } from "lucide-react"
import { ApiError } from "@/api/client"
import { getHealth, getSystemConfig, type HealthDependencyStatus, type HealthResponse, type SystemConfigResponse } from "@/api/systemApi"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Input } from "./ui/input"
import { Label } from "./ui/label"
import { Select } from "./ui/select"
import { Slider } from "./ui/slider"

const DEFAULT_TOP_K = 5
const TOP_K_STORAGE_KEY = "retrievaller.defaultTopK"
const HEALTH_DEPENDENCY_LABELS: Record<string, string> = {
  mysql: "MySQL",
  redis: "Redis",
  minio: "MinIO",
  milvus: "Milvus",
  ollama_embedding: "Ollama Embedding",
  ollama_llm: "Ollama LLM",
  deepseek_config: "DeepSeek 配置",
  celery_config: "Celery 配置",
}

export default function SettingsPage() {
  const [temperature, setTemperature] = useState(0.2)
  const [topK, setTopK] = useState(() => readStoredTopK())
  const [config, setConfig] = useState<SystemConfigResponse | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    let ignore = false
    async function loadConfig() {
      try {
        const data = await getSystemConfig()
        if (!ignore) setConfig(data)
      } catch (unknownError) {
        if (!ignore) {
          setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
        }
      }
    }
    void loadConfig()
    return () => {
      ignore = true
    }
  }, [])

  async function refreshHealth() {
    setHealthLoading(true)
    setError("")
    try {
      setHealth(await getHealth())
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : String(unknownError))
    } finally {
      setHealthLoading(false)
    }
  }

  useEffect(() => {
    void refreshHealth()
  }, [])

  return (
    <section>
      <PageHeader
        title="设置"
        description="查看后端运行配置与前端检索偏好。敏感密钥只在服务端环境变量中配置。"
      />

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <Card className="mb-5">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" />
              系统健康状态
            </CardTitle>
            <CardDescription>后端、中间件、Ollama 模型服务与可选配置状态</CardDescription>
          </div>
          <Button variant="outline" onClick={() => void refreshHealth()} disabled={healthLoading}>
            <RefreshCw className="h-4 w-4" />
            {healthLoading ? "刷新中..." : "刷新状态"}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <HealthStatusTile label="Backend" status={health?.backend} />
            {Object.entries(HEALTH_DEPENDENCY_LABELS).map(([key, label]) => (
              <HealthStatusTile
                key={key}
                label={label}
                status={health?.dependencies?.[key]}
              />
            ))}
          </div>
        </CardContent>
      </Card>

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
              <Input readOnly value={config?.llm?.local_llm_model ?? "加载中..."} />
            </Field>
            <Field label="Ollama 地址">
              <Input readOnly value={config?.llm?.base_url ?? "加载中..."} />
            </Field>
            <Field label="Embedding 模型">
              <Input readOnly value={config?.embedding?.model_name ?? config?.embedding?.embedding_model_name ?? "加载中..."} />
            </Field>
            <Field label="Embedding 维度">
              <Input readOnly value={String(config?.embedding?.dimension ?? config?.embedding?.embedding_dimension ?? "") || "加载中..."} />
            </Field>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <Label>前端展示 Temperature</Label>
                <span className="text-sm font-semibold">{temperature.toFixed(2)}</span>
              </div>
              <Slider min={0} max={1} step={0.01} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ScanText className="h-5 w-5 text-primary" />
              文档处理
            </CardTitle>
            <CardDescription>当前后台处理能力</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="处理模式">
              <Input readOnly value={config?.document_processing?.mode ?? "加载中..."} />
            </Field>
            <Field label="支持文件类型">
              <Input readOnly value={config?.document_processing?.supported_file_types?.join(" / ") ?? "加载中..."} />
            </Field>
            <Field label="默认分段参数">
              <Input
                readOnly
                value={
                  config?.document_processing
                    ? `${config.document_processing.default_chunk_size} 字符，重叠 ${config.document_processing.default_chunk_overlap}`
                    : "加载中..."
                }
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-primary" />
              存储配置
            </CardTitle>
            <CardDescription>对象存储和向量集合</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="原始文件 Bucket"><Input readOnly value={config?.storage?.documents_bucket ?? "加载中..."} /></Field>
            <Field label="解析结果 Bucket"><Input readOnly value={config?.storage?.parsed_results_bucket ?? "加载中..."} /></Field>
            <Field label="Milvus Collection"><Input readOnly value={config?.storage?.milvus_collection ?? "加载中..."} /></Field>
            <Field label="DeepSeek 评估">
              <Input readOnly value={config?.evaluation ? `${config.evaluation.model} / ${config.evaluation.configured ? "已配置" : "未配置 API Key"}` : "加载中..."} />
            </Field>
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
            <Field label="默认 Top-K">
              <Input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => {
                  const next = clampTopK(Number(event.target.value))
                  setTopK(next)
                  window.localStorage.setItem(TOP_K_STORAGE_KEY, String(next))
                }}
              />
            </Field>
            <Field label="默认检索方式">
              <Select defaultValue="similarity">
                <option value="similarity">相似度检索</option>
              </Select>
            </Field>
            <Field label="Rerank 状态">
              <Input readOnly value={config?.rerank?.enabled ? "已启用" : "未接入"} />
            </Field>
            <div className="rounded-lg border bg-blue-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-blue-700">
                <Gauge className="h-4 w-4" />
                当前说明
              </div>
              <p className="mt-2 text-sm leading-6 text-blue-700">
                RAG 请求会使用这里的默认 Top-K；模型、存储和 DeepSeek 密钥请在后端环境变量中配置。
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function readStoredTopK() {
  return clampTopK(Number(window.localStorage.getItem(TOP_K_STORAGE_KEY)))
}

function clampTopK(value: number) {
  if (Number.isNaN(value)) return DEFAULT_TOP_K
  return Math.min(20, Math.max(1, value))
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function HealthStatusTile({
  label,
  status,
}: {
  label: string
  status?: HealthDependencyStatus
}) {
  const state = status?.status ?? "loading"
  const detail = status?.detail || status?.error || status?.model || status?.broker || "-"
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold">{label}</div>
        <Badge variant={healthBadgeVariant(state)}>{statusLabel(state)}</Badge>
      </div>
      <p className="break-words text-xs leading-5 text-muted-foreground">{detail}</p>
    </div>
  )
}

function healthBadgeVariant(status: string) {
  if (status === "ok") return "success"
  if (status === "warning") return "warning"
  if (status === "error") return "destructive"
  return "secondary"
}

function statusLabel(status: string) {
  if (status === "ok") return "ok"
  if (status === "warning") return "warning"
  if (status === "error") return "error"
  return "加载中"
}
