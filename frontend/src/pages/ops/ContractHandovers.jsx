import { useEffect, useMemo, useState } from "react";
import { Plus, Send, Users, Search, FileText, FileSpreadsheet, Clock, Briefcase, X, Eye, Sparkles, RefreshCcw, Paperclip } from "lucide-react";
import FileUploader from "@/components/FileUploader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { DepartmentSelect } from "@/components/DepartmentSelect";

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-300",
  submitted: "bg-amber-100 text-amber-800 border-amber-300",
  under_review: "bg-amber-100 text-amber-800 border-amber-300",
  allocated: "bg-blue-100 text-blue-800 border-blue-300",
  active: "bg-green-100 text-green-800 border-green-300",
  on_hold: "bg-orange-100 text-orange-800 border-orange-300",
  completed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  closed: "bg-zinc-100 text-zinc-600 border-zinc-300",
  sent_back: "bg-red-100 text-red-700 border-red-300",
};

const PRIORITIES = ["low", "medium", "high", "critical"];

function emptyForm() {
  return {
    project_name: "", client_name: "", site_location: "", work_order_number: "",
    contract_value: 0, contract_start_date: "", contract_end_date: "",
    scope_of_work: "", billing_terms: "", payment_terms: "", gst_details: "",
    customer_contact_person: "", customer_contact_number: "", customer_email: "",
    special_conditions: "", safety_requirements: "", manpower_requirements: "",
    material_requirements: "", asset_requirements: "", remarks: "",
    attachments: [],
  };
}

