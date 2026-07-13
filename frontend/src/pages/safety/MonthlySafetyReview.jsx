/**
 * Monthly Safety Review (Phase 4) — monthly HSE meeting minutes with
 * action items. Each action item auto-creates a CAPA.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CalendarDays, Plus, RefreshCcw, X, Eye } from "lucide-react";

const EMPTY_ACTION = { description: "", responsible_person: "", target_date: "", status: "open" };
const EMPTY = {
  month: new Date().toISOString().slice(0, 7),
  meeting_date: new Date().toISOString().slice(0, 10),
  project_id: "", project_code: "", site_location: "",
  attendees: [], key_observations: "", ofis: "",
  incident_review: "", capa_status_summary: "", training_status: "",
  ppe_compliance_status: "", client_observations: "", action_items: [],
};

export default function MonthlySafetyReview() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [attendeeInput, setAttendeeInput] = useState("");

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/reviews"), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const r = await api.post(`/safety/reviews`, form);
      toast.success(`Review ${r.data.review_no} recorded · ${(r.data.action_items || []).length} auto-CAPAs raised`);
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const addAttendee = () => {
    if (!attendeeInput.trim()) return;
    setForm((f) => ({ ...f, attendees: [...(f.attendees || []), attendeeInput.trim()] }));
    setAttendeeInput("");
  };
  const removeAttendee = (i) => setForm((f) => ({ ...f, attendees: (f.attendees || []).filter((_, idx) => idx !== i) }));

  const setAction = (i, patch) => setForm((f) => {
    const arr = [...(f.action_items || [])]; arr[i] = { ...arr[i], ...patch }; return { ...f, action_items: arr };
  });
  const addAction = () => setForm((f) => ({ ...f, action_items: [...(f.action_items || []), { ...EMPTY_ACTION }] }));
  const removeAction = (i) => setForm((f) => ({ ...f, action_items: (f.action_items || []).filter((_, idx) => idx !== i) }));

  return (
    <div className="p-6 space-y-4" data-testid="monthly-review-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <CalendarDays className="h-6 w-6 text-red-600" /> Monthly Safety Review
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Monthly HSE meeting minutes with action items — each action auto-creates a CAPA for tracking.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="rev-new">
            <Plus className="h-4 w-4 mr-1" /> New Review
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Review #</th>
              <th className="text-left px-3 py-2">Month</th>
              <th className="text-left px-3 py-2">Date</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-center px-3 py-2">Attendees</th>
              <th className="text-center px-3 py-2">Actions</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={7} className="text-center py-8 text-slate-400">No monthly reviews recorded yet.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`rev-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.review_no}</td>
                <td className="px-3 py-2">{r.month}</td>
                <td className="px-3 py-2">{r.meeting_date}</td>
                <td className="px-3 py-2">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-center">{(r.attendees || []).length}</td>
                <td className="px-3 py-2 text-center">{(r.action_items || []).length}</td>
                <td className="px-3 py-2 text-right">
                  <Button size="sm" variant="outline" onClick={() => setViewing(r)} data-testid={`rev-view-${r.id}`}>
                    <Eye className="h-3 w-3 mr-1" /> View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Create dialog */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Monthly Safety Review</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Month</Label>
              <Input type="month" value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} />
            </div>
            <div>
              <Label>Meeting Date</Label>
              <Input type="date" value={form.meeting_date} onChange={(e) => setForm({ ...form, meeting_date: e.target.value })} />
            </div>
            <div>
              <Label>Project</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.project_id} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }}>
                <option value="">— Optional / Corporate —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Site Location</Label>
              <Input value={form.site_location} onChange={(e) => setForm({ ...form, site_location: e.target.value })} />
            </div>

            <div className="col-span-2">
              <Label>Attendees</Label>
              <div className="flex gap-2 mb-1">
                <Input value={attendeeInput} onChange={(e) => setAttendeeInput(e.target.value)} placeholder="Type name and press +" />
                <Button size="sm" variant="outline" onClick={addAttendee}><Plus className="h-3 w-3" /></Button>
              </div>
              <div className="flex flex-wrap gap-1">
                {(form.attendees || []).map((a, i) => (
                  <span key={i} className="inline-flex items-center gap-1 text-xs bg-slate-100 rounded px-2 py-0.5">
                    {a} <button onClick={() => removeAttendee(i)}><X className="h-3 w-3" /></button>
                  </span>
                ))}
              </div>
            </div>

            <div className="col-span-2">
              <Label>Key Observations</Label>
              <Textarea rows={2} value={form.key_observations} onChange={(e) => setForm({ ...form, key_observations: e.target.value })} />
            </div>
            <div className="col-span-2">
              <Label>OFIs (Opportunities for Improvement)</Label>
              <Textarea rows={2} value={form.ofis} onChange={(e) => setForm({ ...form, ofis: e.target.value })} />
            </div>
            <div>
              <Label>Incident Review</Label>
              <Textarea rows={2} value={form.incident_review} onChange={(e) => setForm({ ...form, incident_review: e.target.value })} />
            </div>
            <div>
              <Label>CAPA Status Summary</Label>
              <Textarea rows={2} value={form.capa_status_summary} onChange={(e) => setForm({ ...form, capa_status_summary: e.target.value })} />
            </div>
            <div>
              <Label>Training Status</Label>
              <Textarea rows={2} value={form.training_status} onChange={(e) => setForm({ ...form, training_status: e.target.value })} />
            </div>
            <div>
              <Label>PPE Compliance Status</Label>
              <Textarea rows={2} value={form.ppe_compliance_status} onChange={(e) => setForm({ ...form, ppe_compliance_status: e.target.value })} />
            </div>
            <div className="col-span-2">
              <Label>Client Observations</Label>
              <Textarea rows={2} value={form.client_observations} onChange={(e) => setForm({ ...form, client_observations: e.target.value })} />
            </div>
          </div>

          <div className="mt-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Action Items ({(form.action_items || []).length}) · Each item auto-creates a CAPA
              </div>
              <Button size="sm" variant="outline" onClick={addAction} data-testid="rev-add-action"><Plus className="h-3 w-3 mr-1" /> Add Action</Button>
            </div>
            <div className="space-y-2">
              {(form.action_items || []).map((a, i) => (
                <div key={i} className="border rounded p-2 grid grid-cols-2 gap-2 bg-slate-50/40">
                  <div className="col-span-2 flex items-center gap-2">
                    <Input placeholder="Action description" value={a.description} onChange={(e) => setAction(i, { description: e.target.value })} />
                    <Button size="sm" variant="ghost" onClick={() => removeAction(i)}><X className="h-3 w-3" /></Button>
                  </div>
                  <Input placeholder="Responsible" value={a.responsible_person || ""} onChange={(e) => setAction(i, { responsible_person: e.target.value })} />
                  <Input type="date" value={a.target_date || ""} onChange={(e) => setAction(i, { target_date: e.target.value })} />
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="rev-save">Save Review</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* View dialog */}
      <Dialog open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{viewing?.review_no} · {viewing?.month}</DialogTitle>
          </DialogHeader>
          {viewing && (
            <div className="space-y-3 text-sm">
              <div><span className="text-xs uppercase text-slate-500">Project:</span> {viewing.project_code || "Corporate"}</div>
              <div><span className="text-xs uppercase text-slate-500">Attendees:</span> {(viewing.attendees || []).join(", ") || "—"}</div>
              {viewing.key_observations && (<div><div className="text-xs uppercase text-slate-500">Key Observations</div><div>{viewing.key_observations}</div></div>)}
              {viewing.ofis && (<div><div className="text-xs uppercase text-slate-500">OFIs</div><div>{viewing.ofis}</div></div>)}
              {viewing.incident_review && (<div><div className="text-xs uppercase text-slate-500">Incident Review</div><div>{viewing.incident_review}</div></div>)}
              <div>
                <div className="text-xs uppercase text-slate-500 mb-1">Action Items ({(viewing.action_items || []).length})</div>
                <ul className="list-disc pl-5 space-y-1">
                  {(viewing.action_items || []).map((a, i) => (
                    <li key={i}>{a.description} — <span className="text-slate-500">{a.responsible_person || "Unassigned"} · {a.target_date || "No date"}</span></li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
