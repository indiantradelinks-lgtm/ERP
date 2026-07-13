import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Briefcase, Activity, Banknote, HardHat, ShieldAlert, Truck, RefreshCw,
  AlertTriangle, TrendingUp, Receipt, IndianRupee, Users, ListChecks, MapPin,
  CalendarDays, Layers, Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, BarChart, Bar, Cell,
  PieChart, Pie, Legend,
} from "recharts";
import { api } from "@/lib/api";
import { toast } from "sonner";
import LinkagePanel from "@/components/LinkagePanel";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const pct = (n) => Number(n || 0).toFixed(1) + "%";

export default function ProjectDashboard() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/project-dashboard/projects").then((r) => setProjects(r.data || []))
       .catch((e) => toast.error(e.response?.data?.detail || "Failed to load projects"));
  }, []);

  useEffect(() => {
    if (!id) { setData(null); return; }
    setLoading(true);
    api.get(`/project-dashboard/${id}`)
      .then((r) => setData(r.data))
      .catch((e) => { toast.error(e.response?.data?.detail || "Dashboard failed"); setData(null); })
      .finally(() => setLoading(false));
  }, [id]);

  const filtered = useMemo(() => {
    if (!q.trim()) return projects;
    const s = q.toLowerCase();
    return projects.filter((p) => (p.name + " " + (p.code || "") + " " + (p.client || "")).toLowerCase().includes(s));
  }, [projects, q]);

  if (!id) return <ProjectPicker projects={filtered} q={q} setQ={setQ} navigate={navigate} />;

  return (
    <div className="space-y-5" data-testid="project-dashboard-page">
      <Header data={data} navigate={navigate} loading={loading}
              onRefresh={() => api.get(`/project-dashboard/${id}`).then((r) => setData(r.data))} />
      {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
      {!loading && data && (
        <>
          <KpiStrip kpis={data.kpis} />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 space-y-4">
              <FinancialsCard f={data.financials} />
              <ChartsCard execution={data.execution} financials={data.financials} />
              <ProcurementCard p={data.procurement} />
            </div>
            <div className="space-y-4">
              <ExecutionCard e={data.execution} />
              <SafetyCard s={data.safety} />
              <RecentCard events={data.recent_activity} />
              {data.project?.id && <LinkagePanel resource="projects" recordId={data.project.id} />}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ProjectPicker({ projects, q, setQ, navigate }) {
  return (
    <div className="space-y-5" data-testid="project-picker">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Briefcase className="h-3 w-3" /> Dashboards
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Project-wise Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">Pick any project to open its 360° view — financials, execution, procurement, safety, manpower trend & recent activity.</p>
      </div>
      <Input className="h-10 rounded-sm max-w-md" placeholder="Search by name / code / client…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="pd-search" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {projects.map((p) => (
          <button key={p.id}
                  onClick={() => navigate(`/app/project-dashboard/${p.id}`)}
                  className="text-left p-4 bg-card border border-border rounded-sm hover:border-primary transition-colors"
                  data-testid={`pd-card-${p.id}`}>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{p.code || "—"}</div>
            <div className="font-display font-black text-base mt-0.5 leading-tight">{p.name}</div>
            <div className="text-[12px] text-muted-foreground mt-1">{p.client || "—"}</div>
            <div className="flex items-center justify-between mt-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{p.status || "—"}</span>
              <span className="text-[11px] tabular font-semibold">{inr(p.budget)}</span>
            </div>
          </button>
        ))}
        {projects.length === 0 && <div className="text-sm text-muted-foreground p-6">No projects found.</div>}
      </div>
    </div>
  );
}

function Header({ data, navigate, loading, onRefresh }) {
  const p = data?.project || {};
  return (
    <div className="flex flex-wrap items-start gap-3">
      <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={() => navigate("/app/project-dashboard")} data-testid="pd-back">
        ← All Projects
      </Button>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary flex items-center gap-2">
          <Briefcase className="h-3 w-3" /> Project Dashboard · {p.code || "—"}
        </div>
        <h1 className="font-display font-black text-2xl tracking-tight truncate">{p.name || "—"}</h1>
        <div className="flex flex-wrap gap-3 text-[12px] text-muted-foreground mt-0.5">
          <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" /> {p.client || "—"}</span>
          <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> {p.site || "—"}</span>
          <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" /> {p.start_date || "—"} → {p.end_date || "—"}</span>
          {p.status && <span className="inline-flex items-center gap-1 uppercase tracking-wider text-[10px] font-bold border border-border rounded-sm px-1.5 py-0.5">{p.status}</span>}
        </div>
      </div>
      <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={onRefresh} disabled={loading} data-testid="pd-refresh">
        <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} /> Refresh
      </Button>
    </div>
  );
}

