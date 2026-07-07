import { useState } from "react"
import Sidebar from "./components/Sidebar"
import Dashboard from "./components/Dashboard"
import UploadPage from "./components/UploadPage"
import OCRPage from "./components/OCRPage"
import KnowledgeBasePage from "./components/KnowledgeBasePage"
import ChatPage from "./components/ChatPage"
import QaRecordsPage from "./components/QaRecordsPage"
import CitationPage from "./components/CitationPage"
import EvaluationPage from "./components/EvaluationPage"
import SettingsPage from "./components/SettingsPage"
import type { MenuKey } from "./data/mockData"

const pageMap: Record<Exclude<MenuKey, "chat">, JSX.Element> = {
  dashboard: <Dashboard />,
  upload: <UploadPage />,
  ocr: <OCRPage />,
  knowledge: <KnowledgeBasePage />,
  qaRecords: <QaRecordsPage />,
  citations: <CitationPage />,
  evaluation: <EvaluationPage />,
  settings: <SettingsPage />
}

export default function App() {
  const [active, setActive] = useState<MenuKey>("chat")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="min-h-screen min-w-0 overflow-x-hidden bg-white">
      <div className="flex min-h-screen min-w-0 overflow-hidden">
        <Sidebar
          active={active}
          collapsed={sidebarCollapsed}
          onChange={setActive}
        />
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-white">
          <div className={active === "chat" ? "h-screen min-w-0 overflow-x-hidden" : "mx-auto max-w-[1440px] p-4 lg:p-6"}>
            {active === "chat" ? (
              <ChatPage
                sidebarCollapsed={sidebarCollapsed}
                onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
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