export default function ContractHandovers() {
  const { user } = useAuth();
  const role = user?.role;
  const canCreate = ["super_admin", "director", "general_manager", "dept_head", "sales_executive"].includes(role);
  const canAllocate = ["super_admin", "director", "general_manager", "dept_head"].includes(role);

  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [editing, setEditing] = useState(null);  // {open, mode:'create'|'edit'|'view', data}
  const [allocFor, setAllocFor] = useState(null); // handover row
  const [exporting, setExporting] = useState("");

  const downloadReport = async (fmt) => {
    setExporting(fmt);
    try {
      const { data } = await api.get(`/ops/handovers/export/${fmt}`, {
        responseType: "blob",
        params: filterStatus !== "all" ? { status: filterStatus } : {},
      });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = `contract-handovers.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`${fmt === "xlsx" ? "Excel" : "PDF"} report downloaded`);
    } catch (e) { toast.error("Export failed"); }
    finally { setExporting(""); }
  };

  const load = async () => {
    try {
      const r = await api.get("/ops/handovers");
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load handovers"); }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    return (rows || []).filter((r) => {
      if (filterStatus !== "all" && r.status !== filterStatus) return false;
      if (q) {
        const s = q.toLowerCase();
        return (r.project_name || "").toLowerCase().includes(s)
          || (r.client_name || "").toLowerCase().includes(s)
          || (r.handover_no || "").toLowerCase().includes(s)
          || (r.work_order_number || "").toLowerCase().includes(s);
      }
      return true;
    });
  }, [rows, q, filterStatus]);

  const remove = async (r) => {
    if (!window.confirm(`Delete draft handover "${r.handover_no}"?`)) return;
    try { await api.delete(`/ops/handovers/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const [backfilling, setBackfilling] = useState(false);
  const runBackfill = async () => {
    if (!window.confirm(
      "Scan all WON quotations and auto-create a Contract Handover (+ Project) for any that don't already have one?\n\nThis is safe to run multiple times — duplicates are skipped."
    )) return;
    setBackfilling(true);
    try {
      const { data } = await api.post("/ops/handovers/backfill-from-won");
      const created = data.created || 0;
      const skipped = data.already_handed_over || 0;
      if (created === 0) {
        toast.success(`Nothing to backfill — all ${data.scanned} won quotes already linked to handovers.`);
      } else {
        const sample = (data.created_rows || []).slice(0, 3).map((r) => r.handover_no).join(", ");
        toast.success(
          `Backfilled ${created} handover${created === 1 ? "" : "s"} from won quotes` +
          (sample ? ` (${sample}${created > 3 ? "…" : ""})` : "") +
          (skipped ? ` · ${skipped} already linked` : ""),
          { duration: 8000 }
        );
      }
      if ((data.skipped || []).length) {
        console.warn("Backfill skipped rows:", data.skipped);
        toast.warning(`${data.skipped.length} quote(s) skipped — check console for details.`);
      }
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Backfill failed");
    } finally { setBackfilling(false); }
  };

  const autoDrafts = (rows || []).filter((r) => r.source === "auto_from_quote" && r.status === "draft");

  return (
    <div className="p-6 space-y-4" data-testid="ops-handovers-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Projects & Operations</div>
          <h1 className="font-display font-black text-3xl tracking-tight">Contract Handovers</h1>
          <p className="text-sm text-slate-600 mt-1">Sales hands over confirmed orders to Project Heads for resource allocation.</p>
        </div>
        <div className="flex gap-2 items-center">
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-40" data-testid="ops-filter-status"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {Object.keys(STATUS_TONE).map((s) => <SelectItem key={s} value={s}>{s.replaceAll("_", " ")}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input placeholder="Search no. / project / client" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8 w-72" data-testid="ops-search" />
          </div>
          <Button variant="outline" onClick={() => downloadReport("xlsx")} disabled={exporting === "xlsx"} data-testid="ops-export-xlsx" title="Download Excel report (respects status filter)">
            <FileSpreadsheet className="h-4 w-4 mr-1" /> {exporting === "xlsx" ? "Exporting…" : "Excel"}
          </Button>
          <Button variant="outline" onClick={() => downloadReport("pdf")} disabled={exporting === "pdf"} data-testid="ops-export-pdf" title="Download PDF report (respects status filter)">
            <FileText className="h-4 w-4 mr-1" /> {exporting === "pdf" ? "Exporting…" : "PDF"}
          </Button>
          {canCreate && (
            <Button onClick={() => setEditing({ open: true, mode: "create", data: emptyForm() })} data-testid="ops-new-btn">
              <Plus className="h-4 w-4 mr-1" /> New Contract Handover
            </Button>
          )}
          {canAllocate && (
            <Button
              variant="outline"
              onClick={runBackfill}
              disabled={backfilling}
              data-testid="ops-backfill-btn"
              title="One-shot backfill: creates Contract Handovers for any 'won' quotation that doesn't already have one. Idempotent — safe to run multiple times."
            >
              <RefreshCcw className={`h-4 w-4 mr-1 ${backfilling ? "animate-spin" : ""}`} />
              {backfilling ? "Backfilling…" : "Backfill from Won Quotes"}
            </Button>
          )}
        </div>
      </div>

      {autoDrafts.length > 0 && (
        <div className="rounded-md border border-emerald-300 bg-emerald-50/60 px-4 py-3 flex items-start gap-3" data-testid="ops-auto-drafts-banner">
          <Sparkles className="h-4 w-4 text-emerald-700 mt-0.5 shrink-0" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-emerald-900">
              {autoDrafts.length} draft handover{autoDrafts.length === 1 ? "" : "s"} auto-created from won quotation{autoDrafts.length === 1 ? "" : "s"}
            </div>
            <div className="text-xs text-emerald-800/80 mt-0.5">
              These were pre-filled from the quote + enquiry. Review &amp; submit to allocate a Project Manager.
              {" "}
              <span className="font-mono text-[11px]">{autoDrafts.slice(0, 5).map((r) => r.handover_no).join(" · ")}{autoDrafts.length > 5 ? " · …" : ""}</span>
            </div>
          </div>
        </div>
      )}

      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Handover #</th>
              <th className="text-left px-3 py-2">Project #</th>
              <th className="text-left px-3 py-2">Quote #</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Client</th>
              <th className="text-left px-3 py-2 min-w-[220px]">Scope of Work</th>
              <th className="text-left px-3 py-2">Site</th>
              <th className="text-right px-3 py-2">Value (₹)</th>
              <th className="text-left px-3 py-2">Allocation</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={11} className="text-center py-8 text-slate-500 text-sm">No handovers yet.</td></tr>
            )}
            {filtered.map((r) => (
              <tr key={r.id} className={`border-t hover:bg-slate-50 ${r.source === "auto_from_quote" && r.status === "draft" ? "bg-emerald-50/40" : ""}`} data-testid={`ops-row-${r.id}`}>
                <td className="px-3 py-2 font-mono-data text-xs">
                  {r.handover_no}
                  {r.source === "auto_from_quote" && (
                    <span className="block mt-1 inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] rounded border bg-emerald-100 text-emerald-700 border-emerald-300 font-sans normal-case tracking-normal" data-testid={`ops-auto-badge-${r.id}`}>
                      <Sparkles className="h-2.5 w-2.5" /> auto · from quote
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono-data text-xs">
                  {r.project_code ? (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded border bg-blue-50 text-blue-800 border-blue-300 font-semibold" data-testid={`ops-project-code-${r.id}`}>
                      {r.project_code}
                    </span>
                  ) : <span className="text-slate-400 italic">—</span>}
                </td>
                <td className="px-3 py-2 font-mono-data text-xs">
                  {r.quotation_no ? (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-300" data-testid={`ops-quote-code-${r.id}`}>
                      {r.quotation_no}
                    </span>
                  ) : <span className="text-slate-400 italic">—</span>}
                </td>
                <td className="px-3 py-2">
                  <div className="font-medium flex items-center gap-1.5" data-testid={`ops-project-name-${r.id}`}>
                    {r.project_name}
                    {r.project_name_source && r.project_name_original && r.project_name !== r.project_name_original && (
                      <span
                        title={`Live from ${r.project_name_source}. Original snapshot: "${r.project_name_original}"`}
                        className="inline-flex items-center text-[9px] uppercase tracking-wider px-1 py-0 rounded border bg-blue-50 text-blue-700 border-blue-200"
                        data-testid={`ops-project-live-${r.id}`}
                      >
                        <RefreshCcw className="h-2.5 w-2.5 mr-0.5" /> live
                      </span>
                    )}
                  </div>
                  {r.work_order_number && <div className="text-[10px] text-slate-400 mt-0.5">WO {r.work_order_number}</div>}
                </td>
                <td className="px-3 py-2">
                  <div className="text-sm flex items-center gap-1.5" data-testid={`ops-client-name-${r.id}`}>
                    {r.client_name || <span className="text-slate-400 italic">—</span>}
                    {r.client_name_source && r.client_name_original && r.client_name !== r.client_name_original && (
                      <span
                        title={`Live from ${r.client_name_source}. Original: "${r.client_name_original}"`}
                        className="inline-flex items-center text-[9px] uppercase tracking-wider px-1 py-0 rounded border bg-blue-50 text-blue-700 border-blue-200"
                        data-testid={`ops-client-live-${r.id}`}
                      >
                        <RefreshCcw className="h-2.5 w-2.5 mr-0.5" /> live
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 text-xs max-w-[300px]">
                  <div
                    className="line-clamp-3 flex items-start gap-1.5"
                    title={r.scope_of_work || ""}
                    data-testid={`ops-scope-${r.id}`}
                  >
                    <span className="whitespace-pre-wrap break-words">{r.scope_of_work || <span className="text-slate-400 italic">—</span>}</span>
                    {r.scope_of_work_source && r.scope_of_work_original && r.scope_of_work !== r.scope_of_work_original && (
                      <span
                        title={`Live from ${r.scope_of_work_source}. Original snapshot: "${r.scope_of_work_original}"`}
                        className="shrink-0 inline-flex items-center text-[9px] uppercase tracking-wider px-1 py-0 rounded border bg-blue-50 text-blue-700 border-blue-200"
                        data-testid={`ops-scope-live-${r.id}`}
                      >
                        <RefreshCcw className="h-2.5 w-2.5 mr-0.5" /> live
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 text-xs">{r.site_location || "—"}</td>
                <td className="px-3 py-2 text-right tabular">{(r.contract_value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                <td className="px-3 py-2 text-xs">
                  {r.project_manager_id || r.project_coordinator_id ? (
                    <>
                      {r.project_manager_id && <div>PM: <b>{r.project_manager_label || r.project_manager_id.slice(0, 6)}</b></div>}
                      {r.project_coordinator_id && <div>PC: <b>{r.project_coordinator_label || r.project_coordinator_id.slice(0, 6)}</b></div>}
                      <span className="text-slate-500">{r.priority || ""}</span>
                    </>
                  ) : <span className="text-slate-400 italic">unallocated</span>}
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-block px-2 py-0.5 text-xs rounded border ${STATUS_TONE[r.status] || ""}`}>{r.status?.replaceAll("_", " ")}</span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditing({ open: true, mode: "view", data: r })} data-testid={`ops-view-${r.id}`}><Eye className="h-3.5 w-3.5" /></Button>
                    {(r.status === "draft" || r.status === "sent_back") && canCreate && (
                      <Button size="sm" variant="outline" onClick={() => setEditing({ open: true, mode: "edit", data: r })} data-testid={`ops-edit-${r.id}`}>Edit</Button>
                    )}
                    {(r.status === "submitted" || r.status === "under_review" || r.status === "allocated" || r.status === "active") && canAllocate && (
                      <Button size="sm" onClick={() => setAllocFor(r)} data-testid={`ops-allocate-${r.id}`}>
                        <Users className="h-3.5 w-3.5 mr-1" /> {r.project_manager_id ? "Reassign" : "Allocate"}
                      </Button>
                    )}
                    {r.status === "draft" && canCreate && (
                      <Button size="sm" variant="ghost" onClick={() => remove(r)} data-testid={`ops-delete-${r.id}`}><X className="h-3.5 w-3.5 text-red-600" /></Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing?.open && (
        <HandoverDialog
          mode={editing.mode}
          initial={editing.data}
          onClose={() => setEditing(null)}
          onSaved={() => { load(); setEditing(null); }}
        />
      )}
      {allocFor && (
        <AllocateDialog
          handover={allocFor}
          onClose={() => setAllocFor(null)}
          onSaved={() => { load(); setAllocFor(null); }}
        />
      )}
    </div>
  );
}


function HandoverDialog({ mode, initial, onClose, onSaved }) {
  const [form, setForm] = useState({ ...emptyForm(), ...initial });
  const [tab, setTab] = useState("basic");
  const [docs, setDocs] = useState([]);
  const isView = mode === "view";
  const isEdit = mode === "edit";
  const isNew = mode === "create";

  // Fetch existing attached files for this handover whenever id is known.
  const loadDocs = (id) => {
    if (!id) { setDocs([]); return; }
    api.get(`/files?parent_type=project_handovers&parent_id=${id}`)
      .then((r) => setDocs(r.data || []))
      .catch(() => setDocs([]));
  };
  useEffect(() => { loadDocs(form.id); }, [form.id]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async (alsoSubmit = false) => {
    try {
      const payload = { ...form };
      delete payload.id; delete payload.handover_no; delete payload.status;
      delete payload.created_at; delete payload.created_by; delete payload.created_by_id;
      delete payload.updated_at; delete payload.updated_by; delete payload.submitted_at;
      delete payload.submitted_by; delete payload.submitted_by_id;
      delete payload.allocated_at; delete payload.allocated_by; delete payload.allocated_by_id;
      delete payload.project_id;
      delete payload.project_manager_id; delete payload.project_coordinator_id;
      delete payload.reporting_manager_id; delete payload.department; delete payload.priority;
      delete payload.expected_start_date; delete payload.expected_completion_date;
      delete payload.allocation_remarks;
      delete payload.project_manager_label; delete payload.project_coordinator_label; delete payload.reporting_manager_label;
      payload.contract_value = Number(payload.contract_value || 0);
      let id = form.id;
      if (isNew) {
        const r = await api.post("/ops/handovers", payload);
        toast.success(`Handover ${r.data.handover_no} saved as draft`);
        id = r.data.id;
      } else {
        await api.put(`/ops/handovers/${id}`, payload);
        toast.success("Handover updated");
      }
      if (alsoSubmit && id) {
        await api.post(`/ops/handovers/${id}/submit`);
        toast.success("Submitted to Project Heads (notifications sent)");
      }
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isNew ? "New Contract Handover" : `${isView ? "View" : "Edit"} — ${form.handover_no || ""}`}
            {form.status && (
              <span className={`ml-3 inline-block px-2 py-0.5 text-xs rounded border ${STATUS_TONE[form.status]}`}>{form.status?.replaceAll("_", " ")}</span>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">Project handover detail</DialogDescription>
        </DialogHeader>
        <Tabs value={tab} onValueChange={setTab} className="mt-2">
          <TabsList className="grid grid-cols-5 w-full">
            <TabsTrigger value="basic">Project / Client</TabsTrigger>
            <TabsTrigger value="commercial">Commercial</TabsTrigger>
            <TabsTrigger value="ops">Operations</TabsTrigger>
            <TabsTrigger value="extras">Requirements</TabsTrigger>
            <TabsTrigger value="docs" data-testid="ho-tab-docs">
              <Paperclip className="h-3.5 w-3.5 mr-1" /> Documents
              {docs.length > 0 && (
                <span className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] rounded-full bg-blue-100 text-blue-800 border border-blue-300">{docs.length}</span>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="basic" className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Project Name *" value={form.project_name} onChange={(v) => set("project_name", v)} disabled={isView} testid="ho-project-name" />
              <Field label="Work Order Number" value={form.work_order_number} onChange={(v) => set("work_order_number", v)} disabled={isView} testid="ho-wo" />
              <Field label="Client Name *" value={form.client_name} onChange={(v) => set("client_name", v)} disabled={isView} testid="ho-client" />
              <Field label="Site Location" value={form.site_location} onChange={(v) => set("site_location", v)} disabled={isView} testid="ho-site" />
              <Field label="Contact Person" value={form.customer_contact_person} onChange={(v) => set("customer_contact_person", v)} disabled={isView} />
              <Field label="Contact Number" value={form.customer_contact_number} onChange={(v) => set("customer_contact_number", v)} disabled={isView} />
              <Field label="Customer Email" value={form.customer_email} onChange={(v) => set("customer_email", v)} disabled={isView} />
              <Field label="GST Details" value={form.gst_details} onChange={(v) => set("gst_details", v)} disabled={isView} />
            </div>
          </TabsContent>

          <TabsContent value="commercial" className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <Field type="number" label="Contract Value (₹) *" value={form.contract_value} onChange={(v) => set("contract_value", v)} disabled={isView} testid="ho-value" />
              <div></div>
              <Field type="date" label="Contract Start Date" value={form.contract_start_date} onChange={(v) => set("contract_start_date", v)} disabled={isView} />
              <Field type="date" label="Contract End Date" value={form.contract_end_date} onChange={(v) => set("contract_end_date", v)} disabled={isView} />
              <Area label="Billing Terms" value={form.billing_terms} onChange={(v) => set("billing_terms", v)} disabled={isView} />
              <Area label="Payment Terms" value={form.payment_terms} onChange={(v) => set("payment_terms", v)} disabled={isView} />
            </div>
          </TabsContent>

          <TabsContent value="ops" className="space-y-3 mt-4">
            <Area label="Scope of Work" value={form.scope_of_work} onChange={(v) => set("scope_of_work", v)} disabled={isView} rows={5} />
            <Area label="Special Conditions" value={form.special_conditions} onChange={(v) => set("special_conditions", v)} disabled={isView} />
            <Area label="Safety Requirements" value={form.safety_requirements} onChange={(v) => set("safety_requirements", v)} disabled={isView} />
            <Area label="Remarks" value={form.remarks} onChange={(v) => set("remarks", v)} disabled={isView} />
          </TabsContent>

          <TabsContent value="extras" className="space-y-3 mt-4">
            <Area label="Manpower Requirements" value={form.manpower_requirements} onChange={(v) => set("manpower_requirements", v)} disabled={isView} />
            <Area label="Material Requirements (if known)" value={form.material_requirements} onChange={(v) => set("material_requirements", v)} disabled={isView} />
            <Area label="Asset Requirements (if known)" value={form.asset_requirements} onChange={(v) => set("asset_requirements", v)} disabled={isView} />
          </TabsContent>

          <TabsContent value="docs" className="space-y-3 mt-4">
            <div className="rounded-md border border-amber-200 bg-amber-50/40 p-3 text-sm flex items-start gap-2" data-testid="ho-docs-policy">
              <Paperclip className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
              <div>
                <div className="font-semibold text-amber-900">Handover Documents</div>
                <div className="text-[12px] text-amber-800/80">
                  Attach the signed contract, customer PO, work order, site photos, BOQ, drawings, safety plans — anything the Project Head needs to take over.
                  {isNew && <span className="block mt-1 font-medium">Save the draft first to enable uploads.</span>}
                </div>
              </div>
            </div>

            {form.id ? (
              <FileUploader
                folder="documents"
                parent_type="project_handovers"
                parent_id={form.id}
                accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.docx,.doc,.csv,.dwg,.dxf"
                files={docs}
                onUploaded={(file) => setDocs((d) => [...d, file])}
                onDeleted={(fileId) => setDocs((d) => d.filter((x) => x.id !== fileId))}
                testidPrefix="ho-docs"
              />
            ) : (
              <div className="text-xs text-slate-500 italic px-1 py-3 text-center">
                Save the handover as draft first, then come back to this tab to upload files.
              </div>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter className="mt-4">
          {!isView && (
            <>
              <Button variant="outline" onClick={() => save(false)} data-testid="ho-save-draft"><FileText className="h-4 w-4 mr-1" /> Save Draft</Button>
              <Button onClick={() => save(true)} data-testid="ho-submit"><Send className="h-4 w-4 mr-1" /> Save & Submit to Project Head</Button>
            </>
          )}
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function AllocateDialog({ handover, onClose, onSaved }) {
  const [users, setUsers] = useState({ project_manager: [], project_coordinator: [], reporting_manager: [] });
  const [form, setForm] = useState({
    project_manager_id: handover.project_manager_id || "",
    project_coordinator_id: handover.project_coordinator_id || "",
    reporting_manager_id: handover.reporting_manager_id || "",
    department: handover.department || "",
    priority: handover.priority || "medium",
    expected_start_date: handover.expected_start_date || handover.contract_start_date || "",
    expected_completion_date: handover.expected_completion_date || handover.contract_end_date || "",
    remarks: "",
  });

  useEffect(() => {
    api.get("/ops/assignable-users").then((r) => setUsers(r.data || users)).catch(() => {});
    // eslint-disable-next-line
  }, []);

  const submit = async () => {
    if (!form.project_manager_id && !form.project_coordinator_id) {
      toast.error("Pick at least a Project Manager or Coordinator");
      return;
    }
    try {
      await api.post(`/ops/handovers/${handover.id}/allocate`, form);
      toast.success(handover.project_manager_id ? "Re-assigned" : "Allocated · notifications sent");
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Allocation failed"); }
  };

  const userOpt = (u) => `${u.name || u.email} (${u.role})`;
  // Iter 90 — Employee-source options for PM / Coordinator. Show designation
  // and a subtle hint when no linked ERP user (notifications won't reach them).
  const empOpt = (e) => {
    const base = `${e.name || "—"} · ${e.designation || "—"}`;
    return e.linked_user_id ? base : `${base}  ⚠ no ERP login`;
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Allocate Project — {handover.handover_no}</DialogTitle>
          <DialogDescription className="sr-only">Assign PM/coordinator</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-sm bg-blue-50 border border-blue-200 rounded px-3 py-2">
            <b>{handover.project_name}</b> · {handover.client_name} · ₹{(handover.contract_value || 0).toLocaleString("en-IN")}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Project Manager (Projects & Operations)"
                          value={form.project_manager_id}
                          onChange={(v) => setForm({ ...form, project_manager_id: v })}
                          options={users.project_manager} optLabel={empOpt} testid="alloc-pm"
                          emptyHint="No HRMS employee found with designation 'Projects & Operations'. Update an employee's designation in HRMS → Employees first." />
            <SelectField label="Project Coordinator (Data Entry Operator)"
                          value={form.project_coordinator_id}
                          onChange={(v) => setForm({ ...form, project_coordinator_id: v })}
                          options={users.project_coordinator} optLabel={empOpt} testid="alloc-pc"
                          emptyHint="No HRMS employee found with designation 'Data Entry Operator'. Update an employee's designation in HRMS → Employees first." />
            <SelectField label="Reporting Manager" value={form.reporting_manager_id} onChange={(v) => setForm({ ...form, reporting_manager_id: v })}
                          options={users.reporting_manager} optLabel={userOpt} testid="alloc-rm" />
            <DepartmentSelect value={form.department} onChange={(v) => setForm({ ...form, department: v })} testid="alloc-dept" />
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Priority</Label>
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
                       className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="alloc-priority">
                {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <Field type="date" label="Expected Start" value={form.expected_start_date} onChange={(v) => setForm({ ...form, expected_start_date: v })} />
            <Field type="date" label="Expected Completion" value={form.expected_completion_date} onChange={(v) => setForm({ ...form, expected_completion_date: v })} />
          </div>
          <Area label="Remarks for the assigned manager" value={form.remarks} onChange={(v) => setForm({ ...form, remarks: v })} />
        </div>
        <DialogFooter className="mt-4">
          <Button onClick={submit} data-testid="alloc-submit">{handover.project_manager_id ? "Re-assign" : "Allocate"}</Button>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* Helpers */
function Field({ label, value, onChange, disabled, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled} className="h-9 mt-1" data-testid={testid} />
    </div>
  );
}
function Area({ label, value, onChange, disabled, rows = 3 }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Textarea rows={rows} value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled} className="mt-1" />
    </div>
  );
}
function SelectField({ label, value, onChange, options, optLabel, testid, emptyHint }) {
  const isEmpty = !(options || []).length;
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <select value={value || ""} onChange={(e) => onChange(e.target.value)}
               className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm"
               data-testid={testid}>
        <option value="">— select —</option>
        {(options || []).map((u) => <option key={u.id} value={u.id}>{optLabel(u)}</option>)}
      </select>
      {isEmpty && emptyHint && (
        <p className="text-[10px] text-amber-700 mt-1" data-testid={`${testid}-empty-hint`}>{emptyHint}</p>
      )}
    </div>
  );
}
