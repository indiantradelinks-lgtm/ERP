import { useEffect, useMemo, useState } from "react";
import {
  BarChart3, Calendar, Users, Boxes, TrendingUp, Clock, Search,
  AlertTriangle, ChevronRight,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line, Legend, PieChart, Pie, Cell,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const TABS = [
  { id: "monthly", label: "Monthly Trend", icon: Calendar },
  { id: "by-client", label: "By Client", icon: Users },
  { id: "by-service", label: "By Service", icon: Boxes },
  { id: "won-lost", label: "Win / Loss", icon: TrendingUp },
  { id: "deadline-tracker", label: "Deadline Tracker", icon: Clock },
  { id: "search", label: "Global Search", icon: Search },
];

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const PIE_COLORS = ["hsl(var(--primary))", "hsl(var(--chart-3))", "hsl(var(--chart-4))", "hsl(var(--chart-5))", "hsl(var(--destructive))"];

export default function SalesReports() {
  const [active, setActive] = useState("monthly");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (active === "search") { setData(null); return; }
    setLoading(true); setData(null);
    api.get(`/sales/reports/${active}`)
      .then((r) => setData(r.data))
      .catch((e) => { toast.error(e.response?.data?.detail || "Failed to load report"); setData(null); })
      .finally(() => setLoading(false));
  }, [active]);

  return (
    <div className="space-y-6" data-testid="sales-reports">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <BarChart3 className="h-3 w-3" /> Sales · Pipeline Analytics
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Sales Reports</h1>
        <p className="text-sm text-muted-foreground mt-1">Pipeline trend, win-rates, deadlines, and global search across enquiries / quotes / orders.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Button
              key={t.id}
              variant={active === t.id ? "default" : "outline"}
              className="rounded-sm h-9"
              onClick={() => setActive(t.id)}
              data-testid={`sreport-tab-${t.id}`}
            >
              <Icon className="h-3.5 w-3.5 mr-1.5" /> {t.label}
            </Button>
          );
        })}
      </div>

      <div className="bg-card border border-border rounded-sm p-5 min-h-[260px]" data-testid={`sreport-pane-${active}`}>
        {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {!loading && active === "monthly" && <MonthlyTrend rows={data || []} />}
        {!loading && active === "by-client" && <ByClient rows={data || []} />}
        {!loading && active === "by-service" && <ByService rows={data || []} />}
        {!loading && active === "won-lost" && <WonLost summary={data} />}
        {!loading && active === "deadline-tracker" && <DeadlineTracker rows={data || []} />}
        {active === "search" && <GlobalSearch />}
      </div>
    </div>
  );
}

