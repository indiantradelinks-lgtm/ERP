/**
 * Work Order Mapping · Customer PO/LOI registry linked to Projects.
 * Backend: /api/work-orders
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, RefreshCcw, FileSignature, Filter, Search, Link2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const STATUSES = ["draft", "received", "active", "completed", "cancelled", "hold"];
const EMPTY = { wo_no: "", project_id: "", wo_date: "", valid_from: "", valid_until: "",
                scope: "", value: 0, currency: "INR", status: "draft", remarks: "",
                quotation_no: "", approved_quotation: null, boq: "",
                payment_terms: "", retention_clause: "", retention_percentage: 0,
                tds_applicability: "", gst_applicability: "",
                project_start_condition: "", billing_milestone: "",
                contractual_completion_date: "",
                source_handover_id: "", source_handover_no: "" };

// Fields we auto-pull from a Contract Handover. Everything not listed here
// (validity dates, retention %, TDS/GST, billing milestones, etc.) must be
// entered manually on the Work Order form.
function prefillFromHandover(handover) {
  if (!handover) return { ...EMPTY };
  return {
    ...EMPTY,
    wo_no: handover.work_order_number || "",
    project_id: handover.project_id || "",
    scope: handover.scope_of_work || "",
    value: Number(handover.contract_value) || 0,
    quotation_no: handover.quotation_no || "",
    payment_terms: handover.payment_terms || "",
    contractual_completion_date: handover.contract_end_date || "",
    // GST inferred from handover.gst_details being present
    gst_applicability: handover.gst_details ? "applicable" : "",
    // Client / site labels are cascaded on the backend from project_id, but we
    // also expose them so the UI shows something useful before save.
    client_name: handover.client_name || "",
    site_name: handover.site_location || "",
    // Traceability
    source_handover_id: handover.id,
    source_handover_no: handover.handover_no || "",
  };
}

export default function WorkOrders() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [stats, setStats] = useState(null);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [projectFilter, setProjectFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [handoverPickerOpen, setHandoverPickerOpen] = useState(false);
  const { user } = useAuth() || {};
  const canWrite = !["sales_executive", "purchase_officer", "store_incharge"].includes(user?.role);

  const load = async () => {
    try {
      const [a, b, c] = await Promise.all([
        api.get("/work-orders"),
        api.get("/projects"),
        api.get("/work-orders/stats").catch(() => ({ data: null })),
      ]);
      setRows(a.data);
      setProjects(b.data);
      setStats(c.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const projectById = useMemo(() => Object.fromEntries(projects.map((p) => [p.id, p])), [projects]);

  const filtered = useMemo(() => rows.filter((r) =>
    (!projectFilter || r.project_id === projectFilter) &&
    (!statusFilter || r.status === statusFilter)
  ), [rows, projectFilter, statusFilter]);

  const save = async () => {
    if (!form.wo_no?.trim()) { toast.error("WO Number is required"); return; }
    try {
      const payload = { ...form, value: Number(form.value) || 0 };
      if (editing?.id) {
        await api.put(`/work-orders/${editing.id}`, payload);
        toast.success("Work Order updated");
      } else {
        await api.post(`/work-orders`, payload);
        toast.success("Work Order created");
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete Work Order ${r.wo_no}?`)) return;
    try {
      await api.delete(`/work-orders/${r.id}`);
      toast.success("Deleted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const totalValue = stats?.total_value || filtered.reduce((s, r) => s + (Number(r.value) || 0), 0);

  return (
    <div className="p-6 space-y-4" data-testid="page-work-orders">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileSignature className="h-6 w-6 text-primary" /> Work Order Mapping
          </h1>
          <p className="text-sm text-muted-foreground">Customer PO / LOI documents that authorize Project execution. One Project can have multiple Work Orders (phased releases).</p>
        </div>
        {canWrite && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setHandoverPickerOpen(true)}
              data-testid="wo-new-from-handover"
              title="Pick a Contract Handover — the common fields (WO#, project, scope, value, quote, payment terms, completion date) will be pre-filled"
            >
              <Link2 className="h-4 w-4 mr-1" /> New from Handover
            </Button>
            <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="wo-new">
              <Plus className="h-4 w-4 mr-1" /> New Work Order
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total WOs" value={stats?.total ?? rows.length} />
        <Stat label="Active" value={(stats?.by_status || []).find((s) => s.status === "active")?.count ?? 0} />
        <Stat label="Total Value" value={"₹ " + Number(totalValue).toLocaleString("en-IN")} />
        <Stat label="Linked Projects" value={new Set(rows.map((r) => r.project_id).filter(Boolean)).size} />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Work Orders <span className="text-xs text-slate-400">({filtered.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" />
            <select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}
                     className="h-7 rounded-sm border border-input bg-background px-2" data-testid="wo-filter-project">
              <option value="">All projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                     className="h-7 rounded-sm border border-input bg-background px-2" data-testid="wo-filter-status">
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Button size="sm" variant="outline" onClick={load}>
              <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">WO #</th>
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2">Client</th>
                  <th className="px-3 py-2">Site</th>
                  <th className="px-3 py-2">WO Date</th>
                  <th className="px-3 py-2">Valid Until</th>
                  <th className="px-3 py-2 text-right">Value</th>
                  <th className="px-3 py-2 text-center">Status</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={9} className="text-center py-8 text-slate-400">No Work Orders yet</td></tr>
                )}
                {filtered.map((r) => {
                  const p = projectById[r.project_id];
                  return (
                    <tr key={r.id} className="border-b hover:bg-slate-50/50" data-testid={`wo-row-${r.id}`}>
                      <td className="px-3 py-2 font-mono font-bold text-primary">
                        {r.wo_no}
                        {r.source_handover_no && (
                          <span
                            className="block mt-0.5 inline-flex items-center gap-0.5 px-1 py-0 text-[9px] rounded border bg-blue-50 text-blue-700 border-blue-200 font-sans normal-case tracking-normal"
                            title={`Linked to Contract Handover ${r.source_handover_no}`}
                            data-testid={`wo-source-badge-${r.id}`}
                          >
                            <Link2 className="h-2.5 w-2.5" /> from {r.source_handover_no}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">{p ? <span><span className="font-mono text-xs">{p.code}</span> · {p.name}</span> : (r.project_code || "—")}</td>
                      <td className="px-3 py-2">{r.client_name || p?.client || "—"}</td>
                      <td className="px-3 py-2">{r.site_name || p?.site || "—"}</td>
                      <td className="px-3 py-2 text-xs">{r.wo_date || "—"}</td>
                      <td className="px-3 py-2 text-xs">{r.valid_until || "—"}</td>
                      <td className="px-3 py-2 text-right font-mono">₹ {Number(r.value || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusTone(r.status)}`}>{r.status}</span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        {canWrite && (
                          <div className="flex justify-end gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`wo-edit-${r.id}`}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`wo-del-${r.id}`}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editing?.id ? "Edit" : "New"} Work Order</DialogTitle>
          </DialogHeader>
          {form.source_handover_no && (
            <div
              className="rounded-md border border-blue-200 bg-blue-50/60 px-3 py-2 text-xs flex items-start gap-2 -mt-1"
              data-testid="wo-form-source-banner"
            >
              <Link2 className="h-3.5 w-3.5 text-blue-700 mt-0.5 shrink-0" />
              <div className="flex-1">
                <span className="font-semibold text-blue-900">Linked to Contract Handover {form.source_handover_no}.</span>
                <span className="text-blue-800/80 ml-1">
                  WO #, project, scope, value, quotation, payment terms and completion date were auto-filled — edit only the fields you need to override.
                </span>
              </div>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Customer WO / PO / LOI # *"><Input value={form.wo_no} onChange={(e) => setForm({ ...form, wo_no: e.target.value })} data-testid="wo-form-no" /></F>
            <F label="Project">
              <select value={form.project_id || ""} onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="wo-form-project">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </F>
            <F label="WO Date"><Input type="date" value={form.wo_date || ""} onChange={(e) => setForm({ ...form, wo_date: e.target.value })} /></F>
            <F label="Valid From"><Input type="date" value={form.valid_from || ""} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} /></F>
            <F label="Valid Until"><Input type="date" value={form.valid_until || ""} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} /></F>
            <F label="Status">
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </F>
            <F label="Value (INR)"><Input type="number" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} /></F>
            <F label="Currency"><Input value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} /></F>
            <F label="Scope" full><Textarea rows={3} value={form.scope || ""} onChange={(e) => setForm({ ...form, scope: e.target.value })} /></F>

            <div className="md:col-span-2 pt-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary border-b border-border pb-1.5">Sales Linkage</div>
            </div>
            <F label="Sales Quotation #"><Input value={form.quotation_no || ""} onChange={(e) => setForm({ ...form, quotation_no: e.target.value })} data-testid="wo-form-quote-no" /></F>
            <F label="Quotation Approved?">
              <select value={form.approved_quotation === true ? "yes" : form.approved_quotation === false ? "no" : ""}
                       onChange={(e) => setForm({ ...form, approved_quotation: e.target.value === "yes" ? true : e.target.value === "no" ? false : null })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— select —</option><option value="yes">Yes</option><option value="no">No</option>
              </select>
            </F>
            <F label="BOQ (Bill of Quantities)" full>
              <Textarea rows={3} value={form.boq || ""} onChange={(e) => setForm({ ...form, boq: e.target.value })}
                         placeholder="Free-form BOQ description / link to attached file" />
            </F>

            <div className="md:col-span-2 pt-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary border-b border-border pb-1.5">Commercial</div>
            </div>
            <F label="Payment Terms"><Input value={form.payment_terms || ""} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} placeholder="30 days from RA bill" /></F>
            <F label="Retention Clause"><Input value={form.retention_clause || ""} onChange={(e) => setForm({ ...form, retention_clause: e.target.value })} placeholder="5% retained, released on closure" /></F>
            <F label="Retention %"><Input type="number" value={form.retention_percentage || 0} onChange={(e) => setForm({ ...form, retention_percentage: Number(e.target.value) || 0 })} /></F>
            <F label="TDS Applicability">
              <select value={form.tds_applicability || ""} onChange={(e) => setForm({ ...form, tds_applicability: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">—</option><option value="applicable">Applicable</option><option value="not_applicable">Not Applicable</option>
              </select>
            </F>
            <F label="GST Applicability">
              <select value={form.gst_applicability || ""} onChange={(e) => setForm({ ...form, gst_applicability: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">—</option><option value="applicable">Applicable</option><option value="not_applicable">Not Applicable</option><option value="exempt">Exempt</option>
              </select>
            </F>
            <F label="Contractual Completion Date"><Input type="date" value={form.contractual_completion_date || ""} onChange={(e) => setForm({ ...form, contractual_completion_date: e.target.value })} /></F>

            <div className="md:col-span-2 pt-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary border-b border-border pb-1.5">Execution</div>
            </div>
            <F label="Project Start Condition" full><Textarea rows={2} value={form.project_start_condition || ""} onChange={(e) => setForm({ ...form, project_start_condition: e.target.value })} placeholder="e.g. after mobilization advance receipt + safety induction" /></F>
            <F label="Billing Milestone" full><Textarea rows={2} value={form.billing_milestone || ""} onChange={(e) => setForm({ ...form, billing_milestone: e.target.value })} placeholder="Milestone 1: Erection complete · 30%. Milestone 2: Final handover · 70%." /></F>
            <F label="Remarks" full><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>

            {editing?.revision_history?.length > 0 && (
              <div className="md:col-span-2 pt-2">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 border-b border-amber-200 pb-1.5">Value Revision History ({editing.revision_history.length})</div>
                <ul className="mt-2 space-y-1 text-xs">
                  {editing.revision_history.map((h, i) => (
                    <li key={i} className="border rounded-sm p-2 bg-amber-50">
                      <div className="flex justify-between font-mono">
                        <span>{(h.at || "").slice(0, 16).replace("T", " ")}</span>
                        <span><b>₹ {Number(h.from_value || 0).toLocaleString("en-IN")}</b> → <b>₹ {Number(h.to_value || 0).toLocaleString("en-IN")}</b></span>
                      </div>
                      <div className="text-muted-foreground">by {h.by_name || "—"} {h.reason && `· ${h.reason}`}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="wo-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {handoverPickerOpen && (
        <HandoverPickerDialog
          onClose={() => setHandoverPickerOpen(false)}
          onPick={(h) => {
            setHandoverPickerOpen(false);
            setEditing({});
            setForm(prefillFromHandover(h));
            toast.success(`Pre-filled from handover ${h.handover_no}`);
          }}
        />
      )}
    </div>
  );
}

const TONES = {
  draft: "bg-slate-50 text-slate-600 border-slate-200",
  received: "bg-blue-50 text-blue-700 border-blue-200",
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  completed: "bg-violet-50 text-violet-700 border-violet-200",
  cancelled: "bg-rose-50 text-rose-700 border-rose-200",
  hold: "bg-amber-50 text-amber-700 border-amber-200",
};
function statusTone(s) { return TONES[s] || "bg-slate-50 text-slate-600 border-slate-200"; }
function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
function Stat({ label, value }) {
  return (
    <div className="border rounded-sm p-3 bg-card">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-xl font-bold truncate">{value}</div>
    </div>
  );
}

/* ─── Contract Handover picker ────────────────────────────────────────
 * Lists handovers, filters out drafts (they're not ready to become a WO
 * yet), lets the user search + click one to pre-fill the WO form.
 * Common fields flow through; WO-specific fields (validity, retention,
 * TDS/GST, billing milestones, etc.) are entered manually afterwards.
 */