function KpiStrip({ kpis }) {
  const tiles = [
    { label: "Contract Value", value: inr(kpis.contract_value), icon: IndianRupee, tone: "primary" },
    { label: "Billed", value: pct(kpis.billed_pct), icon: TrendingUp, tone: "emerald", sub: "of contract" },
    { label: "Outstanding", value: inr(kpis.outstanding), icon: Wallet, tone: "amber" },
    { label: "GP %", value: pct(kpis.gp_pct), icon: Banknote, tone: kpis.gp_pct >= 0 ? "emerald" : "red" },
    { label: "Manpower Today", value: kpis.manpower_today, icon: HardHat, tone: "primary" },
    { label: "Open Safety", value: kpis.open_safety_incidents, icon: ShieldAlert, tone: kpis.open_safety_incidents ? "red" : "emerald" },
  ];
  const toneClass = {
    primary: "border-primary/40 text-primary",
    emerald: "border-emerald-500/40 text-emerald-700",
    amber: "border-amber-500/40 text-amber-700",
    red: "border-red-500/40 text-red-700",
  };
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {tiles.map((t, i) => (
        <div key={i} className={`bg-card border-l-4 ${toneClass[t.tone]} border-y border-r border-border rounded-sm p-3`}
             data-testid={`pd-kpi-${i}`}>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
            <t.icon className="h-3 w-3" /> {t.label}
          </div>
          <div className="font-display font-black text-xl tabular mt-1">{t.value}</div>
          {t.sub && <div className="text-[10px] text-muted-foreground">{t.sub}</div>}
        </div>
      ))}
    </div>
  );
}

function FinancialsCard({ f }) {
  return (
    <Card title="Financial Snapshot" icon={Banknote} testid="pd-financials">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Row k="Contract Value" v={inr(f.contract_value)} />
        <Row k="PO Committed" v={inr(f.po_committed)} />
        <Row k="GRN Received" v={inr(f.grn_value)} />
        <Row k="Measurements Certified" v={inr(f.measurements_certified)} />
        <Row k="RA Bills Raised" v={inr(f.bills_raised)} sub={`${f.bills_count} bill(s)`} />
        <Row k="Retention Held" v={inr(f.retention_held)} />
        <Row k="TDS Deducted" v={inr(f.tds_deducted)} />
        <Row k="GST Charged" v={inr(f.gst_charged)} />
        <Row k="Payments Received" v={inr(f.payments_received)} sub={`${f.payments_count} payment(s)`} />
        <Row k="Outstanding" v={inr(f.outstanding)} tone={f.outstanding > 0 ? "amber" : "emerald"} />
        <Row k="Revenue Recognised" v={inr(f.revenue_recognised)} />
        <Row k="Cost Incurred" v={inr(f.cost_incurred)} sub="(GRN proxy)" />
        <Row k="Gross Profit" v={inr(f.gross_profit)} tone={f.gross_profit >= 0 ? "emerald" : "red"} />
        <Row k="GP %" v={pct(f.gp_pct)} tone={f.gp_pct >= 0 ? "emerald" : "red"} />
        <Row k="Billing Progress" v={pct(f.progress_billed_pct)} />
      </div>
    </Card>
  );
}

