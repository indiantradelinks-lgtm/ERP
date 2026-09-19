/**
 * Project Activity Schedule · P&O Phase 2 (Round 2)
 *
 * List/table of project activities with start/end/duration/progress and
 * optional WBS linkage. Predecessor support for simple dependency lists.
 *
 * Backend: /api/proj-phase2/activities/{project_id} ...
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
import { CalendarRange, Plus, Pencil, Trash2, RefreshCcw } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const ACT_STATUS = ["not_started", "in_progress", "completed", "on_hold", "cancelled", "delayed"];
const EMPTY = {
  code: "", name: "", wbs_id: "", start_date: "", end_date: "",
  duration_days: "", predecessor_ids: [], responsible: "",
  status: "not_started", progress_pct: 0, remarks: "",
};

export default function ProjectActivities() {
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [activities, setActivities] = useState([]);
  const [wbsNodes, setWbsNodes]   = useState([]);
  const [editing, setEditing]     = useState(null);
  const [form, setForm]           = useState(EMPTY);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => {
    if (!projectId) { setActivities([]); setWbsNodes([]); return; }
    load();
  }, [projectId]);

  const load = async () => {
    try {
      const [a, w] = await Promise.all([
        api.get(`/proj-phase2/activities/${projectId}`),
        api.get(`/proj-phase2/wbs/${projectId}`),
      ]);
      setActivities(a.data || []);
      setWbsNodes(w.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  const save = async () => {
    if (!form.name?.trim()) { toast.error("Name is required"); return; }
    try {
      const payload = {
        ...form,
        wbs_id: form.wbs_id || null,
        duration_days: form.duration_days === "" ? null : Number(form.duration_days),
        progress_pct: Number(form.progress_pct) || 0,
      };
      if (editing?.id) {
        await api.put(`/proj-phase2/activities/${editing.id}`, payload);
        toast.success("Activity updated");
      } else {
        await api.post(`/proj-phase2/activities/${projectId}`, payload);
        toast.success("Activity created");
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete activity '${r.name}'?`)) return;
    try {
      await api.delete(`/proj-phase2/activities/${r.id}`);
      toast.success("Activity deleted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-project-activities">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarRange className="h-6 w-6 text-primary" /> Activity Schedule
          </h1>
          <p className="text-sm text-muted-foreground">Time-phased activities with start/end dates, duration, progress and predecessor dependencies.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm min-w-[260px]" data-testid="act-project-select">
            <option value="">— select project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={!projectId}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          {canEdit && projectId && (
            <Button onClick={() => { setEditing({}); setForm({ ...EMPTY }); }} data-testid="act-new">
              <Plus className="h-4 w-4 mr-1" /> Add Activity
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Activities <span className="text-xs text-slate-400">({activities.length})</span></CardTitle></CardHeader>
        <CardContent>
          {!projectId ? (
            <div className="text-center py-10 text-slate-400">Select a project to view its activities</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2">Code</th>
                    <th className="px-2 py-2">Name</th>
                    <th className="px-2 py-2">WBS</th>
                    <th className="px-2 py-2">Start</th>
                    <th className="px-2 py-2">End</th>
                    <th className="px-2 py-2 text-right">Days</th>
                    <th className="px-2 py-2 text-center">Status</th>
                    <th className="px-2 py-2 text-right">%</th>
                    <th className="px-2 py-2">Responsible</th>
                    <th className="px-2 py-2 text-right w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {activities.length === 0 && <tr><td colSpan={10} className="text-center py-6 text-slate-400">No activities yet</td></tr>}
                  {activities.map((a) => {
                    const wbs = wbsNodes.find((w) => w.id === a.wbs_id);
                    return (
                      <tr key={a.id} className="border-b hover:bg-slate-50/50" data-testid={`act-row-${a.id}`}>
                        <td className="px-2 py-1 font-mono text-xs">{a.code}</td>
                        <td className="px-2 py-1">{a.name}</td>
                        <td className="px-2 py-1 text-xs font-mono">{wbs ? `${wbs.code} ${wbs.name}` : "—"}</td>
                        <td className="px-2 py-1 text-xs">{a.start_date || "—"}</td>
                        <td className="px-2 py-1 text-xs">{a.end_date || "—"}</td>
                        <td className="px-2 py-1 text-right font-mono">{a.duration_days ?? "—"}</td>
                        <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone(a.status)}`}>{a.status}</span></td>
                        <td className="px-2 py-1 text-right">
                          <div className="inline-flex items-center gap-1">
                            <div className="h-1.5 w-12 bg-slate-200 rounded">
                              <div className="h-1.5 bg-primary rounded" style={{ width: `${Math.min(100, Math.max(0, Number(a.progress_pct) || 0))}%` }} />
                            </div>
                            <span className="text-xs font-mono">{a.progress_pct || 0}%</span>
                          </div>
                        </td>
                        <td className="px-2 py-1 text-xs">{a.responsible || "—"}</td>
                        <td className="px-2 py-1 text-right">
                          {canEdit && (
                            <div className="flex justify-end gap-1">
                              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(a); setForm({ ...EMPTY, ...a, wbs_id: a.wbs_id || "", duration_days: a.duration_days ?? "" }); }} data-testid={`act-edit-${a.id}`}>
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(a)} data-testid={`act-del-${a.id}`}>
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "Add"} Activity</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Code"><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="auto" /></F>
            <F label="WBS Node">
              <select value={form.wbs_id} onChange={(e) => setForm({ ...form, wbs_id: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="act-form-wbs">
                <option value="">— none —</option>
                {wbsNodes.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
              </select>
            </F>
            <F label="Name *" full><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="act-form-name" /></F>
            <F label="Start Date"><Input type="date" value={form.start_date || ""} onChange={(e) => setForm({ ...form, start_date: e.target.value })} data-testid="act-form-start" /></F>
            <F label="End Date"><Input type="date" value={form.end_date || ""} onChange={(e) => setForm({ ...form, end_date: e.target.value })} data-testid="act-form-end" /></F>
            <F label="Duration (days)"><Input type="number" value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} placeholder="auto" /></F>
            <F label="Progress %"><Input type="number" min="0" max="100" value={form.progress_pct} onChange={(e) => setForm({ ...form, progress_pct: e.target.value })} /></F>
            <F label="Status">
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {ACT_STATUS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </F>
            <F label="Responsible"><Input value={form.responsible || ""} onChange={(e) => setForm({ ...form, responsible: e.target.value })} placeholder="Site engineer / PM" /></F>
            <F label="Predecessors" full>
              <select multiple value={form.predecessor_ids || []}
                       onChange={(e) => setForm({ ...form, predecessor_ids: Array.from(e.target.selectedOptions, (o) => o.value) })}
                       className="min-h-[80px] w-full rounded-sm border border-input bg-background px-2 py-1 text-sm">
                {activities.filter((a) => a.id !== editing?.id).map((a) => <option key={a.id} value={a.id}>{a.code} · {a.name}</option>)}
              </select>
            </F>
            <F label="Remarks" full><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="act-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const TONES = {
  not_started: "bg-slate-50 text-slate-600 border-slate-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  completed:   "bg-emerald-50 text-emerald-700 border-emerald-200",
  on_hold:     "bg-amber-50 text-amber-700 border-amber-200",
  cancelled:   "bg-rose-50 text-rose-700 border-rose-200",
  delayed:     "bg-orange-50 text-orange-700 border-orange-200",
};
function tone(s) { return TONES[s] || TONES.not_started; }

function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
