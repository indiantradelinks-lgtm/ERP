/**
 * Safety Plan Register — per-project safety plan (one plan per project).
 * Simple register + edit dialog; no line items.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ShieldCheck, Plus, Pencil, RefreshCcw, Trash2 } from "lucide-react";

const STATUSES = ["draft", "active", "closed"];
const EMPTY = {
  project_id: "", project_code: "", client_name: "", site_location: "", service_type: "",
  scope_summary: "", key_hazards: "", ppe_summary: "", permits_summary: "",
  manpower_competency: "", emergency_plan: "", prepared_by: "", reviewed_by: "",
  approved_by: "", status: "draft", remarks: "",
};

export default function SafetyPlanRegister() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/plans"), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!form.project_id) { toast.error("Project is required"); return; }
    try {
      if (editing?.id) { await api.put(`/safety/plans/${editing.id}`, form); toast.success("Plan updated"); }
      else { const r = await api.post(`/safety/plans`, form); toast.success(`Plan ${r.data.plan_no} created`); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete plan ${r.plan_no}?`)) return;
    try { await api.delete(`/safety/plans/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="safety-plans-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <ShieldCheck className="h-6 w-6 text-emerald-600" /> Safety Plan Register
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">Project-level safety plans — one per project.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="plan-new">
            <Plus className="h-4 w-4 mr-1" /> New Safety Plan
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Plan #</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Client</th>
              <th className="text-left px-3 py-2">Service</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="text-center py-8 text-slate-400">No safety plans yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`plan-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">{r.plan_no}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.client_name || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.service_type || "—"}</td>
                <td className="px-3 py-2"><span className="inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded bg-slate-100">{r.status}</span></td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? `Edit ${editing.plan_no}` : "New Safety Plan"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Project *</Label>
              <select value={form.project_id || ""} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "", client_name: p?.client || "", site_location: p?.site || "" });
              }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="plan-form-project">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Status</Label>
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Service Type</Label><Input value={form.service_type || ""} onChange={(e) => setForm({ ...form, service_type: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Site Location</Label><Input value={form.site_location || ""} onChange={(e) => setForm({ ...form, site_location: e.target.value })} /></div>
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Scope Summary</Label><Textarea rows={2} value={form.scope_summary || ""} onChange={(e) => setForm({ ...form, scope_summary: e.target.value })} /></div>
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Key Hazards</Label><Textarea rows={2} value={form.key_hazards || ""} onChange={(e) => setForm({ ...form, key_hazards: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">PPE Summary</Label><Textarea rows={2} value={form.ppe_summary || ""} onChange={(e) => setForm({ ...form, ppe_summary: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Permits Summary</Label><Textarea rows={2} value={form.permits_summary || ""} onChange={(e) => setForm({ ...form, permits_summary: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Manpower Competency</Label><Textarea rows={2} value={form.manpower_competency || ""} onChange={(e) => setForm({ ...form, manpower_competency: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Emergency Plan</Label><Textarea rows={2} value={form.emergency_plan || ""} onChange={(e) => setForm({ ...form, emergency_plan: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Prepared By</Label><Input value={form.prepared_by || ""} onChange={(e) => setForm({ ...form, prepared_by: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Approved By</Label><Input value={form.approved_by || ""} onChange={(e) => setForm({ ...form, approved_by: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="plan-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
