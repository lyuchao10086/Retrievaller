import assert from "node:assert/strict"
import fs from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"
import vm from "node:vm"
import ts from "typescript"

const require = createRequire(import.meta.url)
const sourcePath = new URL("../src/components/knowledgeBaseDetailUtils.ts", import.meta.url)
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
  buildDocumentRecallCounts,
  filterDocuments,
  formatCompactCount,
  getDocumentAvailabilityLabel,
  getDocumentStatusLabel,
  isDocumentRetrievable
} = module.exports

test("filters documents by file name and type", () => {
  const documents = [
    { id: "doc_1", file_name: "三国演义资料.md", file_type: "md" },
    { id: "doc_2", file_name: "水浒传语料.txt", file_type: "txt" }
  ]

  assert.deepEqual(filterDocuments(documents, "三国"), [documents[0]])
  assert.deepEqual(filterDocuments(documents, "TXT"), [documents[1]])
  assert.deepEqual(filterDocuments(documents, " "), documents)
})

test("counts document recalls from qa record sources", () => {
  const records = [
    {
      sources_json: [
        { document_id: "doc_1", knowledge_base_id: "kb_1" },
        { document_id: "doc_1", knowledge_base_id: "kb_1" },
        { document_id: "doc_2", knowledge_base_id: "kb_2" }
      ]
    },
    {
      sources_json: [
        { document_id: "doc_2", knowledge_base_id: "kb_1" },
        { document_id: "doc_3", knowledge_base_id: "kb_1" }
      ]
    }
  ]

  assert.equal(JSON.stringify(buildDocumentRecallCounts(records, "kb_1")), JSON.stringify({
    doc_1: 2,
    doc_2: 1,
    doc_3: 1
  }))
})

test("formats table metrics for compact display", () => {
  assert.equal(formatCompactCount(999), "999")
  assert.equal(formatCompactCount(19500), "19.5k")
})

test("labels uploaded documents as not yet retrievable", () => {
  assert.equal(getDocumentStatusLabel("uploaded"), "已上传，待处理")
  assert.equal(getDocumentAvailabilityLabel("uploaded"), "待处理")
  assert.equal(isDocumentRetrievable("uploaded"), false)
  assert.equal(getDocumentStatusLabel("embedded"), "已入库，可检索")
  assert.equal(getDocumentAvailabilityLabel("embedded"), "可检索")
  assert.equal(isDocumentRetrievable("embedded"), true)
  assert.equal(getDocumentStatusLabel("failed"), "处理失败")
})
