/**
 * Safety Observations / OFI register. High-risk observations auto-create a
 * draft CAPA on save (backend handles it).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Eye, Plus, RefreshCcw, Ban, AlertTriangle } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const KINDS = [
  { v: "unsafe_act", label: "Unsafe Act" },
  { v: "unsafe_condition", label: "Unsafe Condition" },
  { v: "ofi", label: "Opportunity for Improvement (OFI)" },
];
const RISK = ["", "low", "medium", "high", "critical"];
const STATUS_TONE = { open: "bg-red-100 text-red-700", in_progress: "bg-amber-100 text-amber-800", closed: "bg-emerald-100 text-emerald-800", overdue: "bg-red-200 text-red-900", escalated: "bg-purple-100 text-purple-800" };
const EMPTY = { observation_date: new Date().toISOString().slice(0, 10), project_id: "", project_code: "", site_location: "", category_id: "", kind: "unsafe_act", description: "", risk_level: "", immediate_action_taken: "", corrective_action_required: false, responsible_person: "", target_date: "", reported_by: "" };

export default function SafetyObservationsRegister() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [categories, setCategories] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b, c] = await Promise.all([api.get("/safety/observations-v2"), lookupGet("/projects"), api.get("/safety/masters/observation-categories")]);
      setRows(a.data || []); setProjects(b.data || []); setCategories(c.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const r = await api.post("/safety/observations-v2", form);
      if (r.data.capa_id) toast.success(`Observation ${r.data.observation_no} created — high-risk → CAPA auto-created`);
      else toast.success(`Observation ${r.data.observation_no} created`);
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const close = async (r) => { try { await api.post(`/safety/observations-v2/${r.id}/close`); toast.success("Closed"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Close failed"); } };

  const isHighRisk = ["high", "critical"].includes((form.risk_level || "").toLowerCase());

  return (
    <div className="p-6 space-y-4" data-testid="obs-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><Eye className="h-6 w-6 text-amber-600" /> Safety Observations / OFI</h1>
          <p className="text-xs text-muted-foreground mt-0.5">High-risk observations automatically create a draft CAPA + escalation.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="obs-new"><Plus className="h-4 w-4 mr-1" /> New Observation</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600"><tr><th className="text-left px-3 py-2">Obs #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Kind</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Description</th><th className="text-left px-3 py-2">Risk</th><th className="text-left px-3 py-2">Status</th><th className="text-right px-3 py-2"></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No observations yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`obs-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">{r.observation_no}{r.capa_id && <span className="block text-[9px] text-blue-600">→ CAPA</span>}</td>
                <td className="px-3 py-2 text-xs">{r.observation_date}</td>
                <td className="px-3 py-2 text-xs">{r.kind?.replaceAll("_", " ")}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs max-w-xs truncate">{r.description}</td>
                <td className="px-3 py-2 text-xs uppercase tracking-wider">{r.risk_level || "—"}</td>
                <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>{r.status}</span></td>
                <td className="px-3 py-2 text-right">{r.status !== "closed" && <Button size="icon" variant="ghost" className="h-7 w-7 text-purple-700" onClick={() => close(r)}><Ban className="h-3.5 w-3.5" /></Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Observation</DialogTitle></DialogHeader>
          {isHighRisk && (
            <div className="rounded-sm border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              High-risk observation — a **draft CAPA + escalation** will be auto-created on save.
            </div>
          )}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div><Label className="text-[10px] uppercase tracking-wider">Date *</Label><Input type="date" value={form.observation_date} onChange={(e) => setForm({ ...form, observation_date: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Kind</Label>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {KINDS.map((k) => <option key={k.v} value={k.v}>{k.label}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Risk</Label>
              <select value={form.risk_level || ""} onChange={(e) => setForm({ ...form, risk_level: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="obs-form-risk">
                {RISK.map((r) => <option key={r} value={r}>{r || "—"}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => { const p = projects.find((x) => x.id === e.target.value); setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" }); }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Site</Label><Input value={form.site_location || ""} onChange={(e) => setForm({ ...form, site_location: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Category</Label>
              <select value={form.category_id || ""} onChange={(e) => setForm({ ...form, category_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Description * (min 3 chars)</Label><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="obs-form-desc" /></div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Immediate Action Taken</Label><Textarea rows={2} value={form.immediate_action_taken || ""} onChange={(e) => setForm({ ...form, immediate_action_taken: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Responsible</Label><Input value={form.responsible_person || ""} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Target Date</Label><Input type="date" value={form.target_date || ""} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Reported By</Label><Input value={form.reported_by || ""} onChange={(e) => setForm({ ...form, reported_by: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="obs-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
