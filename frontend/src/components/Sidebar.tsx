import type { ViewId } from "../types";

interface NavItem {
  id: ViewId;
  label: string;
  icon: string;
}

const PRIMARY_ITEMS: NavItem[] = [
  { id: "documents", label: "Documents", icon: "📄" },
  { id: "summary", label: "Report Summary", icon: "📊" },
  { id: "chat", label: "Ask Questions", icon: "💬" },
];

const SECONDARY_ITEMS: NavItem[] = [
  { id: "history", label: "History", icon: "🕘" },
];

interface SidebarProps {
  view: ViewId;
  collapsed: boolean;
  mobileOpen: boolean;
  onNavigate: (view: ViewId) => void;
  onToggleCollapsed: () => void;
  onCloseMobile: () => void;
}

function navButtonClass(active: boolean, collapsed: boolean, mobile: boolean) {
  const base = "flex w-full items-center gap-3 rounded-lg text-sm transition";
  const alignment = collapsed && !mobile ? "justify-center px-2" : "px-3";
  const state = active
    ? "bg-teal-600/15 font-semibold text-teal-200"
    : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-100";
  const padding = collapsed && !mobile ? "py-3" : "py-2.5";
  return `${base} ${alignment} ${state} ${padding}`;
}

function NavList({
  items,
  view,
  collapsed,
  mobile,
  onSelect,
}: {
  items: NavItem[];
  view: ViewId;
  collapsed: boolean;
  mobile: boolean;
  onSelect: (view: ViewId) => void;
}) {
  return (
    <ul className="space-y-1">
      {items.map((item) => {
        const active = view === item.id;
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onSelect(item.id)}
              title={collapsed && !mobile ? item.label : undefined}
              aria-current={active ? "page" : undefined}
              className={navButtonClass(active, collapsed, mobile)}
            >
              <span
                className="text-base"
                aria-hidden="true"
              >
                {item.icon}
              </span>
              <span
                className={`min-w-0 truncate ${collapsed && !mobile ? "hidden" : ""}`}
              >
                {item.label}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function Sidebar({
  view,
  collapsed,
  mobileOpen,
  onNavigate,
  onToggleCollapsed,
  onCloseMobile,
}: SidebarProps) {
  return (
    <>
      <aside
        className={`hidden h-full shrink-0 flex-col border-r border-slate-800 bg-slate-900/60 px-3 py-4 transition-[width] duration-200 lg:flex ${
          collapsed ? "w-16" : "w-60"
        }`}
      >
        <nav className="flex-1 space-y-5 overflow-y-auto">
          <NavList
            items={PRIMARY_ITEMS}
            view={view}
            collapsed={collapsed}
            mobile={false}
            onSelect={onNavigate}
          />
          <NavList
            items={SECONDARY_ITEMS}
            view={view}
            collapsed={collapsed}
            mobile={false}
            onSelect={onNavigate}
          />
        </nav>

        <button
          type="button"
          onClick={onToggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={`mt-4 flex w-full items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-500 hover:bg-slate-800 hover:text-slate-200 ${
            collapsed ? "justify-center px-2" : ""
          }`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`h-4 w-4 shrink-0 transition-transform ${collapsed ? "rotate-180" : ""}`}
            aria-hidden="true"
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
          <span className={`min-w-0 truncate ${collapsed ? "hidden" : ""}`}>
            Collapse sidebar
          </span>
        </button>
      </aside>

      <div
        className={`fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm transition-opacity lg:hidden ${
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onCloseMobile}
        aria-hidden="true"
      />

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-800 bg-slate-900 px-3 py-4 transition-transform duration-200 lg:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
      >
        <div className="mb-4 flex items-center justify-between gap-2 px-1">
          <p className="text-sm font-bold tracking-tight text-white">MedDoc AI</p>
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label="Close navigation"
            className="rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto">
          <NavList
            items={PRIMARY_ITEMS}
            view={view}
            collapsed={false}
            mobile
            onSelect={onNavigate}
          />
          <NavList
            items={SECONDARY_ITEMS}
            view={view}
            collapsed={false}
            mobile
            onSelect={onNavigate}
          />
        </nav>

        <p className="px-1 pt-4 text-[11px] leading-relaxed text-slate-600">
          Educational prototype — not for clinical use.
        </p>
      </aside>
    </>
  );
}