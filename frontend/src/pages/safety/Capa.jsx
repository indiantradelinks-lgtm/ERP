/**
 * CAPA Register — closure requires evidence unless override reason is given.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Wrench, Plus, RefreshCcw, Ban, AlertOctagon, Filter } from "lucide-react";

const STATUS_TONE = { open: "bg-slate-100 text-slate-700", in_progress: "bg-amber-100 text-amber-800", closed: "bg-emerald-100 text-emerald-800", overdue: "bg-red-100 text-red-700" };
const SOURCES = ["inspection", "observation", "incident", "audit", "client_feedback"];
const EMPTY = { source_type: "observation", source_id: "", source_no: "", project_id: "", project_code: "", corrective_action: "", preventive_action: "", responsible_department: "", responsible_person: "", target_date: "", remarks: "" };

export default function Capa() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [closureFor, setClosureFor] = useState(null);
  const [closureForm, setClosureForm] = useState({ evidence_ids: [], evidence_input: "", override_reason: "", completion_notes: "" });

  const load = async () => {
    try {
      const q = statusFilter ? `?status=${statusFilter}` : "";
      const [a, b] = await Promise.all([api.get(`/safety/capa${q}`), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [statusFilter]);

  const save = async () => {
    try {
      if (editing?.id) { await api.put(`/safety/capa/${editing.id}`, form); toast.success("Updated"); }
      else { const r = await api.post("/safety/capa", form); toast.success(`CAPA ${r.data.capa_no} created`); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const closeCapa = async () => {
    try {
      const payload = { evidence_ids: closureForm.evidence_ids, override_reason: closureForm.override_reason || null, completion_notes: closureForm.completion_notes };
      await api.post(`/safety/capa/${closureFor.id}/close`, payload);
      toast.success("CAPA closed"); setClosureFor(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Close failed"); }
  };
  const tickOverdue = async () => { try { const r = await api.post(`/safety/capa/-/tick-overdue`); toast.success(`Flagged ${r.data.flagged_overdue} as overdue`); load(); } catch (e) { toast.error(e.response?.data?.detail || "Tick failed"); } };

  return (
    <div className="p-6 space-y-4" data-testid="capa-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><Wrench className="h-6 w-6 text-blue-600" /> CAPA Register</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Corrective + Preventive actions. Closure needs evidence unless override reason ≥ 10 chars.</p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-8 rounded-sm border border-input bg-background text-xs px-2">
            <option value="">All statuses</option><option>open</option><option>in_progress</option><option>overdue</option><option>closed</option>
          </select>
          <Button variant="outline" onClick={tickOverdue} data-testid="capa-tick">Flag Overdue</Button>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="capa-new"><Plus className="h-4 w-4 mr-1" /> New CAPA</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600"><tr><th className="text-left px-3 py-2">CAPA #</th><th className="text-left px-3 py-2">Source</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Corrective Action</th><th className="text-left px-3 py-2">Target</th><th className="text-left px-3 py-2">Status</th><th className="text-right px-3 py-2"></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">No CAPAs.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`capa-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">{r.capa_no}{r.auto_created && <span className="block text-[9px] text-blue-600">auto</span>}</td>
                <td className="px-3 py-2 text-xs"><span className="uppercase tracking-wider">{r.source_type}</span>{r.source_no && <div className="font-mono text-[10px]">{r.source_no}</div>}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs max-w-md truncate">{r.corrective_action}</td>
                <td className="px-3 py-2 text-xs">{r.target_date || "—"}</td>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>{r.status}</span></td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    {r.status !== "closed" && <>
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }}><Plus className="h-3.5 w-3.5 rotate-45" /></Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-purple-700" onClick={() => { setClosureFor(r); setClosureForm({ evidence_ids: [], evidence_input: "", override_reason: "", completion_notes: "" }); }} data-testid={`capa-close-${r.id}`}><Ban className="h-3.5 w-3.5" /></Button>
                    </>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit CAPA" : "New CAPA"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-[10px] uppercase tracking-wider">Source Type *</Label>
              <select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">{SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Source Reference (#)</Label><Input value={form.source_no || ""} onChange={(e) => setForm({ ...form, source_no: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => { const p = projects.find((x) => x.id === e.target.value); setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" }); }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Responsible Department</Label><Input value={form.responsible_department || ""} onChange={(e) => setForm({ ...form, responsible_department: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Responsible Person</Label><Input value={form.responsible_person || ""} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Target Date</Label><Input type="date" value={form.target_date || ""} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></div>
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Corrective Action *</Label><Textarea rows={3} value={form.corrective_action} onChange={(e) => setForm({ ...form, corrective_action: e.target.value })} data-testid="capa-form-corr" /></div>
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Preventive Action</Label><Textarea rows={3} value={form.preventive_action || ""} onChange={(e) => setForm({ ...form, preventive_action: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="capa-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={closureFor !== null} onOpenChange={(o) => !o && setClosureFor(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Close CAPA {closureFor?.capa_no}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="rounded-sm border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 flex items-start gap-2">
              <AlertOctagon className="h-3.5 w-3.5 mt-0.5" /> Provide evidence (comma-separated file IDs) **or** an override reason (min 10 chars).
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Evidence file IDs (comma-sep)</Label><Input value={closureForm.evidence_input || ""} onChange={(e) => setClosureForm({ ...closureForm, evidence_input: e.target.value, evidence_ids: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} data-testid="capa-close-evidence" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Override Reason (if no evidence)</Label><Textarea rows={2} value={closureForm.override_reason} onChange={(e) => setClosureForm({ ...closureForm, override_reason: e.target.value })} data-testid="capa-close-override" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Completion Notes</Label><Textarea rows={2} value={closureForm.completion_notes} onChange={(e) => setClosureForm({ ...closureForm, completion_notes: e.target.value })} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setClosureFor(null)}>Cancel</Button><Button onClick={closeCapa} data-testid="capa-close-submit">Close CAPA</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
