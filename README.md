# Retrievaller

Retrievaller 是一个前后端分离的通用知识库检索平台雏形，目标是把文档上传、知识库管理、多知识库 RAG 问答、引用来源追踪和问答质量评估串成一套可迭代系统。

当前技术栈目标包括：

- FastAPI 后端
- React + Vite + TypeScript 前端
- MySQL
- Redis
- MinIO
- Milvus + etcd
- Ollama 本地 embedding / chat 模型服务
- Celery 后台任务预留

当前代码已经具备知识库 CRUD、文档上传/列表/删除/重命名、多知识库 RAG 问答、问答记录、指定 QA 记录评估、健康检查等基础功能。需要注意：文档解析、分段、embedding 写入 Milvus 的后端接口和服务代码已有雏形，但当前前端产品入口已按“待接入/草稿”处理，整体文档处理闭环仍不应视为稳定完成。OCR、rerank、真正多用户鉴权、多轮会话等功能也仍待后续接入。

## 目录结构

```text
.
├── backend/              # FastAPI 后端、service/repository/schema、测试
├── frontend/             # React + Vite + TypeScript 前端
├── example/              # 示例文本语料
├── deploy/               # 部署相关占位目录，当前代码未发现完整部署脚本
├── docker-compose.yml    # 后端与 MySQL/Redis/MinIO/Milvus/etcd/Celery 编排
├── .env.example          # 后端和中间件环境变量示例
└── frontend/.env.example # 前端 API 地址示例
```

## 技术栈

前端：

- React 18
- Vite 6
- TypeScript
- Tailwind CSS 风格的 utility class
- lucide-react 图标

后端：

- FastAPI
- aiomysql
- pydantic-settings
- httpx
- pytest

数据库 / 中间件：

- MySQL 8.4
- Redis 7
- MinIO
- Milvus 2.5 standalone
- etcd
- Celery + Redis broker/result backend

模型服务：

- Ollama embedding model，具体名称以 `.env.example` 的 `EMBEDDING_MODEL_NAME` 为准
- Ollama chat/LLM model，具体名称以 `.env.example` 的 `LOCAL_LLM_MODEL` 为准
- DeepSeek API 用于可选 QA 评估

部署方式：

- 当前主要通过 `docker-compose.yml` 启动后端和中间件
- 前端通常本地 `npm run dev` 启动

## 环境要求

建议准备：

- Docker / Docker Compose
- Node.js 与 npm
- Python 3.12 推荐
- 本地 Ollama
- 已按 `.env.example` 拉取对应 Ollama 模型，例如 embedding model 与 LLM model

示例 Ollama 拉取命令请以你的 `.env` 配置为准，例如：

```bash
ollama pull <EMBEDDING_MODEL_NAME>
ollama pull <LOCAL_LLM_MODEL>
```

## 环境变量

复制环境变量模板：

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

不要提交真实 `.env`，尤其不要提交任何 API Key、对象存储密钥或数据库密码。

关键变量说明：

- `BACKEND_PORT`：宿主机访问后端的端口，默认示例为 `8089`
- `MYSQL_*`：MySQL 连接和容器暴露端口
- `REDIS_*`：Redis 连接、Celery broker/result backend 使用的 DB
- `MINIO_*`：MinIO endpoint、bucket、访问凭据和端口
- `MILVUS_*`：Milvus host、port、collection 名称
- `OLLAMA_BASE_URL`：后端访问 Ollama 的地址，Docker 环境常见为 `http://host.docker.internal:11434`
- `EMBEDDING_MODEL_NAME`：embedding 模型名
- `EMBEDDING_DIMENSION`：embedding 输出维度，必须和模型真实输出一致
- `LOCAL_LLM_MODEL`：本地问答模型名
- `DEEPSEEK_API_KEY`：DeepSeek 评估 API Key；未配置时评估相关能力不可用或返回提示
- `CORS_ALLOW_ORIGINS`：允许访问后端的前端来源
- `VITE_API_BASE_URL`：前端请求后端的 base URL，见 `frontend/.env.example`

`.env.example` 中也包含 `RERANK_BASE_URL`、`RERANK_MODEL_NAME`，但当前代码未发现 rerank 后端链路真正接入。

## 启动方式

### 后端与中间件

在项目根目录执行：

```bash
docker compose up -d
```

如果修改了后端依赖或 Dockerfile，可以使用：

```bash
docker compose up -d --build
```

后端默认地址：

```text
http://localhost:8089
```

健康检查：

```bash
curl http://localhost:8089/health
```

`/health` 会返回 backend、MySQL、Redis、MinIO、Milvus、Ollama embedding、Ollama LLM、DeepSeek 配置、Celery 配置状态。

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认前端地址：

```text
http://localhost:5173
```

如果前端请求后端失败，先检查 `frontend/.env` 中的 `VITE_API_BASE_URL` 是否指向 `http://localhost:8089`，再检查后端 `CORS_ALLOW_ORIGINS` 是否包含当前前端地址。

## 测试与构建

### 后端

本地 Python 环境：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

也可以在项目根目录指定测试目录：

```bash
python -m pytest backend/tests -q
```

### 前端

```bash
cd frontend
npm install
npm exec tsc -- --noEmit -p tsconfig.json
npm run build
```

当前仓库还包含几个轻量脚本测试，可在项目根目录运行：

