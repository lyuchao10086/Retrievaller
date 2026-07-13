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

当前代码已经具备账户注册/登录、按用户隔离的知识库 CRUD、文档上传/列表/删除/重命名、多知识库 RAG 问答、问答记录、指定 QA 记录评估、健康检查等基础功能。需要注意：文档解析、分段、embedding 写入 Milvus 的后端接口和服务代码已有雏形，但当前前端产品入口已按“待接入/草稿”处理，整体文档处理闭环仍不应视为稳定完成。OCR、rerank、多轮会话等功能也仍待后续接入。

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

- 当前主要通过 `docker-compose.yml` 启动后端、Celery 和中间件
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
- `JWT_SECRET_KEY`：HS256 访问令牌签名密钥；非本地环境必须替换为足够长的随机值
- `ACCESS_TOKEN_EXPIRE_MINUTES`：访问令牌有效期，示例值为 720 分钟
- `APP_ENV`：运行环境标识；示例为 `development`
- `APP_VERSION`：写入基准评测运行快照的应用版本标识；发布时建议设置为 Git tag 或构建号
- `LOG_LEVEL`、`LOG_FORMAT`：后端和 Celery 日志级别、格式；部署建议保留 `json`
- `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS`、`CELERY_TASK_TIME_LIMIT_SECONDS`：单个后台任务的软/硬超时，硬超时必须大于软超时
- `CORS_ALLOW_ORIGINS`：允许访问后端的前端来源
- `VITE_API_BASE_URL`：前端请求后端的 base URL，见 `frontend/.env.example`

容器内 MySQL、Redis、MinIO、Milvus 一律使用 Compose 服务名：`mysql`、`redis`、`minio`、`milvus`。不要将这些变量设为 `localhost`，因为容器中的 `localhost` 只代表当前容器。`OLLAMA_BASE_URL` 是后端容器访问宿主机模型服务的地址；Compose 已提供 `host.docker.internal:host-gateway` 映射以兼容 Docker Desktop 和 Linux Docker。

`.env.example` 中也包含 `RERANK_BASE_URL`、`RERANK_MODEL_NAME`。启用某个知识库的 rerank 后，RAG 与基准评测都会使用该知识库保存的 rerank 配置；服务不可用时请求会返回明确错误，不会静默降级。

服务依赖关系：

| 调用方 | 目标 | 容器/主机地址 |
| --- | --- | --- |
| 浏览器前端 | FastAPI | `VITE_API_BASE_URL`，默认 `http://localhost:8089` |
| FastAPI / Celery | MySQL、Redis、MinIO、Milvus | `mysql`、`redis`、`minio`、`milvus` |
| FastAPI / Celery | Ollama embedding / LLM | `OLLAMA_BASE_URL`，默认宿主机 `host.docker.internal:11434` |
| Milvus | MinIO、etcd | Compose 内 `minio:9000`、`etcd:2379` |
| Celery worker | Redis、FastAPI 已完成初始化的数据库 | 由 Compose `depends_on` 等待后端 readiness |

## 启动方式

### 标准 Docker 启动

在项目根目录执行：

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
# 编辑 .env：至少替换 JWT_SECRET_KEY，并确认 Ollama 地址与模型名

# 在宿主机准备模型服务
ollama serve
ollama pull <EMBEDDING_MODEL_NAME>
ollama pull <LOCAL_LLM_MODEL>

docker compose up -d
```

如果修改了后端依赖或 Dockerfile，可以使用：

```bash
docker compose up -d --build
```

首次启动时，FastAPI 会在 MySQL 中创建当前代码所需表；Celery worker 会等待后端 readiness 成功后再启动。当前没有 Alembic，升级已有环境前应先备份 MySQL 数据卷或数据库。

确认运行状态：

```bash
docker compose ps
curl -s http://localhost:8089/health/live
curl -s http://localhost:8089/health/ready
docker compose logs --tail=100 backend celery-worker
```

后端默认地址：

```text
http://localhost:8089
```

健康检查：

```bash
curl http://localhost:8089/health/live
curl http://localhost:8089/health/ready
curl http://localhost:8089/health
```

- `/health/live`：只检查 FastAPI 进程存活，供容器 liveness probe 使用。
- `/health/ready`：检查 MySQL、Redis、MinIO、Milvus、Ollama embedding/LLM；任一未就绪返回 HTTP `503`。
- `/health`：兼容诊断接口，始终返回依赖详情，适合前端设置页和人工排障。

DeepSeek、Celery Redis 配置、rerank 均会出现在详情中，但只有 DeepSeek/rerank 的 warning 不阻塞 `/health/ready`。模型不存在时，健康详情会返回类似 `ollama pull <model>` 的修复提示；响应不含密码、Token 或 API Key。

`/health/ready` 的典型失败响应：

```json
{
  "backend": {"status": "error"},
  "unready_dependencies": ["ollama_llm"],
  "dependencies": {
    "ollama_llm": {
      "status": "warning",
      "code": "model_missing",
      "hint": "Pull the model: ollama pull <configured-model>"
    }
  }
}
```

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

### 本地调试服务

常规开发建议让 MySQL、Redis、MinIO、Milvus 继续由 Docker Compose 承载，并在容器内运行后端和 worker，避免宿主机将 `MYSQL_HOST=mysql` 误解析为本机：

```bash
docker compose up -d
docker compose logs -f backend celery-worker
```

后端测试使用项目的 Conda 环境：

```bash
cd backend
conda run -n retrievaller python -m pytest -q
```

若必须从宿主机直接启动 Uvicorn/Celery，请将 MySQL、Redis、MinIO、Milvus 的 `*_HOST`/endpoint 临时改为 `127.0.0.1` 和对应宿主机端口；不要使用容器内服务名。

### 停止与清理

```bash
docker compose down                 # 停止容器，保留数据卷
docker compose down -v              # 同时删除 MySQL/Redis/MinIO/Milvus 数据，危险操作
docker compose restart backend celery-worker
```

### 排障与可观测性

后端与 worker 默认输出 JSON 日志，不记录请求体、密码、Bearer Token、API Key 或完整文档原文。每个 HTTP 响应都会携带 `X-Request-ID`；传入合规的 `X-Request-ID` 会被复用，方便将网关、后端和任务日志关联。用户 ID 在日志中会脱敏，文档处理日志包含知识库 ID、文档 ID、Celery task ID 和稳定错误码。

```bash
# 以请求 ID 关联 API 调用与 backend 日志
curl -i -H 'X-Request-ID: deploy-check-001' http://localhost:8089/health/ready
docker compose logs --tail=200 backend | grep deploy-check-001

