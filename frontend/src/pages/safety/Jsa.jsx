/**
 * JSA Register — Job Safety Analysis (job-step-based hazard register).
 * Same lifecycle as HIRA; high-risk lines route to approvals.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { ClipboardList, Plus, Pencil, Send, RefreshCcw, RotateCcw, Trash2, X } from "lucide-react";

const RISK = ["", "low", "medium", "high", "critical"];
const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700",
  pending_approval: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  sent_back: "bg-red-100 text-red-700",
  closed: "bg-zinc-100 text-zinc-600",
};
const RISK_TONE = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-300",
  medium: "bg-amber-50 text-amber-700 border-amber-300",
  high: "bg-orange-50 text-orange-700 border-orange-300",
  critical: "bg-red-50 text-red-700 border-red-300",
};

const EMPTY_LINE = {
  step_no: null, step: "", hazard: "", risk: "", control_measure: "",
  required_ppe: [], required_permit_ids: [], manpower_competency: "", responsible_person: "",
};
const EMPTY = {
  project_id: "", project_code: "", site_location: "", activity: "",
  prepared_by: "", reviewed_by: "", approved_by: "", remarks: "", lines: [],
};

export default function Jsa() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/jsa"), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const openEditor = (r) => { setEditing(r || {}); setForm(r ? { ...EMPTY, ...r, lines: r.lines || [] } : EMPTY); };

  const save = async () => {
    if (!form.activity?.trim()) { toast.error("Activity is required"); return; }
    try {
      const payload = { ...form };
      if (editing?.id) { await api.put(`/safety/jsa/${editing.id}`, payload); toast.success("JSA updated"); }
      else { const r = await api.post(`/safety/jsa`, payload); toast.success(`JSA ${r.data.jsa_no} created`); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const submit = async (r) => {
    try {
      const res = await api.post(`/safety/jsa/${r.id}/submit`);
      toast.success(res.data.status === "pending_approval" ? "Submitted for approval (high-risk)" : "Auto-approved");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Submit failed"); }
  };
  const revise = async (r) => {
    if (!window.confirm(`Revise ${r.jsa_no}?`)) return;
    try { await api.post(`/safety/jsa/${r.id}/revise`); toast.success("Revised"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Revise failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.jsa_no}?`)) return;
    try { await api.delete(`/safety/jsa/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const setLine = (i, patch) => setForm((f) => { const lines = [...(f.lines || [])]; lines[i] = { ...lines[i], ...patch }; return { ...f, lines }; });
  const addLine = () => setForm((f) => ({ ...f, lines: [...(f.lines || []), { ...EMPTY_LINE, step_no: (f.lines?.length || 0) + 1 }] }));
  const removeLine = (i) => setForm((f) => ({ ...f, lines: (f.lines || []).filter((_, idx) => idx !== i) }));

  const hasHighRisk = (form.lines || []).some((l) => ["high", "critical"].includes((l.risk || "").toLowerCase()));

  return (
    <div className="p-6 space-y-4" data-testid="jsa-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <ClipboardList className="h-6 w-6 text-red-600" /> JSA · Job Safety Analysis
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Job-step-based hazard register with PPE + permit + competency requirements. High-risk JSAs need approval.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => openEditor(null)} data-testid="jsa-new"><Plus className="h-4 w-4 mr-1" /> New JSA</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">JSA #</th>
              <th className="text-left px-3 py-2">Rev</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Activity</th>
              <th className="text-center px-3 py-2">Steps</th>
              <th className="text-center px-3 py-2">High Risk</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No JSAs yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`jsa-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">{r.jsa_no}</td>
                <td className="px-3 py-2 text-xs">R{r.rev || 0}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.activity}</td>
                <td className="px-3 py-2 text-center text-xs tabular">{(r.lines || []).length}</td>
                <td className="px-3 py-2 text-center">{r.high_risk ? <span className="text-red-600 font-bold text-xs">YES</span> : <span className="text-slate-400 text-xs">no</span>}</td>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>{(r.status || "").replaceAll("_", " ")}</span></td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEditor(r)} data-testid={`jsa-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    {(r.status === "draft" || r.status === "sent_back") && <Button size="icon" variant="ghost" className="h-7 w-7 text-blue-600" onClick={() => submit(r)} data-testid={`jsa-submit-${r.id}`}><Send className="h-3.5 w-3.5" /></Button>}
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-amber-600" onClick={() => revise(r)}><RotateCcw className="h-3.5 w-3.5" /></Button>
                    {r.status !== "approved" && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)}><Trash2 className="h-3.5 w-3.5" /></Button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-6xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing?.id ? `Edit ${editing.jsa_no}` : "New JSA"}</DialogTitle>
            <DialogDescription className="text-xs">
              {hasHighRisk
                ? <span className="text-red-700 font-semibold">⚠ High-risk lines detected — Safety Officer + Project Manager approval required.</span>
                : "Only low/medium risk lines — will auto-approve on submit."}
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "", site_location: p?.site || form.site_location });
              }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Site Location</Label><Input value={form.site_location || ""} onChange={(e) => setForm({ ...form, site_location: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Activity *</Label><Input value={form.activity || ""} onChange={(e) => setForm({ ...form, activity: e.target.value })} data-testid="jsa-form-activity" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Prepared By</Label><Input value={form.prepared_by || ""} onChange={(e) => setForm({ ...form, prepared_by: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Reviewed By</Label><Input value={form.reviewed_by || ""} onChange={(e) => setForm({ ...form, reviewed_by: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Approved By</Label><Input value={form.approved_by || ""} onChange={(e) => setForm({ ...form, approved_by: e.target.value })} /></div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Remarks</Label><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>

          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Job Steps ({(form.lines || []).length})</div>
              <Button size="sm" onClick={addLine}><Plus className="h-3.5 w-3.5 mr-1" /> Add Step</Button>
            </div>
            <div className="border rounded-sm overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-2 py-1.5 w-14">#</th>
                    <th className="text-left px-2 py-1.5">Step</th>
                    <th className="text-left px-2 py-1.5">Hazard</th>
                    <th className="text-left px-2 py-1.5 w-24">Risk</th>
                    <th className="text-left px-2 py-1.5">Control Measure</th>
                    <th className="text-left px-2 py-1.5">Manpower Competency</th>
                    <th className="text-left px-2 py-1.5 w-28">Responsible</th>
                    <th className="w-6"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.lines || []).length === 0 && <tr><td colSpan={8} className="text-center py-4 text-slate-400 italic">No steps yet.</td></tr>}
                  {(form.lines || []).map((l, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-1"><Input type="number" className="h-8 text-xs w-14" value={l.step_no || i + 1} onChange={(e) => setLine(i, { step_no: Number(e.target.value) || null })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.step} onChange={(e) => setLine(i, { step: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.hazard} onChange={(e) => setLine(i, { hazard: e.target.value })} /></td>
                      <td className="p-1">
                        <select className={`h-8 w-full rounded-sm border text-xs px-1 ${l.risk ? RISK_TONE[l.risk] || "border-input bg-background" : "border-input bg-background"}`}
                          value={l.risk || ""} onChange={(e) => setLine(i, { risk: e.target.value })} data-testid={`jsa-line-${i}-risk`}>
                          {RISK.map((v) => <option key={v} value={v}>{v || "—"}</option>)}
                        </select>
                      </td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.control_measure} onChange={(e) => setLine(i, { control_measure: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.manpower_competency} onChange={(e) => setLine(i, { manpower_competency: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.responsible_person} onChange={(e) => setLine(i, { responsible_person: e.target.value })} /></td>
                      <td className="p-1"><Button size="icon" variant="ghost" className="h-6 w-6 text-rose-600" onClick={() => removeLine(i)}><X className="h-3 w-3" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {editing?.revisions?.length > 0 && (
            <div className="mt-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Revision History ({editing.revisions.length})</div>
              <ul className="text-xs space-y-1">{editing.revisions.map((rv, i) => <li key={i} className="border rounded-sm p-1.5 bg-amber-50/40">R{rv.rev} · {rv.revised_at?.slice(0, 16).replace("T", " ")} by <b>{rv.revised_by}</b></li>)}</ul>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="jsa-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