function MonthlyTrend({ rows }) {
  if (!rows?.length) return <Empty />;
  const chart = rows.map((r) => ({ ...r, won_value: Number(r.won_value || 0) }));
  return (
    <div className="space-y-6">
      <div className="h-72 min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={11} />
            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} allowDecimals={false} />
            <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="total" name="Enquiries" stroke="hsl(var(--primary))" strokeWidth={2} />
            <Line type="monotone" dataKey="won" name="Won" stroke="hsl(var(--chart-3))" strokeWidth={2} />
            <Line type="monotone" dataKey="lost" name="Lost" stroke="hsl(var(--destructive))" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Month</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider"># Enquiries</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Won</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Lost</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Pipeline Value</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Won Value</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.month} className="hover:bg-muted/30" data-testid={`sreport-monthly-${r.month}`}>
              <TableCell className="font-mono-data text-xs">{r.month}</TableCell>
              <TableCell className="text-sm tabular">{r.total}</TableCell>
              <TableCell className="text-sm tabular text-success">{r.won}</TableCell>
              <TableCell className="text-sm tabular text-destructive">{r.lost}</TableCell>
              <TableCell className="text-sm tabular">{inr(r.pipeline_value)}</TableCell>
              <TableCell className="text-sm tabular font-bold">{inr(r.won_value)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ByClient({ rows }) {
  if (!rows?.length) return <Empty />;
  const top = rows.slice(0, 8).map((r) => ({ name: r.customer, value: r.pipeline_value }));
  return (
    <div className="space-y-6">
      <div className="h-72 min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={top}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={10} angle={-15} textAnchor="end" height={60} />
            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
            <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2 }}
              formatter={(v) => inr(v)} />
            <Bar dataKey="value" name="Pipeline Value" fill="hsl(var(--primary))" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Client</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider"># Enquiries</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Won</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Lost</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Win %</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Pipeline Value</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Won Value</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={`${r.client_id || r.customer}-${i}`} className="hover:bg-muted/30" data-testid={`sreport-client-${i}`}>
              <TableCell className="text-sm font-semibold">{r.customer}</TableCell>
              <TableCell className="text-sm tabular">{r.total}</TableCell>
              <TableCell className="text-sm tabular text-success">{r.won}</TableCell>
              <TableCell className="text-sm tabular text-destructive">{r.lost}</TableCell>
              <TableCell className="text-sm tabular">{r.win_ratio_pct != null ? `${r.win_ratio_pct}%` : "—"}</TableCell>
              <TableCell className="text-sm tabular">{inr(r.pipeline_value)}</TableCell>
              <TableCell className="text-sm tabular font-bold">{inr(r.won_value)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ByService({ rows }) {
  if (!rows?.length) return <Empty />;
  const pie = rows.map((r) => ({ name: (r.service || "—").replaceAll("_", " "), value: r.total }));
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="h-72 min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pie} dataKey="value" nameKey="name" outerRadius={100} label>
              {pie.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Service</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Total</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Won</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Lost</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Win %</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Won Value</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={`${r.service || "unknown"}-${i}`} className="hover:bg-muted/30" data-testid={`sreport-service-${r.service || "unknown"}`}>
              <TableCell className="text-sm font-semibold capitalize">{(r.service || "—").replaceAll("_", " ")}</TableCell>
              <TableCell className="text-sm tabular">{r.total}</TableCell>
              <TableCell className="text-sm tabular text-success">{r.won}</TableCell>
              <TableCell className="text-sm tabular text-destructive">{r.lost}</TableCell>
              <TableCell className="text-sm tabular">{r.win_ratio_pct != null ? `${r.win_ratio_pct}%` : "—"}</TableCell>
              <TableCell className="text-sm tabular font-bold">{inr(r.won_value)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function WonLost({ summary }) {
  if (!summary) return <Empty />;
  const data = [
    { name: "Won", value: summary.won || 0 },
    { name: "Lost", value: summary.lost || 0 },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
      <div className="h-56 md:col-span-1 min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" outerRadius={80} label>
              <Cell fill="hsl(var(--chart-3))" />
              <Cell fill="hsl(var(--destructive))" />
            </Pie>
            <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 2 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="md:col-span-2 grid grid-cols-2 gap-3">
        <Stat label="Won" value={summary.won} tone="success" />
        <Stat label="Lost" value={summary.lost} tone="danger" />
        <Stat label="Win Ratio" value={summary.win_ratio_pct != null ? `${summary.win_ratio_pct}%` : "—"} tone="primary" />
        <Stat label="Avg Cycle (days)" value={summary.avg_cycle_days ?? "—"} tone="info" />
      </div>
    </div>
  );
}

function DeadlineTracker({ rows }) {
  if (!rows?.length) return <Empty msg="No open enquiries with deadlines." />;
  const overdue = rows.filter((r) => r.bucket === "overdue").length;
  const dueSoon = rows.filter((r) => r.bucket === "due_soon").length;
  return (
    <div className="space-y-5">
      <div className="flex gap-3 flex-wrap">
        <Stat label="Overdue" value={overdue} tone="danger" icon={AlertTriangle} />
        <Stat label="Due ≤ 7d" value={dueSoon} tone="warning" icon={Clock} />
        <Stat label="Upcoming" value={rows.length - overdue - dueSoon} tone="info" />
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Bucket</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Enquiry #</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Client / Site</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Deadline</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Priority</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Services</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`sreport-deadline-${r.id}`}>
              <TableCell>
                <StatusBadge text={r.bucket?.replaceAll("_", " ")} tone={r.bucket === "overdue" ? "danger" : r.bucket === "due_soon" ? "warning" : "info"} />
              </TableCell>
              <TableCell className="font-mono-data text-xs">{r.enquiry_no}</TableCell>
              <TableCell className="text-sm font-semibold">
                {r.customer}
                <div className="text-[11px] text-muted-foreground font-normal">{r.site_code || ""} {r.site_location || ""}</div>
              </TableCell>
              <TableCell className="font-mono-data text-xs">{r.submission_deadline}</TableCell>
              <TableCell><StatusBadge text={r.priority || "—"} tone={r.priority === "high" ? "danger" : r.priority === "medium" ? "warning" : "neutral"} /></TableCell>
              <TableCell className="text-xs">{(r.service_categories || []).join(", ").replaceAll("_", " ") || "—"}</TableCell>
              <TableCell className="text-sm tabular">{inr(r.expected_value)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function GlobalSearch() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!q.trim()) { setResult(null); return; }
    setBusy(true);
    try {
      const { data } = await api.get(`/sales/search?q=${encodeURIComponent(q.trim())}`);
      setResult(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Search failed");
    } finally { setBusy(false); }
  };

  const totalHits = useMemo(() => {
    if (!result) return 0;
    return (result.enquiries?.length || 0) + (result.quotations?.length || 0) + (result.orders?.length || 0);
  }, [result]);

  return (
    <div className="space-y-5">
      <div className="flex gap-2">
        <div className="relative flex-1 max-w-xl">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9 h-9 rounded-sm"
            placeholder="Search by code, customer PO, scope keyword…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
            data-testid="sales-search-input"
          />
        </div>
        <Button className="h-9 rounded-sm" onClick={run} disabled={busy} data-testid="sales-search-go">{busy ? "Searching…" : "Search"}</Button>
      </div>
      {result && (
        <div className="text-xs text-muted-foreground">{totalHits} match{totalHits !== 1 ? "es" : ""} across enquiries, quotations and orders.</div>
      )}
      {result?.enquiries?.length > 0 && (
        <SearchBucket title="Enquiries" rows={result.enquiries.map((r) => ({
          code: r.enquiry_no, who: r.customer, sub: r.scope_of_work || r.scope || r.site_location,
          tone: r.status === "won" ? "success" : r.status === "lost" ? "danger" : "info", status: r.status,
          id: r.id,
        }))} />
      )}
      {result?.quotations?.length > 0 && (
        <SearchBucket title="Quotations" rows={result.quotations.map((r) => ({
          code: r.quote_number, who: r.client, sub: r.project,
          tone: r.status === "won" ? "success" : r.status === "lost" ? "danger" : "info", status: r.status,
          id: r.id,
        }))} />
      )}
      {result?.orders?.length > 0 && (
        <SearchBucket title="Orders" rows={result.orders.map((r) => ({
          code: r.order_no, who: r.customer, sub: r.customer_po || r.scope,
          tone: r.status === "active" ? "success" : "neutral", status: r.status,
          id: r.id,
        }))} />
      )}
    </div>
  );
}

function SearchBucket({ title, rows }) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2 flex items-center gap-1">
        <ChevronRight className="h-3 w-3" /> {title} ({rows.length})
      </div>
      <ul className="divide-y divide-border border border-border rounded-sm">
        {rows.map((r) => (
          <li key={r.id} className="px-3 py-2 flex items-center gap-3 hover:bg-muted/30" data-testid={`sales-search-${r.id}`}>
            <span className="font-mono-data text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded-sm font-bold">{r.code}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold truncate">{r.who || "—"}</div>
              <div className="text-[11px] text-muted-foreground truncate">{r.sub || ""}</div>
            </div>
            {r.status && <StatusBadge text={r.status?.replaceAll("_", " ")} tone={r.tone} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, tone = "neutral", icon: Icon }) {
  const c = { primary: "text-primary", success: "text-success", danger: "text-destructive",
    warning: "text-warning", info: "text-chart-3", neutral: "text-foreground" }[tone];
  return (
    <div className="bg-muted/30 border border-border rounded-sm p-4 flex items-center gap-3 min-w-[140px]">
      {Icon && <Icon className={`h-5 w-5 ${c}`} />}
      <div>
        <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className={`font-display font-black text-2xl tabular ${c}`}>{value ?? 0}</div>
      </div>
    </div>
  );
}

function Empty({ msg = "No data yet." }) {
  return <div className="text-sm text-muted-foreground text-center py-10">{msg}</div>;
}
