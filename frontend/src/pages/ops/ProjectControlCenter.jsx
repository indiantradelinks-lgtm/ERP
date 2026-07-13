/**
 * Project Control Center · P&O Phase 4
 *
 * Two modes:
 *   • Portfolio view (no project selected) — KPI counter grid + project list
 *   • Single-project view — module tabs (manpower / material / safety / logistics /
 *     procurement / accounts / finance) + blockers + alerts + transition actions
 *
 * Backend: /api/proj-phase4/control-center · /control-center/{id} ·
 *           /blockers/{id} · /alerts · /transition/{id}
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Layers, RefreshCcw, AlertTriangle, BellRing, Users, Package,
  ShieldAlert, Truck, Briefcase, DollarSign, Wallet, ChevronRight, CheckCircle2,
} from "lucide-react";

const TRANSITIONS = ["active", "on_hold", "completed", "closure_pending", "closed"];

export default function ProjectControlCenter() {
  const [portfolio, setPortfolio] = useState(null);
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [detail, setDetail]       = useState(null);
  const [alerts, setAlerts]       = useState([]);
  const [busy, setBusy]           = useState(false);

  useEffect(() => { loadPortfolio(); }, []);
  useEffect(() => {
    if (projectId) { loadDetail(); loadAlerts(); }
    else { setDetail(null); setAlerts([]); }
  }, [projectId]);

  const loadPortfolio = async () => {
    setBusy(true);
    try {
      const [a, b] = await Promise.all([
        api.get("/proj-phase4/control-center"),
        api.get("/projects"),
      ]);
      setPortfolio(a.data); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
    setBusy(false);
  };
  const loadDetail = async () => {
    try {
      const { data } = await api.get(`/proj-phase4/control-center/${projectId}`);
      setDetail(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  const loadAlerts = async () => {
    try {
      const { data } = await api.get(`/proj-phase4/alerts`, { params: { project_id: projectId, acknowledged: false } });
      setAlerts(data || []);
    } catch (e) { /* silent */ }
  };

  const ackAlert = async (a) => {
    const note = window.prompt("Acknowledgement note (optional):") ?? "";
    try { await api.post(`/proj-phase4/alerts/${a.id}/ack`, { note }); toast.success("Acknowledged"); loadAlerts(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const transition = async (to) => {
    try {
      const chk = await api.get(`/proj-phase4/transition-check/${projectId}`, { params: { to } });
      if (chk.data.blocked) {
        const blockerStr = chk.data.blockers.map((b) => `• [${b.severity}] ${b.message}`).join("\n");
        const reason = window.prompt(`Transition to ${to} is BLOCKED by:\n\n${blockerStr}\n\nEnter override reason (Director/GM only) or cancel:`);
        if (!reason) return;
        await api.post(`/proj-phase4/transition/${projectId}`, null, { params: { to, override_reason: reason } });
        toast.success(`Transitioned (override): ${to}`);
      } else {
        if (!window.confirm(`Transition project status to '${to}'?`)) return;
        await api.post(`/proj-phase4/transition/${projectId}`, null, { params: { to } });
        toast.success(`Transitioned to ${to}`);
      }
      loadDetail(); loadAlerts(); loadPortfolio();
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (detail && typeof detail === "object") toast.error(detail.message + ": " + JSON.stringify(detail.blockers));
      else toast.error(detail || "Transition failed");
    }
  };

  if (!projectId) {
    return <PortfolioView portfolio={portfolio} projects={projects} busy={busy}
                          onSelect={setProjectId} onRefresh={loadPortfolio} />;
  }
  if (!detail) return (
    <div className="p-6 text-slate-400" data-testid="page-control-center">
      <button onClick={() => setProjectId("")} className="text-sm text-primary mb-2" data-testid="cc-back">← Back to portfolio</button>
      Loading…
    </div>
  );

  return (
    <div className="p-6 space-y-4" data-testid="page-control-center-detail">
      <button onClick={() => setProjectId("")} className="text-sm text-primary inline-flex items-center mb-1" data-testid="cc-back">← Back to portfolio</button>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Layers className="h-6 w-6 text-primary" />
            <span>{detail.project.code}</span>
            <span className="text-muted-foreground font-normal text-lg">· {detail.project.name}</span>
            <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusTone(detail.project.status)}`}>{detail.project.status}</span>
          </h1>
          <p className="text-sm text-muted-foreground">{detail.project.client || "—"}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {TRANSITIONS.map((t) => (
            <Button key={t} size="sm" variant="outline" onClick={() => transition(t)} disabled={detail.project.status === t} data-testid={`cc-tr-${t}`}>
              → {t}
            </Button>
          ))}
          <Button size="sm" variant="outline" onClick={loadDetail}><RefreshCcw className="h-3.5 w-3.5 mr-1"/>Refresh</Button>
        </div>
      </div>

      {alerts.length > 0 && (
        <Card className="border-amber-300 bg-amber-50/30">
          <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2 text-amber-700"><BellRing className="h-4 w-4" /> Active Alerts ({alerts.length})</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-1">
              {alerts.map((a) => (
                <div key={a.id} className="flex items-center justify-between text-sm border-b py-1" data-testid={`cc-alert-${a.id}`}>
                  <div>
                    <span className={`mr-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${severityTone(a.severity)}`}>{a.severity}</span>
                    <span className="font-medium">{a.title}</span>
                    <span className="text-muted-foreground"> — {a.detail}</span>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => ackAlert(a)} data-testid={`cc-ack-${a.id}`}>Acknowledge</Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {detail.blockers_active.length > 0 && (
        <BlockerCard title="Pre-start / Active Blockers" rows={detail.blockers_active} testid="cc-blockers-active" />
      )}
      {detail.blockers_closure.length > 0 && (
        <BlockerCard title="Closure Blockers" rows={detail.blockers_closure} testid="cc-blockers-closure" />
      )}

      <Tabs defaultValue="manpower">
        <TabsList>
          <TabsTrigger value="manpower" data-testid="cc-tab-manpower"><Users className="h-3.5 w-3.5 mr-1" />Manpower</TabsTrigger>
          <TabsTrigger value="material" data-testid="cc-tab-material"><Package className="h-3.5 w-3.5 mr-1" />Material</TabsTrigger>
          <TabsTrigger value="safety" data-testid="cc-tab-safety"><ShieldAlert className="h-3.5 w-3.5 mr-1" />Safety</TabsTrigger>
          <TabsTrigger value="logistics" data-testid="cc-tab-logistics"><Truck className="h-3.5 w-3.5 mr-1" />Logistics</TabsTrigger>
          <TabsTrigger value="procurement" data-testid="cc-tab-procurement"><Briefcase className="h-3.5 w-3.5 mr-1" />Procurement</TabsTrigger>
          <TabsTrigger value="accounts" data-testid="cc-tab-accounts"><DollarSign className="h-3.5 w-3.5 mr-1" />Accounts</TabsTrigger>
          <TabsTrigger value="finance" data-testid="cc-tab-finance"><Wallet className="h-3.5 w-3.5 mr-1" />Finance</TabsTrigger>
        </TabsList>

        <TabsContent value="manpower"><MetricGrid rows={[
          ["Planned",                detail.manpower.planned_count],
          ["Deployed",               detail.manpower.deployed_count],
          ["Present Today",          detail.manpower.deployed_present_today],
          ["Absent Today",           detail.manpower.absent_today, "alert"],
          ["Overtime Today",         detail.manpower.overtime_today],
          ["Demobilised",            detail.manpower.demobilised_count],
          ["Replacement Pending",    detail.manpower.pending_replacement_count, "alert"],
          ["Shortage",               detail.manpower.shortage_count, "alert"],
          ["Planned Cost (₹)",       `₹ ${Number(detail.manpower.planned_cost).toLocaleString("en-IN")}`],
        ]} />{detail.manpower.skill_breakdown && Object.keys(detail.manpower.skill_breakdown).length > 0 && (
          <Card className="mt-3"><CardHeader className="pb-2"><CardTitle className="text-sm">Skill Mix (Active)</CardTitle></CardHeader>
            <CardContent className="text-xs space-y-1">
              {Object.entries(detail.manpower.skill_breakdown).map(([k, v]) => (
                <div key={k} className="flex justify-between"><span>{k}</span><span className="font-mono font-bold">{v}</span></div>
              ))}
            </CardContent></Card>
        )}</TabsContent>

        <TabsContent value="material"><MetricGrid rows={[
          ["Planned Qty",          Number(detail.material.planned_qty).toLocaleString("en-IN")],
          ["Planned Cost",         `₹ ${Number(detail.material.planned_cost).toLocaleString("en-IN")}`],
          ["Issued Lines",         detail.material.issued_count],
          ["Consumed",             detail.material.consumed_count],
          ["Returned",             detail.material.returned_count],
          ["Pending Returnable",   detail.material.pending_returnable, "alert"],
          ["Damaged / Lost",       detail.material.damaged_count, "alert"],
          ["PO Committed",         `₹ ${Number(detail.material.po_committed).toLocaleString("en-IN")}`],
          ["Material Cost",        `₹ ${Number(detail.material.material_cost).toLocaleString("en-IN")}`, "highlight"],
        ]} /></TabsContent>

        <TabsContent value="safety"><MetricGrid rows={[
          ["Permits Active",        detail.safety.permits_active],
          ["Expiring (7 days)",     detail.safety.permits_expiring_in_7d, "alert"],
          ["Expired",               detail.safety.permits_expired, "alert"],
          ["Safety Issues Open",    detail.safety.safety_issues_open],
          ["Critical Open",         detail.safety.critical_safety_open, "alert"],
          ["Observations",          detail.safety.observations_logged],
          ["Readiness",             detail.safety.readiness, detail.safety.readiness === "ready" ? "ok" : "alert"],
          ["Safety Cost",           `₹ ${Number(detail.safety.safety_cost).toLocaleString("en-IN")}`],
        ]} /></TabsContent>

        <TabsContent value="logistics"><MetricGrid rows={[
          ["Pending Dispatches",    detail.logistics.pending_dispatches, "alert"],
          ["In Transit",            detail.logistics.in_transit],
          ["Delivered",             detail.logistics.delivered],
          ["Transit Damage",        detail.logistics.transit_damage, "alert"],
          ["Logistics Cost",        `₹ ${Number(detail.logistics.logistics_cost).toLocaleString("en-IN")}`, "highlight"],
        ]} /></TabsContent>

        <TabsContent value="procurement"><MetricGrid rows={[
          ["POs",                   detail.procurement.purchase_orders_count],
          ["POs Pending",           detail.procurement.purchase_orders_pending, "alert"],
          ["PO Value",              `₹ ${Number(detail.procurement.purchase_orders_value).toLocaleString("en-IN")}`],
          ["Vendor Bills",          detail.procurement.vendor_bills_count],
          ["Bills Pending",         detail.procurement.vendor_bills_pending, "alert"],
          ["Vendor Cost",           `₹ ${Number(detail.procurement.vendor_cost).toLocaleString("en-IN")}`, "highlight"],
          ["Subcontract Items",     detail.procurement.subcontract_count],
          ["Subcontract Value",     `₹ ${Number(detail.procurement.subcontract_value).toLocaleString("en-IN")}`],
        ]} /></TabsContent>

        <TabsContent value="accounts"><MetricGrid rows={[
          ["Work Order Value",      `₹ ${Number(detail.accounts.work_order_value).toLocaleString("en-IN")}`],
          ["Invoice Raised",        `₹ ${Number(detail.accounts.invoice_raised).toLocaleString("en-IN")}`],
          ["Collection",            `₹ ${Number(detail.accounts.collection).toLocaleString("en-IN")}`],
          ["Outstanding",           `₹ ${Number(detail.accounts.outstanding_receivable).toLocaleString("en-IN")}`, "alert"],
          ["Pending Billing",       `₹ ${Number(detail.accounts.pending_billing).toLocaleString("en-IN")}`, "alert"],
          ["Total Cost",            `₹ ${Number(detail.accounts.total_cost).toLocaleString("en-IN")}`],
          ["Profit / Loss",         `₹ ${Number(detail.accounts.profit_or_loss).toLocaleString("en-IN")}`, detail.accounts.profit_or_loss >= 0 ? "ok" : "alert"],
          ["Margin %",              `${detail.accounts.margin_pct}%`, "highlight"],
        ]} /></TabsContent>

        <TabsContent value="finance"><MetricGrid rows={[
          ["Approved Budget",       `₹ ${Number(detail.finance.approved_budget).toLocaleString("en-IN")}`],
          ["Actual Cost",           `₹ ${Number(detail.finance.actual_cost).toLocaleString("en-IN")}`],
          ["Variance",              `₹ ${Number(detail.finance.variance).toLocaleString("en-IN")}`, detail.finance.variance >= 0 ? "ok" : "alert"],
          ["Variance %",            `${detail.finance.variance_pct}%`],
          ["Cash Flow Req'd",       `₹ ${Number(detail.finance.cash_flow_requirement).toLocaleString("en-IN")}`],
          ["Pending Approvals",     detail.finance.pending_financial_approvals, "alert"],
          ["Health",                detail.finance.finance_health, detail.finance.finance_health === "healthy" ? "ok" : "alert"],
        ]} /></TabsContent>
      </Tabs>
    </div>
  );
}

// ─────────── Portfolio view ───────────
function PortfolioView({ portfolio, projects, busy, onSelect, onRefresh }) {
  const counterRows = portfolio?.counters || {};
  const cards = portfolio?.projects || [];
  const projectsById = useMemo(() => Object.fromEntries(projects.map((p) => [p.id, p])), [projects]);

  return (
    <div className="p-6 space-y-4" data-testid="page-control-center">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Layers className="h-6 w-6 text-primary" /> Project Control Center</h1>
          <p className="text-sm text-muted-foreground">Portfolio-wide health. Click a project for a unified module-by-module drill-down.</p>
        </div>
        <Button size="sm" variant="outline" onClick={onRefresh} disabled={busy}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
      </div>

      {!portfolio && <Card><CardContent className="py-12 text-center text-slate-400">Loading…</CardContent></Card>}
      {portfolio && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <CounterTile label="Active"           value={counterRows.projects_active} tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
            <CounterTile label="Delayed"          value={counterRows.projects_delayed} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
            <CounterTile label="Manpower Short"   value={counterRows.projects_with_manpower_shortage} tone="bg-amber-50 border-amber-200 text-amber-700" alert />
            <CounterTile label="Material Short"   value={counterRows.projects_blocked_material_return} tone="bg-amber-50 border-amber-200 text-amber-700" alert />
            <CounterTile label="Safety Pending"   value={counterRows.projects_with_safety_pending} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
            <CounterTile label="Logistics Pending" value={counterRows.projects_with_logistics_pending} tone="bg-blue-50 border-blue-200 text-blue-700" />
            <CounterTile label="Over Budget"      value={counterRows.projects_over_budget} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
            <CounterTile label="Pending Billing"  value={counterRows.projects_pending_billing} tone="bg-amber-50 border-amber-200 text-amber-700" alert />
            <CounterTile label="Pending Collection" value={counterRows.projects_pending_collection} tone="bg-amber-50 border-amber-200 text-amber-700" alert />
            <CounterTile label="Open Issues"      value={counterRows.projects_with_open_issues} tone="bg-blue-50 border-blue-200 text-blue-700" />
            <CounterTile label="Pending Cert."    value={counterRows.projects_with_pending_client_measurement} tone="bg-blue-50 border-blue-200 text-blue-700" />
            <CounterTile label="Ready to Close"   value={counterRows.projects_ready_for_closure} tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
            <CounterTile label="Blocked: Material" value={counterRows.projects_blocked_material_return} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
            <CounterTile label="Blocked: Safety"  value={counterRows.projects_blocked_safety} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
            <CounterTile label="Blocked: Manpower" value={counterRows.projects_blocked_manpower} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
          </div>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Project Cards <span className="text-xs text-slate-400">({cards.length})</span></CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2">Project</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2 text-right">MP Short</th>
                    <th className="px-2 py-2 text-right">Mat. Pending</th>
                    <th className="px-2 py-2 text-right">Critical Safety</th>
                    <th className="px-2 py-2 text-right">Expired Permits</th>
                    <th className="px-2 py-2 text-right">Issues</th>
                    <th className="px-2 py-2 text-right">Pending Bill</th>
                    <th className="px-2 py-2 text-right">Outstanding</th>
                    <th className="px-2 py-2 text-center">Budget</th>
                    <th className="px-2 py-2 text-right w-12"></th>
                  </tr></thead>
                  <tbody>
                    {cards.length === 0 && <tr><td colSpan={11} className="text-center py-6 text-slate-400">No projects</td></tr>}
                    {cards.map((c) => (
                      <tr key={c.project_id} className="border-b hover:bg-slate-50/50 cursor-pointer" onClick={() => onSelect(c.project_id)} data-testid={`cc-row-${c.project_id}`}>
                        <td className="px-2 py-1"><span className="font-mono text-xs text-primary mr-1">{c.project_code}</span>{c.name}</td>
                        <td className="px-2 py-1"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusTone(c.status)}`}>{c.status}</span></td>
                        <td className={`px-2 py-1 text-right font-mono ${c.manpower_shortage > 0 ? "text-rose-600 font-bold" : ""}`}>{c.manpower_shortage}</td>
                        <td className={`px-2 py-1 text-right font-mono ${c.material_pending_return > 0 ? "text-amber-700 font-bold" : ""}`}>{c.material_pending_return}</td>
                        <td className={`px-2 py-1 text-right font-mono ${c.safety_critical > 0 ? "text-rose-600 font-bold" : ""}`}>{c.safety_critical}</td>
                        <td className={`px-2 py-1 text-right font-mono ${c.permits_expired > 0 ? "text-rose-600 font-bold" : ""}`}>{c.permits_expired}</td>
                        <td className="px-2 py-1 text-right font-mono">{c.open_issues}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(c.pending_billing).toLocaleString("en-IN")}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(c.outstanding).toLocaleString("en-IN")}</td>
                        <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${budgetTone(c.budget_health)}`}>{c.budget_health}</span></td>
                        <td className="px-2 py-1 text-right"><ChevronRight className="h-4 w-4 text-slate-400" /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ─── small helpers ───
function CounterTile({ label, value, tone = "", alert }) {
  return (
    <div className={`border rounded-sm p-3 ${tone}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-80 flex items-center gap-1">
        {alert && Number(value) > 0 && <AlertTriangle className="h-3 w-3" />}{label}
      </div>
      <div className="text-2xl font-bold">{value ?? 0}</div>
    </div>
  );
}
function MetricGrid({ rows }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-3">
      {rows.map(([label, value, tone]) => (
        <div key={label} className={`border rounded-sm p-3 ${toneClass(tone)}`}>
          <div className="text-[10px] uppercase tracking-wider opacity-80">{label}</div>
          <div className="text-lg font-bold truncate">{value ?? "—"}</div>
        </div>
      ))}
    </div>
  );
}
function BlockerCard({ title, rows, testid }) {
  return (
    <Card className="border-rose-300 bg-rose-50/30" data-testid={testid}>
      <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2 text-rose-700"><AlertTriangle className="h-4 w-4" />{title}</CardTitle></CardHeader>
      <CardContent>
        <div className="space-y-1">
          {rows.map((b, i) => (
            <div key={i} className="text-sm border-b py-1">
              <span className={`mr-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${severityTone(b.severity)}`}>{b.severity}</span>
              <span className="font-medium">{b.kind}</span>
              <span className="text-muted-foreground"> — {b.message}</span>
              {b.override_approved && <span className="ml-2 text-emerald-700 inline-flex items-center text-xs"><CheckCircle2 className="h-3 w-3 mr-0.5" /> override approved</span>}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
const STATUS_TONES = { active: "bg-emerald-50 text-emerald-700 border-emerald-200", on_hold: "bg-amber-50 text-amber-700 border-amber-200", completed: "bg-blue-50 text-blue-700 border-blue-200", closure_pending: "bg-amber-50 text-amber-700 border-amber-200", closed: "bg-slate-50 text-slate-600 border-slate-200" };
const SEV_TONES = { low: "bg-slate-50 text-slate-600 border-slate-200", medium: "bg-amber-50 text-amber-700 border-amber-200", high: "bg-orange-50 text-orange-700 border-orange-200", critical: "bg-rose-50 text-rose-700 border-rose-200" };
const BUDGET_TONES = { healthy: "bg-emerald-50 text-emerald-700 border-emerald-200", approaching_limit: "bg-amber-50 text-amber-700 border-amber-200", over_budget: "bg-rose-50 text-rose-700 border-rose-200" };
function statusTone(s) { return STATUS_TONES[s] || STATUS_TONES.active; }
function severityTone(s) { return SEV_TONES[s] || SEV_TONES.medium; }
function budgetTone(s) { return BUDGET_TONES[s] || BUDGET_TONES.healthy; }
function toneClass(t) {
  if (t === "alert") return "bg-rose-50 border-rose-200 text-rose-700";
  if (t === "ok") return "bg-emerald-50 border-emerald-200 text-emerald-700";
  if (t === "highlight") return "bg-primary/5 border-primary/30 text-primary";
  return "";
}
