/**
 * Site Issue Register · P&O Phase 3 (Round 3B)
 *
 * Categorised site-issue tracking. Critical issues auto-notify
 * PM/GM/Director. Cost-impact issues notify Accounts.
 * Backend: /api/proj-phase3/issues
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
import { AlertTriangle, Plus, Pencil, Trash2, RefreshCcw, CheckCircle2, ArrowUpCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const CATEGORIES = ["manpower", "material", "safety", "client", "permit", "logistics", "equipment", "weather", "technical", "billing", "other"];
const IMPACTS = ["low", "medium", "high", "critical"];
const STATUSES = ["open", "in_progress", "closed", "escalated"];
const EMPTY = {
  project_id: "", issue_date: new Date().toISOString().slice(0, 10), category: "other",
  title: "", description: "", impact: "medium", delay_impact: false, cost_impact: false,
  responsible_department: "", assigned_to: "", target_closure_date: "", corrective_action: "", attachment_ids: [],
};

export default function SiteIssues() {
  const [projects, setProjects] = useState([]);
  const [rows, setRows] = useState([]);
  const [filt, setFilt] = useState({ project_id: "", status: "", impact: "" });
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [filt]);

  const load = async () => {
    try {
      const { data } = await api.get("/proj-phase3/issues", { params: { project_id: filt.project_id || undefined, status: filt.status || undefined, impact: filt.impact || undefined } });
      setRows(data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  const save = async () => {
    if (!form.project_id) return toast.error("Project is required");
    if (!form.title?.trim()) return toast.error("Title is required");
    try {
      if (editing?.id) {
        await api.put(`/proj-phase3/issues/${editing.id}`, form);
        toast.success("Issue updated");
      } else {
        await api.post("/proj-phase3/issues", form);
        toast.success("Issue created");
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.issue_no}?`)) return;
    try { await api.delete(`/proj-phase3/issues/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  const close = async (r) => {
    const note = window.prompt("Closure note:");
    if (note === null) return;
    try { await api.post(`/proj-phase3/issues/${r.id}/close?closure_note=${encodeURIComponent(note)}`); toast.success("Closed"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Close failed"); }
  };
  const escalate = async (r) => {
    if (!window.confirm(`Escalate ${r.issue_no} to GM / Director?`)) return;
    try { await api.post(`/proj-phase3/issues/${r.id}/escalate`); toast.success("Escalated"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Escalate failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-site-issues">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><AlertTriangle className="h-6 w-6 text-rose-600" /> Site Issue Register</h1>
          <p className="text-sm text-muted-foreground">All categorised site issues. Critical impact and cost-impact rows trigger inbox alerts.</p>
        </div>
        {canEdit && (
          <Button onClick={() => { setEditing({}); setForm({ ...EMPTY, project_id: filt.project_id || "" }); }} data-testid="iss-new">
            <Plus className="h-4 w-4 mr-1" /> New Issue
          </Button>
        )}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Issues <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <select value={filt.project_id} onChange={(e) => setFilt({ ...filt, project_id: e.target.value })} className="h-7 rounded-sm border px-2" data-testid="iss-filter-project">
              <option value="">All projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </select>
            <select value={filt.impact} onChange={(e) => setFilt({ ...filt, impact: e.target.value })} className="h-7 rounded-sm border px-2">
              <option value="">All impacts</option>
              {IMPACTS.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
            <select value={filt.status} onChange={(e) => setFilt({ ...filt, status: e.target.value })} className="h-7 rounded-sm border px-2">
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">Issue #</th>
                <th className="px-2 py-2">Date</th>
                <th className="px-2 py-2">Project</th>
                <th className="px-2 py-2">Category</th>
                <th className="px-2 py-2">Title</th>
                <th className="px-2 py-2 text-center">Impact</th>
                <th className="px-2 py-2 text-center">Flags</th>
                <th className="px-2 py-2">Assigned</th>
                <th className="px-2 py-2 text-center">Status</th>
                <th className="px-2 py-2 text-right w-32"></th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={10} className="text-center py-6 text-slate-400">No issues</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b" data-testid={`iss-row-${r.id}`}>
                    <td className="px-2 py-1 font-mono font-bold text-primary">{r.issue_no}</td>
                    <td className="px-2 py-1 text-xs">{r.issue_date}</td>
                    <td className="px-2 py-1 text-xs">{r.project_code}</td>
                    <td className="px-2 py-1 text-xs">{r.category}</td>
                    <td className="px-2 py-1">{r.title}</td>
                    <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${impactTone(r.impact)}`}>{r.impact}</span></td>
                    <td className="px-2 py-1 text-center text-xs space-x-1">
                      {r.delay_impact && <span className="text-rose-600">delay</span>}
                      {r.cost_impact && <span className="text-amber-700">$</span>}
                    </td>
                    <td className="px-2 py-1 text-xs">{r.assigned_to || "—"}</td>
                    <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusTone(r.status)}`}>{r.status}</span></td>
                    <td className="px-2 py-1 text-right">
                      {canEdit && (
                        <div className="flex justify-end gap-1">
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`iss-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                          {r.status !== "closed" && <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-600" onClick={() => close(r)} data-testid={`iss-close-${r.id}`}><CheckCircle2 className="h-3.5 w-3.5" /></Button>}
                          {r.status !== "escalated" && r.status !== "closed" && <Button size="icon" variant="ghost" className="h-7 w-7 text-amber-700" onClick={() => escalate(r)} data-testid={`iss-esc-${r.id}`}><ArrowUpCircle className="h-3.5 w-3.5" /></Button>}
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`iss-del-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Site Issue</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Project *">
              <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm" disabled={!!editing?.id} data-testid="iss-form-project">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </F>
            <F label="Issue Date"><Input type="date" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} /></F>
            <F label="Title *" full><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="iss-form-title" /></F>
            <F label="Category">
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm">
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </F>
            <F label="Impact">
              <select value={form.impact} onChange={(e) => setForm({ ...form, impact: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="iss-form-impact">
                {IMPACTS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </F>
            <F label="Responsible Dept"><Input value={form.responsible_department} onChange={(e) => setForm({ ...form, responsible_department: e.target.value })} /></F>
            <F label="Assigned To"><Input value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })} /></F>
            <F label="Target Closure"><Input type="date" value={form.target_closure_date} onChange={(e) => setForm({ ...form, target_closure_date: e.target.value })} /></F>
            <F label="Description" full><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></F>
            <F label="Corrective Action" full><Textarea rows={2} value={form.corrective_action} onChange={(e) => setForm({ ...form, corrective_action: e.target.value })} /></F>
            <F label="Delay Impact?">
              <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.delay_impact} onChange={(e) => setForm({ ...form, delay_impact: e.target.checked })} />Yes</label>
            </F>
            <F label="Cost Impact?">
              <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.cost_impact} onChange={(e) => setForm({ ...form, cost_impact: e.target.checked })} />Yes</label>
            </F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="iss-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const IMPACT_TONES = { low: "bg-slate-50 text-slate-600 border-slate-200", medium: "bg-blue-50 text-blue-700 border-blue-200", high: "bg-amber-50 text-amber-700 border-amber-200", critical: "bg-rose-50 text-rose-700 border-rose-200" };
const STATUS_TONES = { open: "bg-slate-50 text-slate-600 border-slate-200", in_progress: "bg-blue-50 text-blue-700 border-blue-200", closed: "bg-emerald-50 text-emerald-700 border-emerald-200", escalated: "bg-rose-50 text-rose-700 border-rose-200" };
function impactTone(s) { return IMPACT_TONES[s] || IMPACT_TONES.medium; }
function statusTone(s) { return STATUS_TONES[s] || STATUS_TONES.open; }
function F({ label, full, children }) { return <div className={full ? "md:col-span-2" : ""}><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>; }
