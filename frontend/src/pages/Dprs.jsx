import { useEffect, useMemo, useState } from "react";
import { Plus, Search, ClipboardList, CheckCircle2, XCircle, Send, Trash2, Eye, RefreshCw, X, Smartphone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";

const STATUS_TONE = {
  draft: "neutral", submitted: "warning", approved: "success", rejected: "danger",
};
const SERVICE_OPTIONS = ["scaffolding", "painting", "rope_access", "insulation", "roof_sheeting", "combined"];
const SITE_ROLES = ["site_engineer", "supervisor", "scaffolder", "painter", "rope_access_tech", "insulation_fitter", "roof_sheeting_worker", "helper", "safety_officer", "storekeeper"];
const PC_ROLES = new Set(["super_admin", "director", "general_manager", "dept_head", "project_manager"]);

const blankManpower = () => ({ role: "scaffolder", count: 0 });
const blankMat = () => ({ item_name: "", quantity: 0, unit: "Nos" });
const blankForm = () => ({
  date: new Date().toISOString().slice(0, 10),
  project_code: "", site_name: "", service_type: "scaffolding",
  manpower: [blankManpower()],
  work_completed: "",
  material_used: [], material_received: [], material_returned: [],
  safety_observations: "", client_instructions: "",
  delay_reasons: "", delay_hours: "",
  extra_work: "", supervisor_remarks: "",
  submit: false,
});

export default function Dprs() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isPC = user && PC_ROLES.has(user.role);
  const [rows, setRows] = useState([]);
  const [kpis, setKpis] = useState({});
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [viewing, setViewing] = useState(null);

  const load = async () => {
    try {
      const params = statusFilter ? `?status=${statusFilter}` : "";
      const [r1, r2] = await Promise.all([api.get(`/dprs${params}`), api.get("/dprs/dashboard")]);
      setRows(r1.data || []); setKpis(r2.data?.kpis || {});
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load DPRs"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter]);

  const create = async () => {
    if (!form.project_code) { toast.error("project_code is required"); return; }
    try {
      const payload = {
        ...form,
        delay_hours: form.delay_hours === "" ? null : Number(form.delay_hours),
        manpower: form.manpower.filter((m) => m.role && Number(m.count) > 0).map((m) => ({ role: m.role, count: Number(m.count) })),
      };
      const { data } = await api.post("/dprs", payload);
      toast.success(`${data.dpr_number} ${data.status === "submitted" ? "submitted" : "saved"}`);
      setOpen(false); setForm(blankForm()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const submit = async (d) => {
    try { await api.post(`/dprs/${d.id}/submit`); toast.success("Submitted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const approve = async (d) => {
    const comment = window.prompt("Approval comment (optional)") || "";
    try { await api.post(`/dprs/${d.id}/approve`, { comment }); toast.success("Approved"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const reject = async (d) => {
    const reason = window.prompt("Reason for rejection (required)") || "";
    if (!reason.trim()) return;
    try { await api.post(`/dprs/${d.id}/reject`, { reason }); toast.success("Rejected"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const remove = async (d) => {
    if (!window.confirm(`Delete ${d.dpr_number}?`)) return;
    try { await api.delete(`/dprs/${d.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.dpr_number, r.project_code, r.site_name, r.service_type, r.supervisor_name, r.status, r.work_completed]
      .some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="dprs-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ClipboardList className="h-3 w-3" /> Site Execution · Daily Site Reports
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Daily Site Reports (DPR)</h1>
        <p className="text-sm text-muted-foreground mt-1">End-of-day site state: manpower · work done · material flow · safety · approvals by Project Coordinator.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Total DPRs" value={kpis.total} tone="neutral" testid="dpr-kpi-total" />
        <Kpi label="Submitted Today" value={kpis.submitted_today} tone="info" testid="dpr-kpi-today" />
        <Kpi label="Pending Approval" value={kpis.pending_approval} tone={kpis.pending_approval ? "warning" : "neutral"} testid="dpr-kpi-pending" />
        <Kpi label="Approved (7d)" value={kpis.approved_last_7d} tone="success" testid="dpr-kpi-approved" />
        <Kpi label="Rejected" value={kpis.rejected} tone={kpis.rejected ? "danger" : "neutral"} testid="dpr-kpi-rejected" />
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search DPR #, project, site…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="dpr-search" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="dpr-status-filter">
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="submitted">Submitted</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={load} data-testid="dpr-reload"><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" className="h-9 rounded-sm" onClick={() => navigate("/app/dprs/mobile")} data-testid="dpr-mobile-cta"><Smartphone className="h-4 w-4 mr-1" /> Mobile Capture</Button>
            <Button className="h-9 rounded-sm" onClick={() => { setForm(blankForm()); setOpen(true); }} data-testid="dpr-add"><Plus className="h-4 w-4 mr-1" /> New DPR</Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">DPR #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Project · Site</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Service</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Manpower</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Supervisor</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {filtered.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10 text-sm">No DPRs yet.</TableCell></TableRow>}
              {filtered.map((d) => {
                const totalMen = (d.manpower || []).reduce((a, m) => a + Number(m.count || 0), 0);
                return (
                  <TableRow key={d.id} data-testid={`dpr-row-${d.id}`}>
                    <TableCell className="font-mono-data text-sm font-bold">{d.dpr_number}</TableCell>
                    <TableCell className="text-xs">{d.date}</TableCell>
                    <TableCell className="text-xs">
                      <div className="font-semibold">{d.project_code || "—"}</div>
                      <div className="text-muted-foreground">{d.site_name || "—"}</div>
                    </TableCell>
                    <TableCell className="text-xs">{(d.service_type || "—").replaceAll("_", " ")}</TableCell>
                    <TableCell className="text-xs tabular">{totalMen}</TableCell>
                    <TableCell><StatusBadge text={(d.status || "").replaceAll("_", " ")} tone={STATUS_TONE[d.status] || "neutral"} /></TableCell>
                    <TableCell className="text-xs">{d.supervisor_name || "—"}</TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setViewing(d)} data-testid={`dpr-view-${d.id}`}><Eye className="h-3 w-3" /></Button>
                        {(d.status === "draft" || d.status === "rejected") && (
                          <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => submit(d)} data-testid={`dpr-submit-${d.id}`}><Send className="h-3 w-3 mr-1" />Submit</Button>
                        )}
                        {isPC && d.status === "submitted" && (
                          <>
                            <Button size="sm" className="h-7 rounded-sm bg-success text-success-foreground hover:bg-success/90" onClick={() => approve(d)} data-testid={`dpr-approve-${d.id}`}><CheckCircle2 className="h-3 w-3 mr-1" />Approve</Button>
                            <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => reject(d)} data-testid={`dpr-reject-${d.id}`}><XCircle className="h-3 w-3 mr-1" />Reject</Button>
                          </>
                        )}
                        {d.status !== "approved" && (
                          <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(d)} data-testid={`dpr-delete-${d.id}`}><Trash2 className="h-3 w-3" /></Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">New Daily Site Report</DialogTitle>
            <DialogDescription className="sr-only">Capture daily site state for approval by the project coordinator.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Field label="Date" type="date" value={form.date} onChange={(v) => setForm({ ...form, date: v })} testid="dpr-form-date" />
              <Field label="Project code *" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} testid="dpr-form-project" />
              <Field label="Site name" value={form.site_name} onChange={(v) => setForm({ ...form, site_name: v })} testid="dpr-form-site" />
              <SelectField label="Service" value={form.service_type} options={SERVICE_OPTIONS} onChange={(v) => setForm({ ...form, service_type: v })} testid="dpr-form-service" />
            </div>

            <Section title="Manpower present">
              {form.manpower.map((m, i) => (
                <div key={`mp-${i}`} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-6"><SelectField label="Role" value={m.role} options={SITE_ROLES} onChange={(v) => setForm({ ...form, manpower: form.manpower.map((x, ix) => ix === i ? { ...x, role: v } : x) })} testid={`dpr-form-mp-role-${i}`} /></div>
                  <div className="col-span-4"><Field label="Count" type="number" value={m.count} onChange={(v) => setForm({ ...form, manpower: form.manpower.map((x, ix) => ix === i ? { ...x, count: v } : x) })} testid={`dpr-form-mp-count-${i}`} /></div>
                  <Button variant="outline" size="sm" className="col-span-2 h-9 rounded-sm" onClick={() => setForm({ ...form, manpower: form.manpower.filter((_, ix) => ix !== i) })}><X className="h-3.5 w-3.5" /></Button>
                </div>
              ))}
              <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={() => setForm({ ...form, manpower: [...form.manpower, blankManpower()] })} data-testid="dpr-form-mp-add"><Plus className="h-3.5 w-3.5 mr-1" /> Add role</Button>
            </Section>

            <Section title="Work & material">
              <TextArea label="Work completed" value={form.work_completed} onChange={(v) => setForm({ ...form, work_completed: v })} testid="dpr-form-work" />
              <MatGroup label="Material used" rows={form.material_used} onChange={(rows) => setForm({ ...form, material_used: rows })} prefix="used" />
              <MatGroup label="Material received" rows={form.material_received} onChange={(rows) => setForm({ ...form, material_received: rows })} prefix="recv" />
              <MatGroup label="Material returned" rows={form.material_returned} onChange={(rows) => setForm({ ...form, material_returned: rows })} prefix="ret" />
            </Section>

            <Section title="Safety, client & delays">
              <TextArea label="Safety observations" value={form.safety_observations} onChange={(v) => setForm({ ...form, safety_observations: v })} testid="dpr-form-safety" />
              <TextArea label="Client instructions" value={form.client_instructions} onChange={(v) => setForm({ ...form, client_instructions: v })} testid="dpr-form-client" />
              <div className="grid grid-cols-2 gap-3">
                <TextArea label="Delay reasons" value={form.delay_reasons} onChange={(v) => setForm({ ...form, delay_reasons: v })} testid="dpr-form-delay" />
                <Field label="Delay hours" type="number" value={form.delay_hours} onChange={(v) => setForm({ ...form, delay_hours: v })} testid="dpr-form-delay-hours" />
              </div>
              <TextArea label="Extra work" value={form.extra_work} onChange={(v) => setForm({ ...form, extra_work: v })} testid="dpr-form-extra" />
              <TextArea label="Supervisor remarks" value={form.supervisor_remarks} onChange={(v) => setForm({ ...form, supervisor_remarks: v })} testid="dpr-form-remarks" />
            </Section>

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.submit} onChange={(e) => setForm({ ...form, submit: e.target.checked })} data-testid="dpr-form-submit-checkbox" />
              Submit for PC approval now
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="dpr-form-save">Save DPR</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {viewing && <ViewDialog dpr={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

function Kpi({ label, value, tone, testid }) {
  const c = { success: "text-success", warning: "text-warning", danger: "text-destructive", info: "text-chart-3", neutral: "text-primary" }[tone] || "text-primary";
  return (
    <div className="bg-card border border-border rounded-sm p-3" data-testid={testid}>
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-display font-black text-2xl tabular mt-1 ${c}`}>{value ?? 0}</div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
function TextArea({ label, value, onChange, testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Textarea value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="rounded-sm mt-1 min-h-[60px]" data-testid={testid} />
    </div>
  );
}
function SelectField({ label, value, options, onChange, testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid={testid}>
        {options.map((o) => <option key={o} value={o}>{(o || "").replaceAll("_", " ")}</option>)}
      </select>
    </div>
  );
}
function Section({ title, children }) {
  return (
    <div className="border border-border rounded-sm p-3 space-y-2">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{title}</div>
      {children}
    </div>
  );
}
function MatGroup({ label, rows, onChange, prefix }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{label}</div>
      {(rows || []).map((m, i) => (
        <div key={`${prefix}-${i}`} className="grid grid-cols-12 gap-2 items-end mb-1">
          <div className="col-span-6"><Input placeholder="Item" value={m.item_name} onChange={(e) => onChange(rows.map((x, ix) => ix === i ? { ...x, item_name: e.target.value } : x))} className="h-8 rounded-sm" data-testid={`dpr-form-${prefix}-name-${i}`} /></div>
          <div className="col-span-3"><Input type="number" placeholder="Qty" value={m.quantity} onChange={(e) => onChange(rows.map((x, ix) => ix === i ? { ...x, quantity: e.target.value } : x))} className="h-8 rounded-sm" /></div>
          <div className="col-span-2"><Input placeholder="Unit" value={m.unit} onChange={(e) => onChange(rows.map((x, ix) => ix === i ? { ...x, unit: e.target.value } : x))} className="h-8 rounded-sm" /></div>
          <Button variant="outline" size="sm" className="col-span-1 h-8 rounded-sm" onClick={() => onChange(rows.filter((_, ix) => ix !== i))}><X className="h-3 w-3" /></Button>
        </div>
      ))}
      <Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={() => onChange([...(rows || []), blankMat()])} data-testid={`dpr-form-${prefix}-add`}><Plus className="h-3 w-3 mr-1" /> Add</Button>
    </div>
  );
}

function ViewDialog({ dpr, onClose }) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="dpr-view-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-3">
            {dpr.dpr_number} <StatusBadge text={(dpr.status || "").replaceAll("_", " ")} tone={STATUS_TONE[dpr.status] || "neutral"} />
          </DialogTitle>
          <DialogDescription className="sr-only">DPR detail</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <KV label="Date" v={dpr.date} />
            <KV label="Project · Site" v={`${dpr.project_code || "—"} · ${dpr.site_name || "—"}`} />
            <KV label="Service" v={(dpr.service_type || "—").replaceAll("_", " ")} />
            <KV label="Supervisor" v={dpr.supervisor_name} />
            <KV label="Approved by" v={dpr.approved_by || "—"} />
            <KV label="Approved at" v={dpr.approved_at || "—"} />
            {dpr.reject_reason && <KV label="Reject reason" v={dpr.reject_reason} className="col-span-2 text-destructive" />}
          </div>
          <Block title="Manpower">{(dpr.manpower || []).map((m, i) => <div key={`mp-${i}`} className="text-xs">{m.role.replaceAll("_", " ")} × {m.count}</div>)}</Block>
          {dpr.work_completed && <Block title="Work completed">{dpr.work_completed}</Block>}
          {(dpr.material_used || []).length > 0 && <Block title="Material used">{dpr.material_used.map((m, i) => <div key={`u-${i}`} className="text-xs">{m.item_name} — {m.quantity} {m.unit}</div>)}</Block>}
          {(dpr.material_received || []).length > 0 && <Block title="Material received">{dpr.material_received.map((m, i) => <div key={`r-${i}`} className="text-xs">{m.item_name} — {m.quantity} {m.unit}</div>)}</Block>}
          {(dpr.material_returned || []).length > 0 && <Block title="Material returned">{dpr.material_returned.map((m, i) => <div key={`ret-${i}`} className="text-xs">{m.item_name} — {m.quantity} {m.unit}</div>)}</Block>}
          {dpr.safety_observations && <Block title="Safety observations">{dpr.safety_observations}</Block>}
          {dpr.client_instructions && <Block title="Client instructions">{dpr.client_instructions}</Block>}
          {dpr.delay_reasons && <Block title={`Delays${dpr.delay_hours ? ` · ${dpr.delay_hours}h` : ""}`}>{dpr.delay_reasons}</Block>}
          {dpr.extra_work && <Block title="Extra work">{dpr.extra_work}</Block>}
          {dpr.supervisor_remarks && <Block title="Supervisor remarks">{dpr.supervisor_remarks}</Block>}
        </div>
        <DialogFooter><Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function KV({ label, v, className = "" }) {
  return <div className={className}><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="font-mono-data tabular">{v ?? "—"}</div></div>;
}
function Block({ title, children }) {
  return (
    <div className="border border-border rounded-sm p-2.5">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1">{title}</div>
      <div className="text-xs">{children}</div>
    </div>
  );
}
