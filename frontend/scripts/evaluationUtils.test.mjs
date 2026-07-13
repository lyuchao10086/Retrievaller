import assert from "node:assert/strict"
import fs from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"
import vm from "node:vm"
import ts from "typescript"

const require = createRequire(import.meta.url)
const sourcePath = new URL("../src/components/evaluationUtils.ts", import.meta.url)
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

const { buildEvaluationMetrics, buildEvaluationDimensions } = module.exports

test("summarizes persisted evaluation scores as percentages", () => {
  const evaluations = [
    {
      faithfulness_score: 5,
      relevance_score: 4,
      citation_score: 3,
      completeness_score: 4,
      overall_score: 4
    },
    {
      faithfulness_score: 3,
      relevance_score: 5,
      citation_score: 5,
      completeness_score: 2,
      overall_score: 4
    }
  ]

  assert.equal(JSON.stringify(buildEvaluationMetrics(evaluations)), JSON.stringify([
    { label: "忠实度", key: "Faithfulness", value: 80 },
    { label: "回答相关性", key: "Answer Relevance", value: 90 },
    { label: "完整性", key: "Completeness", value: 60 },
    { label: "引用准确率", key: "Citation Accuracy", value: 80 }
  ]))
  assert.equal(JSON.stringify(buildEvaluationDimensions(evaluations)), JSON.stringify([
    { label: "Faithfulness", value: 80 },
    { label: "Answer Relevance", value: 90 },
    { label: "Citation Accuracy", value: 80 },
    { label: "Completeness", value: 60 },
    { label: "Overall", value: 80 }
  ]))
})

test("uses zero scores when no persisted evaluation exists", () => {
  assert.equal(buildEvaluationMetrics([])[0].value, 0)
  assert.equal(buildEvaluationDimensions([])[4].value, 0)
})
