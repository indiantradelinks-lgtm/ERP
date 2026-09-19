/**
 * Work Permit Register (Iter 128 · Phase 2)
 * Rich lifecycle-aware register for the new Safety Work Permit workflow.
 * Draft → Requested → Approved → Active → Expired/Closed/Cancelled.
 * Handles HIRA/JSA linkage, LOTO/gas/rescue flags and closure notes.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { ClipboardCheck, Plus, Pencil, RefreshCcw, Send, PlayCircle, XCircle, Filter, CheckCircle2, Ban } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-300",
  requested: "bg-amber-100 text-amber-800 border-amber-300",
  approved: "bg-blue-100 text-blue-800 border-blue-300",
  active: "bg-emerald-100 text-emerald-800 border-emerald-300",
  expired: "bg-red-100 text-red-700 border-red-300",
  closed: "bg-zinc-100 text-zinc-600 border-zinc-300",
  cancelled: "bg-rose-100 text-rose-700 border-rose-300",
  sent_back: "bg-orange-100 text-orange-700 border-orange-300",
};
const STATUSES = ["all", "draft", "requested", "approved", "active", "expired", "closed", "cancelled"];
const EMPTY = {
  permit_type_id: "", permit_type_name: "", project_id: "", project_code: "", client_name: "", site_location: "",
  activity: "", work_area: "", permit_date: "", valid_from: "", valid_to: "",
  requested_by: "", permit_issuer: "", required_ppe_ids: [], required_competency: "",
  related_hira_id: "", related_jsa_id: "",
  isolation_loto_required: false, gas_testing_required: false, rescue_plan_required: false,
  emergency_contact: "", attachments: [], remarks: "",
};

export default function WorkPermitRegister() {
  const [statusFilter, setStatusFilter] = useState("all");
  const { rows: filtered, pagination, search, setSearch, reload } = usePagedList("/safety/work-permits", { status: statusFilter === "all" ? "" : statusFilter }, {
    viewKey: "safety_work_permits", errorLabel: "work permits",
    searchKeys: "permit_no,permit_type,work_description,project_name,project_code,location,status,issued_to,contractor",
  });
  const [projects, setProjects] = useState([]);
  const [permitTypes, setPermitTypes] = useState([]);
  const [hiraOptions, setHiraOptions] = useState([]);
  const [jsaOptions, setJsaOptions] = useState([]);
  const [ppeCategories, setPpeCategories] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [closureFor, setClosureFor] = useState(null);
  const [closureForm, setClosureForm] = useState({ completion_notes: "", incidents_reported: false });

  const loadAux = async () => {
    try {
      const [b, c, d, e, f] = await Promise.all([
        lookupGet("/projects"),
        api.get("/safety/masters/work-permit-types"),
        api.get("/safety/hira?status=approved"),
        api.get("/safety/jsa?status=approved"),
        api.get("/safety/masters/ppe-categories"),
      ]);
      setProjects(b.data || []);
      setPermitTypes(c.data || []); setHiraOptions(d.data || []);
      setJsaOptions(e.data || []); setPpeCategories(f.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  const load = () => { reload(); loadAux(); };
  useEffect(() => { loadAux(); }, []);

  const save = async () => {
    try {
      const payload = { ...form };
      if (editing?.id) { await api.put(`/safety/work-permits/${editing.id}`, payload); toast.success("Permit updated"); }
      else { const r = await api.post(`/safety/work-permits`, payload); toast.success(`Permit ${r.data.permit_no} created`); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const doAction = async (r, action, payload) => {
    try {
      await api.post(`/safety/work-permits/${r.id}/${action}`, payload || {});
      toast.success(`${action} — done`); load();
    } catch (e) { toast.error(e.response?.data?.detail || `${action} failed`); }
  };
  const tickExpiries = async () => {
    try { const r = await api.post(`/safety/work-permits/-/tick-expiries`); toast.success(`Marked ${r.data.expired_now} as expired`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Tick failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="wp-register-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <ClipboardCheck className="h-6 w-6 text-primary" /> Work Permit Register
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Draft → Requested → Approved → Active → Expired / Closed / Cancelled. HIRA + JSA must be approved before request.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <Input className="h-8 w-52 text-xs" placeholder="Search permit #, work, project…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="wp-search" />
          <TableViewsMenu pagination={pagination} testidPrefix="wp" />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-8 rounded-sm border border-input bg-background text-xs px-2" data-testid="wp-filter">
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button variant="outline" onClick={tickExpiries} data-testid="wp-tick">Auto-expire past-due</Button>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="wp-new"><Plus className="h-4 w-4 mr-1" /> New Permit</Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Permit #</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Activity</th>
              <th className="text-left px-3 py-2">Valid</th>
              <th className="text-left px-3 py-2">HIRA / JSA</th>
              <th className="text-left px-3 py-2">Flags</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && <tr><td colSpan={9} className="text-center py-8 text-slate-400">No permits.</td></tr>}
            {filtered.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`wp-row-${r.id}`}>
                <td className="px-3 py-2 font-mono font-bold text-primary">
                  {r.permit_no}
                  {r.high_risk && <span className="block mt-0.5 text-[9px] uppercase tracking-wider text-red-600 font-semibold">High-risk</span>}
                </td>
                <td className="px-3 py-2 text-xs">{r.permit_type_name || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.activity || "—"}</td>
                <td className="px-3 py-2 text-xs whitespace-nowrap">
                  {(r.valid_from || "—")}<br/>→ {(r.valid_to || "—")}
                </td>
                <td className="px-3 py-2 text-xs">
                  {r.related_hira_id && <span className="inline-block px-1.5 py-0.5 rounded border bg-amber-50 border-amber-200 text-amber-800 mr-1">HIRA</span>}
                  {r.related_jsa_id && <span className="inline-block px-1.5 py-0.5 rounded border bg-blue-50 border-blue-200 text-blue-800">JSA</span>}
                </td>
                <td className="px-3 py-2 text-[10px] uppercase tracking-wider">
                  {r.isolation_loto_required && <div className="text-red-700">LOTO</div>}
                  {r.gas_testing_required && <div className="text-amber-700">GAS</div>}
                  {r.rescue_plan_required && <div className="text-blue-700">RESCUE</div>}
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded border ${STATUS_TONE[r.status] || "bg-slate-100"}`}>{r.status?.replaceAll("_", " ")}</span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1 flex-wrap">
                    {(r.status === "draft" || r.status === "sent_back") && <>
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-blue-600" onClick={() => doAction(r, "request")} data-testid={`wp-request-${r.id}`}><Send className="h-3.5 w-3.5" /></Button>
                    </>}
                    {r.status === "requested" && <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-600" onClick={() => doAction(r, "approve")} data-testid={`wp-approve-${r.id}`}><CheckCircle2 className="h-3.5 w-3.5" /></Button>}
                    {r.status === "approved" && <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-700" onClick={() => doAction(r, "activate")}><PlayCircle className="h-3.5 w-3.5" /></Button>}
                    {(r.status === "active" || r.status === "expired") && <Button size="icon" variant="ghost" className="h-7 w-7 text-purple-700" onClick={() => { setClosureFor(r); setClosureForm({ completion_notes: "", incidents_reported: false }); }} data-testid={`wp-close-${r.id}`}><Ban className="h-3.5 w-3.5" /></Button>}
                    {!(r.status === "closed" || r.status === "cancelled") && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => { const reason = window.prompt("Cancellation reason (min 3 chars):"); if (reason && reason.length >= 3) doAction(r, "cancel", { reason }); }}><XCircle className="h-3.5 w-3.5" /></Button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-3 py-2 border-t border-border"><TablePager pagination={pagination} testidPrefix="wp" /></div>
      </div>

      {/* Editor */}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing?.id ? `Edit ${editing.permit_no}` : "New Work Permit"}</DialogTitle>
            <DialogDescription className="text-xs">
              A permit needs an approved HIRA (mandatory) and optionally an approved JSA before it can be requested.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Permit Type</Label>
              <select value={form.permit_type_id || ""} onChange={(e) => {
                const pt = permitTypes.find((x) => x.id === e.target.value);
                setForm({ ...form, permit_type_id: e.target.value, permit_type_name: pt?.name || "" });
              }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="wp-form-type">
                <option value="">— select —</option>
                {permitTypes.map((p) => <option key={p.id} value={p.id}>{p.name} {p.severity ? `· ${p.severity}` : ""}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "", client_name: p?.client || "", site_location: p?.site || "" });
              }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Site Location</Label><Input value={form.site_location || ""} onChange={(e) => setForm({ ...form, site_location: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Activity</Label><Input value={form.activity || ""} onChange={(e) => setForm({ ...form, activity: e.target.value })} data-testid="wp-form-activity" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Work Area / Location</Label><Input value={form.work_area || ""} onChange={(e) => setForm({ ...form, work_area: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Permit Date</Label><Input type="date" value={form.permit_date || ""} onChange={(e) => setForm({ ...form, permit_date: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Valid From</Label><Input type="date" value={form.valid_from || ""} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Valid To</Label><Input type="date" value={form.valid_to || ""} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Requested By</Label><Input value={form.requested_by || ""} onChange={(e) => setForm({ ...form, requested_by: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Permit Issuer</Label><Input value={form.permit_issuer || ""} onChange={(e) => setForm({ ...form, permit_issuer: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Required Competency</Label><Input value={form.required_competency || ""} onChange={(e) => setForm({ ...form, required_competency: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Emergency Contact</Label><Input value={form.emergency_contact || ""} onChange={(e) => setForm({ ...form, emergency_contact: e.target.value })} /></div>

            <div>
              <Label className="text-[10px] uppercase tracking-wider">Related HIRA (approved)</Label>
              <select value={form.related_hira_id || ""} onChange={(e) => setForm({ ...form, related_hira_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="wp-form-hira">
                <option value="">— none —</option>
                {hiraOptions.map((h) => <option key={h.id} value={h.id}>{h.hira_no} · {h.project_code || h.site_location}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Related JSA (approved)</Label>
              <select value={form.related_jsa_id || ""} onChange={(e) => setForm({ ...form, related_jsa_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>
                {jsaOptions.map((j) => <option key={j.id} value={j.id}>{j.jsa_no} · {j.activity}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Required PPE (multi)</Label>
              <select multiple value={form.required_ppe_ids || []} onChange={(e) => setForm({ ...form, required_ppe_ids: Array.from(e.target.selectedOptions, (o) => o.value) })} className="min-h-[80px] w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="wp-form-ppe">
                {ppeCategories.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>

            <div className="col-span-full flex items-center gap-6 flex-wrap py-2">
              <Toggle label="Isolation / LOTO required" checked={form.isolation_loto_required} onChange={(v) => setForm({ ...form, isolation_loto_required: v })} testid="wp-form-loto" />
              <Toggle label="Gas testing required" checked={form.gas_testing_required} onChange={(v) => setForm({ ...form, gas_testing_required: v })} testid="wp-form-gas" />
              <Toggle label="Rescue plan required" checked={form.rescue_plan_required} onChange={(v) => setForm({ ...form, rescue_plan_required: v })} testid="wp-form-rescue" />
            </div>
            <div className="col-span-full"><Label className="text-[10px] uppercase tracking-wider">Remarks</Label><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="wp-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Closure */}
      <Dialog open={closureFor !== null} onOpenChange={(o) => !o && setClosureFor(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Close Permit {closureFor?.permit_no}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Completion Notes *</Label>
              <Textarea rows={4} value={closureForm.completion_notes} onChange={(e) => setClosureForm({ ...closureForm, completion_notes: e.target.value })} data-testid="wp-close-notes" />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={closureForm.incidents_reported} onChange={(e) => setClosureForm({ ...closureForm, incidents_reported: e.target.checked })} data-testid="wp-close-incidents" />
              Incidents reported during permit period
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClosureFor(null)}>Cancel</Button>
            <Button onClick={async () => { await doAction(closureFor, "close", closureForm); setClosureFor(null); }} data-testid="wp-close-submit">Close Permit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Toggle({ label, checked, onChange, testid }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} data-testid={testid} />
      {label}
    </label>
  );
}
