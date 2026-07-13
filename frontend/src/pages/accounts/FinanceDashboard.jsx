/**
 * Finance Dashboard · Phase 7 · CFO landing page
 *
 * Two tabs: Summary (KPI cards) + Cash Flow (30-day forecast timeline).
 * Backend: /api/finance/dashboard/{summary,cashflow}
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { LineChart, RefreshCcw, TrendingDown, TrendingUp, Wallet, AlertCircle } from "lucide-react";

const fmt = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function FinanceDashboard() {
  const [summary, setSummary] = useState(null);
  const [cashflow, setCashflow] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        api.get("/finance/dashboard/summary"),
        api.get("/finance/dashboard/cashflow?days=30"),
      ]);
      setSummary(s.data);
      setCashflow(c.data);
    } catch (e) { toast.error("Load failed"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (!summary) return <div className="p-6 text-slate-400">Loading…</div>;

  return (
    <div className="p-6 space-y-4" data-testid="page-finance-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><LineChart className="h-6 w-6 text-primary" /> Finance Dashboard</h1>
          <p className="text-sm text-muted-foreground">Real-time CFO landing page · as of {summary.as_of}</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
      </div>

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary" data-testid="fd-tab-summary">Summary</TabsTrigger>
          <TabsTrigger value="cashflow" data-testid="fd-tab-cashflow">30-day Cash Flow</TabsTrigger>
        </TabsList>

        <TabsContent value="summary">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <Kpi label="Total Receivable" value={fmt(summary.receivable.total)} sub={`Overdue ${fmt(summary.receivable.overdue)}`} tone={summary.receivable.overdue > 0 ? "amber" : "emerald"} />
            <Kpi label="Total Payable" value={fmt(summary.payable.total)} sub={`Overdue ${fmt(summary.payable.overdue)}`} tone={summary.payable.overdue > 0 ? "rose" : "slate"} />
            <Kpi label="Bank + Cash" value={fmt(summary.balances.total)} sub={`Bank ${fmt(summary.balances.bank)} · Cash ${fmt(summary.balances.cash)}`} tone="blue" icon={<Wallet className="h-4 w-4" />} />
            <Kpi label="Net Cash Position" value={fmt(summary.net_cash_position)} sub="Bank + Cash − Overdue AP" tone={summary.net_cash_position >= 0 ? "emerald" : "rose"} />

            <Kpi label="This Month Billing" value={fmt(summary.this_month.billing)} tone="blue" icon={<TrendingUp className="h-4 w-4" />} />
            <Kpi label="This Month Collection" value={fmt(summary.this_month.collection)} tone="emerald" icon={<TrendingUp className="h-4 w-4" />} />
            <Kpi label="This Month Expense" value={fmt(summary.this_month.expense)} tone="rose" icon={<TrendingDown className="h-4 w-4" />} />
            <Kpi label="Pending Approvals" value={summary.pending_approvals.total} sub={`Inv ${summary.pending_approvals.client_invoices} · Bills ${summary.pending_approvals.vendor_bills} · JE ${summary.pending_approvals.journal_entries} · Adv ${summary.pending_approvals.advances}`} tone={summary.pending_approvals.total > 0 ? "amber" : "emerald"} icon={<AlertCircle className="h-4 w-4" />} />

            <Kpi label="GST Payable" value={fmt(summary.statutory_payable.gst_payable)} sub="Last month accrual" tone="amber" />
            <Kpi label="TDS Payable" value={fmt(summary.statutory_payable.tds)} tone="amber" />
            <Kpi label="PF Payable" value={fmt(summary.statutory_payable.pf)} tone="amber" />
            <Kpi label="ESIC Payable" value={fmt(summary.statutory_payable.esic)} tone="amber" />
          </div>
        </TabsContent>

        <TabsContent value="cashflow">
          {cashflow && (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <Kpi label="Expected Inflow (30d)" value={fmt(cashflow.total_expected_inflow)} tone="emerald" icon={<TrendingUp className="h-4 w-4" />} />
                <Kpi label="Expected Outflow (30d)" value={fmt(cashflow.total_expected_outflow)} tone="rose" icon={<TrendingDown className="h-4 w-4" />} />
                <Kpi label="Net Projected" value={fmt(cashflow.net_projected)} tone={cashflow.net_projected >= 0 ? "emerald" : "rose"} />
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <FlowTable rows={cashflow.inflows} title="Expected Inflows" emerald />
                <FlowTable rows={cashflow.outflows} title="Expected Outflows" />
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Kpi({ label, value, sub, tone = "slate", icon }) {
  const tones = {
    slate: "border-slate-200 bg-white",
    blue: "border-blue-200 bg-blue-50",
    emerald: "border-emerald-200 bg-emerald-50",
    amber: "border-amber-200 bg-amber-50",
    rose: "border-rose-200 bg-rose-50",
  };
  return (
    <Card className={`${tones[tone] || tones.slate} border`} data-testid={`kpi-${label.toLowerCase().replace(/\W+/g, "-")}`}>
      <CardContent className="p-3">
        <div className="text-[11px] text-slate-600 flex items-center gap-1">{icon}{label}</div>
        <div className="text-2xl font-bold tabular-nums mt-0.5">{value}</div>
        {sub && <div className="text-[10px] text-slate-500 mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function FlowTable({ rows, title, emerald }) {
  return (
    <Card>
      <CardContent className="p-0">
        <div className="px-3 py-2 text-sm font-semibold bg-slate-50 border-b">{title} ({rows.length})</div>
        <div className="max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-white text-xs uppercase text-slate-600 sticky top-0">
              <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Type</th><th className="p-2 text-left">Party / Ref</th><th className="p-2 text-right">Amount</th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b">
                  <td className="p-2 text-xs font-mono">{r.date}</td>
                  <td className="p-2"><Badge variant="outline" className="text-[10px]">{r.kind}</Badge></td>
                  <td className="p-2 text-xs"><div className="font-medium">{r.party}</div><div className="text-[10px] text-slate-500">{r.ref}</div></td>
                  <td className={`p-2 text-right font-semibold ${emerald ? "text-emerald-700" : "text-rose-700"}`}>{fmt(r.amount)}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={4} className="p-8 text-center text-slate-400">No items</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
