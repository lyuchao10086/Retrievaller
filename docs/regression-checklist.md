# Retrievaller 核心流程冒烟测试与回归检查清单

本文档用于每次发版、交接或较大改动后快速确认当前已实现能力没有退化。当前项目仍处于通用知识库检索平台雏形阶段，文档上传后的正式解析、分段、embedding、Milvus 入库链路尚未作为上传流程完整闭环接入。

## 1. 自动化检查

### 后端测试

```bash
cd backend
pytest
```

当前自动化重点覆盖：

- 健康检查响应结构与依赖状态汇总。
- 知识库 CRUD service 与 API。
- 文档上传、列表、删除、重命名、处理接口的轻量 fake 依赖测试。
- 多知识库 RAG 的无可检索内容、非法知识库、本地 LLM 不可用分支。
- QA 记录列表与删除。
- QA 记录评估列表、DeepSeek 未配置错误、已有评估复用。
- demo RAG seed 脚本的文本切分纯函数。

### 前端脚本测试

```bash
cd frontend
node scripts/viteConfig.test.mjs
node scripts/knowledgeBaseDetailUtils.test.mjs
node scripts/qaRecordDetailUtils.test.mjs
node scripts/chatHistoryUtils.test.mjs
```

当前自动化重点覆盖：

- Vite dev server 端口配置。
- 文档筛选、召回统计、文档状态文案映射。
- 历史问答详情来源格式化。
- 单轮 QA 记录恢复为只读聊天消息。

### 前端类型检查与构建

```bash
cd frontend
npm exec tsc -- --noEmit -p tsconfig.json
npm run build
```

## 2. 启动环境冒烟检查

1. 复制环境变量模板，不要提交真实密钥。

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

2. 启动后端与中间件。

```bash
docker compose up -d
```

3. 检查后端健康状态。

```bash
curl http://localhost:8089/health
```

期望：

- `backend` 为可用状态。
- MySQL、Redis、MinIO、Milvus 返回明确状态。
- Ollama 不在线时返回明确 `error`，不应导致 `/health` 崩溃。
- DeepSeek 未配置时为 `warning`，且不泄露 API key。

4. 启动前端。

```bash
cd frontend
npm run dev
```

默认访问 `http://localhost:5173`。

## 3. 知识库流程

1. 打开知识库页面。
2. 创建一个测试知识库。
3. 修改知识库名称和描述。
4. 返回列表，确认名称和描述更新。
5. 删除测试知识库。
6. 刷新页面，确认已删除知识库不再展示。

期望：

- 创建、编辑、删除都有明确反馈。
- 删除不存在或已删除对象时后端返回 404，前端错误提示可读。

## 4. 文档流程

1. 创建或选择一个知识库。
2. 上传 `.txt` 或 `.md` 文件。
3. 查看文档列表。
4. 确认文档状态显示为 `已上传，待处理`。
5. 确认上传成功提示为“文件已上传，尚未完成分段与向量入库”或等价文案。
6. 重命名文档。
7. 删除文档。
8. 尝试上传 PDF、DOCX、图片等未接入格式。

期望：

- 当前只允许 TXT/MD/MARKDOWN 文本文件。
- 上传后不暗示已解析、已分段或已入库。
- 分段设置入口标注为草稿或待接入。
- 删除文档后列表刷新，相关记录消失。

## 5. 聊天与 RAG 流程

### 无向量数据场景

1. 选择只有 uploaded 文档、没有 embedded chunks 的知识库。
2. 在聊天页提问。

期望：

- 后端返回“当前选择的知识库中没有检索到与问题相关的内容。”或等价提示。
- 前端不要展示伪造引用来源。

### demo seed 数据场景

1. 确认 Docker 中间件与 Ollama embedding/LLM 服务可用。
2. 运行开发 seed 脚本。

```bash
cd backend
python scripts/seed_demo_rag.py
```

3. 打开前端，选择 `示例知识库`。
4. 提问：

```text
水浒传中宋江的性格特点是什么？
```

期望：

- 回答能返回。
- `sources` 不为空。
- 引用来源包含文档名、chunk_id、score 和原文内容。

## 6. 历史记录流程

1. 完成一次 RAG 提问。
2. 进入历史问答记录页。
3. 查看列表。
4. 点击一条记录。
5. 确认详情展示标题、创建时间、用户问题、AI 回答、知识库 ID 和引用来源。
6. 删除记录。

期望：

- 点击记录打开只读详情。
- 删除按钮不触发打开详情。
- 删除后列表刷新。
- 当前仍是“一条 QA 记录 = 一轮历史问答”，不是真正多轮会话。

## 7. 评估流程

1. 对带 `qa_record_id` 的回答点击评估。
2. 如果 DeepSeek API key 未配置，确认错误提示明确。
3. 如果已存在评估结果，再次打开/触发时应复用已有结果，不重复调用 DeepSeek。

期望：

- 未配置 DeepSeek 时不泄露密钥。
- 已评估记录可以查询到历史评估结果。

## 8. 设置与健康状态页面

1. 打开设置页。
2. 刷新系统状态。
3. 对照 `/health` 返回内容。

期望：

- MySQL、Redis、MinIO、Milvus、Ollama、DeepSeek 配置、Celery 配置状态显示清楚。
- `warning` 与 `error` 能区分可选配置未接入和核心依赖不可用。

## 9. 当前仍需手动验证的流程

- 真实 Docker Compose 启动与各中间件网络连通。
- Ollama 模型是否已经拉取、embedding 维度是否与 Milvus collection 一致。
- demo seed 脚本写入 MySQL、MinIO、Milvus 的真实效果。
- 前端页面的实际交互和视觉状态。
- DeepSeek 真实 API 调用效果。

## 10. 发版前建议命令清单

```bash
cd backend
pytest

cd ../frontend
node scripts/viteConfig.test.mjs
node scripts/knowledgeBaseDetailUtils.test.mjs
node scripts/qaRecordDetailUtils.test.mjs
node scripts/chatHistoryUtils.test.mjs
npm exec tsc -- --noEmit -p tsconfig.json
npm run build
```

如果使用本地 conda 环境，先确认依赖已安装：

```bash
conda activate retrievaller
cd backend
pip install -r requirements.txt
pytest
```
