/**
 * Incidents & Near-Miss unified register. Critical incident types auto-create
 * escalations + optional cost approval. Investigation close spawns a CAPA.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { AlertTriangle, Plus, RefreshCcw, Search, Ban, FileSearch, Filter, Lock } from "lucide-react";

const TYPES = [
  { v: "near_miss", label: "Near Miss", critical: false },
  { v: "first_aid_case", label: "First Aid Case", critical: false },
  { v: "medical_treatment_case", label: "Medical Treatment Case", critical: false },
  { v: "lost_time_injury", label: "Lost Time Injury", critical: true },
  { v: "fatality", label: "Fatality", critical: true },
  { v: "property_damage", label: "Property Damage", critical: true },
  { v: "fire", label: "Fire", critical: true },
  { v: "vehicle_incident", label: "Vehicle Incident", critical: false },
  { v: "environmental_incident", label: "Environmental Incident", critical: true },
  { v: "unsafe_condition", label: "Unsafe Condition", critical: false },
  { v: "other", label: "Other", critical: false },
];
const STATUS_TONE = { reported: "bg-red-100 text-red-800", investigating: "bg-amber-100 text-amber-800", closed: "bg-emerald-100 text-emerald-800" };
const EMPTY_PERSON = { employee_id: "", name: "", role: "", injury_type: "", injury_body_part: "", treatment_given: "", medical_notes: "", days_lost: 0 };
const EMPTY = {
  incident_datetime: new Date().toISOString().slice(0, 16), project_id: "", project_code: "", site_location: "",
  incident_type: "near_miss", description: "", location_area: "",
  people_involved: [], immediate_action_taken: "", root_cause: "", corrective_action: "", preventive_action: "",
  responsible_person: "", target_closure_date: "", attachments: [], damaged_ppe_ids: [],
  medical_cost: 0, penalty_cost: 0, recovery_amount: 0, reported_by: "",
};

export default function Incidents() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const q = typeFilter ? `?incident_type=${typeFilter}` : "";
      const [a, b] = await Promise.all([api.get(`/safety/incidents${q}`), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [typeFilter]);

  const save = async () => {
    if ((form.description || "").length < 10) { toast.error("Description must be at least 10 chars"); return; }
    try {
      if (editing?.id) { await api.put(`/safety/incidents/${editing.id}`, form); toast.success("Incident updated"); }
      else { const r = await api.post(`/safety/incidents`, form); toast.success(`Incident ${r.data.incident_no} logged`); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const closeInvestigation = async (r) => {
    if (!r.root_cause) { toast.error("Add root cause before closing investigation"); return; }
    try { const res = await api.post(`/safety/incidents/${r.id}/close-investigation`); toast.success(`Investigation closed · CAPA ${res.data.capa_no} auto-created`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const closeIncident = async (r) => {
    try { await api.post(`/safety/incidents/${r.id}/close`); toast.success("Incident closed"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const addPerson = () => setForm((f) => ({ ...f, people_involved: [...(f.people_involved || []), { ...EMPTY_PERSON }] }));
  const setPerson = (i, patch) => setForm((f) => { const p = [...(f.people_involved || [])]; p[i] = { ...p[i], ...patch }; return { ...f, people_involved: p }; });
  const removePerson = (i) => setForm((f) => ({ ...f, people_involved: (f.people_involved || []).filter((_, idx) => idx !== i) }));

  const selectedType = TYPES.find((t) => t.v === form.incident_type);

  return (
    <div className="p-6 space-y-4" data-testid="incidents-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><AlertTriangle className="h-6 w-6 text-red-600" /> Incidents & Near-Miss</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Critical types auto-escalate to Owner / Ops Head / Safety Head. Costs ≥ ₹50k auto-route to Finance Head.</p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="h-8 rounded-sm border border-input bg-background text-xs px-2">
            <option value="">All types</option>{TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="inc-new"><Plus className="h-4 w-4 mr-1" /> Log Incident</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600"><tr><th className="text-left px-3 py-2">Inc #</th><th className="text-left px-3 py-2">When</th><th className="text-left px-3 py-2">Type</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Description</th><th className="text-right px-3 py-2">Cost (₹)</th><th className="text-left px-3 py-2">Status</th><th className="text-right px-3 py-2"></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No incidents recorded.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`inc-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">
                  {r.incident_no}
                  {r.is_critical && <span className="block text-[9px] text-red-700 font-bold uppercase">CRITICAL</span>}
                  {r.escalation_id && <span className="block text-[9px] text-purple-600">escalated</span>}
                  {r.cost_approval_id && <span className="block text-[9px] text-blue-600">cost →Fin</span>}
                </td>
                <td className="px-3 py-2 text-xs">{r.incident_datetime?.slice(0, 16).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs">{r.incident_type?.replaceAll("_", " ")}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs max-w-xs truncate">{r.description}</td>
                <td className="px-3 py-2 text-xs tabular text-right">{((r.medical_cost || 0) + (r.penalty_cost || 0)).toLocaleString("en-IN")}</td>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>{r.status?.replaceAll("_", " ")}</span>
                  <div className="text-[9px] mt-0.5 text-muted-foreground">Inv: {r.investigation_status}</div>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r, people_involved: r.people_involved || [] }); }}><FileSearch className="h-3.5 w-3.5" /></Button>
                    {r.investigation_status === "pending" && r.status !== "closed" && <Button size="icon" variant="ghost" className="h-7 w-7 text-amber-700" onClick={() => closeInvestigation(r)} data-testid={`inc-close-inv-${r.id}`}><Search className="h-3.5 w-3.5" /></Button>}
                    {r.investigation_status === "closed" && r.status !== "closed" && <Button size="icon" variant="ghost" className="h-7 w-7 text-purple-700" onClick={() => closeIncident(r)}><Ban className="h-3.5 w-3.5" /></Button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing?.id ? `Edit ${editing.incident_no}` : "Log Incident / Near-Miss"}</DialogTitle>
            {selectedType?.critical && <DialogDescription className="text-red-700 font-semibold text-xs">⚠ Critical type — auto-escalation to Owner / Ops Head / Safety Head on save.</DialogDescription>}
          </DialogHeader>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div><Label className="text-[10px] uppercase tracking-wider">When *</Label><Input type="datetime-local" value={form.incident_datetime} onChange={(e) => setForm({ ...form, incident_datetime: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Type *</Label>
              <select value={form.incident_type} onChange={(e) => setForm({ ...form, incident_type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="inc-form-type">
                {TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}{t.critical ? " ⚠" : ""}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => { const p = projects.find((x) => x.id === e.target.value); setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" }); }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Site</Label><Input value={form.site_location || ""} onChange={(e) => setForm({ ...form, site_location: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Location / Area</Label><Input value={form.location_area || ""} onChange={(e) => setForm({ ...form, location_area: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Reported By</Label><Input value={form.reported_by || ""} onChange={(e) => setForm({ ...form, reported_by: e.target.value })} /></div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Description * (min 10 chars)</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="inc-form-desc" /></div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Immediate Action Taken</Label><Textarea rows={2} value={form.immediate_action_taken || ""} onChange={(e) => setForm({ ...form, immediate_action_taken: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Medical Cost (₹)</Label><Input type="number" value={form.medical_cost || 0} onChange={(e) => setForm({ ...form, medical_cost: Number(e.target.value) || 0 })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Penalty Cost (₹)</Label><Input type="number" value={form.penalty_cost || 0} onChange={(e) => setForm({ ...form, penalty_cost: Number(e.target.value) || 0 })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Recovery (₹)</Label><Input type="number" value={form.recovery_amount || 0} onChange={(e) => setForm({ ...form, recovery_amount: Number(e.target.value) || 0 })} /></div>
          </div>

          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">People Involved ({(form.people_involved || []).length})</div>
              <Button size="sm" onClick={addPerson}><Plus className="h-3.5 w-3.5 mr-1" /> Add Person</Button>
            </div>
            {(form.people_involved || []).length > 0 && (
              <div className="text-[10px] text-amber-700 flex items-center gap-1 mb-2"><Lock className="h-3 w-3" /> Medical / injury details are visible only to Safety Head / HR Head / Doctor.</div>
            )}
            {(form.people_involved || []).map((p, i) => (
              <div key={i} className="grid grid-cols-2 md:grid-cols-4 gap-2 border rounded-sm p-2 mb-2 bg-slate-50/40">
                <Input placeholder="Employee ID" value={p.employee_id || ""} onChange={(e) => setPerson(i, { employee_id: e.target.value })} />
                <Input placeholder="Name" value={p.name || ""} onChange={(e) => setPerson(i, { name: e.target.value })} />
                <Input placeholder="Role" value={p.role || ""} onChange={(e) => setPerson(i, { role: e.target.value })} />
                <Input placeholder="Days Lost" type="number" value={p.days_lost || 0} onChange={(e) => setPerson(i, { days_lost: Number(e.target.value) || 0 })} />
                <Input placeholder="Injury Type (restricted)" value={p.injury_type || ""} onChange={(e) => setPerson(i, { injury_type: e.target.value })} />
                <Input placeholder="Body Part (restricted)" value={p.injury_body_part || ""} onChange={(e) => setPerson(i, { injury_body_part: e.target.value })} />
                <Input placeholder="Treatment (restricted)" value={p.treatment_given || ""} onChange={(e) => setPerson(i, { treatment_given: e.target.value })} />
                <div className="flex gap-1"><Input placeholder="Medical notes (restricted)" value={p.medical_notes || ""} onChange={(e) => setPerson(i, { medical_notes: e.target.value })} /><Button variant="ghost" size="icon" className="text-rose-600" onClick={() => removePerson(i)}>×</Button></div>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-2">Investigation</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Root Cause (required to close investigation)</Label><Textarea rows={2} value={form.root_cause || ""} onChange={(e) => setForm({ ...form, root_cause: e.target.value })} data-testid="inc-form-root" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Corrective Action</Label><Textarea rows={2} value={form.corrective_action || ""} onChange={(e) => setForm({ ...form, corrective_action: e.target.value })} /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Preventive Action</Label><Textarea rows={2} value={form.preventive_action || ""} onChange={(e) => setForm({ ...form, preventive_action: e.target.value })} /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Responsible</Label><Input value={form.responsible_person || ""} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Target Closure</Label><Input type="date" value={form.target_closure_date || ""} onChange={(e) => setForm({ ...form, target_closure_date: e.target.value })} /></div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="inc-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