# 查看 worker、任务队列和依赖容器日志
docker compose logs --tail=200 celery-worker
docker compose exec celery-worker celery -A app.tasks.celery_app.celery_app inspect ping --timeout=5
docker compose logs --tail=200 mysql redis minio milvus
```

可在非生产环境分别模拟依赖不可用，并观察 `/health/ready` 的 `503` 与 `unready_dependencies`：

```bash
docker compose stop mysql
curl -i http://localhost:8089/health/ready
docker compose start mysql
```

对 Redis、MinIO、Milvus 重复上述操作即可。Ollama 由宿主机提供时，可暂时停止 Ollama，或在隔离环境将 `OLLAMA_BASE_URL` 指向不可达地址后重建 backend；恢复真实地址和模型后执行 `docker compose up -d --force-recreate backend`。

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
- 用户名/密码注册与登录；业务接口使用 `Authorization: Bearer <access_token>`
- 知识库、文档、RAG 检索、QA 记录、评估结果均按当前用户隔离
- 文档上传、列表、删除、重命名
- 文档上传类型收敛到 TXT / MD / MARKDOWN
- 多知识库 RAG 问答接口和聊天页基础交互
- QA 记录列表、查看详情、删除
- 点击历史 QA 记录查看单轮问答详情
- 对指定 QA 记录调用 DeepSeek 评估
- 每个知识库的 RAG 基准集导入/导出、Celery 异步批量评测、运行快照与两次运行对比
- `GET /health` 健康检查
- `GET /api/system/config` 非密钥运行配置展示
- 前端知识库、聊天、历史、设置等页面基础 UI

## RAG 基准评测

基准评测面向同一知识库的参数、模型和索引回归验证。它不新增前端页面，使用已登录账户的 Bearer Token 调用后端 API。一次运行会冻结题集、知识库配置版本、切分/检索/生成参数、Embedding/LLM/Rerank/DeepSeek 模型名和 `APP_VERSION`，随后由 Celery 顺序执行每个启用样本。

主要接口：

- `POST /api/knowledge-bases/{kb_id}/benchmarks/import`：导入 JSON；`mode` 可为 `replace` 或 `append`。
- `POST /api/knowledge-bases/{kb_id}/benchmarks/import/csv?mode=replace`：以 `text/csv` 导入 CSV。
- `GET /api/knowledge-bases/{kb_id}/benchmarks/export?format=json|csv`：导出样本。
- `POST /api/knowledge-bases/{kb_id}/benchmark-runs`：创建异步评测，返回 `202` 与 `task_id`。
- `GET /api/knowledge-bases/{kb_id}/benchmark-runs/{run_id}`：查看汇总和单题结果。
- `GET /api/knowledge-bases/{kb_id}/benchmark-runs/{baseline_run_id}/compare/{candidate_run_id}`：比较两次已结束运行。

JSON 导入示例：

```json
{
  "mode": "replace",
  "items": [
    {
      "question": "系统的核心流程是什么？",
      "expected_document_ids": ["doc_example"],
      "expected_chunk_ids": ["chunk_example"],
      "tags": ["smoke"],
      "enabled": true
    }
  ]
}
```

CSV 列为 `question`、`expected_answer`、`expected_document_ids`、`expected_chunk_ids`、`tags`、`enabled`；三个列表列使用 JSON 数组字符串，例如 `"[""doc_example""]"`。

有期望文档或分块时，结果计算对应的召回/引用命中率；无期望来源时该指标为 `null`，不会被当成未命中。DeepSeek 会对每个成功生成的答案给出既有的 1-5 分维度评分。没有 `expected_answer` 时，系统不生成“标准答案正确率”，该维度仍需要人工审核。

## 认证与旧数据

所有业务接口都要求 JWT Bearer Token。`POST /api/auth/register` 与 `POST /api/auth/login` 接收 JSON 的 `username`、`password`：用户名只能使用字母、数字、`.`、`_`、`-`，密码至少 8 位。Token 过期、账户被停用或 Token 中用户名与账户记录不一致时，接口返回 `401`。

现有 `default_user` 数据会保留在不可登录的 legacy 账户下，新注册账户无法读取。若需要把开发数据明确转交给一个已注册账户，可运行：

```bash
cd backend
conda run -n retrievaller python scripts/migrate_legacy_user_data.py \
  --to-username <existing_username> --confirm
```

该脚本可重复运行：它删除旧租户的 Milvus 向量和 chunks，转移知识库/文档/QA/评估元数据，并将文档重置为 `uploaded`。迁移后必须由目标账户重新处理文档，避免旧向量的 `user_id` 元数据造成检索不一致。

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
