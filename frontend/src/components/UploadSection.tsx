import { useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

export type UploadState =
  | "idle"
  | "uploading"
  | "processing"
  | "success"
  | "error";

interface UploadSectionProps {
  state: UploadState;
  error: string | null;
  lastFilename: string | null;
  disabled: boolean;
  onUploadFile: (file: File) => void;
}

export default function UploadSection({
  state,
  error,
  lastFilename,
  disabled,
  onUploadFile,
}: UploadSectionProps) {
  const [dragging, setDragging] = useState(false);
  const busy = state === "uploading" || state === "processing";

  const onPickFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) onUploadFile(file);
    event.target.value = "";
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    const file = event.dataTransfer.files?.[0];
    if (file) onUploadFile(file);
  };

  return (
    <section className="rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900/70 to-slate-900/40 p-6 sm:p-8">
      <div className="text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-teal-400">
          MedDoc AI
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">
          Understand your medical reports
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-slate-400">
          Upload a cardiology report, blood test, lab results, prescription,
          radiology report, or any other medical document. MedDoc AI reads the
          whole document and turns it into a clear, plain-language summary —
          then you can ask questions about it.
        </p>
      </div>

      <label
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-6 flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
          dragging
            ? "border-teal-400 bg-teal-500/10"
            : disabled
              ? "cursor-not-allowed border-slate-700/60 bg-slate-900/40 opacity-60"
              : "border-slate-700 bg-slate-900/40 hover:border-teal-500/60 hover:bg-slate-900/60"
        }`}
      >
        <input
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          disabled={disabled}
          onChange={onPickFile}
          className="hidden"
        />

        <div
          className={`flex h-12 w-12 items-center justify-center rounded-full border ${
            busy
              ? "border-teal-500/50 bg-teal-500/10"
              : "border-slate-600 bg-slate-800/60"
          }`}
        >
          {busy ? (
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-teal-500/40 border-t-teal-400" />
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-6 w-6 text-teal-400"
              aria-hidden="true"
            >
              <path d="M12 16V4m0 0 4 4m-4-4-4 4" />
              <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
            </svg>
          )}
        </div>

        {busy ? (
          <>
            <span className="text-sm font-medium text-slate-200">
              {state === "uploading" ? "Uploading document…" : "Analyzing document…"}
            </span>
            <span className="text-xs text-slate-500">
              Please keep this tab open. Processing can take a few seconds.
            </span>
          </>
        ) : (
          <>
            <span className="text-sm text-slate-300">
              Drag &amp; drop your medical report here, or
            </span>
            <span
              className={`rounded-lg bg-gradient-to-br from-teal-600 to-emerald-600 px-5 py-2.5 text-sm font-medium text-white ${
                disabled ? "opacity-50" : "shadow-lg shadow-teal-900/40 hover:from-teal-500 hover:to-emerald-500"
              }`}
            >
              Choose a document
            </span>
            <span className="text-xs text-slate-500">
              PDF or .txt · up to 10 MB · processed and indexed automatically
            </span>
          </>
        )}
      </label>

      {state === "processing" && (
        <p className="mt-4 rounded-lg border border-teal-500/30 bg-teal-500/10 px-3 py-2 text-sm text-teal-300">
          Your document is being processed. Once finished, the summary and chat
          will appear below.
        </p>
      )}

      {state === "success" && lastFilename && (
        <p className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          <span className="break-all font-medium">{lastFilename}</span> processed
          successfully — your summary and chat are ready below.
        </p>
      )}

      {state === "error" && (
        <p className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {error ?? "The upload could not be completed."}
        </p>
      )}
    </section>
  );
}