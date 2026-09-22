import { useMemo, useState } from "react";

import type { DocumentItem, SummaryResponse } from "../types";
import StatusBadge from "./StatusBadge";

interface DocumentHistoryProps {
  documents: DocumentItem[];
  activeDocument: DocumentItem | null;
  loading: boolean;
  summaries: Record<number, SummaryResponse>;
  onSelect: (document: DocumentItem) => void;
  onStartChat: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
}

function typeLabel(contentType: string): string {
  if (contentType === "application/pdf") return "PDF";
  if (contentType === "text/plain") return "TXT";
  return contentType;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function DocumentHistory({
  documents,
  activeDocument,
  loading,
  summaries,
  onSelect,
  onStartChat,
  onDelete,
}: DocumentHistoryProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const sorted = [...documents].sort((a, b) => b.id - a.id);
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return sorted;
    return sorted.filter((doc) => doc.filename.toLowerCase().includes(trimmed));
  }, [documents, query]);

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            History
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            All uploaded documents. Select one to open it or start a chat.
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-0.5 text-[11px] text-slate-400">
          {filtered.length} of {documents.length}
        </span>
      </div>

      <div className="relative mt-4">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search documents by name…"
          aria-label="Search documents"
          className="w-full rounded-lg border border-slate-700 bg-slate-950/60 py-2.5 pl-10 pr-4 text-sm text-slate-100 placeholder:text-slate-500 focus:border-teal-600 focus:outline-none"
        />
      </div>

      <div className="mt-4 space-y-3">
        {loading && documents.length === 0 && (
          <p className="text-sm text-slate-500">Loading documents…</p>
        )}

        {!loading && documents.length === 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
            No documents uploaded yet. Upload a medical document to get started.
          </div>
        )}

        {!loading && documents.length > 0 && filtered.length === 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
            No documents matched “{query.trim()}”.
          </div>
        )}

        {filtered.map((doc) => {
          const isActive = activeDocument?.id === doc.id;
          const isProcessed = doc.status === "processed";
          const hasSummary = Boolean(summaries[doc.id]);
          return (
            <div
              key={doc.id}
              className={`rounded-xl border p-3 ${
                isActive
                  ? "border-teal-600/50 bg-teal-600/10"
                  : "border-slate-800 bg-slate-900/40"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="break-all text-sm font-medium text-slate-200">
                    {doc.filename}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-slate-500">
                    <span>{typeLabel(doc.content_type)}</span>
                    {formatDate(doc.created_at) && (
                      <span>· {formatDate(doc.created_at)}</span>
                    )}
                    <span>·</span>
                    <StatusBadge status={doc.status} />
                  </p>
                  {doc.status === "processed" && (
                    <p className="mt-1 text-xs text-slate-500">
                      {doc.page_count > 0 &&
                        `${doc.page_count} page${doc.page_count === 1 ? "" : "s"}`}
                      {doc.chunk_count > 0 &&
                        ` · ${doc.chunk_count} chunk${doc.chunk_count === 1 ? "" : "s"}`}
                      {hasSummary && " · Summary ready"}
                    </p>
                  )}
                  {doc.error_message && (
                    <p className="mt-1 break-words text-xs text-rose-400">
                      {doc.error_message}
                    </p>
                  )}
                </div>
                {isActive && (
                  <span className="shrink-0 rounded-full border border-teal-600/40 bg-teal-600/10 px-2 py-0.5 text-[11px] font-medium text-teal-300">
                    Active
                  </span>
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {isProcessed ? (
                  <>
                    <button
                      type="button"
                      onClick={() => onSelect(doc)}
                      className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      Open
                    </button>
                    <button
                      type="button"
                      onClick={() => onStartChat(doc)}
                      className="rounded-md border border-teal-700 px-2.5 py-1 text-xs text-teal-300 hover:bg-teal-950/40"
                    >
                      Start Chat
                    </button>
                  </>
                ) : (
                  <span className="text-xs text-slate-600">
                    Chat unavailable until processed
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => void onDelete(doc)}
                  className="ml-auto rounded-md border border-rose-700 px-2.5 py-1 text-xs text-rose-300 hover:bg-rose-950/40"
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}