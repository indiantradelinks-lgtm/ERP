import { useEffect, useState } from "react";
import { Briefcase, Calendar, MapPin, Users, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";

const PRIO_TONE = {
  critical: "bg-red-100 text-red-800 border-red-300",
  high: "bg-orange-100 text-orange-800 border-orange-300",
  medium: "bg-blue-100 text-blue-800 border-blue-300",
  low: "bg-slate-100 text-slate-700 border-slate-300",
};

export default function MyAssignedProjects() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/ops/my-projects")
      .then((r) => setRows(r.data || []))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 space-y-4" data-testid="my-projects-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Projects & Operations</div>
        <h1 className="font-display font-black text-3xl tracking-tight">My Assigned Projects</h1>
        <p className="text-sm text-slate-600 mt-1">Projects where you are PM, Coordinator, or Reporting Manager.</p>
      </div>

      {loading && <div className="text-sm text-slate-500 py-6">Loading…</div>}

      {!loading && rows.length === 0 && (
        <div className="border border-dashed rounded-lg p-12 text-center text-slate-500">
          <Briefcase className="h-10 w-10 mx-auto mb-2 text-slate-400" />
          <div className="text-sm">No projects allocated to you yet.</div>
          <div className="text-xs mt-1">Project Heads will appear here once they allocate a contract handover.</div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {rows.map((p) => (
          <div key={p.id} className="border rounded-lg bg-white p-4 hover:shadow-md transition-shadow" data-testid={`my-project-${p.id}`}>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="min-w-0 flex-1">
                <div className="font-mono-data text-xs text-slate-500">{p.handover_no}</div>
                <div className="font-display font-bold text-base truncate">{p.project_name}</div>
                <div className="text-xs text-slate-600 truncate">{p.client_name}</div>
              </div>
              {p.priority && (
                <span className={`inline-block px-2 py-0.5 text-[10px] rounded border ${PRIO_TONE[p.priority]}`}>{p.priority}</span>
              )}
            </div>
            <div className="space-y-1 text-xs">
              {p.site_location && <div className="flex items-center gap-1.5 text-slate-600"><MapPin className="h-3 w-3" /> {p.site_location}</div>}
              {(p.expected_start_date || p.expected_completion_date) && (
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Calendar className="h-3 w-3" /> {p.expected_start_date || "—"} → {p.expected_completion_date || "—"}
                </div>
              )}
              <div className="flex items-center gap-1.5 text-slate-600">
                <Users className="h-3 w-3" />
                {p.project_manager_label && <span>PM: <b>{p.project_manager_label}</b></span>}
                {!p.project_manager_label && p.project_coordinator_label && <span>PC: <b>{p.project_coordinator_label}</b></span>}
              </div>
              <div className="text-slate-600">Contract Value · <b className="text-slate-900">₹{(p.contract_value || 0).toLocaleString("en-IN")}</b></div>
            </div>
            <div className="flex items-center justify-between mt-3 pt-3 border-t">
              <Badge variant="outline" className="text-[10px]">{p.status?.replaceAll("_", " ")}</Badge>
              <div className="flex gap-1">
                {p.project_id && (
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => navigate(`/app/project-dashboard?project_id=${p.project_id}`)} data-testid={`my-project-open-${p.id}`}>
                    Open Dashboard
                  </Button>
                )}
                <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => navigate(`/app/ops/handovers`)}>Details</Button>
              </div>
            </div>
            {p.allocation_remarks && (
              <div className="mt-2 text-[11px] bg-amber-50 border border-amber-200 rounded p-2 text-amber-800 flex items-start gap-1.5">
                <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                <span>{p.allocation_remarks}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
