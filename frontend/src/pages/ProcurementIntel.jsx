import { useEffect, useMemo, useState } from "react";
import { Award, IndianRupee, ShieldAlert, Search, Wallet, BookOpen, Layers, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const TABS = [
  { id: "vendors", label: "Vendor Performance", icon: Award, url: "/vendor-performance" },
  { id: "budgets", label: "Budget vs Actual", icon: Wallet, url: "/procurement/budgets" },
  { id: "reservations", label: "Reservations", icon: Layers, url: "/procurement/reservations" },
  { id: "audit", label: "Audit Explorer", icon: History, url: "/audit/explorer?limit=100" },
];

export default function ProcurementIntel() {
  const [active, setActive] = useState("vendors");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true); setData(null);
    const tab = TABS.find((t) => t.id === active);
    if (!tab) return;
    try { const { data } = await api.get(tab.url); setData(data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [active]);

  return (
    <div className="space-y-6" data-testid="proc-intel-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <BookOpen className="h-3 w-3" /> Procurement · Insights
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Procurement Intelligence</h1>
        <p className="text-sm text-muted-foreground mt-1">Vendor performance, budget vs actual, soft reservations and a global audit log explorer.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Button key={t.id} variant={active === t.id ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setActive(t.id)} data-testid={`pintel-tab-${t.id}`}>
              <Icon className="h-3.5 w-3.5 mr-1.5" /> {t.label}
            </Button>
          );
        })}
      </div>
      <div className="bg-card border border-border rounded-sm p-5 min-h-[260px]" data-testid={`pintel-pane-${active}`}>
        {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {!loading && active === "vendors" && <VendorPerf data={data} />}
        {!loading && active === "budgets" && <Budgets data={data} />}
        {!loading && active === "reservations" && <Reservations data={data} />}
        {!loading && active === "audit" && <AuditExplorer initial={data} />}
      </div>
    </div>
  );
}

const GRADE_TONE = { "A+": "success", A: "success", B: "info", C: "warning", D: "danger" };

