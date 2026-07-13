/**
 * Compliance Center · Finance Phase 6
 *
 * 3-tab consolidated GST/TDS/PF/ESIC tracker:
 *   • Dashboard    — KPI cards for current period (GST net, TDS payable/recv, PF/ESIC)
 *   • Calendar     — Indian tax due-date calendar with mark-paid
 *   • Items        — full list of filed/pending compliance items
 *
 * Backend: /api/finance/compliance/*
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Landmark, RefreshCcw, CheckCircle2, Calendar, AlertTriangle, Receipt } from "lucide-react";

const SEV = {
  paid: "bg-emerald-100 text-emerald-700",
  pending: "bg-amber-100 text-amber-700",
  overdue: "bg-rose-100 text-rose-700",
};

const fmt = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

const lastMonth = () => {
  const d = new Date();
  d.setDate(1); d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export default function ComplianceCenter() {
  const [period, setPeriod] = useState(lastMonth());
  const [dashboard, setDashboard] = useState(null);
  const [calendar, setCalendar] = useState({ items: [] });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [dRes, cRes] = await Promise.all([
        api.get(`/finance/compliance/dashboard?period=${period}`),
        api.get(`/finance/compliance/calendar?period=${period}`),
      ]);
      setDashboard(dRes.data);
      setCalendar(cRes.data);
    } catch (e) { toast.error("Load failed"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [period]);

  const markPaid = async (item) => {
    const challan = window.prompt("Challan / ARN number:");
    if (!challan) return;
    const paidDate = window.prompt("Paid date (YYYY-MM-DD):", new Date().toISOString().slice(0, 10));
    if (!paidDate) return;
    const amount = window.prompt("Amount (optional):");
    try {
      let itemId = item.item_id;
      if (!itemId) {
        // Create item first
        const { data } = await api.post("/finance/compliance/items", {
          period, kind: item.kind, label: item.label, due_date: item.due_date,
          challan_number: challan, paid_date: paidDate,
          amount: amount ? Number(amount) : undefined,
        });
        itemId = data.id;
      } else {
        await api.post(`/finance/compliance/items/${itemId}/mark-paid`, null, {
          params: { challan_number: challan, paid_date: paidDate, amount: amount ? Number(amount) : undefined },
        });
      }
      toast.success("Marked as paid");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-compliance-center">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Landmark className="h-6 w-6 text-primary" /> Compliance Center</h1>
          <p className="text-sm text-muted-foreground">GST · TDS · PF · ESIC · Professional Tax — single pane of glass.</p>
        </div>
        <div className="flex items-center gap-2">
          <Input type="month" value={period} onChange={e => setPeriod(e.target.value)} className="h-9 w-40" data-testid="comp-period" />
          <Button variant="outline" size="sm" onClick={load} data-testid="comp-refresh"><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
        </div>
      </div>

      <Tabs defaultValue="dashboard">
        <TabsList>
          <TabsTrigger value="dashboard" data-testid="comp-tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="calendar" data-testid="comp-tab-calendar">Calendar</TabsTrigger>
          <TabsTrigger value="items" data-testid="comp-tab-items">Items</TabsTrigger>
        </TabsList>

        {/* Dashboard */}
        <TabsContent value="dashboard">
          {loading && <div className="py-8 text-center text-slate-400">Loading…</div>}
          {dashboard && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <Kpi label="GST Output" value={fmt(dashboard.gst.output_accrued)} sub={`Period ${dashboard.period}`} tone="blue" />
              <Kpi label="GST Input Credit" value={fmt(dashboard.gst.input_credit)} sub="Set-off available" tone="emerald" />
              <Kpi label="GST Net Payable" value={fmt(dashboard.gst.net_payable)} sub={`Due 20th of ${monthName(dashboard.period)}`} tone="amber" />
              <Kpi label="GST Paid" value={fmt(dashboard.gst.paid)} sub="During this period" tone="slate" />

              <Kpi label="TDS Payable (accrued)" value={fmt(dashboard.tds.payable_accrued)} tone="blue" />
              <Kpi label="TDS Payable Balance" value={fmt(dashboard.tds.payable_balance)} sub="Due 7th of next month" tone="rose" />
              <Kpi label="TDS Receivable" value={fmt(dashboard.tds.receivable_due)} sub="From client deductions" tone="emerald" />
              <Kpi label="Items Summary" value={`${dashboard.items_summary.paid}/${dashboard.items_summary.total}`} sub={`${dashboard.items_summary.overdue} overdue`} tone={dashboard.items_summary.overdue > 0 ? "rose" : "emerald"} />

              <Kpi label="PF Payable" value={fmt(dashboard.pf.balance)} sub={`Accrued ${fmt(dashboard.pf.accrued)} · Paid ${fmt(dashboard.pf.paid)}`} tone="amber" />
              <Kpi label="ESIC Payable" value={fmt(dashboard.esic.balance)} sub={`Accrued ${fmt(dashboard.esic.accrued)} · Paid ${fmt(dashboard.esic.paid)}`} tone="amber" />
            </div>
          )}
        </TabsContent>

        {/* Calendar */}
        <TabsContent value="calendar">
          <Card><CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr><th className="p-2 text-left">Filing / Payment</th><th className="p-2 text-left">Section</th><th className="p-2 text-left">Due Date</th><th className="p-2 text-right">Amount</th><th className="p-2 text-left">Status</th><th className="p-2 text-left">Challan / ARN</th><th className="p-2 text-right">Action</th></tr>
              </thead>
              <tbody>
                {calendar.items.map((it) => (
                  <tr key={it.kind} className={`border-b ${it.status === "overdue" ? "bg-rose-50" : ""}`} data-testid={`cal-row-${it.kind}`}>
                    <td className="p-2"><Calendar className="h-3.5 w-3.5 inline mr-1 text-slate-400" />{it.label}</td>
                    <td className="p-2 text-xs">{it.section}</td>
                    <td className="p-2 text-xs font-mono">{it.due_date}</td>
                    <td className="p-2 text-right">{it.amount ? fmt(it.amount) : "—"}</td>
                    <td className="p-2"><Badge className={SEV[it.status] || ""}>{it.status}</Badge></td>
                    <td className="p-2 text-xs font-mono">{it.challan_number || "—"}</td>
                    <td className="p-2 text-right">
                      {it.status !== "paid" && (
                        <Button size="sm" variant="outline" onClick={() => markPaid(it)} data-testid={`cal-paid-${it.kind}`}>
                          <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Mark Paid
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {!calendar.items.length && <tr><td colSpan={7} className="p-8 text-center text-slate-400">No items</td></tr>}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        {/* Items */}
        <TabsContent value="items">
          <CompliantItemsList period={period} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Kpi({ label, value, sub, tone = "slate" }) {
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
        <div className="text-[11px] text-slate-600">{label}</div>
        <div className="text-2xl font-bold tabular-nums mt-0.5">{value}</div>
        {sub && <div className="text-[10px] text-slate-500 mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function CompliantItemsList({ period }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/finance/compliance/items?period=${period}`);
        setRows(data || []);
      } catch { /* ignore */ }
    })();
  }, [period]);
  return (
    <Card><CardContent className="p-0">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs uppercase">
          <tr><th className="p-2 text-left">Kind</th><th className="p-2 text-left">Label</th><th className="p-2 text-left">Period</th><th className="p-2 text-left">Due</th><th className="p-2 text-left">Paid</th><th className="p-2 text-left">Challan</th><th className="p-2 text-right">Amount</th><th className="p-2 text-left">Status</th></tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className="border-b" data-testid={`item-row-${r.id}`}>
              <td className="p-2 text-xs font-mono">{r.kind}</td>
              <td className="p-2 text-xs">{r.label || "—"}</td>
              <td className="p-2 text-xs">{r.period}</td>
              <td className="p-2 text-xs">{r.due_date}</td>
              <td className="p-2 text-xs">{r.paid_date || "—"}</td>
              <td className="p-2 text-xs font-mono">{r.challan_number || "—"}</td>
              <td className="p-2 text-right">{r.amount ? fmt(r.amount) : "—"}</td>
              <td className="p-2"><Badge className={SEV[r.status] || ""}>{r.status}</Badge></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={8} className="p-8 text-center text-slate-400">No items recorded yet for {period}</td></tr>}
        </tbody>
      </table>
    </CardContent></Card>
  );
}

function monthName(period) {
  const [y, m] = (period || "").split("-");
  if (!y || !m) return "";
  return new Date(Number(y), Number(m), 1).toLocaleString("en-IN", { month: "long" });
}
