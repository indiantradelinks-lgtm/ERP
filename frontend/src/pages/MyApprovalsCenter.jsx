import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Inbox, RefreshCw, CheckCircle2, XCircle, ExternalLink, ClipboardCheck, Wallet, Layers, FileText, HardHat, Receipt, Banknote, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { fmtDT, fmtD, fmtT } from "@/lib/datetime";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const SOURCES = {
  approval: { label: "Approvals", icon: ClipboardCheck, tone: "border-blue-300 text-blue-900 bg-blue-50" },
  project_request: { label: "Project Requests", icon: FileText, tone: "border-violet-300 text-violet-900 bg-violet-50" },
  service_request: { label: "Service Requests", icon: Wrench, tone: "border-indigo-300 text-indigo-900 bg-indigo-50" },
  service_direct_payment: { label: "Direct Payments", icon: Banknote, tone: "border-orange-300 text-orange-900 bg-orange-50" },
  expense: { label: "Daily Expenses", icon: Wallet, tone: "border-amber-300 text-amber-900 bg-amber-50" },
  expense_payment: { label: "Payments Due", icon: Banknote, tone: "border-emerald-300 text-emerald-900 bg-emerald-50" },
  scaffolding: { label: "Scaffolding Transfers", icon: Layers, tone: "border-cyan-300 text-cyan-900 bg-cyan-50" },
  dpr: { label: "Site Reports (DPR)", icon: HardHat, tone: "border-orange-300 text-orange-900 bg-orange-50" },
  ra_bill: { label: "RA Bills", icon: Receipt, tone: "border-rose-300 text-rose-900 bg-rose-50" },
};
const PAY_MODE_TONE = {
  UPI: "border-violet-300 text-violet-900 bg-violet-50",
  Accounts: "border-sky-300 text-sky-900 bg-sky-50",
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
  const [ff, setFf] = useState({ status: "pending", q: "", from: "", to: "", pm: "" });
  const [decided, setDecided] = useState(null);
  const setF = (k) => (e) => setFf((p) => ({ ...p, [k]: e.target?.value ?? e }));

  const load = useCallback(() => {
    api.get("/my-inbox").then((r) => setData(r.data)).catch(() => toast.error("Failed to load inbox"));
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (ff.status === "pending") { setDecided(null); return; }
    const p = new URLSearchParams({ status: ff.status });
    if (ff.q) p.set("q", ff.q);
    if (ff.from) p.set("date_from", ff.from);
    if (ff.to) p.set("date_to", ff.to);
    if (ff.pm) p.set("project_manager", ff.pm);
    api.get(`/approvals/report?${p}`).then((r) => setDecided(r.data)).catch(() => toast.error("Failed to load decided approvals"));
  }, [ff]);

  const items = useMemo(() => {
    let all = data?.items || [];
    if (filter) all = all.filter((i) => i.source === filter);
    if (ff.q) {
      const q = ff.q.toLowerCase();
      all = all.filter((i) => `${i.title} ${i.ref} ${i.created_by} ${i.subtitle}`.toLowerCase().includes(q));
    }
    if (ff.pm) {
      const pm = ff.pm.toLowerCase();
      all = all.filter((i) => `${i.title} ${i.subtitle} ${i.created_by}`.toLowerCase().includes(pm));
    }
    if (ff.from) all = all.filter((i) => fmtD(i.created_at) >= ff.from);
    if (ff.to) all = all.filter((i) => fmtD(i.created_at) <= ff.to);
    return all;
  }, [data, filter, ff]);

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

      <div className="bg-card border border-border rounded-sm p-3 grid grid-cols-2 md:grid-cols-5 gap-2">
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.status} onChange={setF("status")} data-testid="inbox-filter-status">
          <option value="pending">Pending (my action)</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <Input placeholder="Search name / ref…" className="h-9" value={ff.q} onChange={setF("q")} data-testid="inbox-filter-q" />
        <Input type="date" className="h-9" value={ff.from} onChange={setF("from")} data-testid="inbox-filter-from" />
        <Input type="date" className="h-9" value={ff.to} onChange={setF("to")} data-testid="inbox-filter-to" />
        <Input placeholder="Project Manager…" className="h-9" value={ff.pm} onChange={setF("pm")} data-testid="inbox-filter-pm" />
      </div>

      {ff.status !== "pending" ? (
        <div className="bg-card border border-border rounded-sm overflow-x-auto" data-testid="inbox-decided-table">
          <Table>
            <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead className="text-[10px] uppercase tracking-wider">Ref / Type</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Request</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Project / PM</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-right">Amount</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">{ff.status === "approved" ? "Approved By" : "Rejected By"}</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">{ff.status === "approved" ? "Approved At" : "Rejected At"}</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {!decided && <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
              {decided && decided.rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No {ff.status} items match the filters.</TableCell></TableRow>}
              {decided && decided.rows.map((r) => (
                <TableRow key={r.id} data-testid={`decided-row-${r.id}`}>
                  <TableCell>
                    <div className="font-mono-data text-xs font-bold">{r.reference || "—"}</div>
                    <div className="text-[10px] text-muted-foreground">{(r.type || "").replaceAll("_", " ")}</div>
                  </TableCell>
                  <TableCell className="max-w-[280px]"><div className="text-sm font-semibold truncate" title={r.title}>{r.title}</div><div className="text-[10px] text-muted-foreground">by {r.requested_by || "—"}</div></TableCell>
                  <TableCell>
                    <div className="text-xs font-semibold">{r.project_code || "—"}</div>
                    {r.project_manager && <div className="text-[10px] text-muted-foreground">PM: {r.project_manager}</div>}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm font-bold">{r.amount ? inr(r.amount) : "—"}</TableCell>
                  <TableCell className="text-xs">{r.decided_by || "—"}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap font-semibold" title={(r.approvers || []).map((a) => `${a.step}: ${a.by} @ ${fmtDT(a.at)}`).join("\n")}>
                    {r.decided_at ? `${fmtD(r.decided_at)} ${fmtT(r.decided_at)}` : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
      <>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-3">
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
            <TableHead className="text-[10px] uppercase tracking-wider">Pay Mode</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Waiting At</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Age</TableHead>
            <TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!data && <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
            {data && items.length === 0 && (
              <TableRow><TableCell colSpan={8} className="text-center py-14">
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
                  <TableCell>
                    {it.payment_mode ? (
                      <Badge variant="outline" className={`rounded-sm text-[10px] font-bold ${PAY_MODE_TONE[it.payment_mode] || "border-border"}`}
                        data-testid={`inbox-paymode-${it.id}`}>{it.payment_mode}</Badge>
                    ) : <span className="text-xs text-muted-foreground" data-testid={`inbox-paymode-${it.id}`}>—</span>}
                  </TableCell>
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
      </>
      )}
    </div>
  );
}
