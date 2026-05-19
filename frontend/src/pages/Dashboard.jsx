import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import KPICard from "@/components/KPICard";
import { StatusBadge } from "@/components/DataTableShell";
import {
  Wallet, TrendingDown, TrendingUp, Briefcase, Users, Truck, Boxes, ShieldAlert,
  ShoppingCart, HardHat, ArrowUpRight, AlertTriangle
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
  CartesianGrid, Cell, Legend, PieChart, Pie
} from "recharts";

const inr = (v) => "₹ " + Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function Dashboard() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();
  useEffect(() => {
    api.get("/dashboard/summary").then((r) => setData(r.data)).catch(() => setData({}));
  }, []);
  if (!data) {
    return <div className="text-sm text-muted-foreground" data-testid="dashboard-loading">Loading dashboard…</div>;
  }
  const k = data.kpis || {};
  const go = (path) => () => navigate(path);

  return (
    <div className="space-y-8" data-testid="dashboard-root">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Executive · Single Window</div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Operations Control Room</h1>
          <p className="text-sm text-muted-foreground mt-1">Real-time visibility across projects, finance, people, safety and supply chain.</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <StatusBadge text="Live" tone="success" />
          <span className="text-muted-foreground">Updated {new Date().toLocaleString()}</span>
        </div>
      </div>

      {/* Top KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 stagger">
        <KPICard testid="kpi-revenue" label="Revenue (6M)" value={inr(k.revenue || 0)} icon={TrendingUp} delta="+12.4%" deltaTone="up" sub="vs prev period" accent onClick={go("/app/accounts")} />
        <KPICard testid="kpi-expenses" label="Expenses (6M)" value={inr(k.expenses || 0)} icon={TrendingDown} delta="+8.1%" deltaTone="down" sub="vs prev period" onClick={go("/app/accounts")} />
        <KPICard testid="kpi-profit" label="Net Profit" value={inr(k.profit || 0)} icon={Wallet} delta="+18.6%" deltaTone="up" sub="margin healthy" onClick={go("/app/reports")} />
        <KPICard testid="kpi-receivables" label="Receivables" value={inr(k.receivables || 0)} icon={ArrowUpRight} sub="open invoices" onClick={go("/app/quotations")} />
        <KPICard testid="kpi-payables" label="Vendor Payables" value={inr(k.payables || 0)} icon={ShoppingCart} sub="due to vendors" onClick={go("/app/purchase-orders")} />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-card border border-border rounded-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Cash Flow · 6 Months</div>
              <div className="font-display font-bold text-lg mt-0.5">Revenue vs Expense</div>
            </div>
            <StatusBadge text="Monthly" tone="primary" />
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.chart_revenue_expense || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={11} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} tickFormatter={(v) => `${(v / 100000).toFixed(0)}L`} />
              <Tooltip
                contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 4, fontSize: 12 }}
                formatter={(v) => inr(v)}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="revenue" fill="hsl(var(--chart-1))" radius={[2, 2, 0, 0]} />
              <Bar dataKey="expense" fill="hsl(var(--chart-5))" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card border border-border rounded-sm p-5">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Project Status</div>
          <div className="font-display font-bold text-lg mt-0.5 mb-3">Active Distribution</div>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={data.project_status || []}
                dataKey="count"
                nameKey="status"
                innerRadius={50}
                outerRadius={85}
                paddingAngle={2}
              >
                {(data.project_status || []).map((entry, i) => (
                  <Cell key={`${entry.status}-${i}`} fill={`hsl(var(--chart-${(i % 5) + 1}))`} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 4, fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Operations KPI grid */}
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-3">Operations Snapshot</div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 stagger">
          <KPICard testid="kpi-projects" label="Active Projects" value={k.active_projects ?? 0} sub={`of ${k.total_projects ?? 0} total`} icon={Briefcase} onClick={go("/app/projects")} />
          <KPICard testid="kpi-employees" label="Employees" value={k.employees ?? 0} sub="on roll" icon={HardHat} onClick={go("/app/employees")} />
          <KPICard testid="kpi-clients" label="Clients" value={k.clients ?? 0} sub="active" icon={Users} onClick={go("/app/clients")} />
          <KPICard testid="kpi-vendors" label="Vendors" value={k.vendors ?? 0} sub="approved" icon={Truck} onClick={go("/app/vendors")} />
          <KPICard testid="kpi-inventory" label="Inventory Items" value={k.inventory_items ?? 0} sub="SKUs tracked" icon={Boxes} onClick={go("/app/inventory")} />
          <KPICard testid="kpi-lowstock" label="Low Stock Alerts" value={k.low_stock_alerts ?? 0} sub="below minimum" icon={AlertTriangle} accent={!!k.low_stock_alerts} onClick={go("/app/inventory")} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Approvals & Safety */}
        <div className="bg-card border border-border rounded-sm p-5 hover:border-primary/40 transition-colors cursor-pointer" onClick={go("/app/approvals")} data-testid="dash-approvals-card">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Pending Approvals</div>
          <div className="font-display font-black text-4xl tabular mt-1">{k.pending_approvals ?? 0}</div>
          <div className="text-xs text-muted-foreground">click to review</div>
          <div className="h-px bg-border my-4" />
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="text-muted-foreground">Open POs</div>
              <div className="font-display font-bold text-lg tabular">{k.pending_purchase_orders ?? 0}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Open Quotes</div>
              <div className="font-display font-bold text-lg tabular">{k.open_quotations ?? 0}</div>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm p-5 hover:border-primary/40 transition-colors cursor-pointer" onClick={go("/app/safety")} data-testid="dash-safety-card">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Safety Today</div>
          <div className="font-display font-black text-4xl tabular mt-1 flex items-center gap-3">
            {k.open_safety_incidents ?? 0}
            <ShieldAlert className="h-7 w-7 text-warning" />
          </div>
          <div className="text-xs text-muted-foreground">open observations</div>
          <div className="h-px bg-border my-4" />
          <div className="space-y-2">
            {(data.safety_by_severity || []).map((s) => (
              <div key={s.severity} className="flex items-center justify-between text-xs">
                <span className="capitalize">{s.severity}</span>
                <StatusBadge text={String(s.count)} tone={s.severity === "high" ? "danger" : s.severity === "medium" ? "warning" : "success"} />
              </div>
            ))}
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm p-5 hover:border-primary/40 transition-colors cursor-pointer" onClick={go("/app/attendance")} data-testid="dash-attendance-card">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Attendance Today</div>
          <div className="grid grid-cols-2 gap-3 mt-1">
            <div>
              <div className="font-display font-black text-3xl tabular text-success">{k.attendance_today_present ?? 0}</div>
              <div className="text-xs text-muted-foreground">Present</div>
            </div>
            <div>
              <div className="font-display font-black text-3xl tabular text-destructive">{k.attendance_today_absent ?? 0}</div>
              <div className="text-xs text-muted-foreground">Absent</div>
            </div>
          </div>
          <div className="h-px bg-border my-4" />
          <ResponsiveContainer width="100%" height={80}>
            <LineChart data={data.chart_revenue_expense || []}>
              <Line type="monotone" dataKey="revenue" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
              <YAxis hide />
              <XAxis dataKey="month" hide />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Revenue trend</div>
        </div>
      </div>
    </div>
  );
}
