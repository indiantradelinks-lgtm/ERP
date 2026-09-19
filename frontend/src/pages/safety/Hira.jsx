/**
 * HIRA Register — Hazard Identification & Risk Assessment.
 * Full register + inline editor for lines. Draft/pending/approved lifecycle
 * with revision history and audit trail. High-risk records go through the
 * shared approvals inbox (Safety Officer + Project Manager).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { AlertTriangle, Plus, Pencil, Send, RefreshCcw, RotateCcw, Trash2, X } from "lucide-react";
import { fmtDT } from "@/lib/datetime";
import { lookupGet } from "@/lib/lookups";

const SERVICE_TYPES = ["scaffolding", "painting", "roof_sheeting", "rope_access", "manpower", "material_handling", "other"];
const RISK_RATINGS = ["", "low", "medium", "high", "critical"];
const LIKELIHOODS = ["", "rare", "unlikely", "possible", "likely", "almost_certain"];
const SEVERITIES = ["", "negligible", "minor", "moderate", "major", "catastrophic"];
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
  activity: "", hazard: "", consequence: "", existing_control: "",
  likelihood: "", severity: "", risk_rating: "", additional_control: "",
  responsible_person: "", target_date: "",
};
const EMPTY = {
  project_id: "", project_code: "", site_location: "", client_name: "",
  service_type: "", prepared_by: "", reviewed_by: "", approved_by: "",
  remarks: "", lines: [],
};

export default function Hira() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/hira"), lookupGet("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const openEditor = (r) => { setEditing(r || {}); setForm(r ? { ...EMPTY, ...r, lines: r.lines || [] } : EMPTY); };

  const save = async () => {
    try {
      const payload = { ...form, lines: form.lines || [] };
      if (editing?.id) {
        await api.put(`/safety/hira/${editing.id}`, payload);
        toast.success(`HIRA ${editing.hira_no} updated`);
      } else {
        const r = await api.post(`/safety/hira`, payload);
        toast.success(`HIRA ${r.data.hira_no} created`);
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const submit = async (r) => {
    try {
      const res = await api.post(`/safety/hira/${r.id}/submit`);
      const s = res.data.status;
      toast.success(s === "pending_approval" ? "Submitted for approval (high-risk)" : "Auto-approved (no high-risk lines)");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Submit failed"); }
  };

  const revise = async (r) => {
    if (!window.confirm(`Create a new revision of ${r.hira_no}? The current version will be preserved in history.`)) return;
    try {
      await api.post(`/safety/hira/${r.id}/revise`);
      toast.success("New revision created"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Revise failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.hira_no}? Approved HIRAs cannot be deleted.`)) return;
    try { await api.delete(`/safety/hira/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const setLine = (i, patch) => setForm((f) => {
    const lines = [...(f.lines || [])];
    lines[i] = { ...lines[i], ...patch };
    return { ...f, lines };
  });
  const addLine = () => setForm((f) => ({ ...f, lines: [...(f.lines || []), { ...EMPTY_LINE }] }));
  const removeLine = (i) => setForm((f) => ({ ...f, lines: (f.lines || []).filter((_, idx) => idx !== i) }));

  const hasHighRisk = (form.lines || []).some((l) => ["high", "critical"].includes((l.risk_rating || "").toLowerCase()));

  return (
    <div className="p-6 space-y-4" data-testid="hira-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <AlertTriangle className="h-6 w-6 text-red-600" /> HIRA · Hazard Identification & Risk Assessment
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Activity-based risk register. High-risk lines route to Safety Officer + Project Manager for approval.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => openEditor(null)} data-testid="hira-new">
            <Plus className="h-4 w-4 mr-1" /> New HIRA
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">HIRA #</th>
              <th className="text-left px-3 py-2">Rev</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Site</th>
              <th className="text-left px-3 py-2">Service</th>
              <th className="text-center px-3 py-2">Lines</th>
              <th className="text-center px-3 py-2">High Risk?</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={9} className="text-center py-8 text-slate-400">No HIRAs yet — click &quot;New HIRA&quot;.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`hira-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">{r.hira_no}</td>
                <td className="px-3 py-2 text-xs">R{r.rev || 0}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.site_location || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.service_type || "—"}</td>
                <td className="px-3 py-2 text-center text-xs tabular">{(r.lines || []).length}</td>
                <td className="px-3 py-2 text-center">
                  {r.high_risk ? <span className="text-red-600 font-bold text-xs">YES</span> : <span className="text-slate-400 text-xs">no</span>}
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>
                    {(r.status || "").replaceAll("_", " ")}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEditor(r)} data-testid={`hira-edit-${r.id}`}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {(r.status === "draft" || r.status === "sent_back") && (
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-blue-600" onClick={() => submit(r)} data-testid={`hira-submit-${r.id}`}>
                        <Send className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-amber-600" onClick={() => revise(r)} data-testid={`hira-revise-${r.id}`}>
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                    {r.status !== "approved" && (
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`hira-del-${r.id}`}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
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
            <DialogTitle>{editing?.id ? `Edit ${editing.hira_no}` : "New HIRA"}</DialogTitle>
            <DialogDescription className="text-xs">
              {hasHighRisk
                ? <span className="text-red-700 font-semibold">⚠ Contains high-risk lines — will require Safety Officer + Project Manager approval on submit.</span>
                : "Only low/medium risk lines — will auto-approve on submit."}
            </DialogDescription>
          </DialogHeader>

          {/* Header fields */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""}
                onChange={(e) => {
                  const p = projects.find((x) => x.id === e.target.value);
                  setForm({ ...form, project_id: e.target.value, project_code: p?.code || "", client_name: p?.client || "", site_location: p?.site || "" });
                }}
                className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="hira-form-project">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Site Location</Label>
              <Input value={form.site_location || ""} onChange={(e) => setForm({ ...form, site_location: e.target.value })} />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Service Type</Label>
              <select value={form.service_type || ""} onChange={(e) => setForm({ ...form, service_type: e.target.value })}
                className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— select —</option>
                {SERVICE_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Prepared By</Label><Input value={form.prepared_by || ""} onChange={(e) => setForm({ ...form, prepared_by: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Reviewed By</Label><Input value={form.reviewed_by || ""} onChange={(e) => setForm({ ...form, reviewed_by: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Approved By</Label><Input value={form.approved_by || ""} onChange={(e) => setForm({ ...form, approved_by: e.target.value })} /></div>
            <div className="col-span-full">
              <Label className="text-[10px] uppercase tracking-wider">Remarks</Label>
              <Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
            </div>
          </div>

          {/* Lines */}
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Hazard Lines ({(form.lines || []).length})</div>
              <Button size="sm" onClick={addLine} data-testid="hira-add-line"><Plus className="h-3.5 w-3.5 mr-1" /> Add Line</Button>
            </div>
            <div className="border rounded-sm overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-2 py-1.5">Activity</th>
                    <th className="text-left px-2 py-1.5">Hazard</th>
                    <th className="text-left px-2 py-1.5">Consequence</th>
                    <th className="text-left px-2 py-1.5">Existing Control</th>
                    <th className="text-left px-2 py-1.5 w-24">Likelihood</th>
                    <th className="text-left px-2 py-1.5 w-24">Severity</th>
                    <th className="text-left px-2 py-1.5 w-24">Risk</th>
                    <th className="text-left px-2 py-1.5">Additional Control</th>
                    <th className="text-left px-2 py-1.5 w-24">Responsible</th>
                    <th className="text-left px-2 py-1.5 w-28">Target Date</th>
                    <th className="w-6"></th>
                  </tr>
                </thead>
                <tbody>
                  {(form.lines || []).length === 0 && (
                    <tr><td colSpan={11} className="text-center py-4 text-slate-400 italic">No lines yet — click &quot;Add Line&quot;.</td></tr>
                  )}
                  {(form.lines || []).map((l, i) => (
                    <tr key={i} className="border-t" data-testid={`hira-line-${i}`}>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.activity} onChange={(e) => setLine(i, { activity: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.hazard} onChange={(e) => setLine(i, { hazard: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.consequence} onChange={(e) => setLine(i, { consequence: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.existing_control} onChange={(e) => setLine(i, { existing_control: e.target.value })} /></td>
                      <td className="p-1">
                        <select className="h-8 w-full rounded-sm border border-input bg-background text-xs px-1" value={l.likelihood || ""} onChange={(e) => setLine(i, { likelihood: e.target.value })}>
                          {LIKELIHOODS.map((v) => <option key={v} value={v}>{v || "—"}</option>)}
                        </select>
                      </td>
                      <td className="p-1">
                        <select className="h-8 w-full rounded-sm border border-input bg-background text-xs px-1" value={l.severity || ""} onChange={(e) => setLine(i, { severity: e.target.value })}>
                          {SEVERITIES.map((v) => <option key={v} value={v}>{v || "—"}</option>)}
                        </select>
                      </td>
                      <td className="p-1">
                        <select
                          className={`h-8 w-full rounded-sm border text-xs px-1 ${l.risk_rating ? RISK_TONE[l.risk_rating] || "border-input bg-background" : "border-input bg-background"}`}
                          value={l.risk_rating || ""} onChange={(e) => setLine(i, { risk_rating: e.target.value })}
                          data-testid={`hira-line-${i}-risk`}
                        >
                          {RISK_RATINGS.map((v) => <option key={v} value={v}>{v || "—"}</option>)}
                        </select>
                      </td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.additional_control} onChange={(e) => setLine(i, { additional_control: e.target.value })} /></td>
                      <td className="p-1"><Input className="h-8 text-xs" value={l.responsible_person} onChange={(e) => setLine(i, { responsible_person: e.target.value })} /></td>
                      <td className="p-1"><Input type="date" className="h-8 text-xs" value={l.target_date || ""} onChange={(e) => setLine(i, { target_date: e.target.value })} /></td>
                      <td className="p-1"><Button size="icon" variant="ghost" className="h-6 w-6 text-rose-600" onClick={() => removeLine(i)}><X className="h-3 w-3" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Revisions history */}
          {editing?.revisions?.length > 0 && (
            <div className="mt-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Revision History ({editing.revisions.length})</div>
              <ul className="text-xs space-y-1">
                {editing.revisions.map((rv, i) => (
                  <li key={i} className="border rounded-sm p-1.5 bg-amber-50/40">
                    R{rv.rev} · {fmtDT(rv.revised_at)} by <b>{rv.revised_by}</b>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="hira-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
