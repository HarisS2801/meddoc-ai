function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center gap-6 p-8">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold tracking-tight text-white">
          MedDoc AI
        </h1>
        <p className="text-lg text-slate-400">
          AI Healthcare Document Assistant
        </p>
        <p className="text-sm text-slate-500 max-w-md mx-auto">
          Educational prototype — not for clinical use. Do not upload real
          patient data.
        </p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center">
        <p className="text-sm text-slate-300 font-mono">Phase 1 ✓ Backend connected</p>
      </div>
    </div>
  );
}

export default App;