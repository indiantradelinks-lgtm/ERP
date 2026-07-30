import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Inbox, RefreshCw, CheckCircle2, XCircle, ExternalLink, ClipboardCheck, Wallet, Layers, FileText, HardHat, Receipt, Banknote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const SOURCES = {
  approval: { label: "Approvals", icon: ClipboardCheck, tone: "border-blue-300 text-blue-900 bg-blue-50" },
  project_request: { label: "Project Requests", icon: FileText, tone: "border-violet-300 text-violet-900 bg-violet-50" },
  expense: { label: "Daily Expenses", icon: Wallet, tone: "border-amber-300 text-amber-900 bg-amber-50" },
  expense_payment: { label: "Payments Due", icon: Banknote, tone: "border-emerald-300 text-emerald-900 bg-emerald-50" },
  scaffolding: { label: "Scaffolding Transfers", icon: Layers, tone: "border-cyan-300 text-cyan-900 bg-cyan-50" },
  dpr: { label: "Site Reports (DPR)", icon: HardHat, tone: "border-orange-300 text-orange-900 bg-orange-50" },
  ra_bill: { label: "RA Bills", icon: Receipt, tone: "border-rose-300 text-rose-900 bg-rose-50" },
};
const ago = (iso) => {
  if (!iso) return "—";
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d <= 0 ? "today" : d === 1 ? "1 day" : `${d} days`;
};

export default function MyApprovalsCenter() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    api.get("/my-inbox").then((r) => setData(r.data)).catch(() => toast.error("Failed to load inbox"));
  }, []);
  useEffect(() => { load(); }, [load]);

  const items = useMemo(() => {
    const all = data?.items || [];
    return filter ? all.filter((i) => i.source === filter) : all;
  }, [data, filter]);

  const act = async (item, kind) => {
    const path = kind === "approve" ? item.approve_path : item.reject_path;
    let remarks = null;
    if (kind === "reject") { remarks = window.prompt("Rejection reason?"); if (remarks === null) return; }
    setBusy(item.id);
    try {
      await api.post(path, { remarks });
      toast.success(`${item.ref} ${kind === "approve" ? "approved" : "rejected"}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Action failed"); }
    finally { setBusy(null); }
  };

  return (
    <div className="space-y-5" data-testid="my-approvals-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Inbox className="h-3 w-3" /> Unified Action Center
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">My Pending Approvals</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Every request, expense, transfer, DPR and bill awaiting <b>your</b> action across the entire ERP — in one place.
          </p>
        </div>
        <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="inbox-reload"><RefreshCw className="h-4 w-4" /></Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <button onClick={() => setFilter("")}
          className={`text-left bg-card border rounded-sm p-3 transition-colors ${filter === "" ? "border-primary ring-1 ring-primary/30" : "border-border hover:border-primary/50"}`}
          data-testid="inbox-kpi-total">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">All Pending</div>
          <div className="text-xl font-black tabular">{data?.total ?? "—"}</div>
        </button>
        {Object.entries(SOURCES).map(([key, s]) => (
          <button key={key} onClick={() => setFilter(filter === key ? "" : key)}
            className={`text-left bg-card border rounded-sm p-3 transition-colors ${filter === key ? "border-primary ring-1 ring-primary/30" : "border-border hover:border-primary/50"}`}
            data-testid={`inbox-kpi-${key}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1"><s.icon className="h-3 w-3" /> {s.label}</div>
            <div className="text-xl font-black tabular">{data?.counts?.[key] || 0}</div>
          </button>
        ))}
      </div>

      <div className="bg-card border border-border rounded-sm">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Source</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Ref # / Raised</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Amount</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Waiting At</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Age</TableHead>
            <TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!data && <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
            {data && items.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-center py-14">
                <Inbox className="h-8 w-8 mx-auto text-muted-foreground/40" />
                <div className="mt-3 text-sm font-semibold">Inbox zero</div>
                <div className="text-xs text-muted-foreground mt-1">Nothing is waiting on your action right now.</div>
              </TableCell></TableRow>
            )}
            {items.map((it) => {
              const s = SOURCES[it.source] || { label: it.source_label, tone: "" };
              return (
                <TableRow key={`${it.source}-${it.id}`} data-testid={`inbox-row-${it.id}`}>
                  <TableCell><Badge variant="outline" className={`rounded-sm text-[10px] ${s.tone}`}>{s.label}</Badge></TableCell>
                  <TableCell>
                    <div className="font-mono-data text-xs font-bold">{it.ref || "—"}</div>
                    <div className="text-[10px] text-muted-foreground">{it.created_by || ""}</div>
                  </TableCell>
                  <TableCell>
                    <div className="font-semibold text-sm">{it.title}</div>
                    {it.subtitle && <div className="text-[11px] text-muted-foreground truncate max-w-[280px]">{it.subtitle}</div>}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm font-bold">{it.amount ? inr(it.amount) : "—"}</TableCell>
                  <TableCell className="text-xs">{it.step_label || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{ago(it.created_at)}</TableCell>
                  <TableCell className="text-right space-x-1 whitespace-nowrap">
                    {it.approve_path && (
                      <>
                        <Button size="sm" className="h-7 rounded-sm" disabled={busy === it.id} onClick={() => act(it, "approve")} data-testid={`inbox-approve-${it.id}`}>
                          <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive" disabled={busy === it.id} onClick={() => act(it, "reject")} data-testid={`inbox-reject-${it.id}`}>
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    )}
                    <Button size="sm" variant="ghost" className="h-7 rounded-sm" onClick={() => navigate(it.link)} data-testid={`inbox-open-${it.id}`}>
                      <ExternalLink className="h-3.5 w-3.5 mr-1" /> Open
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
