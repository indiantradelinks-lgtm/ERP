/**
 * Safety Audits (Phase 4) — schedule + findings capture + close.
 * Auto-creates CAPA on high/critical findings.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ClipboardCheck, Plus, RefreshCcw, X, Lock } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const AUDIT_TYPES = ["internal", "client", "third_party", "site", "contractor", "ppe", "scaffold", "work_permit"];
const RISK_LEVELS = ["", "low", "medium", "high", "critical"];
const RISK_TONE = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-300",
  medium: "bg-amber-50 text-amber-700 border-amber-300",
  high: "bg-orange-50 text-orange-700 border-orange-300",
  critical: "bg-red-50 text-red-700 border-red-300",
};
const STATUS_TONE = { open: "bg-amber-100 text-amber-800", closed: "bg-emerald-100 text-emerald-800" };
const EMPTY_FINDING = { finding: "", non_compliance: "", risk_level: "", corrective_action: "", responsible_person: "", target_date: "", status: "open" };
const EMPTY = {
  audit_date: new Date().toISOString().slice(0, 10),
  audit_type: "internal",
  project_id: "", project_code: "", site_location: "", auditor: "",
  audit_score: "", remarks: "", findings: [],
};

export default function SafetyAudits() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/audits"), lookupGet("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const payload = { ...form };
      if (payload.audit_score === "") delete payload.audit_score;
      else payload.audit_score = Number(payload.audit_score);
      const r = await api.post(`/safety/audits`, payload);
      toast.success(`Audit ${r.data.audit_no} created`);
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const closeAudit = async (r) => {
    try { await api.post(`/safety/audits/${r.id}/close`); toast.success("Audit closed"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Close failed"); }
  };

  const setFinding = (i, patch) => setForm((f) => {
    const arr = [...(f.findings || [])]; arr[i] = { ...arr[i], ...patch }; return { ...f, findings: arr };
  });
  const addFinding = () => setForm((f) => ({ ...f, findings: [...(f.findings || []), { ...EMPTY_FINDING }] }));
  const removeFinding = (i) => setForm((f) => ({ ...f, findings: (f.findings || []).filter((_, idx) => idx !== i) }));

  return (
    <div className="p-6 space-y-4" data-testid="safety-audits-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <ClipboardCheck className="h-6 w-6 text-red-600" /> Safety Audits
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Internal · Client · Third-party audits with findings and auto-CAPA on high/critical risks.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} data-testid="audit-refresh"><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="audit-new">
            <Plus className="h-4 w-4 mr-1" /> New Audit
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Audit #</th>
              <th className="text-left px-3 py-2">Date</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Auditor</th>
              <th className="text-center px-3 py-2">Findings</th>
              <th className="text-center px-3 py-2">Score</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={9} className="text-center py-8 text-slate-400">No audits recorded yet.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`audit-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.audit_no}</td>
                <td className="px-3 py-2">{r.audit_date}</td>
                <td className="px-3 py-2 capitalize">{(r.audit_type || "").replace(/_/g, " ")}</td>
                <td className="px-3 py-2">{r.project_code || "—"}</td>
                <td className="px-3 py-2">{r.auditor || "—"}</td>
                <td className="px-3 py-2 text-center">{(r.findings || []).length}</td>
                <td className="px-3 py-2 text-center">{r.audit_score ?? "—"}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${STATUS_TONE[r.status] || "bg-slate-100 text-slate-700"}`}>{r.status}</span>
                </td>
                <td className="px-3 py-2 text-right">
                  {r.status !== "closed" && (
                    <Button size="sm" variant="outline" onClick={() => closeAudit(r)} data-testid={`audit-close-${r.id}`}>
                      <Lock className="h-3 w-3 mr-1" /> Close
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Safety Audit</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Audit Date</Label>
              <Input type="date" value={form.audit_date} onChange={(e) => setForm({ ...form, audit_date: e.target.value })} data-testid="audit-date" />
            </div>
            <div>
              <Label>Audit Type</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.audit_type} onChange={(e) => setForm({ ...form, audit_type: e.target.value })} data-testid="audit-type">
                {AUDIT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <Label>Project</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.project_id} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }} data-testid="audit-project">
                <option value="">— Select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Site Location</Label>
              <Input value={form.site_location} onChange={(e) => setForm({ ...form, site_location: e.target.value })} />
            </div>
            <div>
              <Label>Auditor</Label>
              <Input value={form.auditor} onChange={(e) => setForm({ ...form, auditor: e.target.value })} />
            </div>
            <div>
              <Label>Score (0–100)</Label>
              <Input type="number" value={form.audit_score} onChange={(e) => setForm({ ...form, audit_score: e.target.value })} />
            </div>
            <div className="col-span-2">
              <Label>Remarks</Label>
              <Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
            </div>
          </div>

          <div className="mt-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-600">Findings ({(form.findings || []).length})</div>
              <Button size="sm" variant="outline" onClick={addFinding} data-testid="audit-add-finding"><Plus className="h-3 w-3 mr-1" /> Add Finding</Button>
            </div>
            <div className="space-y-2">
              {(form.findings || []).map((f, i) => (
                <div key={i} className="border rounded p-2 grid grid-cols-2 gap-2 bg-slate-50/40" data-testid={`audit-finding-${i}`}>
                  <div className="col-span-2 flex items-center gap-2">
                    <Input placeholder="Finding" value={f.finding} onChange={(e) => setFinding(i, { finding: e.target.value })} />
                    <Button size="sm" variant="ghost" onClick={() => removeFinding(i)}><X className="h-3 w-3" /></Button>
                  </div>
                  <Input placeholder="Non-compliance" value={f.non_compliance || ""} onChange={(e) => setFinding(i, { non_compliance: e.target.value })} />
                  <select className="border rounded h-9 px-2 text-sm" value={f.risk_level || ""} onChange={(e) => setFinding(i, { risk_level: e.target.value })}>
                    {RISK_LEVELS.map((r) => <option key={r} value={r}>{r || "— risk —"}</option>)}
                  </select>
                  <Input placeholder="Corrective action" value={f.corrective_action || ""} onChange={(e) => setFinding(i, { corrective_action: e.target.value })} />
                  <Input placeholder="Responsible" value={f.responsible_person || ""} onChange={(e) => setFinding(i, { responsible_person: e.target.value })} />
                  <Input type="date" value={f.target_date || ""} onChange={(e) => setFinding(i, { target_date: e.target.value })} />
                  {f.risk_level && (
                    <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${RISK_TONE[f.risk_level] || ""}`}>
                      {f.risk_level} · {["high", "critical"].includes(f.risk_level) ? "auto-CAPA" : "no CAPA"}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="audit-save">Save Audit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
