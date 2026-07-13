/**
 * Final Safety Management Review Dashboard (Phase 5) — 30 real-time HSE
 * KPIs aggregating across ALL safety phases (1-5) with click-through drill-down.
 * Backed by GET /api/safety/dashboard-v2 (falls back to /management-review).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Activity, RefreshCcw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

const TILES = [
  { key: "total_projects_monitored",       label: "Projects Monitored",           tone: "slate",   fmt: "int",   link: "/app/projects-ops/projects" },
  { key: "projects_safety_ready",          label: "Projects Safety-Ready",        tone: "emerald", fmt: "int",   link: "/app/safety/readiness" },
  { key: "projects_safety_blocked",        label: "Projects Safety-Blocked",      tone: "red",     fmt: "int",   link: "/app/safety/readiness" },
  { key: "hira_pending",                   label: "HIRA Pending",                 tone: "amber",   fmt: "int",   link: "/app/safety/hira" },
  { key: "jsa_pending",                    label: "JSA Pending",                  tone: "amber",   fmt: "int",   link: "/app/safety/jsa" },
  { key: "work_permits_active",            label: "Work Permits Active",          tone: "emerald", fmt: "int",   link: "/app/safety/work-permits" },
  { key: "work_permits_expired",           label: "Work Permits Expired",         tone: "red",     fmt: "int",   link: "/app/safety/work-permits" },
  { key: "work_permits_pending_closure",   label: "Permits Pending Closure",      tone: "amber",   fmt: "int",   link: "/app/safety/work-permits" },
  { key: "training_pending",               label: "Training Pending",             tone: "amber",   fmt: "int",   link: "/app/safety/trainings" },
  { key: "training_expiring",              label: "Training Expiring",            tone: "amber",   fmt: "int",   link: "/app/safety/training-expiry" },
  { key: "medical_fitness_expiring",       label: "Medical Fitness Expiring",     tone: "amber",   fmt: "int",   link: "/app/safety/medical-fitness" },
  { key: "ppe_compliance_pending",         label: "PPE Compliance Pending",       tone: "amber",   fmt: "int",   link: "/app/safety/ppe-compliance" },
  { key: "safety_inspections_due",         label: "Inspections Due",              tone: "amber",   fmt: "int",   link: "/app/safety/inspections" },
  { key: "open_safety_observations",       label: "Open Observations",            tone: "amber",   fmt: "int",   link: "/app/safety/observations" },
  { key: "open_ofis",                      label: "Open OFIs",                    tone: "amber",   fmt: "int",   link: "/app/safety/observations" },
  { key: "open_incidents",                 label: "Open Incidents",               tone: "red",     fmt: "int",   link: "/app/safety/incidents" },
  { key: "open_near_misses",               label: "Open Near Misses",             tone: "amber",   fmt: "int",   link: "/app/safety/incidents" },
  { key: "open_capa",                      label: "Open CAPA",                    tone: "amber",   fmt: "int",   link: "/app/safety/capa" },
  { key: "overdue_capa",                   label: "Overdue CAPA",                 tone: "red",     fmt: "int",   link: "/app/safety/capa" },
  { key: "open_audit_findings",            label: "Open Audit Findings",          tone: "amber",   fmt: "int",   link: "/app/safety/audits" },
  { key: "client_compliance_pending",      label: "Client Compliance Pending",    tone: "amber",   fmt: "int",   link: "/app/safety/client-compliance" },
  { key: "vendor_safety_pending",          label: "Vendor Safety Pending",        tone: "amber",   fmt: "int",   link: "/app/safety/vendor-compliance" },
  { key: "projects_pending_closure",       label: "Projects Pending Closure",     tone: "red",     fmt: "int",   link: "/app/safety/project-closure" },
  { key: "safety_cost_this_month",         label: "Safety Cost (This Month)",     tone: "red",     fmt: "money", link: "/app/safety/costs" },
  { key: "safety_penalty_pending",         label: "Penalty Approvals Pending",    tone: "red",     fmt: "int",   link: "/app/safety/costs" },
  { key: "safety_recovery_pending",        label: "Recovery Approvals Pending",   tone: "emerald", fmt: "int",   link: "/app/safety/costs" },
  { key: "high_risk_activities",           label: "High-Risk Activities Open",    tone: "red",     fmt: "int",   link: "/app/safety/hira" },
  { key: "safety_approval_pending",        label: "Safety Approvals Pending",     tone: "amber",   fmt: "int",   link: "/app/approvals" },
  { key: "projects_active",                label: "Active Projects",              tone: "emerald", fmt: "int",   link: "/app/projects-ops/projects" },
];

const TONE_CLS = {
  red: "border-red-200 hover:border-red-400 hover:bg-red-50/40",
  amber: "border-amber-200 hover:border-amber-400 hover:bg-amber-50/40",
  emerald: "border-emerald-200 hover:border-emerald-400 hover:bg-emerald-50/40",
  slate: "border-slate-200 hover:border-slate-400 hover:bg-slate-50/40",
};
const VAL_CLS = { red: "text-red-700", amber: "text-amber-700", emerald: "text-emerald-700", slate: "text-slate-900" };

export default function SafetyManagementReview() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    try {
      // Phase 5 v2 dashboard preferred; fall back to Phase 4 review if unavailable
      let r;
      try { r = await api.get("/safety/dashboard-v2"); }
      catch { r = await api.get("/safety/management-review"); }
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading Safety Dashboard…</div>;

  const k = data.kpis || {};
  const incidents = data.recent_incidents || [];
  const closures = data.recent_closures || [];

  return (
    <div className="p-6 space-y-5" data-testid="mgmt-review-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 5 · Final</div>
          <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
            <Activity className="h-7 w-7 text-red-600" /> Safety Management Review Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Executive HSE cockpit — 30 real-time KPIs across all safety phases. Snapshot as of {new Date(data.as_of).toLocaleString()}.
          </p>
        </div>
        <Button variant="outline" onClick={load} data-testid="mgmt-review-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {TILES.map((t) => {
          const raw = k[t.key];
          const val = t.fmt === "money" ? inr(raw) : (raw ?? 0);
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => navigate(t.link)}
              className={`bg-card border rounded-sm p-3 text-left transition-colors cursor-pointer ${TONE_CLS[t.tone]}`}
              data-testid={`kpi-${t.key}`}
            >
              <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground leading-tight">
                {t.label}
              </div>
              <div className={`mt-1 text-2xl font-black ${VAL_CLS[t.tone]}`}>{val}</div>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border rounded-sm bg-card overflow-hidden">
          <div className="px-3 py-2 border-b bg-red-50/40 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-600" />
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700">Recent Incidents (90d)</div>
          </div>
          <table className="w-full text-xs">
            <tbody>
              {incidents.length === 0 && (
                <tr><td colSpan={4} className="text-center py-6 text-slate-400">No recent incidents.</td></tr>
              )}
              {incidents.map((r) => (
                <tr key={r.incident_no} className="border-t hover:bg-slate-50/40 cursor-pointer" onClick={() => navigate("/app/safety/incidents")} data-testid={`inc-${r.incident_no}`}>
                  <td className="px-3 py-1.5 font-mono">{r.incident_no}</td>
                  <td className="px-3 py-1.5">{r.incident_date}</td>
                  <td className="px-3 py-1.5 text-slate-600">{r.project_code || "—"}</td>
                  <td className="px-3 py-1.5"><span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 bg-red-100 text-red-800 rounded">{r.severity}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="border rounded-sm bg-card overflow-hidden">
          <div className="px-3 py-2 border-b bg-emerald-50/40">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700">Recent Safety Closures</div>
          </div>
          <table className="w-full text-xs">
            <tbody>
              {closures.length === 0 && (
                <tr><td colSpan={2} className="text-center py-6 text-slate-400">No closures completed yet.</td></tr>
              )}
              {closures.map((r, i) => (
                <tr key={i} className="border-t hover:bg-slate-50/40 cursor-pointer" onClick={() => navigate("/app/safety/project-closure")}>
                  <td className="px-3 py-1.5 font-mono">{r.project_code}</td>
                  <td className="px-3 py-1.5 text-slate-600">{(r.closed_at || "").slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
