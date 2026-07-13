# Model Retrieval Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist knowledge-base-scoped processing, retrieval and generation configuration, snapshot it for document jobs, and use it during RAG retrieval and reranking.

**Architecture:** Add a focused `knowledge_base_configs` repository and JSON-backed dataclasses. Documents persist an immutable processing snapshot plus a reindex flag. The RAG route resolves each selected knowledge base configuration, performs per-knowledge-base retrieval, and uses the confirmed `/v1/rerank` protocol when enabled.

**Tech Stack:** FastAPI, Pydantic v2, aiomysql/MySQL 8, Celery, httpx, React/TypeScript.

## Global Constraints

- Do not add LangChain, new queues, or a new frontend page.
- Keep RAG paths and existing document processing APIs compatible.
- External Ollama, Milvus, Celery and rerank calls are faked in tests.
- Do not log document bodies, credentials, tokens or API keys.
- Delete `docs/superpowers/specs/2026-07-13-model-retrieval-configuration-design.md` after implementation.

---

### Task 1: Persistent Configuration Domain

**Files:**
- Create: `backend/app/models/knowledge_base_config.py`
- Create: `backend/app/repositories/knowledge_base_config.py`
- Create: `backend/app/schemas/knowledge_base_config.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_knowledge_base_config.py`

**Interfaces:**
- Produces `KnowledgeBaseConfig`, `ProcessingConfig`, `RetrievalConfig`, `GenerationConfig`.
- Produces `KnowledgeBaseConfigRepository.get_or_create_by_knowledge_base_and_user` and `update_by_knowledge_base_and_user`.

- [ ] Write tests that create two configs with distinct chunk and retrieval values and assert each read returns its own values.
- [ ] Run the focused test and verify it fails because the configuration repository does not exist.
- [ ] Add the dataclasses, schemas, MySQL table/compatibility columns and repository; generate defaults from `Settings`.
- [ ] Run the focused test and verify it passes.

### Task 2: Configuration APIs and Reindex Marking

**Files:**
- Modify: `backend/app/api/routes/knowledge_base.py`
- Modify: `backend/app/services/knowledge_base.py`
- Modify: `backend/app/repositories/document.py`
- Modify: `backend/app/models/document.py`
- Modify: `backend/app/schemas/document.py`
- Test: `backend/tests/test_knowledge_base_config.py`

**Interfaces:**
- Produces `GET|PUT /api/knowledge-bases/{kb_id}/config`.
- Produces `Document.processing_config_json`, `config_version`, `needs_reindex`.

- [ ] Write tests that update index-affecting config and expect embedded documents to become `needs_reindex`, while retrieval-only changes do not.
- [ ] Run the focused test and verify it fails because the route and document flag are missing.
- [ ] Implement ownership-checked routes, configuration validation, and mark only index-affecting changes.
- [ ] Run the focused test and verify it passes.

### Task 3: Snapshot Processing Configuration

**Files:**
- Modify: `backend/app/api/routes/document.py`
- Modify: `backend/app/tasks/document_processing.py`
- Modify: `backend/app/services/document.py`
- Test: `backend/tests/test_documents.py`

**Interfaces:**
- `POST /process` resolves a config, stores a snapshot/version on the document, and queues the same snapshot.
- Celery task consumes only the snapshot fields accepted by `create_document_chunks` and `embed_document_chunks`.

- [ ] Write a route test that processes a document without a body and asserts the saved snapshot and queued arguments match its knowledge base config.
- [ ] Run the test and verify it fails because no config snapshot is persisted.
- [ ] Implement snapshot persistence and clear `needs_reindex` only after successful embedding.
- [ ] Run document tests and verify they pass.

### Task 4: Per-Knowledge-Base Retrieval and Rerank

**Files:**
- Create: `backend/app/services/rerank_service.py`
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/app/services/rag_service.py`
- Modify: `backend/app/api/routes/rag.py`
- Modify: `backend/app/services/local_llm_service.py`
- Modify: `backend/app/services/health.py`
- Test: `backend/tests/test_rag.py`

**Interfaces:**
- `RerankService.rerank(query, documents, model_name)` calls `/v1/rerank` and returns index/score pairs.
- RAG resolves configs by knowledge base, filters score thresholds and stale documents, and passes model/options to LLM generation.

- [ ] Write tests with two fake configs asserting distinct top-k/thresholds are passed to retrieval, rerank order follows `relevance_score`, and the first knowledge base controls LLM options.
- [ ] Run tests and verify they fail because config and rerank dependencies are absent.
- [ ] Implement the minimal rerank adapter, per-knowledge-base retrieval orchestration, generation options and protocol-based rerank health check.
- [ ] Run RAG tests and verify they pass.

### Task 5: Existing Frontend Wiring and Cleanup

**Files:**
- Modify: `frontend/src/api/knowledgeBaseApi.ts`
- Modify: `frontend/src/types/knowledgeBase.ts`
- Modify: `frontend/src/components/KnowledgeBaseCreateWizard.tsx`
- Modify: `frontend/src/components/ChunkSettingsPage.tsx`
- Modify: `frontend/src/components/KnowledgeBaseDetailPage.tsx`
- Modify: `frontend/src/components/ChatPage.tsx`
- Delete: `docs/superpowers/specs/2026-07-13-model-retrieval-configuration-design.md`

- [ ] Add only required request/response types and connect the existing wizard and chunk settings controls to configuration APIs.
- [ ] Remove the misleading local-only processing configuration behavior and omit the ChatPage local Top-K default when no explicit override is intended.
- [ ] Surface existing-document `needs_reindex` using existing status/error presentation without changing page layout.
- [ ] Delete the approved design document as requested.
- [ ] Run TypeScript, production build and backend full test suite.
