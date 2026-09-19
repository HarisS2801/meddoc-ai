import type { DocumentItem, SummaryResponse } from "../types";
import StructuredSummaryView from "./StructuredSummaryView";

interface SummaryViewProps {
  document: DocumentItem;
  summary: SummaryResponse | undefined;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onRegenerate: () => void;
}

type Block =
  | { type: "heading"; text: string }
  | { type: "bullet"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "note"; text: string };

function parseBlocks(summary: string): Block[] {
  const blocks: Block[] = [];
  for (const rawLine of summary.replace(/\r\n/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    if (/^\*\*(.+)\*\*$/.test(line)) {
      blocks.push({ type: "heading", text: line.replace(/^\*\*|\*\*$/g, "") });
    } else if (/^[-*+]\s+/.test(line)) {
      blocks.push({ type: "bullet", text: line.replace(/^[-*+]\s+/, "") });
    } else if (/^\*\*Note/i.test(line) || /does not replace advice/i.test(line)) {
      blocks.push({ type: "note", text: line });
    } else {
      blocks.push({ type: "paragraph", text: line });
    }
  }
  return blocks;
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={index} className="font-semibold text-white">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={index}>{part}</span>
    ),
  );
}

export default function SummaryView({
  document,
  summary,
  loading,
  error,
  onRetry,
  onRegenerate,
}: SummaryViewProps) {
  const blocks = summary ? parseBlocks(summary.summary) : [];

  return (
    <section className="rounded-2xl border border-teal-600/30 bg-gradient-to-b from-slate-900/70 to-slate-900/40 p-6">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-teal-300">
            Your Medical Report Summary
          </h2>
          {summary && (
            <p className="mt-1 break-words text-xs text-slate-500">
              {document.filename}
              {summary.source_pages.length > 0 &&
                ` · pages ${summary.source_pages.map(String).join(", ")}`}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {summary && summary.document_type && (
            <span className="rounded-full border border-teal-600/40 bg-teal-600/10 px-3 py-1 text-xs font-medium text-teal-300">
              {summary.document_type}
            </span>
          )}
          {summary && summary.model_used && (
            <span className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1 text-[11px] text-slate-400">
              {summary.provider_used}
              {summary.cached ? " · served from cache" : ` · ${summary.model_used}`}
            </span>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-800/40 px-4 py-3 text-sm text-slate-300">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-teal-500/40 border-t-teal-400" />
          Analyzing the document and preparing your summary…
        </div>
      )}

      {!loading && !summary && !error && document.status === "processed" && (
        <p className="text-sm text-slate-400">
          No summary yet. Select or upload a document to analyze it.
        </p>
      )}

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          <p>{error}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 rounded-md border border-rose-700 px-3 py-1 text-xs hover:bg-rose-950/40"
          >
            Try again
          </button>
        </div>
      )}

      {!loading && !error && summary && (
        <>
          <div className="space-y-3 break-words text-sm leading-relaxed text-slate-200">
            {summary.notice && (
              <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90">
                {summary.notice}
              </p>
            )}
            {summary.structured ? (
              <StructuredSummaryView data={summary.structured} />
            ) : (
              blocks.map((block, index) => {
                if (block.type === "heading") {
                  return (
                    <h3
                      key={index}
                      className="pt-2 text-base font-semibold text-white first:pt-0"
                    >
                      {renderInline(block.text)}
                    </h3>
                  );
                }
                if (block.type === "bullet") {
                  return (
                    <ul key={index} className="list-disc space-y-1.5 pl-5">
                      <li>{renderInline(block.text)}</li>
                    </ul>
                  );
                }
                if (block.type === "note") {
                  return (
                    <p
                      key={index}
                      className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90"
                    >
                      {renderInline(block.text)}
                    </p>
                  );
                }
                return (
                  <p key={index} className="text-slate-200">
                    {renderInline(block.text)}
                  </p>
                );
              })
            )}
          </div>
          <div className="mt-4 border-t border-slate-800 pt-3">
            <button
              type="button"
              onClick={onRegenerate}
              className="rounded-md border border-teal-600/40 bg-teal-600/10 px-3 py-1.5 text-xs font-medium text-teal-300 hover:border-teal-500 hover:bg-teal-600/20"
            >
              Retry AI Analysis
            </button>
          </div>
        </>
      )}
    </section>
  );
}