// HR Phase 5 — Final HR Dashboard, Reports Center, Audit Trail,
// Integration Review and Final Controls
import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { useNavigate } from "react-router-dom";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import {
  LayoutDashboard, FileText, History, Layers, ShieldCheck, RefreshCw, Filter, Check, X,
} from "lucide-react";

const monthIso = () => new Date().toISOString().slice(0, 7);
const inr = (n) => (typeof n === "number" ? `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : n);

const SEVERITY_TONE = {
  high: "border-rose-300 bg-rose-50",
  medium: "border-amber-300 bg-amber-50",
  low: "border-slate-200 bg-slate-50",
  info: "border-slate-200 bg-white",
};

// ─────────── FINAL DASHBOARD (30 cards) ───────────
function FinalDashboard() {
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const load = async () => {
    try { setD((await api.get("/hr5/dashboard")).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  if (!d) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  const renderValue = (v) => {
    if (typeof v === "number") return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
    if (Array.isArray(v)) {
      return (
        <div className="text-xs space-y-0.5 mt-1">
          {v.slice(0, 4).map((x, i) => (
            <div key={i} className="flex justify-between">
              <span className="truncate max-w-[140px]">{x.project_code || x.skill || JSON.stringify(x)}</span>
              <span className="font-mono">{x.count}</span>
            </div>
          ))}
          {v.length === 0 && <div className="text-muted-foreground">—</div>}
        </div>
      );
    }
    return String(v);
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <div className="text-sm text-muted-foreground">Real-time KPIs — {d.total_cards} cards · as of {(d.as_of || "").slice(0, 16)}</div>
        <Button size="sm" variant="outline" onClick={load} data-testid="hr5-dash-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Refresh</Button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {d.cards.map(c => (
          <Card key={c.key}
                onClick={() => c.link && nav(c.link)}
                className={`cursor-pointer hover:shadow transition border ${SEVERITY_TONE[c.severity]}`}
                data-testid={`hr5-card-${c.key}`}>
            <CardContent className="p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{c.label}</div>
              {typeof c.value === "number" || typeof c.value === "string" ? (
                <div className="text-xl font-semibold mt-1">{renderValue(c.value)}</div>
              ) : renderValue(c.value)}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ─────────── REPORTS CENTER ───────────
function ReportsCenter() {
  const [catalog, setCatalog] = useState([]);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [data, setData] = useState(null);
  const [month, setMonth] = useState(monthIso());

  useEffect(() => { (async () => {
    try { setCatalog((await api.get("/hr5/reports/catalog")).data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  })(); }, []);

  const categories = useMemo(() => ["all", ...new Set(catalog.map(c => c.category))], [catalog]);
  const filtered = catalog.filter(c => filter === "all" || c.category === filter);

  const run = async (rep) => {
    setSelected(rep); setData(null);
    try {
      const params = {};
      if (month) params.month = month;
      const r = await api.get(`/hr5/reports/${rep.key}`, { params });
      setData(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const cols = useMemo(() => {
    const rows = data?.rows || [];
    if (rows.length === 0) return [];
    const seen = new Set();
    rows.slice(0, 10).forEach(r => Object.keys(r).forEach(k => seen.add(k)));
    return [...seen].slice(0, 8);
  }, [data]);

  return (
    <div className="grid grid-cols-12 gap-4">
      <Card className="col-span-4 lg:col-span-3">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2"><FileText className="h-4 w-4" /> Reports ({catalog.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="h-8" data-testid="hr5-rep-filter"><SelectValue /></SelectTrigger>
            <SelectContent>{categories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
          </Select>
          <Input value={month} onChange={e => setMonth(e.target.value)} placeholder="YYYY-MM" className="h-8" data-testid="hr5-rep-month" />
          <div className="space-y-1 max-h-[480px] overflow-y-auto">
            {filtered.map(r => (
              <button key={r.key}
                      onClick={() => run(r)}
                      className={`w-full text-left text-xs px-2 py-1 rounded hover:bg-slate-100 ${selected?.key === r.key ? "bg-blue-50 font-medium" : ""}`}
                      data-testid={`hr5-rep-${r.key}`}>
                <div>{r.label}</div>
                <div className="text-[10px] text-muted-foreground">{r.category}</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="col-span-8 lg:col-span-9">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            {selected ? `${selected.label} — ${data?.count || 0} row(s)` : "Select a report"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!selected && <div className="text-sm text-muted-foreground py-6 text-center">Pick a report from the left</div>}
          {selected && !data && <div className="text-sm text-muted-foreground py-6 text-center">Loading…</div>}
          {selected && data && (
            <>
              {(data.rows || []).length === 0 && <div className="text-sm text-muted-foreground py-6 text-center">No data</div>}
              {(data.rows || []).length > 0 && (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {cols.map(k => <TableHead key={k} className="text-xs">{k}</TableHead>)}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.rows.slice(0, 200).map((r, i) => (
                        <TableRow key={i} data-testid={`hr5-rep-row-${i}`}>
                          {cols.map(k => (
                            <TableCell key={k} className="text-xs">
                              {typeof r[k] === "object" ? JSON.stringify(r[k])?.slice(0, 40) :
                                typeof r[k] === "number" ? r[k].toLocaleString("en-IN") :
                                String(r[k] ?? "—").slice(0, 60)}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─────────── AUDIT TRAIL ───────────
function AuditTrailView() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ resource: "", employee_id: "" });
  const load = async () => {
    try {
      const params = {};
      if (filter.resource) params.resource = filter.resource;
      if (filter.employee_id) params.employee_id = filter.employee_id;
      const r = await api.get("/hr5/audit-trail", { params });
      setRows(r.data.rows || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><History className="h-4 w-4" /> HR Audit Trail ({rows.length})</CardTitle>
        <div className="flex gap-2">
          <Input placeholder="Resource (e.g. attendance)" value={filter.resource} onChange={e => setFilter({ ...filter, resource: e.target.value })} className="w-44 h-8" data-testid="hr5-audit-resource" />
          <Input placeholder="Employee ID" value={filter.employee_id} onChange={e => setFilter({ ...filter, employee_id: e.target.value })} className="w-44 h-8" data-testid="hr5-audit-empid" />
          <Button size="sm" onClick={load} data-testid="hr5-audit-apply"><Filter className="h-4 w-4 mr-1" /> Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>At</TableHead><TableHead>Action</TableHead>
            <TableHead>Resource</TableHead><TableHead>Record ID</TableHead>
            <TableHead>User</TableHead><TableHead>IP</TableHead>
            <TableHead>Source</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">No audit entries</TableCell></TableRow>}
            {rows.slice(0, 200).map((r, i) => (
              <TableRow key={i} data-testid={`hr5-audit-row-${i}`}>
                <TableCell className="text-xs">{(r.at || "").slice(0, 19)}</TableCell>
                <TableCell><Badge variant="outline" className="text-xs">{r.action}</Badge></TableCell>
                <TableCell className="text-xs">{r.resource}</TableCell>
                <TableCell className="font-mono text-[10px]">{(r.record_id || "").slice(0, 12)}</TableCell>
                <TableCell className="text-xs">{r.by_name || "—"}</TableCell>
                <TableCell className="text-xs">{r.ip || "—"}</TableCell>
                <TableCell className="text-[10px] text-muted-foreground">{r.source}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─────────── INTEGRATION REVIEW ───────────
function IntegrationView() {
  const [data, setData] = useState(null);
  const load = async () => {
    try { setData((await api.get("/hr5/integration-review")).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Layers className="h-4 w-4" /> Module Integration Review ({data.health_pct}% healthy)</CardTitle>
        <Button size="sm" variant="outline" onClick={load} data-testid="hr5-integ-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Refresh</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Module</TableHead><TableHead>Signal</TableHead>
            <TableHead>Status</TableHead><TableHead>Detail</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data.checks.map((c, i) => (
              <TableRow key={i} data-testid={`hr5-integ-${c.module.replace(/\//g, "-")}-${i}`}>
                <TableCell className="font-medium">{c.module}</TableCell>
                <TableCell>{c.signal}</TableCell>
                <TableCell>
                  {c.status === "ok"
                    ? <Badge className="bg-emerald-100 text-emerald-900 border-emerald-300"><Check className="h-3 w-3 inline mr-1" />OK</Badge>
                    : <Badge className="bg-rose-100 text-rose-900 border-rose-300"><X className="h-3 w-3 inline mr-1" />Missing</Badge>}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{c.detail}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─────────── FINAL CONTROLS (preflight) ───────────
function ControlsView() {
  const [month, setMonth] = useState(monthIso());
  const [data, setData] = useState(null);
  const load = async () => {
    try { setData((await api.get(`/hr5/controls/preflight?month=${month}`)).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Final Controls — Preflight ({data?.ok_count || 0}/{data?.total || 0})</CardTitle>
        <div className="flex gap-2">
          <Input value={month} onChange={e => setMonth(e.target.value)} className="w-32 h-8" data-testid="hr5-ctrl-month" />
          <Button size="sm" onClick={load} data-testid="hr5-ctrl-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Refresh</Button>
        </div>
      </CardHeader>
      <CardContent>
        {!data && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}
        {data && (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Control</TableHead><TableHead>OK</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.controls.map(c => (
                <TableRow key={c.key} data-testid={`hr5-ctrl-${c.key}`}>
                  <TableCell>{c.label}</TableCell>
                  <TableCell>
                    {c.ok
                      ? <Badge className="bg-emerald-100 text-emerald-900 border-emerald-300"><Check className="h-3 w-3 inline mr-1" />OK</Badge>
                      : <Badge className="bg-amber-100 text-amber-900 border-amber-300"><X className="h-3 w-3 inline mr-1" />Action Needed</Badge>}
                  </TableCell>
                  <TableCell className="text-xs">{typeof c.value === "number" ? c.value.toLocaleString("en-IN") : String(c.value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────── PARENT HUB ───────────
export default function HrPhase5() {
  const [tab, setTab] = useState("dashboard");
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <LayoutDashboard className="h-5 w-5" /> HR Command Center — Final Consolidation
        </h1>
        <p className="text-sm text-muted-foreground">Phase 5 — real-time KPIs, reports center, audit trail, integration review and final controls</p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="dashboard" data-testid="hr5-tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="reports" data-testid="hr5-tab-reports">Reports Center</TabsTrigger>
          <TabsTrigger value="audit" data-testid="hr5-tab-audit">Audit Trail</TabsTrigger>
          <TabsTrigger value="integration" data-testid="hr5-tab-integration">Integration</TabsTrigger>
          <TabsTrigger value="controls" data-testid="hr5-tab-controls">Final Controls</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><FinalDashboard /></TabsContent>
        <TabsContent value="reports"><ReportsCenter /></TabsContent>
        <TabsContent value="audit"><AuditTrailView /></TabsContent>
        <TabsContent value="integration"><IntegrationView /></TabsContent>
        <TabsContent value="controls"><ControlsView /></TabsContent>
      </Tabs>
    </div>
  );
}