function ChartsCard({ execution, financials }) {
  const fundFlow = [
    { name: "Contract", value: financials.contract_value },
    { name: "PO Committed", value: financials.po_committed },
    { name: "GRN", value: financials.grn_value },
    { name: "Cert. Mmts", value: financials.measurements_certified },
    { name: "Bills", value: financials.bills_raised },
    { name: "Received", value: financials.payments_received },
  ];
  const flowColors = ["#2563eb", "#0ea5e9", "#06b6d4", "#10b981", "#f59e0b", "#22c55e"];
  return (
    <Card title="Manpower & Cashflow" icon={TrendingUp} testid="pd-charts">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">Manpower trend (last 30 days)</div>
          <div className="h-48">
            <ResponsiveContainer>
              <AreaChart data={execution.manpower_trend_30d}>
                <defs>
                  <linearGradient id="manp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2563eb" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#2563eb" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fontSize: 10 }} hide={execution.manpower_trend_30d?.length > 14} />
                <YAxis tick={{ fontSize: 10 }} width={28} />
                <Tooltip contentStyle={{ fontSize: 11 }} />
                <Area type="monotone" dataKey="manpower" stroke="#2563eb" strokeWidth={2} fill="url(#manp)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {execution.manpower_trend_30d?.length === 0 && (
            <div className="text-[11px] text-muted-foreground text-center py-3">No DPRs in the last 30 days.</div>
          )}
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">Cashflow waterfall</div>
          <div className="h-48">
            <ResponsiveContainer>
              <BarChart data={fundFlow}>
                <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} />
                <YAxis tick={{ fontSize: 10 }} width={42} tickFormatter={(v) => v >= 100000 ? (v / 100000).toFixed(1) + "L" : v} />
                <Tooltip contentStyle={{ fontSize: 11 }} formatter={(v) => inr(v)} />
                <Bar dataKey="value">
                  {fundFlow.map((_, i) => <Cell key={i} fill={flowColors[i]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </Card>
  );
}

function ProcurementCard({ p }) {
  return (
    <Card title="Procurement" icon={Truck} testid="pd-procurement">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Stat k="PR Count" v={p.pr_count} />
        <Stat k="PO Count" v={p.po_count} />
        <Stat k="GRN Count" v={p.grn_count} />
        <Stat k="Allocations" v={p.alloc_count} sub={`qty ${p.alloc_qty_total}`} />
      </div>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
        <StatusChips title="PR by status" data={p.pr_by_status} />
        <StatusChips title="PO by status" data={p.po_by_status} />
      </div>
    </Card>
  );
}

function ExecutionCard({ e }) {
  const cats = (e.manpower_by_category || []).map((c) => ({ name: c.category, value: c.count }));
  const PIE_COLORS = ["#2563eb", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#84cc16", "#f97316", "#3b82f6", "#a855f7"];
  return (
    <Card title="Site Execution" icon={Activity} testid="pd-execution">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <Stat k="DPRs (total)" v={e.dpr_count_total} sub={`${e.dpr_count_30d} in 30d`} />
        <Stat k="Last DPR" v={e.last_dpr_date || "—"} />
        <Stat k="Manpower today" v={e.manpower_today} />
        <Stat k="Avg manpower (30d)" v={e.manpower_avg_30d} />
        <Stat k="Measurements" v={e.measurements_count} />
        <Stat k="Active Deploys" v={e.deployment_count_active} />
      </div>
      {cats.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">Manpower by category</div>
          <div className="h-40">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={cats} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} innerRadius={32} paddingAngle={1}>
                  {cats.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      {e.measurements_by_status && Object.keys(e.measurements_by_status).length > 0 && (
        <div className="mt-2">
          <StatusChips title="Measurements by status" data={e.measurements_by_status} />
        </div>
      )}
    </Card>
  );
}

function SafetyCard({ s }) {
  return (
    <Card title="Safety" icon={ShieldAlert} testid="pd-safety">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <Stat k="Incidents" v={s.incidents_total} sub={`${s.incidents_open} open`} tone={s.incidents_open ? "red" : "emerald"} />
        <Stat k="PTW" v={s.ptw_total} />
        <Stat k="PPE Issued" v={s.ppe_issued_count} />
        <Stat k="Toolbox Talks" v={s.toolbox_talks_count} />
      </div>
      {Object.keys(s.incidents_by_severity || {}).length > 0 && (
        <div className="mt-3"><StatusChips title="Incidents by severity" data={s.incidents_by_severity} /></div>
      )}
      {Object.keys(s.ptw_by_status || {}).length > 0 && (
        <div className="mt-2"><StatusChips title="PTW by status" data={s.ptw_by_status} /></div>
      )}
    </Card>
  );
}

function RecentCard({ events }) {
  const tone = {
    dpr: "bg-blue-100 text-blue-900",
    ra_bill: "bg-emerald-100 text-emerald-900",
    payment: "bg-emerald-200 text-emerald-900",
    grn: "bg-cyan-100 text-cyan-900",
    measurement: "bg-amber-100 text-amber-900",
    safety: "bg-red-100 text-red-900",
  };
  return (
    <Card title="Recent Activity" icon={Activity} testid="pd-recent">
      {events?.length === 0 && <div className="text-sm text-muted-foreground">No recent activity yet.</div>}
      <ul className="divide-y divide-border -mx-4">
        {(events || []).map((e, i) => (
          <li key={i} className="px-4 py-2 flex items-start gap-2 text-[12.5px]">
            <span className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-sm shrink-0 ${tone[e.kind] || "bg-muted text-muted-foreground"}`}>{e.kind.replaceAll("_", " ")}</span>
            <span className="flex-1">{e.label}</span>
            <span className="text-[10px] text-muted-foreground">{(e.ts || "").slice(0, 10)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Card({ title, icon: Icon, children, testid }) {
  return (
    <div className="bg-card border border-border rounded-sm" data-testid={testid}>
      <div className="px-4 py-2.5 border-b border-border flex items-center gap-2">
        {Icon && <Icon className="h-3.5 w-3.5 text-primary" />}
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function Row({ k, v, sub, tone }) {
  const toneClass = tone === "amber" ? "text-amber-700"
    : tone === "red" ? "text-red-700"
    : tone === "emerald" ? "text-emerald-700" : "";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k}</div>
      <div className={`tabular font-semibold ${toneClass}`}>{v}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
function Stat({ k, v, sub, tone }) { return <Row k={k} v={v} sub={sub} tone={tone} />; }
function StatusChips({ title, data }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(data || {}).map(([k, v]) => (
          <span key={k} className="text-[11px] px-2 py-0.5 rounded-sm border border-border bg-background">
            {k.replaceAll("_", " ")} <span className="tabular font-bold ml-1">{v}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
