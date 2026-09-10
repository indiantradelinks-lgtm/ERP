import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Command as CommandPrimitive } from "cmdk";
import { Search, CornerDownLeft, ArrowRight, Loader2, Clock, FileText, Compass } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { MENU_ITEMS, DEPARTMENT_MAP, isItemVisible } from "@/config/menuConfig";
import { cn } from "@/lib/utils";

const RECENT_KEY = "erp.search.recent.v1";
const readRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } };
const pushRecent = (entry) => {
  const list = [entry, ...readRecent().filter((r) => r.route !== entry.route)].slice(0, 8);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* ignore */ }
};

function Highlight({ text, term }) {
  if (!term || !text) return <>{text}</>;
  const idx = String(text).toLowerCase().indexOf(term.toLowerCase());
  if (idx < 0) return <>{text}</>;
  const s = String(text);
  return (
    <>
      {s.slice(0, idx)}<mark className="bg-primary/25 text-foreground rounded-[2px] px-0.5">{s.slice(idx, idx + term.length)}</mark>{s.slice(idx + term.length)}
    </>
  );
}

function ResultItem({ value, icon: Icon, title, subtitle, badge, term, onSelect, testid }) {
  return (
    <CommandPrimitive.Item
      value={value}
      onSelect={onSelect}
      data-testid={testid}
      className="group flex items-center gap-3 px-3 py-2.5 rounded-sm cursor-pointer text-sm aria-selected:bg-primary/10 aria-selected:text-foreground text-foreground/90 transition-colors"
    >
      <span className="h-8 w-8 shrink-0 grid place-items-center rounded-sm bg-muted text-muted-foreground group-aria-selected:bg-primary group-aria-selected:text-primary-foreground transition-colors">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium"><Highlight text={title} term={term} /></span>
        {subtitle && <span className="block truncate text-xs text-muted-foreground"><Highlight text={subtitle} term={term} /></span>}
      </span>
      {badge && <span className="shrink-0 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-muted text-muted-foreground">{badge}</span>}
      <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-0 group-aria-selected:opacity-70 transition-opacity" />
    </CommandPrimitive.Item>
  );
}

