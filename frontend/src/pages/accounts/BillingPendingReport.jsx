import { useCallback, useEffect, useState } from "react";
import { Banknote, Mail, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const STATUS_META = {
  pending: { label: "Pending", cls: "border-red-300 text-red-800 bg-red-50" },
  requested: { label: "In Flow", cls: "border-amber-300 text-amber-800 bg-amber-50" },
  partially_billed: { label: "Partially Billed", cls: "border-blue-300 text-blue-800 bg-blue-50" },
  billed: { label: "Billed", cls: "border-emerald-300 text-emerald-800 bg-emerald-50" },
};
const TYPE_LABEL = { annual_rate_contract: "Annual Rate Contract (Monthly)", one_time_supply: "One-Time Supply" };

export default function BillingPendingReport() {
  const { user } = useAuth();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [sending, setSending] = useState(false);
  const isMgmt = ["super_admin", "director", "general_manager"].includes(user?.role);

  const load = useCallback(async () => {
    try { setData((await api.get(`/billing/pending-report?month=${month}`)).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  }, [month]);
  useEffect(() => { load(); }, [load]);

  const setType = async (code, billing_type) => {
    try {
      await api.put(`/billing/projects/${code}/billing-type`, { billing_type });
      toast.success(`${code} → ${TYPE_LABEL[billing_type]}`);
      load();
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
          {isMgmt && (
            <Button className="h-9 rounded-sm" disabled={sending} onClick={sendReminder} data-testid="billing-send-reminder">
              <Mail className="h-4 w-4 mr-1" /> {sending ? "Sending…" : "Send Reminder Now"}
            </Button>
          )}
          <Button variant="outline" className="h-9 rounded-sm" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
        </div>
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
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Billed (Total)</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!data && <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
            {data && rows.length === 0 && <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">No projects match.</TableCell></TableRow>}
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
                    <select value={r.billing_type || ""} onChange={(e) => e.target.value && setType(r.project_code, e.target.value)}
                      className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid={`billing-type-${r.project_code}`}>
                      <option value="">— Set type —</option>
                      <option value="annual_rate_contract">Annual Rate Contract (Monthly)</option>
                      <option value="one_time_supply">One-Time Supply</option>
                    </select>
                  </TableCell>
                  <TableCell><Badge variant="outline" className={`rounded-sm text-[10px] ${m.cls || ""}`}>{m.label || r.billing_status}</Badge></TableCell>
                  <TableCell className="text-xs">
                    {r.last_bill_no ? <><div className="font-semibold">{r.last_bill_no}</div><div className="text-[10px] text-muted-foreground">{(r.last_bill_at || "").slice(0, 10)}</div></> : "—"}
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.open_request_no ? <><div className="font-semibold">{r.open_request_no}</div><div className="text-[10px] text-muted-foreground">{(r.open_request_nature || "").replaceAll("_", " ")}</div></> : "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm">{r.bills_generated ? `${inr(r.billed_amount)} · ${r.bills_generated}` : "—"}</TableCell>
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
