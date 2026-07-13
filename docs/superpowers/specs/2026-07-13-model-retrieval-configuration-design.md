# 模型与检索参数配置生效闭环设计

## 目标

让知识库的文档处理、Embedding、检索、rerank 和生成参数有唯一的持久化来源，并在异步处理和 RAG 问答中实际使用。配置属于知识库和当前用户，历史索引不会在配置变更后被静默替换。

## 范围

本轮支持并闭环以下配置：

- 分段与清洗：`separator`、`chunk_size`、`chunk_overlap`、`replace_consecutive_whitespace`、`remove_urls_and_emails`。
- 索引：`embedding_model_name`。
- 检索：`top_k`、`similarity_threshold`、`rerank_enabled`、`rerank_model_name`、`rerank_candidate_count`。
- 生成：`llm_model_name`、`temperature`、`max_tokens`。

不实现语义分块、递归分块、父子块、PDF/OCR 或新的前端配置页。现有前端没有知识库上下文的设置控件不会被伪装成知识库配置。

## 数据模型

新增 `knowledge_base_configs`，每个 active 知识库最多一条配置：

- `knowledge_base_id`、`user_id`：资源归属和隔离边界。
- `processing_config_json`、`retrieval_config_json`、`generation_config_json`：结构化 JSON 配置。
- `version`：每次成功更新递增。
- `created_at`、`updated_at`。

知识库创建时，后端从 `Settings` 生成默认配置并写入该表。创建向导提供的五项分段/清洗参数覆盖默认处理配置。

`documents` 新增：

- `processing_config_json`：提交处理任务时解析出的完整处理配置快照。
- `config_version`：该快照对应的知识库配置版本。
- `needs_reindex`：当前索引是否与知识库有效索引配置不一致。

文档快照不可因后续知识库配置更新而变化。

## API 和配置流

新增知识库配置读取与更新接口：

- `GET /api/knowledge-bases/{kb_id}/config`
- `PUT /api/knowledge-bases/{kb_id}/config`

`PUT` 接受完整或部分配置，并返回解析后的有效配置和版本。请求必须属于当前用户；不存在或越权资源一律返回 `404`。

创建知识库接口可接收可选 `processing_config`，仅包含当前已支持的五项前端字段。创建成功后返回知识库；配置通过上述接口读取。

`POST /documents/{document_id}/process` 保持兼容。默认读取当前知识库配置、写入文档快照并将快照传给 Celery。旧客户端提供的基础分段 body 仍可作为一次任务覆盖，但同样会被保存为该文档快照。

## 文档索引生命周期

处理任务开始前固定处理配置和版本，Celery 只使用传入的快照进行清洗、切分和 Embedding。

配置变更规则：

- 分段/清洗或 Embedding 模型变更：所有当前已处理文档设为 `needs_reindex=true`，保留原有 chunk 和向量。
- 检索、rerank、LLM 参数变更：不标记重建，因为不会改变现有 chunk 或向量。
- 用户显式调用现有处理/重试入口后：先清理该文档旧 chunk 与向量，按新快照重建，成功时清除 `needs_reindex`。

RAG 结果会排除 `needs_reindex=true` 的文档，避免使用与有效 Embedding 配置不兼容的历史向量。

## RAG 规则

RAG 针对每个选中的知识库读取自己的有效配置：

1. 使用该知识库的 Embedding 模型生成 query 向量。
2. 以该知识库的 `rerank_candidate_count` 或 `top_k` 从 Milvus 取候选。
3. 应用 `similarity_threshold`。
4. 启用 rerank 时调用 `POST {RERANK_BASE_URL}/v1/rerank`，请求包含 `model`、`query` 和候选 chunk 文本；按 `results[].relevance_score` 排序。
5. 保留该知识库 `top_k` 条来源，合并多个知识库结果。

多知识库问答的生成模型、temperature、max_tokens 使用请求中第一个知识库的生成配置。这是一个显式且稳定的优先级规则；各知识库的检索和 rerank 参数仍分别生效。

## 校验与错误处理

- 分块参数复用现有范围和 `chunk_overlap < chunk_size` 校验。
- `top_k`、rerank 候选数量、temperature、max_tokens 设定严格边界。
- 保存配置前调用 Ollama `/api/tags`，Embedding 或 LLM 模型不存在返回 `422` 和不含敏感信息的修复提示。
- 启用 rerank 时进行一次最小 `/v1/rerank` 协议校验；服务不可达、模型错误或返回格式错误返回 `422`/`503`。
- RAG 运行期间 Ollama、Milvus 或 rerank 失败保留稳定错误码和请求关联日志，不记录完整原文、Token 或 API Key。

## 前端边界

- 创建向导提交已有五个基础处理字段。
- ChunkSettingsPage 读取并保存所属知识库的已支持字段；未支持控件继续禁用。
- 文档列表只增加必要的“需要重新索引”状态文本和错误提示。
- ChatPage 不再把浏览器 localStorage 的 Top-K 伪装成知识库配置；省略显式 Top-K 时由后端使用知识库配置。
- SettingsPage 保留运行状态展示。其无知识库上下文的 Temperature/Top-K 控件会被收敛为请求偏好或只读说明，不作为持久化知识库配置。

## 测试

- 两个知识库使用不同分段与检索配置时互不影响。
- `process` 将已解析的处理配置和版本持久化到文档，并将同一快照交给任务。
- 索引相关配置更新将 embedded 文档标为需要重建；检索参数更新不会标记重建。
- 伪造 Embedding、Milvus、rerank、LLM 与 Celery，验证每个知识库的参数实际传给切分、检索、rerank 和生成调用。
- 前端仅补 API 类型和已有字段提交/回显检查，运行 TypeScript 与生产构建。
