/**
 * PPE Requirements — configure required PPE per project/service/activity/permit-type.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Hammer, Plus, Pencil, Trash2, RefreshCcw } from "lucide-react";

const EMPTY = { project_id: "", project_code: "", service_type: "", activity: "", permit_type_id: "", hazard_category_id: "", required_ppe_ids: [], notes: "", active: true };

export default function PpeRequirements() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [permitTypes, setPermitTypes] = useState([]);
  const [ppeCategories, setPpeCategories] = useState([]);
  const [hazardCats, setHazardCats] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b, c, d, e] = await Promise.all([
        api.get("/safety/ppe-requirements"),
        api.get("/projects"),
        api.get("/safety/masters/work-permit-types"),
        api.get("/safety/masters/ppe-categories"),
        api.get("/safety/masters/hazard-categories"),
      ]);
      setRows(a.data || []); setProjects(b.data || []); setPermitTypes(c.data || []); setPpeCategories(d.data || []); setHazardCats(e.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!(form.required_ppe_ids || []).length) { toast.error("Select at least one PPE"); return; }
    try {
      if (editing?.id) { await api.put(`/safety/ppe-requirements/${editing.id}`, form); toast.success("Updated"); }
      else { await api.post(`/safety/ppe-requirements`, form); toast.success("Created"); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => { if (!window.confirm("Deactivate?")) return; try { await api.delete(`/safety/ppe-requirements/${r.id}`); toast.success("Deactivated"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); } };

  const nameFor = (list, id) => list.find((x) => x.id === id)?.name || id;

  return (
    <div className="p-6 space-y-4" data-testid="ppe-reqs-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><Hammer className="h-6 w-6 text-orange-600" /> PPE Requirements</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Define what PPE is required per project · service · activity · permit type · hazard.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="ppe-req-new"><Plus className="h-4 w-4 mr-1" /> New Requirement</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Service</th><th className="text-left px-3 py-2">Activity</th><th className="text-left px-3 py-2">Permit Type</th><th className="text-left px-3 py-2">Required PPE</th><th className="text-right px-3 py-2"></th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="text-center py-8 text-slate-400">No requirements yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`ppe-req-row-${r.id}`}>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.service_type || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.activity || "—"}</td>
                <td className="px-3 py-2 text-xs">{nameFor(permitTypes, r.permit_type_id) || "—"}</td>
                <td className="px-3 py-2 text-xs">{(r.required_ppe_ids || []).map((id) => nameFor(ppeCategories, id)).join(", ") || "—"}</td>
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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} PPE Requirement</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => { const p = projects.find((x) => x.id === e.target.value); setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" }); }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— any —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Service Type</Label><Input value={form.service_type || ""} onChange={(e) => setForm({ ...form, service_type: e.target.value })} placeholder="e.g. rope_access" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Activity</Label><Input value={form.activity || ""} onChange={(e) => setForm({ ...form, activity: e.target.value })} /></div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Permit Type</Label>
              <select value={form.permit_type_id || ""} onChange={(e) => setForm({ ...form, permit_type_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— any —</option>{permitTypes.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Hazard Category</Label>
              <select value={form.hazard_category_id || ""} onChange={(e) => setForm({ ...form, hazard_category_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— any —</option>{hazardCats.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Required PPE * (Ctrl/Cmd-click to multi-select)</Label>
              <select multiple value={form.required_ppe_ids || []} onChange={(e) => setForm({ ...form, required_ppe_ids: Array.from(e.target.selectedOptions, (o) => o.value) })} className="min-h-[120px] w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="ppe-req-form-ppe">
                {ppeCategories.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              {ppeCategories.length === 0 && <p className="text-[10px] text-amber-700 mt-1">No PPE categories yet — add some in Safety Master Data → PPE Category.</p>}
            </div>
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Notes</Label><Textarea rows={2} value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="ppe-req-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
