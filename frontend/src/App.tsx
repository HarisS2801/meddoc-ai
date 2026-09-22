import { useCallback, useState } from "react";

import AssistantPage from "./components/AssistantPage";
import Sidebar from "./components/Sidebar";
import type { ViewId } from "./types";

const TITLES: Record<ViewId, string> = {
  documents: "Documents",
  summary: "Medical Report Summary",
  chat: "Ask Questions About Your Report",
  history: "Document History",
};

function App() {
  const [view, setView] = useState<ViewId>("documents");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const navigate = useCallback((next: ViewId) => {
    setView(next);
    setMobileOpen(false);
  }, []);

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-slate-950 text-slate-100">
      <header className="shrink-0 sticky top-0 z-30 border-b border-slate-800 bg-slate-900/80 backdrop-blur">
        <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            className="-ml-1 rounded-md p-2 text-slate-300 hover:bg-slate-800 lg:hidden"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-emerald-600 text-base font-bold text-white shadow-lg shadow-teal-900/40">
              M
            </div>
            <div className="min-w-0">
              <p className="truncate text-lg font-bold tracking-tight text-white">
                MedDoc AI
              </p>
              <p className="hidden truncate text-xs text-slate-400 sm:block">
                Your intelligent medical document assistant
              </p>
            </div>
          </div>

          <p className="ml-auto hidden text-xs text-slate-500 xl:block">
            Educational prototype — not for clinical use.
          </p>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <Sidebar
          view={view}
          collapsed={collapsed}
          mobileOpen={mobileOpen}
          onNavigate={navigate}
          onToggleCollapsed={() => setCollapsed((current) => !current)}
          onCloseMobile={() => setMobileOpen(false)}
        />

        <main className="min-w-0 flex-1 overflow-y-auto overscroll-contain px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-5xl">
            <div className="mb-6">
              <h1 className="text-xl font-bold tracking-tight text-white">
                {TITLES[view]}
              </h1>
            </div>
            <AssistantPage view={view} onNavigate={navigate} />
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;