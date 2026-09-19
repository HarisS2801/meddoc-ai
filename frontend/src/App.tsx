import AssistantPage from "./components/AssistantPage";

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-emerald-600 text-lg font-bold text-white shadow-lg shadow-teal-900/40">
              M
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">
                MedDoc AI
              </h1>
              <p className="text-xs text-slate-400">
                Your intelligent medical document assistant
              </p>
            </div>
          </div>
          <p className="ml-auto hidden text-xs text-slate-500 md:block">
            Educational prototype — not for clinical use.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <AssistantPage />
      </main>
    </div>
  );
}

export default App;