function HandoverPickerDialog({ onClose, onPick }) {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  const [existingWoNumbers, setExistingWoNumbers] = useState(new Set());

  useEffect(() => {
    Promise.all([
      api.get("/ops/handovers"),
      api.get("/work-orders").catch(() => ({ data: [] })),
    ])
      .then(([hoRes, woRes]) => {
        const active = (hoRes.data || []).filter((h) => h.status !== "draft" && h.status !== "sent_back");
        setRows(active);
        const linked = new Set((woRes.data || []).map((w) => w.source_handover_id).filter(Boolean));
        setExistingWoNumbers(linked);
      })
      .catch((e) => {
        toast.error(e.response?.data?.detail || "Failed to load handovers");
        setRows([]);
      });
  }, []);

  const filtered = useMemo(() => {
    const list = rows || [];
    if (!q.trim()) return list;
    const s = q.toLowerCase();
    return list.filter((r) =>
      (r.handover_no || "").toLowerCase().includes(s)
      || (r.project_name || "").toLowerCase().includes(s)
      || (r.client_name || "").toLowerCase().includes(s)
      || (r.work_order_number || "").toLowerCase().includes(s)
    );
  }, [rows, q]);

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[85vh]" data-testid="wo-handover-picker">
        <DialogHeader>
          <DialogTitle>Pick a Contract Handover</DialogTitle>
          <DialogDescription className="text-xs">
            Only submitted / allocated / active handovers are shown (drafts can&apos;t be turned into a Work Order yet).
            Handovers already linked to a WO show a small warning — you can still pick them but you&apos;ll get a WO # clash.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search handover # / project / client / WO#"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-8"
            data-testid="wo-handover-picker-search"
            autoFocus
          />
        </div>

        <div className="border rounded-sm overflow-hidden max-h-[55vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2">Handover #</th>
                <th className="text-left px-3 py-2">WO #</th>
                <th className="text-left px-3 py-2">Project</th>
                <th className="text-left px-3 py-2">Client</th>
                <th className="text-right px-3 py-2">Value (₹)</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows === null && (
                <tr><td colSpan={7} className="text-center py-6 text-slate-400 italic">Loading…</td></tr>
              )}
              {rows !== null && filtered.length === 0 && (
                <tr><td colSpan={7} className="text-center py-6 text-slate-500">No handovers match.</td></tr>
              )}
              {filtered.map((h) => {
                const alreadyLinked = existingWoNumbers.has(h.id);
                return (
                  <tr key={h.id} className="border-t hover:bg-slate-50" data-testid={`wo-handover-pick-${h.id}`}>
                    <td className="px-3 py-2 font-mono-data text-xs">{h.handover_no}</td>
                    <td className="px-3 py-2 font-mono-data text-xs">{h.work_order_number || <span className="text-slate-400 italic">—</span>}</td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{h.project_name}</div>
                      {h.project_code && <div className="text-[10px] text-slate-400">{h.project_code}</div>}
                    </td>
                    <td className="px-3 py-2 text-xs">{h.client_name || "—"}</td>
                    <td className="px-3 py-2 text-right tabular text-xs">{(h.contract_value || 0).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-[10px] uppercase tracking-wider text-slate-600">{h.status?.replaceAll("_", " ")}</td>
                    <td className="px-2 py-2 text-right">
                      <div className="flex flex-col items-end gap-0.5">
                        <Button
                          size="sm"
                          onClick={() => onPick(h)}
                          data-testid={`wo-handover-pick-btn-${h.id}`}
                        >
                          Use
                        </Button>
                        {alreadyLinked && (
                          <span className="text-[9px] text-amber-700" title="A Work Order is already linked to this handover">already linked</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
