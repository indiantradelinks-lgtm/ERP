import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Ruler, CheckCircle2, XCircle, Send, Trash2, Eye, RefreshCw, X, FileSignature, ListChecks } from "lucide-react";
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

const STATUS_TONE = {
  draft: "neutral", submitted: "warning", client_certified: "info",
  approved_for_billing: "success", rejected: "danger", billed: "primary",
};
const SERVICES = ["scaffolding", "painting", "rope_access", "insulation", "roof_sheeting", "other"];
const ACTIVITIES = {
  scaffolding: ["erected", "dismantled", "modified"],
  painting: ["painted", "primer_applied", "surface_prep", "touchup"],
  rope_access: ["inspection", "cleaning", "maintenance", "rope_access_job"],
  insulation: ["insulated", "cladding", "removal"],
  roof_sheeting: ["sheeted", "flashing", "ventilator_install"],
  other: ["custom"],
};
const UNITS = ["m²", "m³", "m", "Nos", "kg", "ltr"];
const PC_LIKE = new Set(["super_admin", "director", "general_manager", "dept_head", "project_manager", "accounts_executive"]);

const blankItem = () => ({ service: "scaffolding", activity: "erected", description: "", executed_qty: 0, certified_qty: 0, unit: "m²", rate: "" });
const blankForm = () => ({
  date: new Date().toISOString().slice(0, 10),
  project_code: "", site_name: "", service_type: "scaffolding",
  po_number: "", joint_measured_with: "", client_designation: "",
  items: [blankItem()], remarks: "", submit: false,
});

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function Measurements() {
  const { user } = useAuth();
  const canApprove = user && PC_LIKE.has(user.role);
  const [rows, setRows] = useState([]);
  const [tab, setTab] = useState("list");
  const [summary, setSummary] = useState({ rows: [] });
  const [statusFilter, setStatusFilter] = useState("");
  const [serviceFilter, setServiceFilter] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [viewing, setViewing] = useState(null);
  const [certifying, setCertifying] = useState(null);

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (serviceFilter) params.set("service", serviceFilter);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const [r1, r2] = await Promise.all([api.get(`/measurements${qs}`), api.get("/measurements/summary")]);
      setRows(r1.data || []); setSummary(r2.data || { rows: [] });
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter, serviceFilter]);

  const kpis = useMemo(() => ({
    total: rows.length,
    draft: rows.filter((r) => r.status === "draft").length,
    submitted: rows.filter((r) => r.status === "submitted").length,
    certified: rows.filter((r) => r.status === "client_certified").length,
    approved: rows.filter((r) => r.status === "approved_for_billing").length,
    rejected: rows.filter((r) => r.status === "rejected").length,
  }), [rows]);

  const create = async () => {
    if (!form.project_code) { toast.error("project_code is required"); return; }
    if (!form.items.length) { toast.error("Add at least one line"); return; }
    try {
      const items = form.items.map((i) => ({
        service: i.service, activity: i.activity, description: i.description || null,
        executed_qty: Number(i.executed_qty) || 0,
        certified_qty: Number(i.certified_qty) || 0,
        unit: i.unit, rate: i.rate === "" ? null : Number(i.rate),
        remark: i.remark || null,
      }));
      const { data } = await api.post("/measurements", { ...form, items });
      toast.success(`${data.measurement_no} ${data.status === "submitted" ? "submitted" : "saved"}`);
      setOpen(false); setForm(blankForm()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const submit = async (m) => {
    try { await api.post(`/measurements/${m.id}/submit`); toast.success("Submitted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const approve = async (m) => {
    try { await api.post(`/measurements/${m.id}/approve-for-billing`); toast.success("Approved for billing"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const reject = async (m) => {
    const reason = window.prompt("Reason (required)") || "";
    if (!reason.trim()) return;
    try { await api.post(`/measurements/${m.id}/reject`, { reason }); toast.success("Rejected"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const remove = async (m) => {
    if (!window.confirm(`Delete ${m.measurement_no}?`)) return;
    try { await api.delete(`/measurements/${m.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.measurement_no, r.project_code, r.site_name, r.service_type, r.po_number, r.status, r.joint_measured_with]
      .some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="meas-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Ruler className="h-3 w-3" /> Site Execution · Measurement & Certification
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Measurement / Work Certification</h1>
        <p className="text-sm text-muted-foreground mt-1">Service-wise executed vs client-certified quantities. Approved measurements feed Running (RA) bills.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Kpi label="Total" value={kpis.total} tone="neutral" testid="meas-kpi-total" />
        <Kpi label="Draft" value={kpis.draft} tone="neutral" testid="meas-kpi-draft" />
        <Kpi label="Submitted" value={kpis.submitted} tone="warning" testid="meas-kpi-submitted" />
        <Kpi label="Client Certified" value={kpis.certified} tone="info" testid="meas-kpi-certified" />
        <Kpi label="Approved (Bill Ready)" value={kpis.approved} tone="success" testid="meas-kpi-approved" />
        <Kpi label="Rejected" value={kpis.rejected} tone={kpis.rejected ? "danger" : "neutral"} testid="meas-kpi-rejected" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant={tab === "list" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("list")} data-testid="meas-tab-list"><ListChecks className="h-3.5 w-3.5 mr-1.5" /> All Measurements</Button>
        <Button variant={tab === "summary" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("summary")} data-testid="meas-tab-summary"><Ruler className="h-3.5 w-3.5 mr-1.5" /> RA Billing Summary</Button>
      </div>

      {tab === "list" && (
        <div className="bg-card border border-border rounded-sm">
          <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
            <div className="relative w-72">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9 h-9 rounded-sm" placeholder="Search measurement #, project, PO…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="meas-search" />
            </div>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="meas-status-filter">
              <option value="">All statuses</option>
              {["draft", "submitted", "client_certified", "approved_for_billing", "rejected", "billed"].map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
            </select>
            <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="meas-service-filter">
              <option value="">All services</option>
              {SERVICES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
            </select>
            <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={load}><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
            <div className="ml-auto">
              <Button className="h-9 rounded-sm" onClick={() => { setForm(blankForm()); setOpen(true); }} data-testid="meas-add"><Plus className="h-4 w-4 mr-1" /> New Measurement</Button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">MEAS #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Project · Site</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Service</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Lines</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Certified Qty</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Billable</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {filtered.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-muted-foreground py-10 text-sm">No measurements yet.</TableCell></TableRow>}
                {filtered.map((m) => (
                  <TableRow key={m.id} data-testid={`meas-row-${m.id}`}>
                    <TableCell className="font-mono-data text-sm font-bold">{m.measurement_no}</TableCell>
                    <TableCell className="text-xs">{m.date}</TableCell>
                    <TableCell className="text-xs">
                      <div className="font-semibold">{m.project_code || "—"}</div>
                      <div className="text-muted-foreground">{m.site_name || "—"}</div>
                    </TableCell>
                    <TableCell className="text-xs">{(m.service_type || "—").replaceAll("_", " ")}</TableCell>
                    <TableCell className="text-xs tabular">{(m.items || []).length}</TableCell>
                    <TableCell className="font-mono-data text-sm tabular">{m.total_certified ?? 0}</TableCell>
                    <TableCell className="font-mono-data text-sm tabular font-bold">{inr(m.billable_value)}</TableCell>
                    <TableCell><StatusBadge text={(m.status || "").replaceAll("_", " ")} tone={STATUS_TONE[m.status] || "neutral"} /></TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setViewing(m)} data-testid={`meas-view-${m.id}`}><Eye className="h-3 w-3" /></Button>
                        {(m.status === "draft" || m.status === "rejected") && (
                          <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => submit(m)} data-testid={`meas-submit-${m.id}`}><Send className="h-3 w-3 mr-1" />Submit</Button>
                        )}
                        {m.status === "submitted" && (
                          <Button size="sm" className="h-7 rounded-sm" onClick={() => setCertifying(m)} data-testid={`meas-certify-${m.id}`} title="Record client signature on measured quantities (site supervisor or above)"><FileSignature className="h-3 w-3 mr-1" />Certify</Button>
                        )}
                        {canApprove && m.status === "client_certified" && (
                          <Button size="sm" className="h-7 rounded-sm bg-success text-success-foreground hover:bg-success/90" onClick={() => approve(m)} data-testid={`meas-approve-${m.id}`}><CheckCircle2 className="h-3 w-3 mr-1" />Bill</Button>
                        )}
                        {canApprove && (m.status === "submitted" || m.status === "client_certified") && (
                          <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => reject(m)} data-testid={`meas-reject-${m.id}`}><XCircle className="h-3 w-3" /></Button>
                        )}
                        {!["approved_for_billing", "billed"].includes(m.status) && (
                          <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(m)} data-testid={`meas-delete-${m.id}`}><Trash2 className="h-3 w-3" /></Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {tab === "summary" && <SummaryView rows={summary.rows} />}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-5xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">New Measurement</DialogTitle>
            <DialogDescription className="sr-only">Capture service-wise executed and certified quantities for client sign-off and billing.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Field label="Date" type="date" value={form.date} onChange={(v) => setForm({ ...form, date: v })} testid="meas-form-date" />
              <Field label="Project code *" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} testid="meas-form-project" />
              <Field label="Site name" value={form.site_name} onChange={(v) => setForm({ ...form, site_name: v })} testid="meas-form-site" />
              <Field label="PO number" value={form.po_number} onChange={(v) => setForm({ ...form, po_number: v })} testid="meas-form-po" />
              <SelectField label="Service" value={form.service_type} options={SERVICES} onChange={(v) => setForm({ ...form, service_type: v })} testid="meas-form-service" />
              <Field label="Joint measured with" value={form.joint_measured_with} onChange={(v) => setForm({ ...form, joint_measured_with: v })} testid="meas-form-witness" />
              <Field label="Client designation" value={form.client_designation} onChange={(v) => setForm({ ...form, client_designation: v })} testid="meas-form-designation" />
            </div>

            <div className="border border-border rounded-sm">
              <div className="flex items-center justify-between p-2.5 border-b border-border">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Measurement lines</div>
                <Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: [...form.items, blankItem()] })} data-testid="meas-form-add-line"><Plus className="h-3 w-3 mr-1" /> Add line</Button>
              </div>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
                    <TableHead className="text-[10px] uppercase tracking-wider">Service</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Activity</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Description</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Executed</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Certified</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
                    <TableHead></TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {form.items.map((it, i) => {
                      const value = (Number(it.rate) || 0) * (Number(it.certified_qty) || 0);
                      const acts = ACTIVITIES[it.service] || ACTIVITIES.other;
                      return (
                        <TableRow key={`item-${i}`} data-testid={`meas-form-row-${i}`}>
                          <TableCell>
                            <select value={it.service} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, service: e.target.value, activity: (ACTIVITIES[e.target.value] || ["custom"])[0] } : x) })} className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid={`meas-form-service-${i}`}>
                              {SERVICES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
                            </select>
                          </TableCell>
                          <TableCell>
                            <select value={it.activity} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, activity: e.target.value } : x) })} className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid={`meas-form-activity-${i}`}>
                              {acts.map((a) => <option key={a} value={a}>{a.replaceAll("_", " ")}</option>)}
                            </select>
                          </TableCell>
                          <TableCell><Input value={it.description} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, description: e.target.value } : x) })} className="h-8 rounded-sm" placeholder="(optional)" /></TableCell>
                          <TableCell><Input type="number" value={it.executed_qty} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, executed_qty: e.target.value } : x) })} className="h-8 rounded-sm w-24 tabular" data-testid={`meas-form-executed-${i}`} /></TableCell>
                          <TableCell><Input type="number" value={it.certified_qty} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, certified_qty: e.target.value } : x) })} className="h-8 rounded-sm w-24 tabular" data-testid={`meas-form-certified-${i}`} /></TableCell>
                          <TableCell>
                            <select value={it.unit} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, unit: e.target.value } : x) })} className="h-8 rounded-sm border border-input bg-background px-1 text-xs">
                              {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                            </select>
                          </TableCell>
                          <TableCell><Input type="number" value={it.rate} onChange={(e) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, rate: e.target.value } : x) })} className="h-8 rounded-sm w-24 tabular" placeholder="optional" /></TableCell>
                          <TableCell className="font-mono-data tabular text-xs font-bold">{inr(value)}</TableCell>
                          <TableCell><Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: form.items.filter((_, ix) => ix !== i) })}><X className="h-3 w-3" /></Button></TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>

            <TextArea label="Remarks" value={form.remarks} onChange={(v) => setForm({ ...form, remarks: v })} testid="meas-form-remarks" />

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.submit} onChange={(e) => setForm({ ...form, submit: e.target.checked })} data-testid="meas-form-submit-check" />
              Submit immediately for client certification
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="meas-form-save">Save Measurement</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {certifying && <CertifyDialog m={certifying} onClose={() => { setCertifying(null); load(); }} />}
      {viewing && <ViewDialog m={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

function SummaryView({ rows }) {
  if (!rows.length) return <div className="bg-card border border-border rounded-sm p-10 text-center text-sm text-muted-foreground">No approved-for-billing measurements yet.</div>;
  const grouped = rows.reduce((acc, r) => {
    const k = r.project || "—";
    (acc[k] = acc[k] || []).push(r);
    return acc;
  }, {});
  return (
    <div className="space-y-4" data-testid="meas-summary">
      {Object.entries(grouped).map(([proj, items]) => {
        const total = items.reduce((a, r) => a + Number(r.billable_value || 0), 0);
        return (
          <div key={proj} className="bg-card border border-border rounded-sm" data-testid={`meas-summary-project-${proj}`}>
            <div className="flex items-center justify-between p-3 border-b border-border">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Project</div>
                <div className="font-display font-bold text-lg">{proj}</div>
              </div>
              <div className="text-right">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Billable Value</div>
                <div className="font-display font-black text-2xl text-primary tabular">{inr(total)}</div>
              </div>
            </div>
            <Table>
              <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
                <TableHead className="text-[10px] uppercase tracking-wider">Service</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Activity</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Lines</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Executed</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Certified</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {items.map((r, i) => (
                  <TableRow key={`${r.service}-${r.activity}-${i}`}>
                    <TableCell className="text-sm font-semibold">{r.service.replaceAll("_", " ")}</TableCell>
                    <TableCell className="text-xs">{r.activity.replaceAll("_", " ")}</TableCell>
                    <TableCell className="text-xs tabular">{r.count}</TableCell>
                    <TableCell className="font-mono-data tabular text-sm">{r.executed_qty}</TableCell>
                    <TableCell className="font-mono-data tabular text-sm font-bold text-success">{r.certified_qty}</TableCell>
                    <TableCell className="text-xs">{r.unit}</TableCell>
                    <TableCell className="font-mono-data tabular text-sm font-bold">{inr(r.billable_value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        );
      })}
    </div>
  );
}

function CertifyDialog({ m, onClose }) {
  const [name, setName] = useState("");
  const [designation, setDesignation] = useState(m.client_designation || "");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (name.trim().length < 2) { toast.error("Signatory name required"); return; }
    setBusy(true);
    try {
      await api.post(`/measurements/${m.id}/certify`, { signatory_name: name, signatory_designation: designation });
      toast.success("Client certification recorded");
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md rounded-sm" data-testid="meas-certify-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Client Certification · {m.measurement_no}</DialogTitle>
          <DialogDescription className="sr-only">Record client representative signature on the measured quantities.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Field label="Signatory name *" value={name} onChange={setName} testid="meas-certify-name" />
          <Field label="Designation" value={designation} onChange={setDesignation} testid="meas-certify-designation" />
          <p className="text-[11px] text-muted-foreground">Recording your name + a timestamp + the source IP constitutes a digital sign-off equivalent to a paper joint measurement sheet.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={go} disabled={busy} data-testid="meas-certify-go">{busy ? "Saving…" : "Record Certification"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ViewDialog({ m, onClose }) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="meas-view-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-3">
            {m.measurement_no} <StatusBadge text={(m.status || "").replaceAll("_", " ")} tone={STATUS_TONE[m.status] || "neutral"} />
          </DialogTitle>
          <DialogDescription className="sr-only">Measurement detail</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
            <KV label="Date" v={m.date} />
            <KV label="Project · Site" v={`${m.project_code || "—"} · ${m.site_name || "—"}`} />
            <KV label="PO #" v={m.po_number} />
            <KV label="Service" v={(m.service_type || "—").replaceAll("_", " ")} />
            <KV label="Joint measured with" v={m.joint_measured_with} />
            <KV label="Created by" v={m.created_by_name} />
          </div>
          {m.client_signature && (
            <div className="bg-success/10 border border-success/40 rounded-sm p-2.5 text-xs">
              <div className="text-[10px] uppercase tracking-wider text-success font-bold">Client signature</div>
              <div className="mt-1"><strong>{m.client_signature.name}</strong>{m.client_signature.designation ? ` · ${m.client_signature.designation}` : ""}</div>
              <div className="text-muted-foreground">signed at {m.client_signature.signed_at} · recorded by {m.client_signature.recorded_by}</div>
            </div>
          )}
          <Table>
            <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead className="text-[10px] uppercase tracking-wider">Service</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Activity</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Description</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Executed</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Certified</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(m.items || []).map((it, i) => (
                <TableRow key={`it-${i}`}>
                  <TableCell className="text-xs font-semibold">{it.service.replaceAll("_", " ")}</TableCell>
                  <TableCell className="text-xs">{it.activity.replaceAll("_", " ")}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{it.description || "—"}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs">{it.executed_qty}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs font-bold">{it.certified_qty}</TableCell>
                  <TableCell className="text-xs">{it.unit}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs">{it.rate != null ? inr(it.rate) : "—"}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs font-bold">{it.rate != null ? inr((it.rate || 0) * (it.certified_qty || 0)) : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <KV label="Total Executed" v={m.total_executed} />
            <KV label="Total Certified" v={m.total_certified} />
            <KV label="Billable Value" v={inr(m.billable_value)} />
          </div>
          {m.remarks && <div className="border border-border rounded-sm p-2.5 text-xs"><div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1">Remarks</div>{m.remarks}</div>}
          {m.reject_reason && <div className="bg-destructive/10 border border-destructive/40 rounded-sm p-2.5 text-xs text-destructive"><strong>Rejected:</strong> {m.reject_reason}</div>}
        </div>
        <DialogFooter><Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
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
function KV({ label, v }) {
  return <div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="font-mono-data tabular">{v ?? "—"}</div></div>;
}
