import { useEffect, useState } from "react";
import { Search, RefreshCw, Wallet, AlertTriangle, TrendingUp, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const SEVERITY_TONE = { high: "danger", medium: "warning", low: "info" };

export default function Receivables() {
  const [dash, setDash] = useState(null);
  const [tab, setTab] = useState("ageing");
  const [overdue, setOverdue] = useState({ rows: [], total_overdue: 0, count: 0 });
  const [cashflow, setCashflow] = useState(null);
  const [ledgerClient, setLedgerClient] = useState("");
  const [ledger, setLedger] = useState(null);

  const load = async () => {
    try {
      const [d, o, c] = await Promise.all([api.get("/receivables/dashboard"), api.get("/receivables/overdue"), api.get("/receivables/cashflow?days=30")]);
      setDash(d.data); setOverdue(o.data); setCashflow(c.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  const loadLedger = async () => {
    if (!ledgerClient.trim()) { toast.error("Enter a client_id"); return; }
    try { const r = await api.get(`/receivables/client-ledger?client_id=${encodeURIComponent(ledgerClient)}`); setLedger(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const kpis = dash?.kpis || {};
  return (
    <div className="space-y-6" data-testid="receivables-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Wallet className="h-3 w-3" /> Accounts · Receivables
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Receivables &amp; Cashflow</h1>
        <p className="text-sm text-muted-foreground mt-1">Ageing buckets · overdue alerts · client ledger · 30-day forecast — built from invoiced RA bills and recorded payments.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Kpi label="Outstanding" value={inr(kpis.outstanding_total)} tone="primary" testid="rcv-kpi-outstanding" />
        <Kpi label="Overdue" value={inr(kpis.overdue_total)} tone={kpis.overdue_total ? "danger" : "neutral"} testid="rcv-kpi-overdue" />
        <Kpi label="Overdue Count" value={kpis.overdue_count ?? 0} tone={kpis.overdue_count ? "danger" : "neutral"} testid="rcv-kpi-overdue-count" />
        <Kpi label="Open Bills" value={kpis.open_bills ?? 0} tone="info" testid="rcv-kpi-open" />
        <Kpi label="Invoiced (LTM)" value={inr(kpis.invoiced_lifetime)} tone="success" testid="rcv-kpi-invoiced" />
        <Kpi label="Received (LTM)" value={inr(kpis.received_lifetime)} tone="success" testid="rcv-kpi-received" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant={tab === "ageing" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("ageing")} data-testid="rcv-tab-ageing"><Users className="h-3.5 w-3.5 mr-1.5" /> Ageing</Button>
        <Button variant={tab === "overdue" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("overdue")} data-testid="rcv-tab-overdue"><AlertTriangle className="h-3.5 w-3.5 mr-1.5" /> Overdue</Button>
        <Button variant={tab === "cashflow" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("cashflow")} data-testid="rcv-tab-cashflow"><TrendingUp className="h-3.5 w-3.5 mr-1.5" /> Cashflow (30d)</Button>
        <Button variant={tab === "ledger" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("ledger")} data-testid="rcv-tab-ledger"><Wallet className="h-3.5 w-3.5 mr-1.5" /> Client Ledger</Button>
        <Button variant="outline" size="sm" className="h-9 rounded-sm ml-auto" onClick={load}><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
      </div>

      {tab === "ageing" && dash?.ageing && <AgeingView ageing={dash.ageing} />}
      {tab === "overdue" && <OverdueView rows={overdue.rows} total={overdue.total_overdue} />}
      {tab === "cashflow" && cashflow && <CashflowView data={cashflow} />}
      {tab === "ledger" && (
        <div className="bg-card border border-border rounded-sm p-4">
          <div className="flex gap-2 mb-3">
            <Input value={ledgerClient} onChange={(e) => setLedgerClient(e.target.value)} placeholder="Enter client_id…" className="h-9 rounded-sm" data-testid="rcv-ledger-client" />
            <Button className="h-9 rounded-sm" onClick={loadLedger} data-testid="rcv-ledger-go"><Search className="h-4 w-4 mr-1" /> Load</Button>
          </div>
          {ledger && <LedgerView ledger={ledger} />}
        </div>
      )}
    </div>
  );
}

function AgeingView({ ageing }) {
  return (
    <div className="space-y-4" data-testid="rcv-ageing-view">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Bucket data={ageing.not_due} tone="success" testid="rcv-bucket-not-due" />
        {ageing.buckets.map((b) => (
          <Bucket key={b.label} data={b} tone={b.label === "0-30d" ? "info" : b.label === "31-60d" ? "warning" : "danger"} testid={`rcv-bucket-${b.label}`} />
        ))}
      </div>
      <div className="bg-card border border-border rounded-sm p-4">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Outstanding</div>
        <div className="font-display font-black text-3xl text-primary tabular">{inr(ageing.total_outstanding)}</div>
      </div>
    </div>
  );
}
function Bucket({ data, tone, testid }) {
  const c = { success: "text-success", warning: "text-warning", danger: "text-destructive", info: "text-chart-3" }[tone] || "text-primary";
  return (
    <div className="bg-card border border-border rounded-sm p-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{data.label}</div>
      <div className={`font-display font-black text-xl tabular mt-1 ${c}`}>{inr(data.amount)}</div>
      <div className="text-[10px] text-muted-foreground mt-0.5">{data.count} bills</div>
    </div>
  );
}

function OverdueView({ rows, total }) {
  return (
    <div className="bg-card border border-border rounded-sm" data-testid="rcv-overdue-view">
      <div className="flex justify-between items-center p-4 border-b border-border">
        <div className="text-sm font-semibold">Overdue Bills</div>
        <div className="text-right"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Overdue</div><div className="font-display font-black text-2xl text-destructive tabular">{inr(total)}</div></div>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Bill #</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Client · Project</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Due Date</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Days Past Due</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Balance</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Severity</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10 text-sm">Nothing overdue 🎉</TableCell></TableRow>}
          {rows.map((r) => (
            <TableRow key={r.id} data-testid={`rcv-overdue-row-${r.id}`}>
              <TableCell className="font-mono-data text-sm font-bold">{r.bill_number}</TableCell>
              <TableCell className="text-xs"><div className="font-semibold">{r.client_name}</div><div className="text-muted-foreground">{r.project_code || "—"}</div></TableCell>
              <TableCell className="text-xs">{r.due_date}</TableCell>
              <TableCell className="font-mono-data tabular text-sm font-bold text-destructive">{r.days_past_due} d</TableCell>
              <TableCell className="font-mono-data tabular text-sm font-bold">{inr(r.balance)}</TableCell>
              <TableCell><StatusBadge text={r.severity} tone={SEVERITY_TONE[r.severity] || "neutral"} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function CashflowView({ data }) {
  return (
    <div className="space-y-3" data-testid="rcv-cashflow-view">
      <div className="grid grid-cols-3 gap-3">
        <Kpi label="Overdue (must collect)" value={inr(data.overdue_amount)} tone="danger" testid="rcv-cf-overdue" />
        <Kpi label="Upcoming (next 30d)" value={inr(data.upcoming_within_horizon)} tone="success" testid="rcv-cf-upcoming" />
        <Kpi label="Horizon" value={`${data.horizon_days} days`} tone="info" testid="rcv-cf-horizon" />
      </div>
      <div className="bg-card border border-border rounded-sm">
        <div className="p-3 border-b border-border text-[10px] uppercase tracking-wider text-muted-foreground">Weekly inflow forecast</div>
        <Table>
          <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="text-[10px] uppercase tracking-wider">Week</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Expected Inflow</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data.weekly_inflow.length === 0 && <TableRow><TableCell colSpan={2} className="text-center text-muted-foreground py-6 text-sm">No expected inflows in the next {data.horizon_days} days.</TableCell></TableRow>}
            {data.weekly_inflow.map((w) => (
              <TableRow key={w.week}>
                <TableCell className="font-mono-data text-xs">{w.week}</TableCell>
                <TableCell className="font-mono-data tabular text-sm font-bold">{inr(w.amount)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function LedgerView({ ledger }) {
  return (
    <div data-testid="rcv-ledger-view">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
        <Kpi label="Invoiced" value={inr(ledger.summary.invoiced)} tone="info" />
        <Kpi label="Received" value={inr(ledger.summary.received)} tone="success" />
        <Kpi label="Balance" value={inr(ledger.summary.balance)} tone={ledger.summary.balance ? "warning" : "neutral"} />
        <Kpi label="Invoices" value={ledger.summary.count_invoices} tone="neutral" />
        <Kpi label="Payments" value={ledger.summary.count_payments} tone="neutral" />
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Type</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Reference</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Debit</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Credit</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Balance</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {ledger.transactions.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-6 text-sm">No transactions yet.</TableCell></TableRow>}
            {ledger.transactions.map((t, i) => (
              <TableRow key={`l-${i}`}>
                <TableCell className="text-xs">{t.date}</TableCell>
                <TableCell><StatusBadge text={t.type} tone={t.type === "invoice" ? "info" : "success"} /></TableCell>
                <TableCell className="font-mono-data text-xs">{t.ref}{t.mode ? ` · ${t.mode}` : ""}</TableCell>
                <TableCell className="font-mono-data tabular text-xs">{t.debit ? inr(t.debit) : "—"}</TableCell>
                <TableCell className="font-mono-data tabular text-xs">{t.credit ? inr(t.credit) : "—"}</TableCell>
                <TableCell className="font-mono-data tabular text-sm font-bold">{inr(t.balance)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone, testid }) {
  const c = { success: "text-success", warning: "text-warning", danger: "text-destructive", info: "text-chart-3", neutral: "text-primary", primary: "text-primary" }[tone] || "text-primary";
  return (
    <div className="bg-card border border-border rounded-sm p-3" data-testid={testid}>
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-display font-black text-2xl tabular mt-1 ${c}`}>{value ?? 0}</div>
    </div>
  );
}
