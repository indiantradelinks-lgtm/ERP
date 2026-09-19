/**
 * Work Progress Tracker · P&O Phase 3 (Round 3A)
 *
 * Read-only-ish progress board per project. Rows are auto-populated when a
 * DPR is approved (cumulative qty, % progress, status). PM can adjust
 * planned_qty / planned_progress_pct / delay_reason / corrective_action /
 * responsible / target_recovery_date in-line.
 *
 * Backend: /api/proj-phase3/work-progress/{project_id} ...
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Activity, RefreshCcw, Pencil, AlertTriangle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const STATUSES = ["on_track", "delayed", "ahead", "on_hold"];

export default function WorkProgressTracker() {
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [rows, setRows]           = useState([]);
  const [editing, setEditing]     = useState(null);
  const [form, setForm]           = useState({});
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { if (projectId) load(); else setRows([]); }, [projectId]);

  const load = async () => {
    try {
      const { data } = await api.get(`/proj-phase3/work-progress/${projectId}`);
      setRows(data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  const save = async () => {
    try {
      const payload = {
        planned_qty: form.planned_qty === "" ? null : Number(form.planned_qty),
        planned_progress_pct: form.planned_progress_pct === "" ? null : Number(form.planned_progress_pct),
        status: form.status,
        delay_reason: form.delay_reason,
        corrective_action: form.corrective_action,
        responsible_person: form.responsible_person,
        target_recovery_date: form.target_recovery_date,
      };
      await api.put(`/proj-phase3/work-progress/${editing.id}`, payload);
      toast.success("Progress updated");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const delayedCount = rows.filter((r) => r.status === "delayed").length;
  const aheadCount   = rows.filter((r) => r.status === "ahead").length;
  const ontrackCount = rows.filter((r) => r.status === "on_track").length;
  const holdCount    = rows.filter((r) => r.status === "on_hold").length;

  return (
    <div className="p-6 space-y-4" data-testid="page-work-progress">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" /> Work Progress Tracker
          </h1>
          <p className="text-sm text-muted-foreground">Per-BOQ / per-Activity progress. Auto-updates from APPROVED DPRs. Edit planned qty &amp; delay reasons inline.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm min-w-[260px]" data-testid="wp-project-select">
            <option value="">— select project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={!projectId}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
        </div>
      </div>

      {projectId && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="On Track"  value={ontrackCount} tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
          <Tile label="Delayed"   value={delayedCount} tone="bg-rose-50 border-rose-200 text-rose-700" alert />
          <Tile label="Ahead"     value={aheadCount}   tone="bg-blue-50 border-blue-200 text-blue-700" />
          <Tile label="On Hold"   value={holdCount}    tone="bg-amber-50 border-amber-200 text-amber-700" />
        </div>
      )}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Activity / BOQ Progress <span className="text-xs text-slate-400">({rows.length})</span></CardTitle></CardHeader>
        <CardContent>
          {!projectId ? (
            <div className="text-center py-10 text-slate-400">Select a project</div>
          ) : rows.length === 0 ? (
            <div className="text-center py-10 text-slate-400">No progress yet — approve at least one DPR with BOQ/Activity-linked work to populate this view.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">Item</th>
                  <th className="px-2 py-2">UOM</th>
                  <th className="px-2 py-2 text-right">Planned Qty</th>
                  <th className="px-2 py-2 text-right">Cumulative</th>
                  <th className="px-2 py-2 text-right">Balance</th>
                  <th className="px-2 py-2 text-right">Planned %</th>
                  <th className="px-2 py-2 text-right">Actual %</th>
                  <th className="px-2 py-2 text-right">Variance</th>
                  <th className="px-2 py-2 text-center">Status</th>
                  <th className="px-2 py-2">Delay Reason / Action</th>
                  <th className="px-2 py-2 text-right w-12"></th>
                </tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b hover:bg-slate-50/50" data-testid={`wp-row-${r.id}`}>
                      <td className="px-2 py-1">{r.description || "—"}</td>
                      <td className="px-2 py-1 text-xs">{r.uom || "—"}</td>
                      <td className="px-2 py-1 text-right font-mono">{Number(r.planned_qty || 0).toLocaleString("en-IN")}</td>
                      <td className="px-2 py-1 text-right font-mono">{Number(r.cumulative_completed_qty || 0).toLocaleString("en-IN")}</td>
                      <td className="px-2 py-1 text-right font-mono">{Number(r.balance_qty || 0).toLocaleString("en-IN")}</td>
                      <td className="px-2 py-1 text-right font-mono">{(Number(r.planned_progress_pct || 0)).toFixed(1)}%</td>
                      <td className="px-2 py-1 text-right font-mono font-semibold">{(Number(r.actual_progress_pct || 0)).toFixed(1)}%</td>
                      <td className={`px-2 py-1 text-right font-mono ${Number(r.variance_pct) < 0 ? "text-rose-600" : Number(r.variance_pct) > 0 ? "text-emerald-700" : ""}`}>{(Number(r.variance_pct || 0)).toFixed(1)}%</td>
                      <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone(r.status)}`}>{r.status}</span></td>
                      <td className="px-2 py-1 text-xs truncate max-w-[260px]">
                        {r.status === "delayed" && r.delay_reason && <span className="text-rose-600">⚠ {r.delay_reason}</span>}
                        {r.corrective_action && <span className="text-slate-500"> · {r.corrective_action}</span>}
                      </td>
                      <td className="px-2 py-1 text-right">
                        {canEdit && (
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm(r); }} data-testid={`wp-edit-${r.id}`}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader><DialogTitle>Update Progress · {editing?.description}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Planned Qty"><Input type="number" value={form.planned_qty ?? ""} onChange={(e) => setForm({ ...form, planned_qty: e.target.value })} /></F>
            <F label="Planned Progress %"><Input type="number" min="0" max="100" value={form.planned_progress_pct ?? ""} onChange={(e) => setForm({ ...form, planned_progress_pct: e.target.value })} data-testid="wp-form-planned-pct" /></F>
            <F label="Status">
              <select value={form.status || "on_track"} onChange={(e) => setForm({ ...form, status: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="wp-form-status">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </F>
            <F label="Responsible Person"><Input value={form.responsible_person || ""} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} /></F>
            <F label="Target Recovery Date"><Input type="date" value={form.target_recovery_date || ""} onChange={(e) => setForm({ ...form, target_recovery_date: e.target.value })} /></F>
            <F label="Delay Reason" full><Textarea rows={2} value={form.delay_reason || ""} onChange={(e) => setForm({ ...form, delay_reason: e.target.value })} data-testid="wp-form-reason" /></F>
            <F label="Corrective Action" full><Textarea rows={2} value={form.corrective_action || ""} onChange={(e) => setForm({ ...form, corrective_action: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="wp-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const TONES = {
  on_track: "bg-emerald-50 text-emerald-700 border-emerald-200",
  delayed:  "bg-rose-50 text-rose-700 border-rose-200",
  ahead:    "bg-blue-50 text-blue-700 border-blue-200",
  on_hold:  "bg-amber-50 text-amber-700 border-amber-200",
};
function tone(s) { return TONES[s] || TONES.on_track; }

function Tile({ label, value, tone, alert }) {
  return (
    <div className={`border rounded-sm p-3 ${tone}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-80 flex items-center gap-1">
        {alert && Number(value) > 0 && <AlertTriangle className="h-3 w-3" />} {label}
      </div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}
function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
