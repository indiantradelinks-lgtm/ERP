/**
 * Safety Escalation Dashboard — traffic-light view of open escalations.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Siren, RefreshCcw, CheckCircle2 } from "lucide-react";

const KIND_LABEL = {
  overdue_capa: "Overdue CAPA",
  critical_incident: "Critical Incident",
  high_risk_observation: "High-risk Observation",
};
const LEVEL_TONE = {
  critical: "bg-red-100 border-red-400 text-red-900",
  high: "bg-orange-100 border-orange-400 text-orange-900",
  medium: "bg-amber-100 border-amber-400 text-amber-900",
};

export default function SafetyEscalationDashboard() {
  const [rows, setRows] = useState([]);

  const load = async () => { try { const r = await api.get("/safety/escalations?status=open"); setRows(r.data || []); } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); } };
  useEffect(() => { load(); }, []);

  const closeIt = async (r) => { try { await api.post(`/safety/escalations/${r.id}/close`); toast.success("Escalation closed"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Close failed"); } };

  const by_level = rows.reduce((acc, r) => { acc[r.level] = (acc[r.level] || 0) + 1; return acc; }, {});

  return (
    <div className="p-6 space-y-4" data-testid="escalations-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><Siren className="h-6 w-6 text-red-600" /> Safety Escalation Dashboard</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Open escalations — critical incidents, high-risk observations, and overdue CAPAs.</p>
        </div>
        <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Chip label="Critical" value={by_level.critical || 0} tone="red" />
        <Chip label="High" value={by_level.high || 0} tone="orange" />
        <Chip label="Medium" value={by_level.medium || 0} tone="amber" />
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600"><tr><th className="text-left px-3 py-2">Level</th><th className="text-left px-3 py-2">Kind</th><th className="text-left px-3 py-2">Reference</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Reason</th><th className="text-left px-3 py-2">Since</th><th className="text-right px-3 py-2"></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">No open escalations.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`esc-row-${r.id}`}>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded border ${LEVEL_TONE[r.level] || "bg-slate-100"}`}>{r.level}</span></td>
                <td className="px-3 py-2 text-xs">{KIND_LABEL[r.kind] || r.kind}</td>
                <td className="px-3 py-2 text-xs font-mono">{r.ref_no || r.ref_id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs">{r.project_id ? r.project_id.slice(0, 12) : "—"}</td>
                <td className="px-3 py-2 text-xs max-w-md truncate">{r.reason}</td>
                <td className="px-3 py-2 text-xs">{r.created_at?.slice(0, 16).replace("T", " ")}</td>
                <td className="px-3 py-2 text-right"><Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-700" onClick={() => closeIt(r)} data-testid={`esc-close-${r.id}`}><CheckCircle2 className="h-3.5 w-3.5" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Chip({ label, value, tone }) {
  const t = tone === "red" ? "bg-red-50 text-red-700 border-red-300" : tone === "orange" ? "bg-orange-50 text-orange-700 border-orange-300" : "bg-amber-50 text-amber-800 border-amber-300";
  return (
    <div className={`border-2 rounded-sm p-3 ${t}`}>
      <div className="text-[10px] uppercase tracking-wider font-semibold">{label}</div>
      <div className="font-display font-black text-3xl tabular leading-none mt-1">{value}</div>
    </div>
  );
}
