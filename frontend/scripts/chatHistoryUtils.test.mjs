import assert from "node:assert/strict"
import fs from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"
import vm from "node:vm"
import ts from "typescript"

const require = createRequire(import.meta.url)
const sourcePath = new URL("../src/components/chatHistoryUtils.ts", import.meta.url)
const source = fs.readFileSync(sourcePath, "utf8")
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020
  }
})
const module = { exports: {} }
vm.runInNewContext(outputText, {
  exports: module.exports,
  module,
  require,
  console
})

const { restoreMessagesFromQaRecord } = module.exports

test("restores a single qa record as readonly chat messages", () => {
  const source = {
    chunk_id: "chunk_1",
    document_id: "doc_1",
    knowledge_base_id: "kb_1",
    score: 0.8,
    content: "引用内容",
    source: {
      knowledge_base_name: "知识库",
      file_name: "文档.md"
    }
  }
  const messages = restoreMessagesFromQaRecord({
    id: "qa_1",
    title: "标题",
    question: "用户问题",
    answer: "AI 回答",
    knowledge_base_ids: ["kb_1"],
    sources_json: [source],
    created_at: "2026-07-08T00:00:00Z"
  })

  assert.equal(JSON.stringify(messages), JSON.stringify([
    { role: "user", content: "用户问题" },
    {
      role: "assistant",
      content: "AI 回答",
      sources: [source],
      qaRecordId: "qa_1"
    }
  ]))
})
