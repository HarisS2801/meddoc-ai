import { useState } from "react";

import { api } from "../lib/api";
import type { DocumentItem, MessageRole, SourceRef } from "../types";
import MarkdownContent from "./MarkdownContent";

interface ChatEntry {
  id: number;
  role: MessageRole;
  content: string;
  sources?: SourceRef[];
  reviewRecommended?: boolean;
  provider?: string;
  model?: string;
}

interface ChatSectionProps {
  document: DocumentItem;
}

export default function ChatSection({ document }: ChatSectionProps) {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSend = async () => {
    const text = question.trim();
    if (!text || sending) return;

    setEntries((current) => [
      ...current,
      { id: Date.now(), role: "user", content: text },
    ]);
    setQuestion("");
    setSending(true);
    setError(null);

    try {
      const response = await api.ask(text, conversationId, [document.id]);
      setConversationId(response.conversation_id);
      setEntries((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          reviewRecommended: response.review_recommended,
          provider: response.provider_used,
          model: response.model_used,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Question failed.");
      setEntries((current) => current.slice(0, -1));
    } finally {
      setSending(false);
    }
  };

  const onNewConversation = () => {
    setConversationId(null);
    setEntries([]);
    setError(null);
  };

  const onClearWorkspace = async () => {
    if (sending) return;
    const confirmed = window.confirm(
      "Clear this chat workspace?\n\nThis will remove the current conversation and forget the active document context for this chat. Your uploaded files will remain available in History.",
    );
    if (!confirmed) return;

    const previousId = conversationId;
    setConversationId(null);
    setEntries([]);
    setQuestion("");
    setError(null);

    if (previousId !== null) {
      try {
        await api.clearConversation(previousId);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "The workspace could not be cleared on the server.",
        );
      }
    }
  };

  const hasWorkspaceState = conversationId !== null || entries.length > 0;

  return (
    <section id="chat-section" className="rounded-2xl border border-slate-800 bg-slate-900/50">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-6 py-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Ask Questions About Your Report
          </h2>
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-slate-500">
            <span>Questions are answered from</span>
            <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-teal-600/40 bg-teal-600/10 px-2.5 py-0.5 font-medium text-teal-300">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-teal-400" />
              <span className="truncate">{document.filename}</span>
            </span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {entries.length > 0 && (
            <button
              type="button"
              onClick={onNewConversation}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              New conversation
            </button>
          )}
          <button
            type="button"
            disabled={!hasWorkspaceState}
            onClick={() => void onClearWorkspace()}
            className="rounded-md border border-rose-700 px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear Workspace
          </button>
        </div>
      </div>

      <div className="flex max-h-[28rem] min-h-40 flex-col overflow-y-auto p-6">
        {entries.length === 0 && (
          <div className="m-auto max-w-md text-center text-sm text-slate-500">
            <p className="font-medium text-slate-300">
              Your chat workspace is empty.
            </p>
            <p className="mt-1">
              Upload or select a medical report to start a new conversation.
              Answers are grounded in{" "}
              <span className="text-slate-300">{document.filename}</span> and
              include source references.
            </p>
          </div>
        )}
        {entries.map((entry) => (
          <div
            key={entry.id}
            className={`flex ${entry.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`mb-3 max-w-[85%] min-w-0 break-words rounded-xl border px-4 py-3 text-sm ${
                entry.role === "user"
                  ? "border-teal-700/50 bg-teal-950/40 text-teal-100"
                  : "border-slate-700 bg-slate-800/60 text-slate-200"
              }`}
            >
              {entry.role === "user" ? (
                <div className="whitespace-pre-wrap break-words">{entry.content}</div>
              ) : (
                <MarkdownContent content={entry.content} />
              )}
              {entry.reviewRecommended && (
                <span className="mt-3 inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-xs text-amber-300">
                  Reviewed by a human before use
                </span>
              )}
              {entry.provider && entry.model && (
                <span className="mt-3 inline-flex items-center rounded-full border border-teal-600/40 bg-teal-600/10 px-2.5 py-0.5 text-xs text-teal-300">
                  {entry.provider} · {entry.model}
                </span>
              )}
              {entry.sources && entry.sources.length > 0 && (
                <SourceList sources={entry.sources} />
              )}
            </div>
          </div>
        ))}
        {sending && (
          <p className="flex items-center gap-2 text-sm text-slate-400">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-teal-500/40 border-t-teal-400" />
            Thinking…
          </p>
        )}
      </div>

      {error && (
        <p className="border-t border-slate-800 bg-rose-500/10 px-6 py-2.5 text-sm text-rose-300">
          {error}
        </p>
      )}

      <div className="border-t border-slate-800 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void onSend();
            }}
            placeholder="Ask anything about your medical report..."
            className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-teal-600 focus:outline-none"
          />
          <button
            type="button"
            disabled={sending || question.trim() === ""}
            onClick={() => void onSend()}
            className="rounded-lg bg-gradient-to-br from-teal-600 to-emerald-600 px-5 py-2.5 text-sm font-medium text-white hover:from-teal-500 hover:to-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Ask
          </button>
        </div>
      </div>
    </section>
  );
}

function SourceList({ sources }: { sources: SourceRef[] }) {
  const seen = new Set<string>();
  const unique = sources.filter((source) => {
    const key = `${source.filename}::${source.page_number ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <div className="mt-3 space-y-1 border-t border-slate-700 pt-2.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Sources
      </div>
      {unique.map((source, index) => (
        <p key={index} className="min-w-0 break-words text-xs leading-5 text-slate-500">
          <span className="font-medium text-slate-400">{source.filename}</span>
          {source.page_number != null && (
            <span> · page {source.page_number}</span>
          )}
        </p>
      ))}
    </div>
  );
}