import type { DocumentStatus } from "../types";

const STYLES: Record<DocumentStatus, string> = {
  uploading: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  processing: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  processed: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  failed: "bg-rose-500/10 text-rose-300 border-rose-500/30",
};

export default function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}