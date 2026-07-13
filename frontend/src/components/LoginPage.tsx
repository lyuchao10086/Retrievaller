import { useState, type FormEvent } from "react"
import { KeyRound } from "lucide-react"
import { ApiError } from "@/api/client"
import { login, register } from "@/api/authApi"
import { saveAuthSession } from "@/api/authSession"
import type { AuthSession } from "@/types/auth"
import { Button } from "./ui/button"
import { Input } from "./ui/input"
import { Label } from "./ui/label"

type LoginPageProps = {
  onAuthenticated: (session: AuthSession) => void
}

export default function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [mode, setMode] = useState<"login" | "register">("login")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError("")
    try {
      const response = await (mode === "login" ? login : register)({ username, password })
      onAuthenticated(saveAuthSession(response))
    } catch (unknownError) {
      setError(unknownError instanceof ApiError ? unknownError.detail : "登录失败，请稍后重试")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f7f7] px-4">
      <section className="w-full max-w-sm rounded-lg border border-[#e6e6e6] bg-white p-6 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-100 text-blue-600">
            <KeyRound className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[#1f1f1f]">Retrievaller</h1>
            <p className="text-sm text-[#777]">{mode === "login" ? "登录后访问你的知识库" : "创建一个本地账户"}</p>
          </div>
        </div>

        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="username">用户名</Label>
            <Input
              id="username"
              autoComplete="username"
              minLength={3}
              maxLength={64}
              pattern="[A-Za-z0-9_.-]+"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
              maxLength={256}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button className="w-full" type="submit" disabled={loading}>
            {loading ? "提交中..." : mode === "login" ? "登录" : "注册并登录"}
          </Button>
        </form>

        <button
          type="button"
          className="mt-4 w-full text-sm text-[#555] underline-offset-4 hover:underline"
          onClick={() => {
            setMode((current) => (current === "login" ? "register" : "login"))
            setError("")
          }}
        >
          {mode === "login" ? "没有账户？注册" : "已有账户？登录"}
        </button>
      </section>
    </main>
  )
}
