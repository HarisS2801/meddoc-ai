import type { DocumentItem } from "../types";
import StatusBadge from "./StatusBadge";

interface DocumentCardProps {
  document: DocumentItem | null;
  documentType: string | null;
  onSummarize: (document: DocumentItem) => void;
  onStartChat: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
}

function typeLabel(contentType: string): string {
  if (contentType === "application/pdf") return "PDF";
  if (contentType === "text/plain") return "TXT";
  return contentType;
}

export default function DocumentCard({
  document,
  documentType,
  onSummarize,
  onStartChat,
  onDelete,
}: DocumentCardProps) {
  const isProcessed = document?.status === "processed";

  return (
    <section className="flex h-full flex-col rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-teal-300">
        Current Document
      </h2>

      {!document && (
        <div className="flex flex-1 flex-col items-center justify-center py-14 text-center">
          <p className="text-sm font-medium text-slate-300">
            No document uploaded yet.
          </p>
          <p className="mt-2 max-w-sm text-sm text-slate-500">
            Upload a medical document to view its details here.
          </p>
        </div>
      )}

      {document && (
        <>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="min-w-0 break-all text-lg font-semibold text-white">
              {document.filename}
            </p>
            <StatusBadge status={document.status} />
          </div>
          {document.error_message && (
            <p className="mt-1 text-sm text-rose-400">{document.error_message}</p>
          )}

          <dl className="mt-4 space-y-3 text-sm">
            <div className="rounded-lg bg-slate-800/50 px-3 py-2">
              <dt className="text-xs text-slate-500">Report type</dt>
              <dd className="mt-0.5 break-words font-medium text-teal-300">
                {documentType || "—"}
              </dd>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                <dt className="text-xs text-slate-500">Page</dt>
                <dd className="mt-0.5 font-medium text-slate-200">
                  {document.page_count}
                </dd>
              </div>
              <div className="rounded-lg bg-slate-800/50 px-3 py-2">
                <dt className="text-xs text-slate-500">Content size</dt>
                <dd className="mt-0.5 font-medium text-slate-200">
                  {(document.extracted_text_len / 1000).toFixed(1)} KB
                </dd>
              </div>
            </div>
            <div className="rounded-lg bg-slate-800/50 px-3 py-2">
              <dt className="text-xs text-slate-500">Format</dt>
              <dd className="mt-0.5 font-medium text-slate-200">
                {typeLabel(document.content_type)}
              </dd>
            </div>
          </dl>

          <div className="mt-auto flex flex-col gap-2 border-t border-slate-800 pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
            {isProcessed && (
              <button
                type="button"
                onClick={() => onSummarize(document)}
                className="w-full rounded-lg bg-gradient-to-br from-teal-600 to-emerald-600 px-4 py-2 text-sm font-medium text-white hover:from-teal-500 hover:to-emerald-500 sm:w-auto"
              >
                Summarize Report
              </button>
            )}
            {isProcessed && (
              <button
                type="button"
                onClick={() => onStartChat(document)}
                className="w-full rounded-md border border-teal-700 px-4 py-2 text-sm text-teal-300 hover:bg-teal-950/40 sm:w-auto"
              >
                Start Chat
              </button>
            )}
            <button
              type="button"
              onClick={() => void onDelete(document)}
              className="w-full rounded-md border border-rose-700 px-4 py-2 text-sm text-rose-300 hover:bg-rose-950/40 sm:w-auto"
            >
              Delete
            </button>
          </div>
        </>
      )}
    </section>
  );
}