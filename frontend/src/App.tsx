import { useEffect, useState } from "react"
import { AUTH_SESSION_EXPIRED_EVENT, readAuthSession } from "./api/authSession"
import Sidebar from "./components/Sidebar"
import UploadPage from "./components/UploadPage"
import OCRPage from "./components/OCRPage"
import KnowledgeBasePage from "./components/KnowledgeBasePage"
import KnowledgeBaseGridPage from "./components/KnowledgeBaseGridPage"
import KnowledgeBaseCreateWizard from "./components/KnowledgeBaseCreateWizard"
import ChatPage from "./components/ChatPage"
import QaRecordsPage from "./components/QaRecordsPage"
import CitationPage from "./components/CitationPage"
import EvaluationPage from "./components/EvaluationPage"
import SettingsPage from "./components/SettingsPage"
import type { MenuKey } from "./data/mockData"
import type { QaRecord } from "./types/rag"
import type { AuthSession } from "./types/auth"
import LoginPage from "./components/LoginPage"

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(() => readAuthSession())
  const [active, setActive] = useState<MenuKey>("chat")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [selectedQaRecord, setSelectedQaRecord] = useState<QaRecord | null>(null)
  const [newChatToken, setNewChatToken] = useState(0)

  useEffect(() => {
    const handleExpiredSession = () => setSession(null)
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleExpiredSession)
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleExpiredSession)
  }, [])

  if (!session) {
    return <LoginPage onAuthenticated={setSession} />
  }

  const navigate = (key: MenuKey) => {
    if (key === "chat") {
      setSelectedQaRecord(null)
      setNewChatToken((value) => value + 1)
    }
    setActive(key)
  }

  const selectHistoryRecord = (record: QaRecord) => {
    setSelectedQaRecord(record)
    setActive("chat")
  }

  const pageMap: Record<Exclude<MenuKey, "chat">, JSX.Element> = {
    upload: <UploadPage />,
    ocr: <OCRPage />,
    knowledge: <KnowledgeBaseGridPage onNavigate={navigate} />,
    kbCreate: <KnowledgeBaseCreateWizard onBack={() => navigate("knowledge")} />,
    kbBuild: <KnowledgeBasePage />,
    qaRecords: <QaRecordsPage />,
    citations: <CitationPage />,
    evaluation: <EvaluationPage />,
    settings: <SettingsPage />
  }

  return (
    <div className="min-h-screen min-w-0 overflow-x-hidden bg-white">
      <div className="flex min-h-screen min-w-0 overflow-hidden">
        <Sidebar
          active={active}
          collapsed={sidebarCollapsed}
          onChange={navigate}
          onSelectHistory={selectHistoryRecord}
          username={session.username}
        />
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-white">
          <div className={active === "chat" ? "h-screen min-w-0 overflow-x-hidden" : "mx-auto max-w-[1440px] p-4 lg:p-6"}>
            {active === "chat" ? (
              <ChatPage
                sidebarCollapsed={sidebarCollapsed}
                onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
                selectedQaRecord={selectedQaRecord}
                newChatToken={newChatToken}
              />
            ) : (
              pageMap[active]
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