function VendorPerf({ data }) {
  if (!data?.vendors?.length) return <Empty />;
  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">{data.vendors.length} vendors · scored from PO + GRN + RFQ history</div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Score</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Grade</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">PO Count</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">PO Value</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Quality %</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">On-Time %</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">RFQ Resp %</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {data.vendors.map((v) => (
            <TableRow key={v.vendor_id} data-testid={`vperf-row-${v.vendor_id}`}>
              <TableCell className="text-sm font-semibold">{v.vendor_name}</TableCell>
              <TableCell className="font-mono-data text-lg font-bold tabular">{v.score ?? "—"}</TableCell>
              <TableCell><StatusBadge text={v.grade} tone={GRADE_TONE[v.grade] || "neutral"} /></TableCell>
              <TableCell className="font-mono-data text-sm tabular">{v.po_count}</TableCell>
              <TableCell className="font-mono-data text-sm tabular">{inr(v.po_value)}</TableCell>
              <TableCell className="text-sm">{v.quality_pct != null ? `${v.quality_pct}%` : "—"}</TableCell>
              <TableCell className="text-sm">{v.on_time_pct != null ? `${v.on_time_pct}%` : "—"}</TableCell>
              <TableCell className="text-sm">{v.response_pct != null ? `${v.response_pct}%` : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Budgets({ data }) {
  if (!data?.budgets?.length) return <Empty msg="No PRs with a budget reference yet." />;
  return (
    <Table>
      <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableHead className="text-[10px] uppercase tracking-wider">Budget Ref</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Departments</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">PRs</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">POs</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Committed</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {data.budgets.map((b) => (
          <TableRow key={b.budget_reference} data-testid={`budget-row-${b.budget_reference}`}>
            <TableCell className="font-mono-data text-sm font-bold">{b.budget_reference}</TableCell>
            <TableCell className="text-xs">{b.departments?.join(", ") || "—"}</TableCell>
            <TableCell className="font-mono-data text-sm tabular">{b.pr_count}</TableCell>
            <TableCell className="font-mono-data text-sm tabular">{b.po_count}</TableCell>
            <TableCell className="font-mono-data text-sm tabular font-bold">{inr(b.committed_value)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Reservations({ data }) {
  if (!data) return <Empty />;
  if (!data.items?.length) return <Empty msg={`No reservations · ${data.open_pr_count} open PRs but none match existing inventory items.`} />;
  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">{data.open_pr_count} open PRs hold soft reservations against {data.items.length} inventory items.</div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">On hand</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Reserved</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Available</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Shortfall</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {data.items.map((r) => (
            <TableRow key={r.id} data-testid={`resv-row-${r.id}`}>
              <TableCell className="text-sm font-semibold">{r.name}</TableCell>
              <TableCell className="font-mono-data text-sm tabular">{r.on_hand} {r.unit}</TableCell>
              <TableCell className="font-mono-data text-sm tabular text-warning">{r.reserved}</TableCell>
              <TableCell className={`font-mono-data text-sm tabular font-bold ${r.available < 0 ? "text-destructive" : "text-success"}`}>{r.available}</TableCell>
              <TableCell className="font-mono-data text-sm tabular text-destructive">{r.shortfall > 0 ? r.shortfall : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function AuditExplorer({ initial }) {
  const [filters, setFilters] = useState({ resource: "", action: "", user_id: "", from_date: "", to_date: "" });
  const [data, setData] = useState(initial);

  const run = async () => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
    params.set("limit", "200");
    try { const { data } = await api.get(`/audit/explorer?${params}`); setData(data); }
    catch (e) { toast.error(e.response?.data?.detail || "Search failed"); }
  };

  useEffect(() => { setData(initial); }, [initial]);

  return (
    <div className="space-y-4" data-testid="audit-explorer">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <select value={filters.resource} onChange={(e) => setFilters({ ...filters, resource: e.target.value })} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="audit-resource">
          <option value="">All resources</option>
          {(initial?.resources || []).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="audit-action">
          <option value="">All actions</option>
          {(initial?.actions || []).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <Input placeholder="User ID" value={filters.user_id} onChange={(e) => setFilters({ ...filters, user_id: e.target.value })} className="h-9 rounded-sm" data-testid="audit-user" />
        <Input type="date" value={filters.from_date} onChange={(e) => setFilters({ ...filters, from_date: e.target.value })} className="h-9 rounded-sm" data-testid="audit-from" />
        <Input type="date" value={filters.to_date} onChange={(e) => setFilters({ ...filters, to_date: e.target.value })} className="h-9 rounded-sm" data-testid="audit-to" />
      </div>
      <Button className="h-9 rounded-sm" onClick={run} data-testid="audit-go"><Search className="h-3.5 w-3.5 mr-1.5" /> Search</Button>
      {data && <div className="text-xs text-muted-foreground">{data.count} entries</div>}
      <div className="max-h-[500px] overflow-y-auto border border-border rounded-sm">
        <Table>
          <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40 sticky top-0">
            <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">User</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Action</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Resource</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Record</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">IP</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.rows || []).map((r, i) => (
              <TableRow key={`${r.id || i}`} data-testid={`audit-row-${i}`}>
                <TableCell className="font-mono-data text-[10px]">{(r.created_at || "").slice(0, 19).replace("T", " ")}</TableCell>
                <TableCell className="text-xs">{r.user_name || r.user_id || "—"}</TableCell>
                <TableCell><StatusBadge text={r.action} tone="info" /></TableCell>
                <TableCell className="text-xs">{r.resource}</TableCell>
                <TableCell className="font-mono-data text-[10px] truncate max-w-[200px]">{r.record_id || "—"}</TableCell>
                <TableCell className="font-mono-data text-[10px]">{r.ip || "—"}</TableCell>
              </TableRow>
            ))}
            {(!data?.rows || data.rows.length === 0) && <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-6">No entries match the filters.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function Empty({ msg = "No data yet." }) {
  return <div className="text-sm text-muted-foreground text-center py-10">{msg}</div>;
}
