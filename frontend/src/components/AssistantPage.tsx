import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import type { DocumentItem, SummaryResponse, ViewId } from "../types";
import ChatSection from "./ChatSection";
import DocumentCard from "./DocumentCard";
import DocumentHistory from "./DocumentHistory";
import SummaryView from "./SummaryView";
import UploadSection, { type UploadState } from "./UploadSection";

interface AssistantPageProps {
  view: ViewId;
  onNavigate: (view: ViewId) => void;
}

function EmptyState({
  title,
  text,
  actionLabel,
  onAction,
}: {
  title: string;
  text: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-sm text-slate-400">
      <p className="font-medium text-slate-300">{title}</p>
      <p className="mt-1">{text}</p>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 rounded-md border border-teal-700 px-3 py-1.5 text-xs text-teal-300 hover:bg-teal-950/40"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}

export default function AssistantPage({ view, onNavigate }: AssistantPageProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [activeDocument, setActiveDocument] = useState<DocumentItem | null>(null);
  const [summaries, setSummaries] = useState<Record<number, SummaryResponse>>({});
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const fetchSummary = useCallback(
    async (document: DocumentItem, force: boolean = false) => {
      setSummaryLoading(true);
      setSummaryError(null);
      try {
        const summary = await api.summarize(document.id, force);
        setSummaries((current) => ({ ...current, [document.id]: summary }));
      } catch (err) {
        setSummaryError(
          err instanceof Error
            ? err.message
            : "The AI summary could not be generated.",
        );
      } finally {
        setSummaryLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const docs = await api.listDocuments();
        if (cancelled) return;
        setDocuments(docs);
        const processed = docs
          .filter((doc) => doc.status === "processed")
          .sort((a, b) => b.id - a.id);
        if (processed.length > 0) {
          setActiveDocument(processed[0]);
          await fetchSummary(processed[0]);
        }
        setPageError(null);
      } catch (err) {
        if (!cancelled) {
          setPageError(err instanceof Error ? err.message : "Failed to load documents.");
        }
      } finally {
        if (!cancelled) setLoadingDocuments(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [fetchSummary]);

  const waitForProcessed = async (
    document: DocumentItem,
  ): Promise<DocumentItem> => {
    let current = document;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      if (current.status === "processed" || current.status === "failed") {
        return current;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
      current = await api.getDocument(document.id);
    }
    return current;
  };

  const onUploadFile = async (file: File) => {
    setUploadError(null);
    setPageError(null);
    setSummaryError(null);
    setLastUpload(file.name);
    setUploadState("uploading");
    try {
      const uploaded = await api.uploadDocument(file);
      setUploadState("processing");
      const processed = await waitForProcessed(uploaded);
      setUploadState("success");

      const docs = await api.listDocuments();
      setDocuments(docs);
      setActiveDocument(processed);
      await fetchSummary(processed);
    } catch (err) {
      setUploadState("error");
      setUploadError(
        err instanceof Error ? err.message : "Document upload failed.",
      );
    }
  };

  const onSelectDocument = (document: DocumentItem) => {
    setActiveDocument(document);
    setSummaryError(null);
    onNavigate("documents");
    if (!summaries[document.id]) {
      void fetchSummary(document);
    }
  };

  const onRetrySummary = () => {
    if (activeDocument && !summaries[activeDocument.id]) {
      void fetchSummary(activeDocument);
    }
  };

  const onRegenerateSummary = () => {
    if (activeDocument) {
      void fetchSummary(activeDocument, true);
    }
  };

  const onDelete = async (document: DocumentItem) => {
    if (!window.confirm(`Delete "${document.filename}"? This cannot be undone.`)) {
      return;
    }
    setPageError(null);
    try {
      await api.deleteDocument(document.id);
      const docs = await api.listDocuments();
      setDocuments(docs);
      setSummaries((current) => {
        const next = { ...current };
        delete next[document.id];
        return next;
      });
      const processed = docs
        .filter((doc) => doc.status === "processed")
        .sort((a, b) => b.id - a.id);
      if (activeDocument?.id === document.id) {
        setActiveDocument(processed[0] ?? null);
        if (processed[0] && !summaries[processed[0].id]) {
          void fetchSummary(processed[0]);
        }
      }
    } catch (err) {
      setPageError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  const onStartChat = (selected: DocumentItem) => {
    setActiveDocument(selected);
    setSummaryError(null);
    onNavigate("chat");
    if (!summaries[selected.id]) {
      void fetchSummary(selected);
    }
  };

  const onSummarizeDocument = (document: DocumentItem) => {
    setActiveDocument(document);
    setSummaryError(null);
    onNavigate("summary");
    if (!summaries[document.id]) {
      void fetchSummary(document);
    }
  };

  const chatEnabled = activeDocument?.status === "processed";
  const activeSummary = activeDocument ? summaries[activeDocument.id] : undefined;
  const uploadBusy = uploadState === "uploading" || uploadState === "processing";

  return (
    <div className="space-y-6">
      {pageError && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {pageError}
        </div>
      )}

      {view === "documents" && (
        <div className="grid items-stretch gap-6 lg:grid-cols-2">
          <UploadSection
            state={uploadState}
            error={uploadError}
            lastFilename={lastUpload}
            disabled={uploadBusy}
            onUploadFile={(file) => void onUploadFile(file)}
          />
          {!loadingDocuments && documents.length === 0 && (
            <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center text-sm text-slate-400">
              Upload a medical document to get an AI summary and the chance to
              ask questions about it.
            </div>
          )}
          <DocumentCard
            document={activeDocument}
            documentType={activeSummary?.document_type ?? null}
            onSummarize={onSummarizeDocument}
            onStartChat={onStartChat}
            onDelete={onDelete}
          />
        </div>
      )}

      {view === "summary" &&
        (activeDocument ? (
          <SummaryView
            document={activeDocument}
            summary={activeSummary}
            loading={summaryLoading}
            error={summaryError}
            onRetry={onRetrySummary}
            onRegenerate={onRegenerateSummary}
          />
        ) : (
          <EmptyState
            title="No summary yet"
            text="Upload a medical document to generate its AI summary."
            actionLabel="Go to documents"
            onAction={() => onNavigate("documents")}
          />
        ))}

      {view === "history" && (
        <DocumentHistory
          documents={documents}
          activeDocument={activeDocument}
          loading={loadingDocuments}
          summaries={summaries}
          onSelect={onSelectDocument}
          onStartChat={onStartChat}
          onDelete={onDelete}
        />
      )}

      {activeDocument && chatEnabled && (
        <div className={view === "chat" ? undefined : "hidden"} aria-hidden={view !== "chat"}>
          <ChatSection key={activeDocument.id} document={activeDocument} />
        </div>
      )}

      {view === "chat" && activeDocument && !chatEnabled && (
        <EmptyState
          title="Chat is not ready yet"
          text={`"${activeDocument.filename}" has not finished processing. Chat becomes available once the document is indexed.`}
          actionLabel="View document status"
          onAction={() => onNavigate("documents")}
        />
      )}

      {view === "chat" && !activeDocument && (
        <EmptyState
          title="No document to chat about"
          text="Select or upload a medical report first, then ask questions grounded in its content."
          actionLabel="Go to documents"
          onAction={() => onNavigate("documents")}
        />
      )}
    </div>
  );
}