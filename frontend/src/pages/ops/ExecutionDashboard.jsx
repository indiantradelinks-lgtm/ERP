/**
 * Execution Dashboard · P&O Phase 3 (Round 3C)
 * Aggregate KPIs per project across DPR / Issues / Permits / Measurements /
 * Extra Work / Progress.
 * Backend: /api/proj-phase3/execution/{project_id}/dashboard
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Activity, RefreshCcw, AlertTriangle, ClipboardCheck, ShieldAlert, Ruler, PlusSquare } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

export default function ExecutionDashboard() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { if (projectId) load(); else setData(null); }, [projectId]);

  const load = async () => {
    try {
      const { data } = await api.get(`/proj-phase3/execution/${projectId}/dashboard`);
      setData(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-execution-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="h-6 w-6 text-primary" /> Project Execution Dashboard</h1>
          <p className="text-sm text-muted-foreground">Aggregate KPIs across DPR / Issues / Permits / Measurements / Extra Work / Progress.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 rounded-sm border px-2 text-sm min-w-[260px]" data-testid="exec-project-select"><option value="">— select project —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}</select>
          <Button size="sm" variant="outline" onClick={load} disabled={!projectId}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
        </div>
      </div>

      {!projectId && <Card><CardContent className="py-12 text-center text-slate-400">Select a project to view its execution dashboard</CardContent></Card>}
      {projectId && !data && <Card><CardContent className="py-12 text-center text-slate-400">Loading…</CardContent></Card>}

      {data && (
        <>
          {/* Top KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tile icon={ClipboardCheck} label="DPRs Today" value={data.dpr?.today || 0} sub={`${data.dpr?.approved || 0} approved`} tone="bg-blue-50 border-blue-200 text-blue-700" />
            <Tile icon={ClipboardCheck} label="DPRs Pending Approval" value={data.dpr?.pending_approval || 0} sub={`${data.dpr?.total || 0} total`} tone="bg-amber-50 border-amber-200 text-amber-700" alert={(data.dpr?.pending_approval || 0) > 0} />
            <Tile icon={Activity} label="Avg Progress" value={`${data.progress?.avg_actual_pct || 0}%`} sub={`${data.progress?.delayed_items || 0} delayed / ${data.progress?.total_items || 0}`} tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
            <Tile icon={AlertTriangle} label="Critical Issues" value={data.issues?.critical_open || 0} sub={`${data.issues?.open || 0} open · ${data.issues?.escalated || 0} escalated`} tone="bg-rose-50 border-rose-200 text-rose-700" alert={(data.issues?.critical_open || 0) > 0} />
          </div>

          {/* Section: Permits */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-amber-600" />Work Permits</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                <Tile label="Active" value={data.permits?.active || 0} tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
                <Tile label="Expiring (7 days)" value={data.permits?.expiring_in_7d || 0} tone="bg-amber-50 border-amber-200 text-amber-700" alert={(data.permits?.expiring_in_7d || 0) > 0} />
                <Tile label="Expired" value={data.permits?.expired || 0} tone="bg-rose-50 border-rose-200 text-rose-700" alert={(data.permits?.expired || 0) > 0} />
              </div>
            </CardContent>
          </Card>

          {/* Section: Measurements & Extra Work */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Ruler className="h-4 w-4 text-primary" />Measurements</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-3">
                <Tile label="Sheets Pending Approval" value={data.measurements?.pending_approval || 0} />
                <Tile label="Lines Pending Certification" value={data.measurements?.pending_certification_lines || 0} alert={(data.measurements?.pending_certification_lines || 0) > 0} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><PlusSquare className="h-4 w-4 text-primary" />Extra Work</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-3">
                <Tile label="Pending PM Approval" value={data.extra_work?.pending_approval || 0} alert={(data.extra_work?.pending_approval || 0) > 0} />
                <Tile label="Billable Value (Pending)" value={`₹ ${Number(data.extra_work?.billable_value || 0).toLocaleString("en-IN")}`} sub={`${data.extra_work?.billable_count || 0} items`} highlight />
              </CardContent>
            </Card>
          </div>

          <div className="text-xs text-slate-400 text-right">As of {data.as_of}</div>
        </>
      )}
    </div>
  );
}

function Tile({ icon: Icon, label, value, sub, tone = "", alert, highlight }) {
  return (
    <div className={`border rounded-sm p-3 ${tone} ${highlight ? "bg-primary/5 border-primary/30 text-primary" : ""}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-80 flex items-center gap-1">
        {alert && <AlertTriangle className="h-3 w-3" />}
        {Icon && <Icon className="h-3 w-3" />}
        {label}
      </div>
      <div className={`text-2xl font-bold ${highlight ? "text-primary" : ""}`}>{value}</div>
      {sub && <div className="text-[10px] opacity-70 mt-0.5">{sub}</div>}
    </div>
  );
}
