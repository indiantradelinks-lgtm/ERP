import { useCallback, useEffect, useState } from "react";
import { Download, GitCompareArrows, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";

const DEPT_STATUS = {
  on_track:    { label: "On Plan",       tone: "bg-emerald-50 border-emerald-300 text-emerald-900" },
  completed:   { label: "Completed",     tone: "bg-emerald-100 border-emerald-400 text-emerald-900" },
  at_risk:     { label: "At Risk",       tone: "bg-orange-50 border-orange-300 text-orange-900" },
  delayed:     { label: "Behind Plan",   tone: "bg-red-50 border-red-300 text-red-900" },
  not_covered: { label: "Not In Plan",   tone: "bg-slate-50 border-slate-300 text-slate-700" },
};
const ROW_STATUS = (r) => {
  if (!r.covered) return ["Not in plan", "bg-slate-100 text-slate-700 border-slate-300"];
  if (r.is_delayed) return ["Delayed", "bg-red-50 text-red-800 border-red-300"];
  if (r.concern) return [r.concern.type_label, "bg-orange-50 text-orange-900 border-orange-300"];
  if (r.premob_status === "completed") return ["Completed", "bg-emerald-50 text-emerald-800 border-emerald-300"];
  return [r.premob_status === "in_progress" ? "In Progress" : "Pending", "bg-blue-50 text-blue-800 border-blue-200"];
};

export const ResourcePlanSync = ({ projectId, canWrite, onImported }) => {
  const [data, setData] = useState({ rows: [], departments: [], all_on_plan: false, uncovered: 0 });
  const [importing, setImporting] = useState(false);

  const load = useCallback(() => {
    api.get("/ops/premob-items/resource-plan", { params: projectId ? { project_id: projectId } : {} })
      .then((r) => setData(r.data || {})).catch(() => {});
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const doImport = async () => {
    if (!projectId) return toast.error("Select a project first to import its resource plan");
    setImporting(true);
    try {
      const { data: res } = await api.post("/ops/premob-items/import-resources", { project_id: projectId });
      toast.success(`${res.created} item(s) imported from Resource Planning`);
      load(); onImported?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Import failed"); }
    finally { setImporting(false); }
  };

  if (!data.rows?.length) return null;

  return (
    <div className="border rounded-sm" data-testid="premob-resource-sync">
      <div className="px-3 py-2 bg-slate-50 flex flex-wrap items-center justify-between gap-2 border-b">
        <div className="text-sm font-semibold flex items-center gap-2">
          <GitCompareArrows className="h-4 w-4 text-primary" /> Resource Planning Sync
          {data.all_on_plan
            ? <Badge className="bg-emerald-600 text-white text-[10px]" data-testid="premob-allplan-ok"><CheckCircle2 className="h-3 w-3 mr-1" /> All departments working as per plan</Badge>
            : <Badge className="bg-red-600 text-white text-[10px]" data-testid="premob-allplan-bad"><AlertTriangle className="h-3 w-3 mr-1" /> Departments behind plan</Badge>}
        </div>
        {canWrite && data.uncovered > 0 && (
          <Button size="sm" variant="outline" onClick={doImport} disabled={importing} data-testid="premob-import-btn">
            <Download className="h-3.5 w-3.5 mr-1" /> {importing ? "Importing…" : `Import ${data.uncovered} missing item(s)`}
          </Button>
        )}
      </div>

      {/* Department status cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3" data-testid="premob-dept-cards">
        {data.departments.map((d) => {
          const s = DEPT_STATUS[d.status] || DEPT_STATUS.on_track;
          return (
            <div key={d.department} className={`border rounded-sm px-3 py-2 ${s.tone}`} data-testid={`premob-dept-${d.resource_type}`}>
              <div className="text-[10px] uppercase tracking-wider opacity-70">{d.department}</div>
              <div className="text-sm font-bold">{s.label}</div>
              <div className="text-[11px] opacity-80">{d.covered}/{d.planned} in plan · {d.completed} done{d.delayed ? ` · ${d.delayed} delayed` : ""}{d.concerns ? ` · ${d.concerns} concern(s)` : ""}</div>
            </div>
          );
        })}
      </div>

      {/* Category-wise resource rows */}
      <div className="overflow-auto max-h-64 border-t">
        <table className="w-full text-sm" data-testid="premob-resource-table">
          <thead className="bg-slate-50 sticky top-0">
            <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-1.5">Project</th><th className="px-3 py-1.5">Department</th>
              <th className="px-3 py-1.5">Category</th><th className="px-3 py-1.5">Item</th>
              <th className="px-3 py-1.5 text-right">Qty</th><th className="px-3 py-1.5">Mobilization</th>
              <th className="px-3 py-1.5">Plan Status</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => {
              const [label, tone] = ROW_STATUS(r);
              return (
                <tr key={r.resource_id} className="border-t">
                  <td className="px-3 py-1.5 text-xs whitespace-nowrap">{r.project_code || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{r.department}</td>
                  <td className="px-3 py-1.5 text-xs">{r.category}</td>
                  <td className="px-3 py-1.5 text-xs font-medium">{r.name}</td>
                  <td className="px-3 py-1.5 text-xs text-right">{r.qty ?? "—"} {r.unit || ""}</td>
                  <td className="px-3 py-1.5 text-xs">{r.mobilization_date || r.premob_target || "—"}</td>
                  <td className="px-3 py-1.5"><Badge variant="outline" className={`text-[10px] ${tone}`}>{label}</Badge></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
