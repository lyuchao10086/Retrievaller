import assert from "node:assert/strict"
import fs from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"
import vm from "node:vm"
import ts from "typescript"

const require = createRequire(import.meta.url)
const sourcePath = new URL("../src/components/qaRecordDetailUtils.ts", import.meta.url)
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

const {
  formatKnowledgeBaseIds,
  formatQaRecordDate,
  formatQaRecordSource,
  formatQaRecordSourceScore
} = module.exports

test("formats qa record source metadata for details", () => {
  assert.equal(formatQaRecordSource({
    knowledge_base_id: "kb_1",
    chunk_id: "chunk_1",
    document_id: "doc_1",
    score: 0.87654,
    content: "source text",
    source: {
      knowledge_base_name: "水浒传知识库",
      file_name: "水浒传语料.md",
      chapter: "第一回",
      section: null,
      subsection: "宋江"
    }
  }), "水浒传知识库 / 水浒传语料.md - 第一回 - 宋江")
  assert.equal(formatQaRecordSourceScore(0.87654), "0.8765")
})

test("formats qa record detail fallbacks", () => {
  assert.equal(formatKnowledgeBaseIds(["kb_1", "kb_2"]), "kb_1, kb_2")
  assert.equal(formatKnowledgeBaseIds([]), "-")
  assert.equal(formatQaRecordSource({
    knowledge_base_id: "kb_1",
    chunk_id: "chunk_1",
    document_id: "doc_1",
    score: 0,
    content: "",
    source: {
      knowledge_base_name: "",
      file_name: "",
      chapter: null,
      section: null,
      subsection: null
    }
  }), "kb_1")
  assert.equal(formatQaRecordDate(null), "-")
})
