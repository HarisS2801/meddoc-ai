import type { DocumentItem, SummaryResponse } from "../types";
import StatusBadge from "./StatusBadge";

interface DocumentInfoProps {
  documents: DocumentItem[];
  activeDocument: DocumentItem | null;
  loading: boolean;
  documentType: string | null;
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

export default function DocumentInfo({
  documents,
  activeDocument,
  loading,
  documentType,
  summaries,
  onSelect,
  onStartChat,
  onDelete,
}: DocumentInfoProps) {
  const formatted = [...documents].sort((a, b) => b.id - a.id);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                  Uploaded document
                </h2>
                <StatusBadge status={activeDocument?.status ?? "uploading"} />
              </div>
              {activeDocument ? (
                <>
                  <p className="mt-2 break-all text-lg font-semibold text-white">
                    {activeDocument.filename}
                  </p>
                  {activeDocument.error_message && (
                    <p className="mt-1 text-sm text-rose-400">
                      {activeDocument.error_message}
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-2 text-sm text-slate-500">
                  {loading ? "Loading…" : "No document selected."}
                </p>
              )}
            </div>
            {activeDocument && (
              <div className="flex shrink-0 items-center gap-2">
                {activeDocument.status === "processed" && (
                  <button
                    type="button"
                    onClick={() => onStartChat(activeDocument)}
                    className="rounded-md border border-teal-700 px-3 py-1.5 text-xs text-teal-300 hover:bg-teal-950/40"
                  >
                    Start Chat
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void onDelete(activeDocument)}
                  className="rounded-md border border-rose-700 px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-950/40"
                >
                  Delete
                </button>
              </div>
            )}
          </div>

          {activeDocument && (
            <dl
              className={`mt-4 grid grid-cols-2 gap-3 text-sm ${
                documentType ? "sm:grid-cols-5" : "sm:grid-cols-4"
              }`}
            >
              {documentType && (
                <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                  <dt className="text-xs text-slate-500">Report type</dt>
                  <dd className="mt-0.5 font-medium text-teal-300">
                    {documentType}
                  </dd>
                </div>
              )}
              <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                <dt className="text-xs text-slate-500">Pages</dt>
                <dd className="mt-0.5 font-medium text-slate-200">
                  {activeDocument.page_count}
                </dd>
              </div>
              <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                <dt className="text-xs text-slate-500">Chunks</dt>
                <dd className="mt-0.5 font-medium text-slate-200">
                  {activeDocument.chunk_count}
                </dd>
              </div>
              <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                <dt className="text-xs text-slate-500">Content size</dt>
                <dd className="mt-0.5 font-medium text-slate-200">
                  {(activeDocument.extracted_text_len / 1000).toFixed(1)} KB
                </dd>
              </div>
              <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                <dt className="text-xs text-slate-500">Format</dt>
                <dd className="mt-0.5 font-medium text-slate-200">
                  {typeLabel(activeDocument.content_type)}
                </dd>
              </div>
            </dl>
          )}
        </div>

        {formatted.length > 0 && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
              History
            </h2>
            <p className="mb-3 text-xs text-slate-500">
              All uploaded documents. Select one to open it or start a chat.
            </p>
            <div className="space-y-3">
              {formatted.map((doc) => {
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
                            {doc.page_count > 0 && `${doc.page_count} page${doc.page_count === 1 ? "" : "s"}`}
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
          </div>
        )}
      </div>
    </section>
  );
}