```bash
node frontend/scripts/viteConfig.test.mjs
node frontend/scripts/knowledgeBaseDetailUtils.test.mjs
node frontend/scripts/qaRecordDetailUtils.test.mjs
node frontend/scripts/chatHistoryUtils.test.mjs
```

## 当前已实现功能

按当前代码和前端可见入口，已实现或已有基础能力：

- 知识库创建、列表、详情、更新、删除
- 文档上传、列表、删除、重命名
- 文档上传类型收敛到 TXT / MD / MARKDOWN
- 多知识库 RAG 问答接口和聊天页基础交互
- QA 记录列表、查看详情、删除
- 点击历史 QA 记录查看单轮问答详情
- 对指定 QA 记录调用 DeepSeek 评估
- `GET /health` 健康检查
- `GET /api/system/config` 非密钥运行配置展示
- 前端知识库、聊天、历史、设置等页面基础 UI

后端代码中还存在文档 parse/chunks/embed/process 相关接口和 service 雏形，但当前产品层面已将知识库构建、分段设置等入口标注为待接入/草稿，不建议把这部分视作稳定可用闭环。

## 当前未完整闭环 / 待接入功能

- 文档解析、分段、embedding、Milvus 入库的稳定端到端闭环
- 前端分段与清洗配置真正持久化并影响后端处理结果
- chunks 创建与 embedding 入库的用户可见正式流程
- Celery 后台处理任务的完整产品化状态、重试、进度展示
- rerank
- OCR / PaddleOCR
- PDF / DOCX / 图片等非纯文本格式
- 前端部分页面仍为演示或规划状态，例如 OCR 页面、系统评估示例页、Dashboard 部分指标
- 真正多用户 / 鉴权 / 权限隔离
- 多轮会话模型；当前历史记录更接近“一条 QA 记录 = 一轮问答”
- Alembic 或其他数据库迁移体系；当前代码未发现正式迁移脚本

## 核心业务流程现状

当前建议按下面方式理解业务链路：

1. 创建知识库。
2. 上传 TXT / MD / MARKDOWN 文档。
3. 当前可靠产品能力首先是保存原始文件和文档元数据。
4. RAG 问答依赖 MySQL chunks 表中存在 `status = embedded` 且 `vector_id` 不为空的 chunk，并依赖 Milvus 中存在对应向量。
5. 如果没有完成 chunks / 向量数据准备，问答可能无法检索到引用来源或内容。

因此，上传文档后如果直接提问没有引用来源，通常不是聊天页问题，而是文档尚未形成可检索的 embedded chunks。

## 常见问题

### 为什么上传文件后问答没有引用来源？

RAG 检索依赖已经 embedding 并写入 Milvus 的 chunks。当前文档处理闭环仍在接入和收敛阶段；如果 chunks 表没有 `embedded` 状态记录，或 Milvus 中没有对应向量，问答就检索不到来源。

### Ollama 模型找不到怎么办？

检查 `.env` 中：

- `OLLAMA_BASE_URL`
- `EMBEDDING_MODEL_NAME`
- `LOCAL_LLM_MODEL`

然后确认 Ollama 正在运行，并拉取对应模型：

```bash
ollama list
ollama pull <model-name>
```

也可以访问：

```bash
curl http://localhost:11434/api/tags
```

如果后端在 Docker 中访问宿主机 Ollama，通常需要使用 `.env.example` 中类似 `http://host.docker.internal:11434` 的地址。

### DeepSeek API key 未配置会影响什么？

DeepSeek 主要用于 QA 记录评估。未配置 `DEEPSEEK_API_KEY` 不应影响知识库 CRUD、文档上传和基础 RAG 问答，但评估请求会不可用或返回配置错误。`/health` 中 `deepseek_config` 未配置时应是 `warning`，不是 `error`。

### MinIO / Milvus / MySQL 连接失败如何排查？

先查看容器状态：

```bash
docker compose ps
```

再查看日志：

```bash
docker compose logs backend
docker compose logs mysql
docker compose logs minio
docker compose logs milvus
docker compose logs redis
```

然后访问健康检查：

```bash
curl http://localhost:8089/health
```

`dependencies` 中会逐项显示 `ok`、`warning` 或 `error`。

### 前端请求后端失败怎么办？

检查：

- 后端是否启动：`curl http://localhost:8089/health`
- 前端 `frontend/.env` 的 `VITE_API_BASE_URL`
- 后端 `.env` 的 `CORS_ALLOW_ORIGINS`
- 浏览器控制台 Network 面板中的真实请求 URL 和状态码

### 为什么有些页面显示“演示”或“待接入”？

为了避免用户误以为未完成能力已经闭环，当前 OCR、系统评估示例、知识库构建的部分操作入口已标注为演示或待接入。保留这些页面是为了展示产品方向和后续开发位置。

## 下一步开发建议

推荐路线：

1. 继续治理前后端接口契约和未接入 UI 提示。
2. 补齐文档解析、chunk、embedding、Milvus 入库的稳定闭环。
3. 接入 Celery 异步处理的任务状态、失败重试和前端进度展示。
4. 接入 rerank。
5. 完善历史对话与评估体验，明确单轮 QA 与多轮会话模型边界。
6. 增加测试覆盖、数据库迁移方案和部署文档。

## 安全说明

- 不要提交 `.env`。
- 不要在 README、issue、日志截图中暴露真实 API Key、MinIO secret、数据库密码。
- 对外展示运行配置时，只展示模型名、URL、bucket、collection 等非密钥信息。
