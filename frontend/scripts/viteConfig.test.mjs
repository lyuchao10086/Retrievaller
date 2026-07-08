import assert from "node:assert/strict"
import fs from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"
import vm from "node:vm"
import ts from "typescript"

const require = createRequire(import.meta.url)
const sourcePath = new URL("../vite.config.ts", import.meta.url)
const source = fs.readFileSync(sourcePath, "utf8")
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    esModuleInterop: true,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020
  }
})

const module = { exports: {} }
vm.runInNewContext(outputText, {
  __dirname: new URL("..", import.meta.url).pathname.replace(/\/$/, ""),
  exports: module.exports,
  module,
  require: (specifier) => {
    if (specifier === "vite") {
      return { defineConfig: (config) => config }
    }
    if (specifier === "@vitejs/plugin-react") {
      return () => ({ name: "mock-react-plugin" })
    }
    return require(specifier)
  },
  console
})

const config = module.exports.default

test("uses a single stable Vite dev server port", () => {
  assert.equal(config.server?.port, 5173)
  assert.equal(config.server?.strictPort, true)
  assert.equal(config.server?.hmr?.clientPort, 5173)
})
