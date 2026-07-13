/**
 * Client Compliance Register (Phase 4) — track mandatory client-side safety
 * documents/requirements per project (blocks project closure if pending).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CheckCircle2, Plus, RefreshCcw, Pencil } from "lucide-react";

const REQ_TYPES = [
  "safety_document", "training", "ppe", "permit", "inspection",
  "scaffold_standard", "medical_fitness", "hr_clearance", "site_clearance",
  "job_completion", "other",
];
const STATUS_TONE = {
  submitted: "bg-emerald-100 text-emerald-800",
  overdue: "bg-red-100 text-red-800",
  pending: "bg-amber-100 text-amber-800",
};

const EMPTY = {
  client_name: "", project_id: "", project_code: "", site_location: "",
  requirement: "", requirement_type: "safety_document",
  due_date: "", submitted_date: "", responsible_person: "",
  mandatory: false, remarks: "",
};

export default function ClientCompliance() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/client-compliance"), api.get("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const payload = { ...form };
      if (!payload.due_date) delete payload.due_date;
      if (!payload.submitted_date) delete payload.submitted_date;
      if (editing?.id) {
        await api.put(`/safety/client-compliance/${editing.id}`, payload);
        toast.success("Updated");
      } else {
        await api.post(`/safety/client-compliance`, payload);
        toast.success("Created");
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const markSubmitted = async (r) => {
    try {
      const payload = { ...r, submitted_date: new Date().toISOString().slice(0, 10) };
      delete payload.status;
      await api.put(`/safety/client-compliance/${r.id}`, payload);
      toast.success("Marked submitted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="client-compliance-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 4</div>
          <h1 className="font-display font-black text-2xl">Client Compliance Register</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Client-mandated safety documents, trainings, permits & inspections. Pending mandatory items block project closure.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="cc-new">
            <Plus className="h-4 w-4 mr-1" /> New Requirement
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Client / Project</th>
              <th className="text-left px-3 py-2">Requirement</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Due</th>
              <th className="text-left px-3 py-2">Submitted</th>
              <th className="text-center px-3 py-2">Mandatory</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={8} className="text-center py-8 text-slate-400">No client requirements logged yet.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`cc-row-${r.id}`}>
                <td className="px-3 py-2">
                  <div className="font-semibold">{r.client_name}</div>
                  <div className="text-xs text-slate-500">{r.project_code || "—"}</div>
                </td>
                <td className="px-3 py-2 max-w-sm">{r.requirement}</td>
                <td className="px-3 py-2 capitalize">{r.requirement_type.replace(/_/g, " ")}</td>
                <td className="px-3 py-2">{r.due_date || "—"}</td>
                <td className="px-3 py-2">{r.submitted_date || "—"}</td>
                <td className="px-3 py-2 text-center">{r.mandatory ? "✔" : ""}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${STATUS_TONE[r.status] || "bg-slate-100 text-slate-700"}`}>{r.status}</span>
                </td>
                <td className="px-3 py-2 text-right space-x-1">
                  {!r.submitted_date && (
                    <Button size="sm" variant="outline" onClick={() => markSubmitted(r)} data-testid={`cc-submit-${r.id}`}>
                      <CheckCircle2 className="h-3 w-3 mr-1" /> Submit
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`cc-edit-${r.id}`}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Client Requirement</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Client Name</Label>
              <Input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
            </div>
            <div>
              <Label>Project</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.project_id} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }}>
                <option value="">— Select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <Label>Requirement</Label>
              <Input value={form.requirement} onChange={(e) => setForm({ ...form, requirement: e.target.value })} placeholder="E.g. Height Work Permit, Safety Induction Certificate" />
            </div>
            <div>
              <Label>Type</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.requirement_type} onChange={(e) => setForm({ ...form, requirement_type: e.target.value })}>
                {REQ_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <Label>Site Location</Label>
              <Input value={form.site_location} onChange={(e) => setForm({ ...form, site_location: e.target.value })} />
            </div>
            <div>
              <Label>Due Date</Label>
              <Input type="date" value={form.due_date || ""} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </div>
            <div>
              <Label>Submitted Date</Label>
              <Input type="date" value={form.submitted_date || ""} onChange={(e) => setForm({ ...form, submitted_date: e.target.value })} />
            </div>
            <div>
              <Label>Responsible</Label>
              <Input value={form.responsible_person} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.mandatory} onChange={(e) => setForm({ ...form, mandatory: e.target.checked })} data-testid="cc-mandatory" />
                <span>Mandatory (blocks project closure)</span>
              </label>
            </div>
            <div className="col-span-2">
              <Label>Remarks</Label>
              <Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="cc-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
