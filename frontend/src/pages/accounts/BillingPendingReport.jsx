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
const ALL = "all";
const STATUS_META = {
  pending: { label: "Pending", cls: "border-red-300 text-red-800 bg-red-50" },
  requested: { label: "In Flow", cls: "border-amber-300 text-amber-800 bg-amber-50" },
  partially_billed: { label: "Partially Billed", cls: "border-blue-300 text-blue-800 bg-blue-50" },
  billed: { label: "Billed", cls: "border-emerald-300 text-emerald-800 bg-emerald-50" },
  out_of_period: { label: "Outside Validity", cls: "border-slate-300 text-slate-600 bg-slate-50" },
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
  const [ff, setFf] = useState({ q: "", project_code: "", category: "", project_manager: "", client: "", billing_type: "", payment_status: "", min_pending_days: "", period_from: "", period_to: "", order_type: "", service_type: "" });
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

  const download = async (fmt) => {
    try {
      const { data: blob } = await api.get(`/billing/pending-report/export?fmt=${fmt}&${qs(true)}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([blob]));
      const a = document.createElement("a");
      a.href = url; a.download = `pending-billing-${month === ALL ? "all-months" : month}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`${fmt.toUpperCase()} downloaded — ${rows.length} project(s)${activeFilters.length || statusFilter ? " (filtered)" : ""}`);
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

  const FILTER_LABELS = { q: "Search", project_code: "Project", category: "Category", project_manager: "PM", client: "Client", billing_type: "Billing Type", payment_status: "Payment", min_pending_days: "Pending ≥ days", period_from: "Period From", period_to: "Period To", order_type: "WO/PO Type", service_type: "Service Type" };
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
            Billing follows the Project Category from Project Master — AMC/ARC projects need one bill every month of the project validity;
            Short-Term, Long-Term, Shutdown and One-Time projects are billed against the project scope / timeline.
            Updates automatically when Accounts generates the bill.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex items-center gap-1">
            <Button variant={month === ALL ? "default" : "outline"} className="h-9 rounded-sm text-xs"
              onClick={() => setMonth(month === ALL ? new Date().toISOString().slice(0, 7) : ALL)}
              data-testid="billing-all-months">
              {month === ALL ? "All Months" : "View All Months"}
            </Button>
            <Input type="month" className="h-9 w-40" value={month === ALL ? "" : month}
              onChange={(e) => setMonth(e.target.value || new Date().toISOString().slice(0, 7))} data-testid="billing-month" />
          </div>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="billing-export-xlsx"><Download className="h-4 w-4 mr-1" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("csv")} data-testid="billing-export-csv"><Download className="h-4 w-4 mr-1" /> CSV</Button>
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
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.project_code} onChange={setF("project_code")} data-testid="billing-filter-project">
          <option value="">All Projects</option>
          {(data?.projects || []).map((p) => <option key={p.code} value={p.code}>{p.code} — {p.name}</option>)}
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={ff.category} onChange={setF("category")} data-testid="billing-filter-category">
          <option value="">All Project Categories</option>
          {(data?.categories || []).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          <option value="unset">Category Not Set</option>
        </select>
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
              onClick={() => { setFf({ q: "", project_code: "", category: "", project_manager: "", client: "", billing_type: "", payment_status: "", min_pending_days: "", period_from: "", period_to: "", order_type: "", service_type: "" }); setStatusFilter(""); }}>
              Clear all
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="bg-card border-2 border-red-200 rounded-sm p-4" data-testid="billing-kpi-pending-amount">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Pending Billing</div>
          <div className="text-2xl font-black tabular text-red-800 mt-0.5">{inr(s?.pending_amount)}</div>
          <div className="text-[11px] text-muted-foreground mt-1">
            {s?.pending_months_total || 0} pending month(s) · {s?.amc_arc || 0} AMC/ARC · {s?.scope || 0} scope-based
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm lg:col-span-2 overflow-x-auto" data-testid="billing-month-wise">
          <div className="px-3 py-2 border-b border-border text-[10px] font-bold uppercase tracking-[0.18em] text-primary">
            Month-wise Pending Billing
          </div>
          <div className="flex gap-2 p-3 min-w-max">
            <button onClick={() => setMonth(ALL)}
              className={`text-left border rounded-sm px-3 py-2 min-w-[140px] transition-colors hover:border-primary ${month === ALL ? "border-primary bg-primary/5" : "border-border"}`}
              data-testid="billing-month-all">
              <div className="text-[11px] font-bold">All Months</div>
              <div className="text-sm font-black tabular text-red-800">{inr(s?.pending_amount)}</div>
              <div className="text-[10px] text-muted-foreground">{(data?.month_wise || []).length} month(s) pending</div>
            </button>
            {(data?.month_wise || []).length === 0 && <div className="text-sm text-muted-foreground">Nothing pending — all months are billed.</div>}
            {(data?.month_wise || []).map((m) => (
              <button key={m.month} onClick={() => setMonth(m.month)}
                className={`text-left border rounded-sm px-3 py-2 min-w-[140px] transition-colors hover:border-primary ${month === m.month ? "border-primary bg-primary/5" : "border-border"} ${m.pending_amount ? "" : "opacity-60"}`}
                data-testid={`billing-month-${m.month}`}>
                <div className="text-[11px] font-bold">{m.month}</div>
                <div className={`text-sm font-black tabular ${m.pending_amount ? "text-red-800" : "text-muted-foreground"}`}>
                  {m.pending_amount ? inr(m.pending_amount) : "Amount not set"}
                </div>
                <div className="text-[10px] text-muted-foreground">{m.projects} project(s)</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Category</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Billing Month / Period</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Client / PM</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Status ({month === ALL ? "All Months" : month})</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Pending (₹)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Last Bill</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Open Request</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Basic (₹)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Payment</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Pending Remarks</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!data && <TableRow><TableCell colSpan={11} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
            {data && rows.length === 0 && <TableRow><TableCell colSpan={11} className="text-center py-10 text-muted-foreground">No projects match.</TableCell></TableRow>}
            {rows.map((r) => {
              const m = STATUS_META[r.billing_status] || {};
              return (
                <TableRow key={r.project_code} data-testid={`billing-row-${r.project_code}`}>
                  <TableCell>
                    <div className="font-mono-data text-xs font-bold">{r.project_code}</div>
                    <div className="text-[11px] text-muted-foreground truncate max-w-[200px]">{r.project_name}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`rounded-sm text-[10px] ${r.billing_mode === "monthly" ? "border-indigo-300 text-indigo-900 bg-indigo-50" : "border-slate-300 text-slate-700 bg-slate-50"}`}
                      data-testid={`billing-category-${r.project_code}`}>
                      {r.category_label || "Not Set"}
                    </Badge>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{r.billing_mode === "monthly" ? "Month-wise" : "Scope / timeline"}</div>
                  </TableCell>
                  <TableCell className="text-xs" data-testid={`billing-period-${r.project_code}`}>
                    <div className="font-semibold">{r.billing_mode === "monthly" && month !== ALL ? month : (r.billing_period || "—")}</div>
                    {r.billing_mode === "monthly" && (r.pending_months || []).length > 0 && (
                      <div className="text-[10px] text-red-700 mt-0.5 max-w-[190px]">
                        Pending: {(r.pending_months || []).slice(0, 4).join(", ")}{(r.pending_months || []).length > 4 ? ` +${r.pending_months.length - 4}` : ""}
                      </div>
                    )}
                    {r.billing_mode === "monthly" && <div className="text-[10px] text-muted-foreground">{inr(r.expected_monthly)}/month</div>}
                  </TableCell>
                  <TableCell>
                    <div className="text-xs">{r.client || "—"}</div>
                    <div className="text-[10px] text-muted-foreground">PM: {r.project_manager || "—"}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`rounded-sm text-[10px] ${m.cls || ""}`}>{m.label || r.billing_status}</Badge>
                    {r.billing_status === "pending" && r.pending_days != null && <div className="text-[10px] text-muted-foreground mt-0.5">{r.pending_days} days</div>}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm font-bold text-red-800" data-testid={`billing-pending-amt-${r.project_code}`}>
                    {r.pending_amount ? inr(r.pending_amount) : "—"}
                    {r.pending_months_count > 1 && <div className="text-[10px] text-muted-foreground font-normal">{r.pending_months_count} months</div>}
                    {!r.pending_amount && r.billing_mode === "monthly" && r.pending_months_count > 0 && (
                      <div className="text-[10px] text-amber-700 font-normal">Monthly amount not set in Project Master</div>
                    )}
                    {!r.pending_amount && r.billing_mode === "scope" && r.billing_status === "pending" && !r.scope_value && (
                      <div className="text-[10px] text-amber-700 font-normal">Contract value not set</div>
                    )}
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.last_bill_no ? <><div className="font-semibold">{r.last_bill_no}</div><div className="text-[10px] text-muted-foreground">{fmtD(r.last_bill_at)}</div></> : "—"}
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.open_request_no ? <><div className="font-semibold">{r.open_request_no}</div><div className="text-[10px] text-muted-foreground">{(r.open_request_nature || "").replaceAll("_", " ")}</div></> : "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm">{r.billed_basic ? inr(r.billed_basic) : "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`rounded-sm text-[10px] ${PAY_META[r.payment_status]?.cls || ""}`}>
                      {PAY_META[r.payment_status]?.label || "—"}
                    </Badge>
                    {r.payment_status === "partially_paid" && <div className="text-[10px] text-muted-foreground mt-0.5">Recd {inr(r.paid_amount)} · Due {inr(r.balance_due)}</div>}
                  </TableCell>
                  <TableCell className="text-[10px] text-muted-foreground max-w-[220px]" data-testid={`billing-remarks-${r.project_code}`}>
                    {r.remarks || "—"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Automated reminder: from the 5th of every month each project with pending billing is emailed to its own Project Manager
        (Accounts, GM and Director in copy) with the project name, category, pending month, pending amount and status — repeating every 7 days until the billing is completed.
      </p>
    </div>
  );
}
