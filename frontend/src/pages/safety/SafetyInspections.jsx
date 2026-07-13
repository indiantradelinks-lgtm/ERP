/**
 * Safety Inspections — register + editor with checklist lines.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ClipboardList, Plus, Pencil, RefreshCcw, X, Ban } from "lucide-react";

const INSPECTION_TYPES = ["daily_site", "weekly", "scaffold", "ppe", "work_at_height", "rope_access", "electrical", "fire_safety", "tools_tackles", "vehicle", "housekeeping", "client_audit"];
const RISK = ["", "low", "medium", "high", "critical"];
const STATUS_TONE = { draft: "bg-slate-100 text-slate-700", closed: "bg-emerald-100 text-emerald-800" };
const RISK_TONE = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-300",
  medium: "bg-amber-50 text-amber-700 border-amber-300",
  high: "bg-orange-50 text-orange-700 border-orange-300",
  critical: "bg-red-50 text-red-700 border-red-300",
};
const EMPTY_LINE = { checklist_item: "", compliant: null, observation: "", risk_level: "", corrective_action_required: false };
const EMPTY = {
  inspection_date: new Date().toISOString().slice(0, 10),
  inspection_type: "daily_site", project_id: "", project_code: "", site_location: "",
  inspector: "", area_inspected: "", compliance_status: "", risk_level: "",
  photo_ids: [], corrective_action_required: false, responsible_person: "", target_closure_date: "",
  remarks: "", lines: [],
};

export default function SafetyInspections() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/inspections"), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const payload = { ...form, lines: form.lines || [] };
      if (editing?.id) { await api.put(`/safety/inspections/${editing.id}`, payload); toast.success("Inspection updated"); }
      else { const r = await api.post(`/safety/inspections`, payload); toast.success(`Inspection ${r.data.inspection_no} created`); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const close = async (r) => { try { await api.post(`/safety/inspections/${r.id}/close`); toast.success("Closed"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Close failed"); } };

  const setLine = (i, patch) => setForm((f) => { const lines = [...(f.lines || [])]; lines[i] = { ...lines[i], ...patch }; return { ...f, lines }; });
  const addLine = () => setForm((f) => ({ ...f, lines: [...(f.lines || []), { ...EMPTY_LINE }] }));
  const removeLine = (i) => setForm((f) => ({ ...f, lines: (f.lines || []).filter((_, idx) => idx !== i) }));

  return (
    <div className="p-6 space-y-4" data-testid="inspections-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><ClipboardList className="h-6 w-6 text-primary" /> Safety Inspections</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Site inspections with checklist lines + risk-tagged findings.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="insp-new"><Plus className="h-4 w-4 mr-1" /> New Inspection</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600"><tr><th className="text-left px-3 py-2">Insp #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Type</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Inspector</th><th className="text-center px-3 py-2">Lines</th><th className="text-left px-3 py-2">Status</th><th className="text-right px-3 py-2"></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No inspections yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`insp-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">{r.inspection_no}</td>
                <td className="px-3 py-2 text-xs">{r.inspection_date}</td>
                <td className="px-3 py-2 text-xs">{r.inspection_type?.replaceAll("_", " ")}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.inspector || "—"}</td>
                <td className="px-3 py-2 text-center text-xs">{(r.lines || []).length}</td>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>{r.status}</span></td>
                <td className="px-3 py-2 text-right"><div className="flex justify-end gap-1">
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r, lines: r.lines || [] }); }}><Pencil className="h-3.5 w-3.5" /></Button>
                  {r.status !== "closed" && <Button size="icon" variant="ghost" className="h-7 w-7 text-purple-700" onClick={() => close(r)} data-testid={`insp-close-${r.id}`}><Ban className="h-3.5 w-3.5" /></Button>}
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-6xl max-h-[92vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? `Edit ${editing.inspection_no}` : "New Inspection"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div><Label className="text-[10px] uppercase tracking-wider">Date *</Label><Input type="date" value={form.inspection_date} onChange={(e) => setForm({ ...form, inspection_date: e.target.value })} data-testid="insp-form-date" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Type</Label>
              <select value={form.inspection_type} onChange={(e) => setForm({ ...form, inspection_type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {INSPECTION_TYPES.map((t) => <option key={t} value={t}>{t.replaceAll("_", " ")}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => { const p = projects.find((x) => x.id === e.target.value); setForm({ ...form, project_id: e.target.value, project_code: p?.code || "", site_location: p?.site || "" }); }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Inspector</Label><Input value={form.inspector || ""} onChange={(e) => setForm({ ...form, inspector: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Area Inspected</Label><Input value={form.area_inspected || ""} onChange={(e) => setForm({ ...form, area_inspected: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Risk Level</Label>
              <select value={form.risk_level || ""} onChange={(e) => setForm({ ...form, risk_level: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {RISK.map((r) => <option key={r} value={r}>{r || "—"}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Responsible</Label><Input value={form.responsible_person || ""} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Target Closure</Label><Input type="date" value={form.target_closure_date || ""} onChange={(e) => setForm({ ...form, target_closure_date: e.target.value })} /></div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Remarks</Label><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>

          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Checklist Lines ({(form.lines || []).length})</div>
              <Button size="sm" onClick={addLine}><Plus className="h-3.5 w-3.5 mr-1" /> Add Item</Button>
            </div>
            <div className="border rounded-sm overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wider"><tr><th className="text-left px-2 py-1.5">Checklist Item</th><th className="text-center px-2 py-1.5 w-24">Compliant?</th><th className="text-left px-2 py-1.5 w-24">Risk</th><th className="text-left px-2 py-1.5">Observation</th><th className="text-center px-2 py-1.5 w-16">Action?</th><th className="w-6"></th></tr></thead>
                <tbody>
                  {(form.lines || []).length === 0 && <tr><td colSpan={6} className="text-center py-4 text-slate-400 italic">No items yet.</td></tr>}
                  {(form.lines || []).map((l, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-1"><Input className="h-8 text-xs" value={l.checklist_item} onChange={(e) => setLine(i, { checklist_item: e.target.value })} /></td>
                      <td className="p-1"><select className="h-8 w-full rounded-sm border border-input bg-background text-xs px-1" value={l.compliant === null ? "" : String(l.compliant)} onChange={(e) => setLine(i, { compliant: e.target.value === "" ? null : e.target.value === "true" })}><option value="">—</option><option value="true">Yes</option><option value="false">No</option></select></td>
                      <td className="p-1"><select className={`h-8 w-full rounded-sm border text-xs px-1 ${l.risk_level ? RISK_TONE[l.risk_level] || "border-input bg-background" : "border-input bg-background"}`} value={l.risk_level || ""} onChange={(e) => setLine(i, { risk_level: e.target.value })}>{RISK.map((v) => <option key={v} value={v}>{v || "—"}</option>)}</select></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.observation || ""} onChange={(e) => setLine(i, { observation: e.target.value })} /></td>
                      <td className="p-1 text-center"><input type="checkbox" checked={!!l.corrective_action_required} onChange={(e) => setLine(i, { corrective_action_required: e.target.checked })} /></td>
                      <td className="p-1"><Button size="icon" variant="ghost" className="h-6 w-6 text-rose-600" onClick={() => removeLine(i)}><X className="h-3 w-3" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="insp-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