export default function CommandPalette({ open, onOpenChange }) {
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const [term, setTerm] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  useEffect(() => { if (!open) { setTerm(""); setData(null); } }, [open]);

  useEffect(() => {
    const q = term.trim();
    if (q.length < 2) { setData(null); setLoading(false); return undefined; }
    setLoading(true);
    const id = ++reqId.current;
    const t = setTimeout(async () => {
      try {
        const r = await api.get("/search", { params: { q, limit: 5 } });
        if (id === reqId.current) setData(r.data);
      } catch { if (id === reqId.current) setData({ groups: [], total: 0 }); }
      finally { if (id === reqId.current) setLoading(false); }
    }, 180);
    return () => clearTimeout(t);
  }, [term]);

  const pages = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (q.length < 2) return [];
    const seen = new Set();
    return MENU_ITEMS.filter((it) => {
      if (!it.to || it.comingSoon || !isItemVisible(it, { role: user?.role, can })) return false;
      const dept = DEPARTMENT_MAP[it.department]?.label || "";
      const hay = `${it.label} ${it.parentLabel || ""} ${dept} ${it.to}`.toLowerCase();
      if (!hay.includes(q) || seen.has(it.to + it.label)) return false;
      seen.add(it.to + it.label);
      return true;
    }).slice(0, 6);
  }, [term, user, can]);

  const go = useCallback((entry) => {
    pushRecent(entry);
    onOpenChange(false);
    navigate(entry.route);
  }, [navigate, onOpenChange]);

  const recent = open && term.trim().length < 2 ? readRecent() : [];
  const groups = data?.groups || [];
  const hasResults = pages.length > 0 || groups.length > 0;
  const showEmpty = term.trim().length >= 2 && !loading && !hasResults;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 gap-0 overflow-hidden max-w-2xl top-[12%] translate-y-0 rounded-sm border-border shadow-2xl [&>button:last-child]:hidden" data-testid="command-palette">
        <DialogTitle className="sr-only">Universal search</DialogTitle>
        <CommandPrimitive shouldFilter={false} loop className="flex flex-col">
          <div className="flex items-center gap-2 px-4 border-b border-border">
            {loading ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" /> : <Search className="h-4 w-4 shrink-0 text-muted-foreground" />}
            <CommandPrimitive.Input
              autoFocus
              value={term}
              onValueChange={setTerm}
              placeholder="Search projects, clients, POs, employees, invoices, pages…"
              className="h-14 w-full bg-transparent text-base outline-none placeholder:text-muted-foreground"
              data-testid="command-palette-input"
            />
            <kbd className="hidden sm:inline-flex h-6 items-center rounded-sm border border-border px-1.5 text-[10px] font-mono text-muted-foreground">ESC</kbd>
          </div>

          <CommandPrimitive.List className="max-h-[60vh] overflow-y-auto p-2 scroll-py-2" data-testid="command-palette-results">
            {term.trim().length < 2 && (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground" data-testid="command-palette-hint">
                Type at least 2 characters to search across every module.
              </div>
            )}
            {recent.length > 0 && (
              <CommandPrimitive.Group heading="Recent" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.15em] [&_[cmdk-group-heading]]:text-muted-foreground">
                {recent.map((r) => (
                  <ResultItem key={r.route} value={`recent:${r.route}`} icon={Clock} title={r.title} subtitle={r.subtitle} badge={r.badge} onSelect={() => go(r)} testid="command-palette-recent-item" />
                ))}
              </CommandPrimitive.Group>
            )}
            {showEmpty && (
              <div className="px-3 py-10 text-center text-sm text-muted-foreground" data-testid="command-palette-empty">
                No matches for <span className="font-semibold text-foreground">“{term.trim()}”</span> in modules you can access.
              </div>
            )}
            {pages.length > 0 && (
              <CommandPrimitive.Group heading="Pages" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.15em] [&_[cmdk-group-heading]]:text-muted-foreground">
                {pages.map((p) => {
                  const dept = DEPARTMENT_MAP[p.department]?.label || "";
                  const entry = { route: p.to, title: p.label, subtitle: `${dept}${p.parentLabel ? " › " + p.parentLabel : ""}`, badge: "Page" };
                  return <ResultItem key={p.to + p.label} value={`page:${p.to}:${p.label}`} icon={p.icon || Compass} title={p.label} subtitle={entry.subtitle} badge="Page" term={term.trim()} onSelect={() => go(entry)} testid="command-palette-page-item" />;
                })}
              </CommandPrimitive.Group>
            )}
            {groups.map((g) => (
              <CommandPrimitive.Group
                key={g.key}
                heading={`${g.module} › ${g.label}`}
                className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.15em] [&_[cmdk-group-heading]]:text-muted-foreground"
                data-testid={`command-palette-group-${g.key}`}
              >
                {g.items.map((it) => {
                  const entry = { route: it.route, title: it.title, subtitle: it.subtitle, badge: g.label };
                  return <ResultItem key={`${g.key}:${it.id}`} value={`${g.key}:${it.id}`} icon={FileText} title={it.title} subtitle={it.subtitle} badge={it.status || undefined} term={term.trim()} onSelect={() => go(entry)} testid={`command-palette-item-${g.key}`} />;
                })}
                <ResultItem value={`all:${g.key}`} icon={Search} title={`Search “${term.trim()}” in ${g.label}`} subtitle={`Open ${g.label} filtered by this term`} onSelect={() => go({ route: `${g.route}?q=${encodeURIComponent(term.trim())}`, title: `${g.label}: ${term.trim()}`, subtitle: g.module, badge: "Filter" })} testid={`command-palette-viewall-${g.key}`} />
              </CommandPrimitive.Group>
            ))}
          </CommandPrimitive.List>

          <div className="flex items-center gap-4 px-4 py-2 border-t border-border bg-muted/40 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1"><kbd className="rounded-sm border border-border px-1 font-mono">↑↓</kbd> navigate</span>
            <span className="inline-flex items-center gap-1"><CornerDownLeft className="h-3 w-3" /> open</span>
            <span className={cn("ml-auto", data && "tabular-nums")} data-testid="command-palette-stats">
              {data ? `${data.total} record${data.total === 1 ? "" : "s"} · ${pages.length} page${pages.length === 1 ? "" : "s"} · ${data.took_ms}ms` : "Ctrl / ⌘ + K"}
            </span>
          </div>
        </CommandPrimitive>
      </DialogContent>
    </Dialog>
  );
}
