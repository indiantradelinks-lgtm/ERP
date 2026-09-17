import { useCallback, useEffect, useState } from "react";
import { Banknote, Download, FileText, Mail, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { fmtD } from "@/lib/datetime";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const STATUS_META = {
  pending: { label: "Pending", cls: "border-red-300 text-red-800 bg-red-50" },
  requested: { label: "In Flow", cls: "border-amber-300 text-amber-800 bg-amber-50" },
  partially_billed: { label: "Partially Billed", cls: "border-blue-300 text-blue-800 bg-blue-50" },
  billed: { label: "Billed", cls: "border-emerald-300 text-emerald-800 bg-emerald-50" },
};
const TYPE_LABEL = { annual_rate_contract: "Annual Rate Contract (Monthly)", one_time_supply: "One-Time Supply" };
const PAY_META = {
  paid: { label: "Paid", cls: "border-emerald-300 text-emerald-800 bg-emerald-50" },
  partially_paid: { label: "Partially Paid", cls: "border-blue-300 text-blue-800 bg-blue-50" },
  unpaid: { label: "Unpaid", cls: "border-amber-300 text-amber-800 bg-amber-50" },
  not_billed: { label: "Not Billed", cls: "border-slate-300 text-slate-600 bg-slate-50" },
};

export default function BillingPendingReport() {
  const { user } = useAuth();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [ff, setFf] = useState({ q: "", project_manager: "", client: "", billing_type: "", payment_status: "", min_pending_days: "", period_from: "", period_to: "", order_type: "", service_type: "" });
  const [sending, setSending] = useState(false);
  const isMgmt = ["super_admin", "director", "general_manager"].includes(user?.role);
  const setF = (k) => (e) => setFf((p) => ({ ...p, [k]: e.target?.value ?? e }));

  const qs = useCallback((withStatus) => {
    const p = new URLSearchParams({ month });
    if (withStatus && statusFilter) p.set("status", statusFilter);
    Object.entries(ff).forEach(([k, v]) => v && p.set(k, v));
    return p.toString();
  }, [month, statusFilter, ff]);

  const load = useCallback(async () => {
    try { setData((await api.get(`/billing/pending-report?${qs(false)}`)).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  }, [qs]);
  useEffect(() => { load(); }, [load]);

  const setType = async (code, patch) => {
    try {
      await api.put(`/billing/projects/${code}/billing-type`, patch);
      toast.success(`${code} updated`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const download = async (fmt) => {
    try {
      const { data: blob } = await api.get(`/billing/pending-report/export?fmt=${fmt}&${qs(true)}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([blob]));
      const a = document.createElement("a");
      a.href = url; a.download = `pending-billing-${month}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const sendReminder = async () => {
    setSending(true);
    try {
      const { data: r } = await api.post(`/billing/pending-report/send-reminder?month=${month}`);
      if (r.sent) toast.success(`Reminder emailed to ${r.recipients} recipient(s) — ${r.pending} pending project(s)`);
      else toast.info(r.reason || "Nothing to send");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setSending(false); }
  };

  const FILTER_LABELS = { q: "Search", project_manager: "PM", client: "Client", billing_type: "Billing Type", payment_status: "Payment", min_pending_days: "Pending ≥ days", period_from: "Period From", period_to: "Period To", order_type: "WO/PO Type", service_type: "Service Type" };
  const activeFilters = Object.entries(ff).filter(([, v]) => v).map(([k, v]) => [k, `${FILTER_LABELS[k]}: ${String(v).replaceAll("_", " ")}`]);

  const s = data?.summary;
  const rows = (data?.rows || []).filter((r) => !statusFilter || r.billing_status === statusFilter);
  return (
    <div className="space-y-5" data-testid="billing-pending-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Banknote className="h-3 w-3" /> Billing Control
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Pending Billing Report</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Live billing status per project — ARC projects need one bill every month; one-time supply projects need final/partial billing.
            Updates automatically when Accounts generates the bill.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <Input type="month" className="h-9 w-40" value={month} onChange={(e) => setMonth(e.target.value)} data-testid="billing-month" />
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="billing-export-xlsx"><Download className="h-4 w-4 mr-1" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="billing-export-pdf"><FileText className="h-4 w-4 mr-1" /> PDF</Button>
          {isMgmt && (
            <Button className="h-9 rounded-sm" disabled={sending} onClick={sendReminder} data-testid="billing-send-reminder">
              <Mail className="h-4 w-4 mr-1" /> {sending ? "Sending…" : "Send Reminder Now"}
            </Button>
          )}
          <Button variant="outline" className="h-9 rounded-sm" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm p-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        <Input placeholder="Search project…" className="h-9" value={ff.q} onChange={setF("q")} data-testid="billing-filter-q" />
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.project_manager} onChange={setF("project_manager")} data-testid="billing-filter-pm">
          <option value="">All Project Managers</option>
          {(data?.managers || []).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.client} onChange={setF("client")} data-testid="billing-filter-client">
          <option value="">All Clients</option>
          {(data?.clients || []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.billing_type} onChange={setF("billing_type")} data-testid="billing-filter-type">
          <option value="">All Billing Types</option>
          <option value="annual_rate_contract">Annual Rate Contract</option>
          <option value="one_time_supply">One-Time Supply</option>
          <option value="unset">Type Not Set</option>
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.payment_status} onChange={setF("payment_status")} data-testid="billing-filter-payment">
          <option value="">All Payment Statuses</option>
          <option value="paid">Paid</option>
          <option value="partially_paid">Partially Paid</option>
          <option value="unpaid">Unpaid</option>
          <option value="not_billed">Not Billed</option>
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.min_pending_days} onChange={setF("min_pending_days")} data-testid="billing-filter-days">
          <option value="">Pending Any Duration</option>
          <option value="7">Pending ≥ 7 days</option>
          <option value="15">Pending ≥ 15 days</option>
          <option value="30">Pending ≥ 30 days</option>
          <option value="60">Pending ≥ 60 days</option>
          <option value="90">Pending ≥ 90 days</option>
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.order_type} onChange={setF("order_type")} data-testid="billing-filter-order-type">
          <option value="">All WO/PO Types</option>
          {(data?.order_types || []).map((t) => <option key={t} value={t}>{t.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}</option>)}
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.service_type} onChange={setF("service_type")} data-testid="billing-filter-service-type">
          <option value="">All Service Types</option>
          {(data?.service_types || []).map((t) => <option key={t} value={t}>{t.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}</option>)}
        </select>
        <div className="flex items-center gap-1 col-span-2">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground whitespace-nowrap">Service Period</span>
          <Input type="date" className="h-9" value={ff.period_from} onChange={setF("period_from")} data-testid="billing-filter-period-from" />
          <span className="text-xs text-muted-foreground">to</span>
          <Input type="date" className="h-9" value={ff.period_to} onChange={setF("period_to")} data-testid="billing-filter-period-to" />
        </div>
        {activeFilters.length > 0 && (
          <div className="col-span-full flex items-center gap-2 flex-wrap pt-1 border-t border-border/60">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Active filters ({activeFilters.length}):</span>
            {activeFilters.map(([k, label]) => (
              <Badge key={k} variant="outline" className="rounded-sm text-[10px] gap-1 pr-1" data-testid={`active-filter-${k}`}>
                {label}
                <button onClick={() => setFf((p) => ({ ...p, [k]: "" }))} className="hover:text-destructive font-bold px-0.5" title="Remove">×</button>
              </Badge>
            ))}
            {statusFilter && (
              <Badge variant="outline" className="rounded-sm text-[10px] gap-1 pr-1">
                Status: {STATUS_META[statusFilter]?.label}
                <button onClick={() => setStatusFilter("")} className="hover:text-destructive font-bold px-0.5">×</button>
              </Badge>
            )}
            <Button size="sm" variant="ghost" className="h-6 text-[11px] text-destructive" data-testid="billing-clear-filters"
              onClick={() => { setFf({ q: "", project_manager: "", client: "", billing_type: "", payment_status: "", min_pending_days: "", period_from: "", period_to: "", order_type: "", service_type: "" }); setStatusFilter(""); }}>
              Clear all
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <button onClick={() => setStatusFilter("")} className={`text-left bg-card border rounded-sm p-3 ${statusFilter === "" ? "border-primary ring-1 ring-primary/30" : "border-border"}`} data-testid="billing-kpi-total">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Projects</div>
          <div className="text-xl font-black tabular">{s?.total ?? "—"}</div>
        </button>
        {Object.entries(STATUS_META).map(([k, m]) => (
          <button key={k} onClick={() => setStatusFilter(statusFilter === k ? "" : k)}
            className={`text-left bg-card border rounded-sm p-3 ${statusFilter === k ? "border-primary ring-1 ring-primary/30" : "border-border"}`} data-testid={`billing-kpi-${k}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.label}</div>
            <div className="text-xl font-black tabular">{s?.[k] || 0}</div>
          </button>
        ))}
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Client / PM</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Billing Type</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Status ({month})</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Last Bill</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Open Request</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Basic (₹)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">GST (₹)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Payment</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!data && <TableRow><TableCell colSpan={9} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
            {data && rows.length === 0 && <TableRow><TableCell colSpan={9} className="text-center py-10 text-muted-foreground">No projects match.</TableCell></TableRow>}
            {rows.map((r) => {
              const m = STATUS_META[r.billing_status] || {};
              return (
                <TableRow key={r.project_code} data-testid={`billing-row-${r.project_code}`}>
                  <TableCell>
                    <div className="font-mono-data text-xs font-bold">{r.project_code}</div>
                    <div className="text-[11px] text-muted-foreground truncate max-w-[200px]">{r.project_name}</div>
                  </TableCell>
                  <TableCell>
                    <div className="text-xs">{r.client || "—"}</div>
                    <div className="text-[10px] text-muted-foreground">PM: {r.project_manager || "—"}</div>
                  </TableCell>
                  <TableCell>
                    <select value={r.billing_type || ""} onChange={(e) => e.target.value && setType(r.project_code, { billing_type: e.target.value })}
                      className="h-8 rounded-sm border border-input bg-background px-2 text-xs w-full" data-testid={`billing-type-${r.project_code}`}>
                      <option value="">— Set type —</option>
                      <option value="annual_rate_contract">Annual Rate Contract (Monthly)</option>
                      <option value="one_time_supply">One-Time Supply</option>
                    </select>
                    <div className="flex gap-1 mt-1">
                      <select value={r.order_type || ""} onChange={(e) => e.target.value && setType(r.project_code, { order_type: e.target.value })}
                        className="h-7 rounded-sm border border-input bg-background px-1 text-[10px] flex-1" data-testid={`order-type-${r.project_code}`}>
                        <option value="">WO/PO type…</option>
                        {(data?.order_types || []).map((t) => <option key={t} value={t}>{t.replaceAll("_", " ")}</option>)}
                      </select>
                      <select value={r.service_type || ""} onChange={(e) => e.target.value && setType(r.project_code, { service_type: e.target.value })}
                        className="h-7 rounded-sm border border-input bg-background px-1 text-[10px] flex-1" data-testid={`service-type-${r.project_code}`}>
                        <option value="">Service…</option>
                        {(data?.service_types || []).map((t) => <option key={t} value={t}>{t.replaceAll("_", " ")}</option>)}
                      </select>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`rounded-sm text-[10px] ${m.cls || ""}`}>{m.label || r.billing_status}</Badge>
                    {r.billing_status === "pending" && r.pending_days != null && <div className="text-[10px] text-muted-foreground mt-0.5">{r.pending_days} days</div>}
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.last_bill_no ? <><div className="font-semibold">{r.last_bill_no}</div><div className="text-[10px] text-muted-foreground">{fmtD(r.last_bill_at)}</div></> : "—"}
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.open_request_no ? <><div className="font-semibold">{r.open_request_no}</div><div className="text-[10px] text-muted-foreground">{(r.open_request_nature || "").replaceAll("_", " ")}</div></> : "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm">{r.billed_basic ? inr(r.billed_basic) : "—"}</TableCell>
                  <TableCell className="text-right font-mono-data tabular text-xs">{r.billed_gst ? inr(r.billed_gst) : "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`rounded-sm text-[10px] ${PAY_META[r.payment_status]?.cls || ""}`}>
                      {PAY_META[r.payment_status]?.label || "—"}
                    </Badge>
                    {r.payment_status === "partially_paid" && <div className="text-[10px] text-muted-foreground mt-0.5">Recd {inr(r.paid_amount)} · Due {inr(r.balance_due)}</div>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Automated reminder: after the 5th of every month, all Project Managers, P&amp;O Heads &amp; Seniors, GM and Director receive an email listing projects with pending billing.
      </p>
    </div>
  );
}
