import { useRef, useState } from "react"
import { FilePlus2, FolderInput, UploadCloud } from "lucide-react"
import PageHeader from "./PageHeader"
import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Input } from "./ui/input"
import { Label } from "./ui/label"
import { Switch } from "./ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { uploadedFiles, type UploadStatus } from "@/data/mockData"

const statusVariant: Record<UploadStatus, "warning" | "processing" | "success" | "destructive"> = {
  待解析: "warning",
  "OCR 处理中": "processing",
  已入库: "success",
  解析失败: "destructive"
}

type FileRow = (typeof uploadedFiles)[number]

export default function UploadPage() {
  const [autoOcr, setAutoOcr] = useState(true)
  const [autoKb, setAutoKb] = useState(true)
  const [files, setFiles] = useState<FileRow[]>(uploadedFiles)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = (incoming: FileList | null) => {
    if (!incoming?.length) return
    const next = Array.from(incoming).map((file) => ({
      name: file.name,
      type: file.name.split(".").pop()?.toUpperCase() || "FILE",
      size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
      time: "2026-07-05 14:30",
      status: autoOcr ? ("OCR 处理中" as UploadStatus) : ("待解析" as UploadStatus)
    }))
    setFiles((current) => [...next, ...current])
  }

  return (
    <section>
      <PageHeader
        title="文档上传"
        description="模拟将指定目录下的 PDF、图片、DOCX、TXT 文档上传到原始文件存储区，并按配置自动触发 OCR 和知识库入库流程。"
      />

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>上传区域</CardTitle>
            <CardDescription>支持 PDF、PNG、JPG、DOCX、TXT</CardDescription>
          </CardHeader>
          <CardContent>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                addFiles(event.dataTransfer.files)
              }}
              className="flex min-h-[260px] w-full flex-col items-center justify-center rounded-lg border-2 border-dashed border-blue-200 bg-blue-50/50 p-8 text-center transition hover:border-primary hover:bg-blue-50"
            >
              <UploadCloud className="h-12 w-12 text-primary" />
              <p className="mt-4 text-lg font-semibold">拖拽文件到此处，或点击上传</p>
              <p className="mt-2 text-sm text-muted-foreground">文件会进入 /data/storage/raw/ 并生成解析任务</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {["PDF", "PNG", "JPG", "DOCX", "TXT"].map((type) => (
                  <Badge key={type} variant="purple">{type}</Badge>
                ))}
              </div>
            </button>
            <input ref={inputRef} type="file" multiple className="hidden" onChange={(e) => addFiles(e.target.files)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>上传配置</CardTitle>
            <CardDescription>后续可对接 FastAPI 上传接口和任务队列</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label>指定上传目录路径</Label>
              <Input defaultValue="/data/documents/" />
            </div>
            <div className="space-y-2">
              <Label>文件存储路径</Label>
              <Input defaultValue="/data/storage/raw/" />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <p className="text-sm font-medium">是否自动 OCR 解析</p>
                <p className="text-xs text-muted-foreground">上传后自动创建 PaddleOCR 任务</p>
              </div>
              <Switch checked={autoOcr} onCheckedChange={setAutoOcr} label="自动 OCR" />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <p className="text-sm font-medium">是否自动加入知识库</p>
                <p className="text-xs text-muted-foreground">解析完成后进入切分与向量化队列</p>
              </div>
              <Switch checked={autoKb} onCheckedChange={setAutoKb} label="自动入库" />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>文件列表</CardTitle>
            <CardDescription>展示文件状态与处理阶段</CardDescription>
          </div>
          <Button variant="outline" onClick={() => inputRef.current?.click()}>
            <FilePlus2 className="h-4 w-4" />
            添加文件
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文件名</TableHead>
                <TableHead>文件类型</TableHead>
                <TableHead>文件大小</TableHead>
                <TableHead>上传时间</TableHead>
                <TableHead>当前状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {files.map((file) => (
                <TableRow key={`${file.name}-${file.time}`}>
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-2">
                      <FolderInput className="h-4 w-4 text-primary" />
                      {file.name}
                    </span>
                  </TableCell>
                  <TableCell>{file.type}</TableCell>
                  <TableCell>{file.size}</TableCell>
                  <TableCell>{file.time}</TableCell>
                  <TableCell><Badge variant={statusVariant[file.status]}>{file.status}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  )
}
