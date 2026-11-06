import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Paperclip, Pencil, Send, Eye, ClipboardList, Banknote } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect, SiteLocationSelect } from "@/components/MasterSelect";
import RowAttachments from "@/components/RowAttachments";
import { StatusChip, PRIORITY_STYLE, inr, dt, useSvcMeta } from "./shared";

const blank = () => ({
  department: "", project_code: "", project_name: "", site_location: "", service_category: "",
  service_type: "", service_description: "", scope_of_work: "", required_date: "",
  priority: "Medium", estimated_budget: 0, cost_center_id: "", cost_center_label: "",
  cost_center_category_id: "",
  from_location: "", to_location: "", remarks: "",
});

const Sel = ({ label, value, onChange, options, testid, required }) => (
  <div>
    <Label className="text-xs">{label}{required ? " *" : ""}</Label>
    <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={value} onChange={onChange} data-testid={testid}>
      <option value="">— select —</option>
      {options.map((o) => (typeof o === "string" ? <option key={o} value={o}>{o}</option> : <option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  </div>
);

export default function ServiceRequests() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const meta = useSvcMeta();
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ status: sp.get("status") || "", department: "", category: "", q: "" });
  const [editing, setEditing] = useState(null);
  const [docsFor, setDocsFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
      const r = await api.get(`/service-workflow/requests?${qs}`);
      setRows(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [f]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (sp.get("new") === "1") { setEditing(blank()); setSp({}, { replace: true }); } }, [sp, setSp]);

  const save = async (submit) => {
    setBusy(true);
    try {
      const payload = { ...editing, estimated_budget: Number(editing.estimated_budget) || 0, submit };
      if (editing.id) await api.put(`/service-workflow/requests/${editing.id}`, payload);
      else {
        const r = await api.post("/service-workflow/requests", payload);
        toast.success(`Service Request ${r.data.sr_no} ${submit ? "submitted — ready for RFQ / Procurement" : "saved as draft"}`);
      }
      if (editing.id) toast.success(submit ? "Resubmitted — ready for RFQ / Procurement" : "Draft updated");
      setEditing(null);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const submitRow = async (r) => {
    try {
      await api.post(`/service-workflow/requests/${r.id}/submit`);
      toast.success(`${r.sr_no} submitted — ready for RFQ / Procurement`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const canEdit = (r) => ["draft", "sent_back", "rejected"].includes(r.status) && (r.requester_id === user?.id || user?.role === "super_admin");
  const pendingStep = (r) => {
    const c = r.approval_chain || [];
    return c[Math.min(r.approval_step ?? 0, c.length - 1)];
  };

  return (
    <div className="p-4 space-y-4" data-testid="svc-requests-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><ClipboardList className="h-5 w-5" /> Service Requests</h1>
          <p className="text-xs text-muted-foreground">Raise any service requirement from one place — <b>no internal approval needed</b>; submitted requests go straight to RFQ / Procurement, and the only approval left is the Accounts payment approval</p>
        </div>
        <div className="flex gap-2">
          {(meta?.role_caps?.accounts || meta?.role_caps?.procurement || ["manager_log", "manager_l_o_g", "logistics_executive", "logistics_manager"].includes(user?.role)) && (
            <Button variant="outline" onClick={() => nav("/app/services/direct-payments?new=1")} data-testid="svc-req-direct-payment-btn" title="Repeat payment to a vendor already paid through the Service workflow — no new SR / RFQ / PO / SRN">
              <Banknote className="h-4 w-4 mr-1" /> Direct Payment
            </Button>
          )}
          <Button onClick={() => setEditing(blank())} data-testid="svc-req-new-btn"><Plus className="h-4 w-4 mr-1" /> New Service Request</Button>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <Label className="text-[10px] uppercase">Status</Label>
          <select className="h-8 rounded-sm border border-input bg-background px-2 text-sm block" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="svc-req-status-filter">
            <option value="">All</option>
            {(meta?.sr_statuses || []).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase">Department</Label>
          <select className="h-8 rounded-sm border border-input bg-background px-2 text-sm block" value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} data-testid="svc-req-dept-filter">
            <option value="">All</option>
            {(meta?.departments || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase">Category</Label>
          <select className="h-8 rounded-sm border border-input bg-background px-2 text-sm block" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="svc-req-cat-filter">
            <option value="">All</option>
            {(meta?.service_categories || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div className="flex-1 min-w-[160px] max-w-xs">
          <Label className="text-[10px] uppercase">Search</Label>
          <Input className="h-8" placeholder="SR no / description" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="svc-req-search" />
        </div>
      </div>

      <div className="border rounded-md bg-white overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>SR No</TableHead><TableHead>Date</TableHead><TableHead>Requester</TableHead>
            <TableHead>Dept</TableHead><TableHead>Site</TableHead><TableHead>Category</TableHead>
            <TableHead>Priority</TableHead><TableHead>Est. Budget</TableHead><TableHead>Status</TableHead>
            <TableHead>Owner</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`svc-req-row-${r.sr_no}`}>
                <TableCell className="font-medium text-primary cursor-pointer" onClick={() => nav(`/app/services/requests/${r.id}`)}>{r.sr_no}</TableCell>
                <TableCell>{dt(r.request_date)}</TableCell>
                <TableCell className="text-xs">{r.requester_name}</TableCell>
                <TableCell className="text-xs">{r.department || "—"}</TableCell>
                <TableCell className="text-xs">{r.site_location || "—"}</TableCell>
                <TableCell className="text-xs">{r.service_category || "—"}</TableCell>
                <TableCell><Badge variant="outline" className={`${PRIORITY_STYLE[r.priority] || ""} text-[10px]`}>{r.priority}</Badge></TableCell>
                <TableCell className="tabular-nums">{inr(r.estimated_budget)}</TableCell>
                <TableCell><StatusChip status={r.status} testid={`svc-req-status-${r.sr_no}`} /></TableCell>
                <TableCell className="text-xs text-muted-foreground">{r.current_owner || "—"}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="icon" className="h-7 w-7" title="View full trail" onClick={() => nav(`/app/services/requests/${r.id}`)} data-testid={`svc-req-view-${r.sr_no}`}><Eye className="h-3.5 w-3.5" /></Button>
                  {canEdit(r) && <Button variant="ghost" size="icon" className="h-7 w-7" title="Edit" onClick={() => setEditing({ ...blank(), ...r, cost_center_category_id: r.cost_center_category_id || (meta?.cost_centers || []).find((c) => c.id === r.cost_center_id)?.category_id || "" })} data-testid={`svc-req-edit-${r.sr_no}`}><Pencil className="h-3.5 w-3.5" /></Button>}
                  {canEdit(r) && <Button variant="ghost" size="icon" className="h-7 w-7" title="Submit — goes straight to RFQ / Procurement" onClick={() => submitRow(r)} data-testid={`svc-req-submit-${r.sr_no}`}><Send className="h-3.5 w-3.5" /></Button>}
                  {["submitted", "under_review"].includes(r.status) &&
                    <Badge variant="outline" className="text-[9px] bg-amber-50 text-amber-700 border-amber-300" title="Approve from My Pending Approvals" data-testid={`svc-req-awaiting-${r.sr_no}`}>Awaiting: {pendingStep(r)?.label || pendingStep(r)?.role || "Approver"}</Badge>}
                  <Button variant="ghost" size="icon" className="h-7 w-7" title="Attachments" onClick={() => setDocsFor(r)} data-testid={`svc-req-docs-${r.sr_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
                </TableCell>
              </TableRow>
            ))}
            {!rows.length && <TableRow><TableCell colSpan={11} className="text-center text-sm text-muted-foreground py-8">No service requests found</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {/* Create / Edit dialog */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-req-form-dialog">
          <DialogHeader><DialogTitle>{editing?.id ? `Edit ${editing.sr_no}` : "New Service Request"}</DialogTitle></DialogHeader>
          {editing && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Sel label="Department" value={editing.department} onChange={(e) => setEditing({ ...editing, department: e.target.value })} options={meta?.departments || []} testid="svc-req-form-dept" />
              <ProjectSelect label="Project" value={editing.project_code} onChange={(code, row) => setEditing({ ...editing, project_code: code, project_name: row?.name || "" })} testid="svc-req-form-project" />
              <SiteLocationSelect label="Site / Location" value={editing.site_location} onChange={(v) => setEditing({ ...editing, site_location: v })} testid="svc-req-form-site" />
              <Sel label="Service Category" required value={editing.service_category} onChange={(e) => setEditing({ ...editing, service_category: e.target.value })} options={meta?.service_categories || []} testid="svc-req-form-category" />
              {/(transport|vehicle)/i.test(editing.service_category || "") && (
                <>
                  <div><Label className="text-xs">From Location *</Label><Input value={editing.from_location || ""} onChange={(e) => setEditing({ ...editing, from_location: e.target.value })} placeholder="Pickup / origin" data-testid="svc-req-form-from" /></div>
                  <div><Label className="text-xs">To Location *</Label><Input value={editing.to_location || ""} onChange={(e) => setEditing({ ...editing, to_location: e.target.value })} placeholder="Drop / destination" data-testid="svc-req-form-to" /></div>
                </>
              )}
              <div><Label className="text-xs">Service Type</Label><Input value={editing.service_type} onChange={(e) => setEditing({ ...editing, service_type: e.target.value })} placeholder="e.g. Crane hire, AMC, Manpower supply" data-testid="svc-req-form-type" /></div>
              <div><Label className="text-xs">Required Date</Label><Input type="date" value={editing.required_date} onChange={(e) => setEditing({ ...editing, required_date: e.target.value })} data-testid="svc-req-form-required-date" /></div>
              <Sel label="Priority" value={editing.priority} onChange={(e) => setEditing({ ...editing, priority: e.target.value })} options={meta?.priorities || ["Low", "Medium", "High", "Urgent"]} testid="svc-req-form-priority" />
              <div><Label className="text-xs">Estimated Budget (₹)</Label><Input type="number" min="0" value={editing.estimated_budget} onChange={(e) => setEditing({ ...editing, estimated_budget: e.target.value })} data-testid="svc-req-form-budget" /></div>
              <Sel label="Cost Center" value={editing.cost_center_category_id || ""}
                onChange={(e) => {
                  const catId = e.target.value;
                  const cat = (meta?.cost_center_categories || []).find((c) => c.category_id === catId);
                  // One cost centre exists per project × category — bind to this project's.
                  const cc = (meta?.cost_centers || []).find(
                    (x) => (x.category_id === catId || x.category_name === catId)
                      && x.project_code === editing.project_code);
                  setEditing({
                    ...editing, cost_center_category_id: catId,
                    cost_center_id: cc?.id || "",
                    cost_center_label: cat?.category_name || "",
                  });
                }}
                options={(meta?.cost_center_categories || []).map((c) => ({ value: c.category_id, label: c.category_name }))}
                testid="svc-req-form-cc" />
              <div className="md:col-span-2"><Label className="text-xs">Service Description *</Label><Textarea rows={2} value={editing.service_description} onChange={(e) => setEditing({ ...editing, service_description: e.target.value })} data-testid="svc-req-form-desc" /></div>
              <div className="md:col-span-2"><Label className="text-xs">Scope of Work</Label><Textarea rows={3} value={editing.scope_of_work} onChange={(e) => setEditing({ ...editing, scope_of_work: e.target.value })} data-testid="svc-req-form-scope" /></div>
              <div className="md:col-span-2"><Label className="text-xs">Remarks</Label><Textarea rows={2} value={editing.remarks} onChange={(e) => setEditing({ ...editing, remarks: e.target.value })} data-testid="svc-req-form-remarks" /></div>
              <p className="md:col-span-2 text-[11px] text-muted-foreground">SR number is auto-generated (SVC-YYYY-####). Attach supporting documents from the paperclip after saving.</p>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setEditing(null)} data-testid="svc-req-form-cancel">Cancel</Button>
            <Button variant="secondary" disabled={busy} onClick={() => save(false)} data-testid="svc-req-form-save-draft">Save as Draft</Button>
            <Button disabled={busy} onClick={() => save(true)} data-testid="svc-req-form-submit">Submit for Approval</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_requests" parentId={docsFor?.id} recordTitle={docsFor?.sr_no} testidPrefix="svc-req-attach" />
    </div>
  );
}
