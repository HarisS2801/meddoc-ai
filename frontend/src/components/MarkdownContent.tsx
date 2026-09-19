import type { ReactNode } from "react";

/*
 * A small, dependency-free Markdown renderer used to display AI chat
 * answers. It understands the markdown our assistant actually produces
 * (paragraphs, headings, lists, tables, emphasis, code, quotes) and renders
 * it with the existing Tailwind design system. The rendered text is exactly
 * the text the backend sent - nothing is invented, edited, or dropped.
 */

type Align = "left" | "center" | "right";

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; headers: string[]; rows: string[][]; align: Align[] }
  | { kind: "blockquote"; text: string }
  | { kind: "code"; code: string };

const INLINE_PATTERN = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;

const STATUS_STYLES: Record<string, string> = {
  high: "border-rose-500/50 bg-rose-500/15 text-rose-300",
  low: "border-amber-500/50 bg-amber-500/15 text-amber-300",
  normal: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
  abnormal: "border-orange-500/50 bg-orange-500/15 text-orange-300",
  moderate: "border-amber-500/50 bg-amber-500/15 text-amber-300",
  "not available": "border-slate-500/60 bg-slate-500/15 text-slate-300",
};

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isSeparatorRow(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes("-")) return false;
  return /^\|?[\s:|-]+$/.test(trimmed);
}

function isTableStart(lines: string[], index: number): boolean {
  if (index + 1 >= lines.length) return false;
  return lines[index].trim().includes("|") && isSeparatorRow(lines[index + 1]);
}

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();

    if (!line) {
      i += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push({ kind: "code", code: codeLines.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      i += 1;
      continue;
    }

    if (isTableStart(lines, i)) {
      const headers = splitRow(lines[i]);
      const sepCells = splitRow(lines[i + 1]);
      const align: Align[] = headers.map((_, col) => {
        const cell = sepCells[col] ?? "";
        if (cell.startsWith(":") && cell.endsWith(":")) return "center";
        if (cell.endsWith(":")) return "right";
        return "left";
      });
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().includes("|")) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ kind: "table", headers, rows, align });
      continue;
    }

    const unordered = line.match(/^[-*+]\s+(.*)$/);
    const ordered = line.match(/^\d+[.)]\s+(.*)$/);
    if (unordered || ordered) {
      const isOrdered = Boolean(ordered);
      const items: string[] = [];
      while (i < lines.length) {
        const l = lines[i].trim();
        const item = isOrdered ? l.match(/^\d+[.)]\s+(.*)$/) : l.match(/^[-*+]\s+(.*)$/);
        if (!item) break;
        items.push(item[1]);
        i += 1;
      }
      blocks.push({ kind: "list", ordered: isOrdered, items });
      continue;
    }

    if (line.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "blockquote", text: quoteLines.join(" ") });
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length) {
      const l = lines[i].trim();
      if (!l || /^#{1,6}\s+/.test(l) || l.startsWith("```") || l.startsWith(">")) break;
      if (/^[-*+]\s+/.test(l) || /^\d+[.)]\s+/.test(l)) break;
      if (isTableStart(lines, i)) break;
      paragraph.push(l);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function renderInline(text: string): ReactNode[] {
  return text.split(INLINE_PATTERN).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded bg-slate-800 px-1.5 py-0.5 text-[0.9em] text-teal-200"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={index} className="italic">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function statusClass(value: string): string | null {
  return STATUS_STYLES[value.trim().toLowerCase()] ?? null;
}

function isNumericish(cell: string): boolean {
  const value = cell.trim();
  if (!value || value.length > 30) return false;
  return /^[-+≥≤<>]?\s*[\d.,]+\s*[a-z%./\u2013-]*$/i.test(value);
}

function columnAlign(headers: string[], rows: string[][], col: number): Align {
  const header = (headers[col] ?? "").toLocaleLowerCase();
  if (/result|value|reading|level|amount|count|score/.test(header)) return "right";
  const cells = rows.map((row) => row[col] ?? "").filter((cell) => cell.trim() !== "");
  if (cells.length === 0) return "left";
  const numeric = cells.filter(isNumericish).length;
  return numeric / cells.length >= 0.6 ? "right" : "left";
}

function TableBlock({ block }: { block: Extract<Block, { kind: "table" }> }) {
  const align = block.align.map((a, col) =>
    a !== "left" ? a : columnAlign(block.headers, block.rows, col),
  );

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-700">
      <table className="w-full min-w-max border-collapse text-left text-xs sm:text-sm">
        <thead>
          <tr className="bg-slate-700/50">
            {block.headers.map((header, col) => (
              <th
                key={col}
                className={`border-b border-slate-600 px-3 py-2 font-semibold text-slate-100 ${
                  align[col] === "right" ? "text-right" : align[col] === "center" ? "text-center" : ""
                }`}
              >
                {renderInline(header)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="border-b border-slate-800 last:border-0 odd:bg-slate-800/20"
            >
              {row.map((cell, col) => {
                const status = statusClass(cell);
                const justify =
                  align[col] === "right"
                    ? "text-right"
                    : align[col] === "center"
                      ? "text-center"
                      : "";
                return (
                  <td
                    key={col}
                    className={`whitespace-normal px-3 py-2 align-top ${justify}`}
                  >
                    {status ? (
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${status}`}
                      >
                        {cell.trim()}
                      </span>
                    ) : (
                      renderInline(cell)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "heading": {
      const size =
        block.level === 1
          ? "text-lg"
          : block.level === 2
            ? "text-base"
            : "text-sm font-semibold";
      return (
        <h3 className={`${size} pt-1 text-white first:pt-0`}>
          {renderInline(block.text)}
        </h3>
      );
    }
    case "paragraph":
      return <p className="text-slate-200">{renderInline(block.text)}</p>;
    case "list":
      return block.ordered ? (
        <ol className="space-y-1.5 pl-5 list-decimal">
          {block.items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>
      ) : (
        <ul className="space-y-1.5 pl-5 list-disc">
          {block.items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>
      );
    case "table":
      return <TableBlock block={block} />;
    case "blockquote":
      return (
        <blockquote className="rounded-r-lg border-l-4 border-teal-500/40 bg-slate-800/40 py-2 pl-3 pr-3 text-slate-300">
          {renderInline(block.text)}
        </blockquote>
      );
    case "code":
      return (
        <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs leading-relaxed text-teal-100">
          <code>{block.code}</code>
        </pre>
      );
  }
}

export default function MarkdownContent({ content }: MarkdownContentProps) {
  const blocks = parseBlocks(content);
  if (blocks.length === 0) return null;

  return (
    <div className="space-y-3 leading-relaxed">
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </div>
  );
}

interface MarkdownContentProps {
  content: string;
}