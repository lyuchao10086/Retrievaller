import {
  BarChart3,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Database,
  FileSearch,
  FileText,
  Layers3,
  MessageSquareText,
  ScanText,
  Sparkles,
  UploadCloud
} from "lucide-react"

export type MenuKey =
  | "dashboard"
  | "upload"
  | "ocr"
  | "knowledge"
  | "chat"
  | "citations"
  | "evaluation"
  | "settings"

export const menuItems = [
  { key: "dashboard" as const, label: "项目概览", icon: BarChart3 },
  { key: "upload" as const, label: "文档上传", icon: UploadCloud },
  { key: "ocr" as const, label: "OCR 解析", icon: ScanText },
  { key: "knowledge" as const, label: "知识库构建", icon: Database },
  { key: "chat" as const, label: "RAG 问答", icon: MessageSquareText },
  { key: "citations" as const, label: "引用来源", icon: FileSearch },
  { key: "evaluation" as const, label: "系统评估", icon: BrainCircuit },
  { key: "settings" as const, label: "设置", icon: Sparkles }
]

export const stats = [
  { label: "已上传文档", value: "128", hint: "PDF / 图片 / DOCX", icon: FileText },
  { label: "已解析页数", value: "3,426", hint: "PaddleOCR 累计处理", icon: ScanText },
  { label: "向量切片数量", value: "18,920", hint: "已写入 Retriever", icon: Layers3 },
  { label: "今日问答次数", value: "256", hint: "带引用回答占 91%", icon: Bot }
]

export const pipelineSteps = [
  { title: "文档上传", desc: "收集 PDF、图片、扫描件", icon: UploadCloud },
  { title: "PaddleOCR 识别", desc: "提取文本、表格与版面", icon: ScanText },
  { title: "文本清洗与切分", desc: "去噪、规范化、Chunk", icon: FileText },
  { title: "Embedding 向量化", desc: "生成语义向量", icon: BrainCircuit },
  { title: "Retriever 检索", desc: "Top-K 相似片段召回", icon: Database },
  { title: "RAG 生成答案", desc: "基于上下文合成回答", icon: MessageSquareText },
  { title: "引用来源展示", desc: "页码、Chunk、原文片段", icon: FileSearch },
  { title: "结果评估", desc: "忠实度、召回率、准确率", icon: CheckCircle2 }
]

export type UploadStatus = "待解析" | "OCR 处理中" | "已入库" | "解析失败"

export const uploadedFiles = [
  { name: "LangChain技术文档.pdf", type: "PDF", size: "18.4 MB", time: "2026-07-05 09:22", status: "已入库" as UploadStatus },
  { name: "企业制度扫描件.png", type: "PNG", size: "4.8 MB", time: "2026-07-05 10:14", status: "OCR 处理中" as UploadStatus },
  { name: "实验室安全手册.docx", type: "DOCX", size: "1.6 MB", time: "2026-07-04 18:40", status: "待解析" as UploadStatus },
  { name: "设备采购流程.jpg", type: "JPG", size: "3.1 MB", time: "2026-07-04 16:08", status: "解析失败" as UploadStatus }
]

export const ocrTasks = [
  { doc: "LangChain技术文档.pdf", pages: 42, progress: 100, confidence: "96.2%", duration: "2m 14s", status: "已完成" },
  { doc: "企业制度扫描件.png", pages: 18, progress: 68, confidence: "91.8%", duration: "1m 02s", status: "处理中" },
  { doc: "科研项目合同.pdf", pages: 67, progress: 34, confidence: "93.5%", duration: "3m 41s", status: "处理中" },
  { doc: "设备采购流程.jpg", pages: 6, progress: 100, confidence: "72.4%", duration: "28s", status: "需复核" }
]

export const chunks = [
  { id: "chunk_023", doc: "LangChain技术文档.pdf", page: "第 6 页", text: "Retriever 是 LangChain 中负责从知识库中检索相关上下文的核心组件。", embedding: "已生成", stored: "已入库" },
  { id: "chunk_041", doc: "知识库评估白皮书.pdf", page: "第 12 页", text: "Context Precision 衡量检索上下文中与问题直接相关的信息占比。", embedding: "已生成", stored: "已入库" },
  { id: "chunk_108", doc: "企业制度文档.docx", page: "第 3 页", text: "制度条款问答应优先依据原文回答，并在答案末尾列出证据来源。", embedding: "队列中", stored: "待入库" }
]

export const citations = [
  {
    question: "请总结第六章的主要内容。",
    summary: "第六章聚焦 Retriever 构建、向量检索和基于上下文的答案生成。",
    doc: "LangChain技术文档.pdf",
    page: "第 6 页",
    chunk: "chunk_023",
    score: 0.89,
    hit: true,
    text: "Retriever 是 LangChain 中负责从知识库中检索相关上下文的核心组件，通常结合向量数据库与相似度匹配实现。",
    confidence: "96.2%",
    used: true
  },
  {
    question: "如何判断回答是否忠实于原文？",
    summary: "需要比较模型回答与检索上下文的一致性，并结合引用准确率验证来源。",
    doc: "知识库评估白皮书.pdf",
    page: "第 12 页",
    chunk: "chunk_041",
    score: 0.84,
    hit: true,
    text: "Faithfulness 评估答案是否完全由给定上下文支持，避免模型引入无法从原文验证的内容。",
    confidence: "94.7%",
    used: true
  },
  {
    question: "制度问答是否允许自由发挥？",
    summary: "制度类文档建议只基于文档回答，缺少证据时应明确说明。",
    doc: "企业制度文档.docx",
    page: "第 3 页",
    chunk: "chunk_108",
    score: 0.78,
    hit: false,
    text: "问答系统在缺少证据来源时，应提示未检索到足够依据，而不是生成未经验证的结论。",
    confidence: "91.1%",
    used: false
  }
]

export const evaluationRows = [
  {
    question: "Retriever 的作用是什么？",
    expected: "从知识库检索与问题相关的上下文。",
    answer: "Retriever 负责召回相关 Chunk，并为 RAG 提供可引用上下文。",
    context: "LangChain技术文档.pdf / chunk_023",
    faithfulness: 95,
    citation: "正确",
    human: "通过"
  },
  {
    question: "如何提升引用准确率？",
    expected: "保留页码、Chunk ID，并过滤低分上下文。",
    answer: "可通过阈值、重排序和证据绑定提升引用质量。",
    context: "知识库评估白皮书.pdf / chunk_041",
    faithfulness: 90,
    citation: "正确",
    human: "通过"
  },
  {
    question: "模型能否回答文档外问题？",
    expected: "若只基于文档回答，应拒绝无依据问题。",
    answer: "默认可自由补充，但制度场景建议关闭。",
    context: "企业制度文档.docx / chunk_108",
    faithfulness: 78,
    citation: "待复核",
    human: "需复查"
  }
]

export const metricCards = [
  { label: "忠实度", value: 92, key: "Faithfulness" },
  { label: "回答相关性", value: 88, key: "Answer Relevance" },
  { label: "上下文召回率", value: 85, key: "Context Recall" },
  { label: "引用准确率", value: 90, key: "Citation Accuracy" }
]
