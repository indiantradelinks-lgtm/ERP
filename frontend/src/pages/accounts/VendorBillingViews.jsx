/**
 * Vendor Billing & Payables Views · Phase 3
 * ==========================================
 * Sub-views rendered inside the Accounts module shell.
 * Endpoints under `/api/payables/*`.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, RefreshCcw, CheckCircle2, X, AlertCircle, Shield, ShieldOff, Pencil, FileDown, History, Truck } from "lucide-react";
import DirectBookingDialog from "@/components/DirectBookingDialog";
import { fmt } from "./AccountsViews";
import { ProjectSelect } from "@/components/MasterSelect";

const STATUS_COLORS = {
  draft: "bg-slate-100 text-slate-700",
  dept_approved: "bg-indigo-100 text-indigo-800",
  accounts_approved: "bg-blue-100 text-blue-800",
  admin_approved: "bg-teal-100 text-teal-800",
  verified_l1: "bg-indigo-100 text-indigo-800",
  verified: "bg-blue-100 text-blue-800",
  approved_l1: "bg-teal-100 text-teal-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-rose-100 text-rose-800",
  partially_paid: "bg-amber-100 text-amber-800",
  paid: "bg-green-100 text-green-800",
  posted: "bg-cyan-100 text-cyan-800",
  cancelled: "bg-rose-100 text-rose-800",
};

const TDS_RATES = { "194C": 2, "194J": 10, "194I": 10, "194H": 2, "194Q": 0.1, "194A": 10, "195": 20 };

const gstinToPan = (g) => {
  const s = (g || "").trim().toUpperCase();
  return s.length >= 12 ? s.slice(2, 12) : "";
};

const PRIORITY_COLORS = {
  high: "bg-rose-100 text-rose-800",
  normal: "bg-slate-100 text-slate-700",
  low: "bg-slate-100 text-slate-500",
  hold: "bg-amber-100 text-amber-800",
};

const EXPENSE_CATS = [
  "material", "labour", "subcontract", "tools", "fuel", "vehicle", "loading",
  "site", "accommodation", "safety", "office", "rent", "professional",
  "bank_charges", "repair", "misc", "inventory", "project_material",
];

const dueBadge = (r) => {
  if (!r.due_date) return <span className="text-slate-400">—</span>;
  const payable = ["approved", "partially_paid"].includes(r.status) && Number(r.outstanding) > 0;
  if (!payable) return <span className="text-slate-400 font-mono text-[11px]">{r.due_date}</span>;
  const days = Math.ceil((new Date(r.due_date) - new Date(new Date().toDateString())) / 86400000);
  if (days < 0) return <span className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-rose-100 text-rose-700 font-semibold whitespace-nowrap" data-testid={`vb-due-${r.bill_no}`}>{-days}d OVERDUE</span>;
  if (days <= 7) return <span className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-700 font-semibold whitespace-nowrap" data-testid={`vb-due-${r.bill_no}`}>due in {days}d</span>;
  return <span className="text-slate-500 font-mono text-[11px]" data-testid={`vb-due-${r.bill_no}`}>{r.due_date}</span>;
};

function Field({ label, children, className = "" }) {
  return (
    <div className={className}>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      {children}
    </div>
  );
}

/* ═══════════════════ Vendor Bills ═══════════════════ */
export function VendorBillsView() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ status: "", payment_priority: "" });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(newFormState());
  const [pendingGrns, setPendingGrns] = useState([]);
  const [poTerms, setPoTerms] = useState(null);
  const [editId, setEditId] = useState(null);
  const [directOpen, setDirectOpen] = useState(false);

  function newFormState() {
    return {
      vendor_name: "", vendor_gstin: "", vendor_pan: "", msme_status: "",
      bank_verified: false, po_number: "", grn_number: "", service_confirmation_no: "",
      project_code: "", invoice_no: "",
      invoice_date: new Date().toISOString().slice(0, 10),
      invoice_received_date: new Date().toISOString().slice(0, 10),
      expense_category: "material", is_inventory: false,
      lines: [{ description: "", quantity: 1, unit: "Nos", rate: 0, gst_pct: null }],
      gst_rate: 18, is_intra_state: true,
      tds_section: "", tds_rate: 0, advance_adjusted: 0, retention_amount: 0,
      due_days: 30, payment_priority: "normal",
      attachments: [], force_no_po: false, force_no_grn: false, notes: "",
    };
  }

  const load = () => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v));
    api.get(`/payables/vendor-bills?${params}`).then(r => setRows(r.data || []));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filter.status, filter.payment_priority]);

  useEffect(() => {
    if (open) api.get("/payables/reports/grn-pending-invoice").then(r => setPendingGrns(r.data?.rows || [])).catch(() => {});
  }, [open]);

  const fetchFromGrn = async (grnNo) => {
    if (!grnNo) { toast.error("Enter / select a GRN number first"); return; }
    try {
      const { data } = await api.get(`/payables/grn-prefill?grn_number=${encodeURIComponent(grnNo)}`);
      setForm(f => ({
        ...f,
        vendor_id: data.vendor_id || null,
        vendor_name: data.vendor_name || f.vendor_name,
        vendor_gstin: data.vendor_gstin || "",
        vendor_pan: data.vendor_pan || "",
        msme_status: data.msme_status || "",
        bank_verified: !!data.bank_verified,
        po_number: data.po_number || "",
        po_id: data.po_id || null,
        grn_number: grnNo,
        grn_id: data.grn_id || null,
        project_code: data.project_code || f.project_code,
        project_id: data.project_id || null,
        due_days: data.due_days || f.due_days,
        lines: data.lines?.length ? data.lines : f.lines,
      }));
      setPoTerms(data);
      toast.success(`Fetched vendor, ${data.lines?.length || 0} line(s) @ PO rates & item-wise GST from ${data.po_number || "PO"}`);
    } catch (e) { toast.error(e.response?.data?.detail || "GRN not found"); }
  };

  // Cross-tab prefill: "Create Bill" from GRN Pending Invoice view
  useEffect(() => {
    const g = sessionStorage.getItem("vb_prefill_grn");
    if (g) {
      sessionStorage.removeItem("vb_prefill_grn");
      setForm(newFormState());
      setOpen(true);
      setTimeout(() => fetchFromGrn(g), 400);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totals = useMemo(() => {
    const taxable = form.lines.reduce((a, l) => a + Number(l.quantity || 0) * Number(l.rate || 0), 0);
    const gst = form.lines.reduce((a, l) => {
      const amt = Number(l.quantity || 0) * Number(l.rate || 0);
      const pct = l.gst_pct !== null && l.gst_pct !== undefined && l.gst_pct !== "" ? Number(l.gst_pct) : Number(form.gst_rate || 0);
      return a + amt * pct / 100;
    }, 0);
    const gross = taxable + gst;
    const tds = taxable * (form.tds_rate || 0) / 100;
    const net = gross - tds - Number(form.advance_adjusted || 0) - Number(form.retention_amount || 0);
    return { taxable, gst, gross, tds, net };
  }, [form.lines, form.gst_rate, form.tds_rate, form.advance_adjusted, form.retention_amount]);

  const submit = async () => {
    if (!form.vendor_name) { toast.error("Vendor name required"); return; }
    if (!form.invoice_no) { toast.error("Vendor invoice # required"); return; }
    if (!form.po_number && !form.force_no_po && !form.service_confirmation_no) {
      toast.error("PO required (or tick 'No PO – override')"); return;
    }
    if (!form.grn_number && !form.force_no_grn && !form.service_confirmation_no) {
      toast.error("GRN required (or tick 'No GRN – override' / supply Service Confirmation #)"); return;
    }
    try {
      const body = { ...form, po_terms: poTerms?.po_terms?.length ? poTerms.po_terms : null, payment_terms: poTerms?.payment_terms || null, attachments: form.attachments?.length ? form.attachments : [{ name: "manual-entry" }] };
      if (editId) {
        await api.put(`/payables/vendor-bills/${editId}`, body);
        toast.success("Vendor bill updated — back to Draft for re-verification");
      } else {
        await api.post("/payables/vendor-bills", body);
        toast.success("Vendor bill created");
      }
      setOpen(false); setEditId(null); setForm(newFormState()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const approve = async (r) => {
    const wf3 = r.workflow_version === 3;
    const wf2 = r.workflow_version === 2;
    const finalStep = wf3 ? r.status === "admin_approved" : wf2 ? r.status === "approved_l1" : true;
    const stageLabel = wf3
      ? { draft: "Department Approval", dept_approved: "Accounts Approval", accounts_approved: "Admin Approval", admin_approved: "Final Approval" }[r.status]
      : null;
    const msg = finalStep
      ? `Final approve ${r.bill_no}? This posts the JE, locks the bill and schedules payment after ${r.due_days || 30} due days.`
      : `${stageLabel || "Approve"} for ${r.bill_no}?`;
    if (!window.confirm(msg)) return;
    try {
      const { data } = await api.post(`/payables/vendor-bills/${r.id}/approve`);
      toast.success(data.status === "approved"
        ? `Approved + JE posted — payment eligible from ${data.payment_release_date || data.due_date}`
        : `${stageLabel || "Approval"} recorded`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const verify = async (r) => {
    try {
      const { data } = await api.post(`/payables/vendor-bills/${r.id}/verify`);
      toast.success(data.status === "verified_l1" ? "Verification Level 1 recorded" : "Verified (Level 2)");
      load();
    }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const reject = async (r) => {
    const reason = window.prompt(`Reject ${r.bill_no} — enter reason:`);
    if (reason === null) return;
    try {
      await api.post(`/payables/vendor-bills/${r.id}/reject`, { reason });
      toast.success("Bill rejected"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const openEdit = (r) => {
    setEditId(r.id);
    setForm({
      ...newFormState(),
      vendor_id: r.vendor_id || null, vendor_name: r.vendor_name || "",
      vendor_gstin: r.vendor_gstin || "", vendor_pan: r.vendor_pan || "",
      msme_status: r.msme_status || "", bank_verified: !!r.bank_verified,
      invoice_no: r.invoice_no || "", invoice_date: r.invoice_date || "",
      invoice_received_date: r.invoice_received_date || "",
      po_number: r.po_number || "", po_id: r.po_id || null,
      grn_number: r.grn_number || "", grn_id: r.grn_id || null,
      service_confirmation_no: r.service_confirmation_no || "",
      project_code: r.project_code || "", project_id: r.project_id || null,
      due_days: r.due_days || 30, expense_category: r.expense_category || newFormState().expense_category,
      lines: r.lines?.length ? r.lines.map(l => ({ ...l })) : newFormState().lines,
      gst_rate: r.gst_rate ?? 18, is_intra_state: r.is_intra_state ?? true,
      tds_section: r.tds_section || "", tds_rate: r.tds_rate || 0,
      advance_adjusted: r.advance_adjusted || 0, retention_amount: r.retention_amount || 0,
      payment_priority: r.payment_priority || "normal", notes: r.notes || "",
      attachments: r.attachments || [],
    });
    setOpen(true);
  };

  const paymentControl = async (r, action) => {
    let payload = { action };
    if (action === "set_due_days") {
      const dd = window.prompt(`New Due Days for ${r.bill_no} (counted from approval date ${(r.approved_at || "").slice(0, 10)}):`, r.due_days || 30);
      if (dd === null) return;
      payload.due_days = Number(dd);
    }
    const remarks = window.prompt(`Remarks for ${action.replace("_", " ")} of ${r.bill_no} (recorded in audit trail):`, "");
    if (remarks === null) return;
    payload.remarks = remarks;
    try {
      const { data } = await api.post(`/payables/vendor-bills/${r.id}/payment-control`, payload);
      toast.success(action === "hold" ? "Payment held" : action === "release" ? "Hold released" : `Due date → ${data.payment_release_date}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const downloadBillPdf = async (r) => {
    try {
      const res = await api.get(`/payables/vendor-bills/${r.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${r.bill_no}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("PDF download failed"); }
  };

  const downloadReport = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.status) params.set("status", filter.status);
      if (filter.payment_priority) params.set("payment_priority", filter.payment_priority);
      const res = await api.get(`/payables/vendor-bills/report/pdf?${params.toString()}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = "vendor-bills-report.pdf"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Report download failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Vendor Bills <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={filter.status} onChange={e => setFilter({ ...filter, status: e.target.value })}>
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="dept_approved">Dept Approved</option>
            <option value="accounts_approved">Accounts Approved</option>
            <option value="admin_approved">Admin Approved</option>
            <option value="approved">Approved</option><option value="rejected">Rejected</option>
            <option value="partially_paid">Partially Paid</option>
            <option value="paid">Paid</option><option value="cancelled">Cancelled</option>
          </select>
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={filter.payment_priority} onChange={e => setFilter({ ...filter, payment_priority: e.target.value })}>
            <option value="">All priorities</option>
            <option value="high">High</option><option value="normal">Normal</option>
            <option value="low">Low</option><option value="hold">Hold</option>
          </select>
          <Button size="sm" variant="outline" onClick={downloadReport} data-testid="pay-vb-report-pdf"><FileDown className="h-3.5 w-3.5 mr-1" />PDF Report</Button>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" onClick={() => setDirectOpen(true)} data-testid="pay-vb-direct" title="Book historical / pre-ERP cost directly to a project"><History className="h-3.5 w-3.5 mr-1" />Direct Booking</Button>
          <Button size="sm" onClick={() => setOpen(true)} data-testid="pay-vb-add"><Plus className="h-3.5 w-3.5 mr-1" />New Bill</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Bill #</th>
                <th className="text-left px-3 py-2">Vendor Inv #</th>
                <th className="text-left px-3 py-2">Date</th>
                <th className="text-left px-3 py-2">Vendor</th>
                <th className="text-left px-3 py-2">PO/GRN</th>
                <th className="text-right px-3 py-2">Gross</th>
                <th className="text-right px-3 py-2">Outstanding</th>
                <th className="text-left px-3 py-2">Due</th>
                <th className="text-center px-3 py-2">Priority</th>
                <th className="text-center px-3 py-2">Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`pay-vb-row-${r.bill_no}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.bill_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_date}</td>
                  <td className="px-3 py-1.5">
                    {r.vendor_name}
                    {r.source === "logistics_vendor_bill"
                      ? <span className="inline-flex items-center gap-0.5 ml-1 px-1 py-0.5 rounded text-[9px] font-bold uppercase bg-orange-100 text-orange-700" title={`Auto-booked from ${r.source_no} (Logistics)`} data-testid={`pay-vb-transport-${r.bill_no}`}><Truck className="h-2.5 w-2.5" />Transport</span>
                      : r.bill_type === "direct_booking"
                        ? <span className="inline-block ml-1 px-1 py-0.5 rounded text-[9px] font-bold uppercase bg-violet-100 text-violet-700" title="Direct cost booking — pre-ERP historical expense" data-testid={`pay-vb-historical-${r.bill_no}`}>Historical</span>
                        : r.bank_verified
                          ? <Shield className="inline h-3 w-3 ml-1 text-emerald-700" title="Bank verified" />
                          : <ShieldOff className="inline h-3 w-3 ml-1 text-rose-700" title="Bank NOT verified" />}
                  </td>
                  <td className="px-3 py-1.5 text-xs">
                    {r.po_number || "—"}{r.grn_number ? ` / ${r.grn_number}` : ""}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.totals?.gross)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.outstanding)}</td>
                  <td className="px-3 py-1.5">{dueBadge(r)}</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${PRIORITY_COLORS[r.payment_priority] || ""}`}>{r.payment_priority}</span></td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[r.status] || ""}`}>{r.status}</span></td>
                  <td className="px-3 py-1.5 text-right whitespace-nowrap">
                    {(() => {
                      if (r.source === "logistics_vendor_bill") {
                        return <span className="text-[10px] text-slate-500" title="Managed in Logistics → Transport Vendor Bills">via {r.source_no || "Logistics"}</span>;
                      }
                      if (r.bill_type === "direct_booking") {
                        return <span className="text-[10px] text-slate-500" title="Historical booking — already settled pre-ERP">booked to {r.project_code || "project"}</span>;
                      }
                      const wf3 = r.workflow_version === 3;
                      const wf2 = r.workflow_version === 2;
                      const canReject = ["draft", "dept_approved", "accounts_approved", "admin_approved", "verified_l1", "verified", "approved_l1"].includes(r.status);
                      const canEdit = ["draft", "rejected"].includes(r.status);
                      const verifyLabel = wf2 ? (r.status === "draft" ? "Verify L1" : r.status === "verified_l1" ? "Verify L2" : null) : null;
                      const approveLabel = wf3
                        ? ({ draft: "Dept Approve", dept_approved: "Accounts Approve", accounts_approved: "Admin Approve", admin_approved: "Final Approve" }[r.status] || null)
                        : wf2
                          ? (r.status === "verified" ? "Approve L1" : r.status === "approved_l1" ? "Final Approve" : null)
                          : (["draft", "verified"].includes(r.status) ? "Approve" : null);
                      const controllable = ["approved", "partially_paid"].includes(r.status);
                      return (
                        <>
                          {canEdit && <Button size="sm" variant="ghost" onClick={() => openEdit(r)} data-testid={`pay-vb-edit-${r.bill_no}`}><Pencil className="h-3 w-3 mr-1" />Edit</Button>}
                          {verifyLabel && <Button size="sm" variant="outline" onClick={() => verify(r)} data-testid={`pay-vb-verify-${r.bill_no}`} className="ml-1"><CheckCircle2 className="h-3 w-3 mr-1" />{verifyLabel}</Button>}
                          {approveLabel && <Button size="sm" onClick={() => approve(r)} data-testid={`pay-vb-approve-${r.bill_no}`} className="ml-1"><CheckCircle2 className="h-3 w-3 mr-1" />{approveLabel}</Button>}
                          {canReject && <Button size="sm" variant="ghost" className="ml-1 text-rose-600" onClick={() => reject(r)} data-testid={`pay-vb-reject-${r.bill_no}`}><X className="h-3 w-3 mr-1" />Reject</Button>}
                          {controllable && (r.payment_hold
                            ? <Button size="sm" variant="outline" className="ml-1 border-emerald-300 text-emerald-700" onClick={() => paymentControl(r, "release")} data-testid={`pay-vb-release-${r.bill_no}`}>Release</Button>
                            : <Button size="sm" variant="outline" className="ml-1 border-rose-300 text-rose-700" onClick={() => paymentControl(r, "hold")} data-testid={`pay-vb-hold-${r.bill_no}`}>Hold</Button>)}
                          {controllable && <Button size="sm" variant="ghost" className="ml-1" onClick={() => paymentControl(r, "set_due_days")} data-testid={`pay-vb-duedays-${r.bill_no}`} title="Change due days (from approval date)">Due±</Button>}
                          <Button size="sm" variant="ghost" className="ml-1" onClick={() => downloadBillPdf(r)} data-testid={`pay-vb-pdf-${r.bill_no}`} title="Bill PDF"><FileDown className="h-3 w-3" /></Button>
                          {r.payment_hold && <span className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-rose-100 text-rose-700 font-semibold ml-1">HELD</span>}
                          {(wf2 || wf3) && r.status === "approved" && r.payment_release_date && !r.payment_hold && (
                            <span className="text-[10px] text-slate-500 ml-1" title="Eligible for Payment Processing from this date">Pay from {r.payment_release_date}</span>
                          )}
                        </>
                      );
                    })()}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={11} className="text-center py-6 text-xs text-slate-400">No bills.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
      {directOpen && <DirectBookingDialog onClose={(saved) => { setDirectOpen(false); if (saved) load(); }} />}

      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setPoTerms(null); setEditId(null); setForm(newFormState()); } }}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editId ? "Edit Vendor Bill" : "New Vendor Bill"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-4 gap-2">
            <Field label="Vendor *"><Input value={form.vendor_name} onChange={e => setForm({ ...form, vendor_name: e.target.value })} data-testid="pay-vb-vendor" /></Field>
            <Field label="GSTIN"><Input value={form.vendor_gstin} onChange={e => {
              const v = e.target.value.toUpperCase();
              setForm({ ...form, vendor_gstin: v, vendor_pan: gstinToPan(v) || form.vendor_pan });
            }} data-testid="pay-vb-gstin" /></Field>
            <Field label="PAN"><Input value={form.vendor_pan} onChange={e => setForm({ ...form, vendor_pan: e.target.value })} /></Field>
            <Field label="MSME">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.msme_status} onChange={e => setForm({ ...form, msme_status: e.target.value })}>
                <option value="">—</option><option value="micro">Micro</option><option value="small">Small</option><option value="medium">Medium</option>
              </select>
            </Field>
            <Field label="Bank Verified">
              <label className="flex items-center gap-2 h-9 text-xs"><input type="checkbox" checked={form.bank_verified} onChange={e => setForm({ ...form, bank_verified: e.target.checked })} data-testid="pay-vb-bank-verified" /> Bank details verified</label>
            </Field>
            <Field label="Vendor Inv # *"><Input value={form.invoice_no} onChange={e => setForm({ ...form, invoice_no: e.target.value })} data-testid="pay-vb-invoice-no" /></Field>
            <Field label="Invoice Date *"><Input type="date" value={form.invoice_date} onChange={e => setForm({ ...form, invoice_date: e.target.value })} /></Field>
            <Field label="Received Date"><Input type="date" value={form.invoice_received_date} onChange={e => setForm({ ...form, invoice_received_date: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-4 gap-2 mt-2">
            <Field label="PO Number"><Input value={form.po_number} onChange={e => setForm({ ...form, po_number: e.target.value })} data-testid="pay-vb-po" /></Field>
            <Field label="GRN Number">
              <div className="flex gap-1">
                <Input list="vb-pending-grns" value={form.grn_number} onChange={e => setForm({ ...form, grn_number: e.target.value })} data-testid="pay-vb-grn" placeholder="Select accepted GRN…" />
                <Button size="sm" variant="outline" className="h-9 px-2 shrink-0" onClick={() => fetchFromGrn(form.grn_number)} data-testid="pay-vb-fetch-grn" title="Auto-fetch vendor, PO rates, GST/PAN/bank & terms">
                  <RefreshCcw className="h-3.5 w-3.5" />
                </Button>
                <datalist id="vb-pending-grns">
                  {pendingGrns.map(g => <option key={g.grn_number} value={g.grn_number} label={`${g.po_number || ""} · ${g.vendor_name || ""}`} />)}
                </datalist>
              </div>
            </Field>
            <Field label="Service Conf #"><Input value={form.service_confirmation_no} onChange={e => setForm({ ...form, service_confirmation_no: e.target.value })} /></Field>
            <Field label="Project Code"><ProjectSelect value={form.project_code} valueKey="code" label={null} testid={null} onChange={(v) => setForm({ ...form, project_code: v })} /></Field>
            <Field label="Expense Category">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.expense_category} onChange={e => setForm({ ...form, expense_category: e.target.value })}>
                {EXPENSE_CATS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Force-Override">
              <div className="flex gap-2 h-9 items-center">
                <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={form.force_no_po} onChange={e => setForm({ ...form, force_no_po: e.target.checked })} /> No PO</label>
                <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={form.force_no_grn} onChange={e => setForm({ ...form, force_no_grn: e.target.checked })} /> No GRN</label>
              </div>
            </Field>
            <Field label="Priority">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.payment_priority} onChange={e => setForm({ ...form, payment_priority: e.target.value })}>
                <option value="high">High</option><option value="normal">Normal</option>
                <option value="low">Low</option><option value="hold">Hold</option>
              </select>
            </Field>
            <Field label="Due Days"><Input type="number" value={form.due_days} onChange={e => setForm({ ...form, due_days: Number(e.target.value) })} /></Field>
          </div>

          {poTerms && (poTerms.po_terms?.length > 0 || poTerms.po_terms_text || poTerms.payment_terms || poTerms.delivery_days) && (
            <div className="border border-amber-200 bg-amber-50 rounded-md p-3 mt-2" data-testid="pay-vb-po-terms">
              <div className="text-[10px] uppercase tracking-wider font-semibold text-amber-800 mb-1">PO Terms & Conditions — {poTerms.po_number || "PO"} (auto-fetched, actions against PO terms)</div>
              <div className="grid grid-cols-3 gap-2 text-xs text-amber-900 mb-1">
                <div><b>PO Payment Terms:</b> {poTerms.payment_terms || "—"}</div>
                <div><b>Delivery:</b> {poTerms.delivery_days ? `${poTerms.delivery_days} days` : "—"}</div>
                <div><b>Due Days Applied:</b> {form.due_days}</div>
              </div>
              {poTerms.po_terms?.length > 0 ? (
                <ul className="text-xs text-amber-900 space-y-0.5 list-disc pl-4">
                  {poTerms.po_terms.map((t, i) => <li key={i}><b>{t.title}</b> <span className="uppercase text-[9px]">[{t.category}]</span> — {t.body}</li>)}
                </ul>
              ) : poTerms.po_terms_text ? (
                <div className="text-xs text-amber-900 whitespace-pre-wrap">{poTerms.po_terms_text}</div>
              ) : null}
            </div>
          )}

          <div className="mt-3">
            <Label className="text-[10px] uppercase tracking-wider mb-1 block">Lines</Label>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-2 py-1">Description</th><th className="text-right px-2 py-1">Qty</th><th className="text-left px-2 py-1">Unit</th><th className="text-right px-2 py-1">Rate</th><th className="text-right px-2 py-1">Amount</th><th className="text-right px-2 py-1">GST %</th><th className="text-right px-2 py-1">GST Amt</th><th></th></tr></thead>
                <tbody>
                  {form.lines.map((ln, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1"><Input value={ln.description} onChange={e => { const lines = [...form.lines]; lines[i].description = e.target.value; setForm({ ...form, lines }); }} className="h-8" data-testid={`pay-vb-line-${i}-desc`} /></td>
                      <td className="px-2 py-1"><Input type="number" value={ln.quantity} onChange={e => { const lines = [...form.lines]; lines[i].quantity = Number(e.target.value); setForm({ ...form, lines }); }} className="h-8 text-right w-20" data-testid={`pay-vb-line-${i}-qty`} /></td>
                      <td className="px-2 py-1"><Input value={ln.unit} onChange={e => { const lines = [...form.lines]; lines[i].unit = e.target.value; setForm({ ...form, lines }); }} className="h-8 w-20" /></td>
                      <td className="px-2 py-1"><Input type="number" value={ln.rate} onChange={e => { const lines = [...form.lines]; lines[i].rate = Number(e.target.value); setForm({ ...form, lines }); }} className="h-8 text-right" data-testid={`pay-vb-line-${i}-rate`} /></td>
                      <td className="px-2 py-1 text-right tabular-nums" data-testid={`pay-vb-line-${i}-amount`}>{fmt(Number(ln.quantity || 0) * Number(ln.rate || 0))}</td>
                      <td className="px-2 py-1"><Input type="number" value={ln.gst_pct ?? ""} placeholder={String(form.gst_rate)} onChange={e => { const lines = [...form.lines]; lines[i].gst_pct = e.target.value === "" ? null : Number(e.target.value); setForm({ ...form, lines }); }} className="h-8 text-right w-16" data-testid={`pay-vb-line-${i}-gst-pct`} /></td>
                      <td className="px-2 py-1 text-right tabular-nums text-slate-600" data-testid={`pay-vb-line-${i}-gst-amt`}>{fmt(Number(ln.quantity || 0) * Number(ln.rate || 0) * ((ln.gst_pct ?? form.gst_rate) || 0) / 100)}</td>
                      <td><Button size="sm" variant="ghost" onClick={() => setForm({ ...form, lines: form.lines.filter((_, x) => x !== i) })}><X className="h-3 w-3" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button variant="outline" size="sm" className="mt-2" onClick={() => setForm({ ...form, lines: [...form.lines, { description: "", quantity: 1, unit: "Nos", rate: 0, gst_pct: null }] })}>+ Line</Button>
          </div>

          <div className="grid grid-cols-4 gap-2 mt-3">
            <Field label="Default GST % (lines w/o PO GST)"><Input type="number" value={form.gst_rate} onChange={e => setForm({ ...form, gst_rate: Number(e.target.value) })} /></Field>
            <Field label="Tax Type">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.is_intra_state ? "intra" : "inter"} onChange={e => setForm({ ...form, is_intra_state: e.target.value === "intra" })}>
                <option value="intra">Intra-state</option><option value="inter">Inter-state</option>
              </select>
            </Field>
            <Field label="TDS Section">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.tds_section}
                onChange={e => {
                  const sec = e.target.value;
                  setForm({ ...form, tds_section: sec, tds_rate: TDS_RATES[sec] ?? (sec ? form.tds_rate : 0) });
                }} data-testid="pay-vb-tds-section">
                <option value="">—</option>
                {Object.entries(TDS_RATES).map(([s, r]) => <option key={s} value={s}>{s} ({r}%)</option>)}
              </select>
            </Field>
            <Field label="TDS %"><Input type="number" value={form.tds_rate} onChange={e => setForm({ ...form, tds_rate: Number(e.target.value) })} /></Field>
            <Field label="Advance Adjusted"><Input type="number" value={form.advance_adjusted} onChange={e => setForm({ ...form, advance_adjusted: Number(e.target.value) })} /></Field>
            <Field label="Retention Withheld"><Input type="number" value={form.retention_amount} onChange={e => setForm({ ...form, retention_amount: Number(e.target.value) })} /></Field>
          </div>

          <div className="border rounded-md p-3 bg-slate-50 mt-3">
            <div className="grid grid-cols-5 gap-2 text-sm">
              <div><div className="text-[10px] uppercase text-slate-500">Taxable</div><div className="font-semibold tabular-nums">{fmt(totals.taxable)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">GST (line-wise)</div><div className="font-semibold tabular-nums">{fmt(totals.gst)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">Gross</div><div className="font-semibold tabular-nums text-blue-700">{fmt(totals.gross)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">TDS</div><div className="font-semibold tabular-nums text-rose-700">−{fmt(totals.tds)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">Net Payable</div><div className="font-bold tabular-nums text-emerald-700">{fmt(totals.net)}</div></div>
            </div>
          </div>
          {!form.bank_verified && (
            <div className="text-xs text-rose-700 flex items-center gap-1 mt-2"><AlertCircle className="h-3 w-3" />Bank details NOT verified — payment will be blocked until verified.</div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} data-testid="pay-vb-save">Create Draft</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════ Vendor Payments ═══════════════════ */
export function VendorPaymentsView() {
  const [rows, setRows] = useState([]);
  const [bills, setBills] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(newFormState());

  function newFormState() {
    return {
      payment_date: new Date().toISOString().slice(0, 10),
      vendor_name: "", bill_ids: [], mode: "Bank", bank_account: "",
      utr: "", cheque_no: "", amount: 0, retention_held: 0, other_deduction: 0,
      remarks: "", excess_reason: "",
    };
  }

  const load = () => api.get("/payables/vendor-payments").then(r => setRows(r.data || []));
  const loadBills = () => api.get("/payables/vendor-bills?status=approved").then(r => setBills(r.data || []));
  useEffect(() => { load(); }, []);

  const openCreate = () => { loadBills(); setForm(newFormState()); setOpen(true); };
  const totalSet = Number(form.amount || 0) + Number(form.retention_held || 0) + Number(form.other_deduction || 0);
  const eligible = bills.filter(b => !form.vendor_name || b.vendor_name === form.vendor_name);

  const submit = async () => {
    if (!form.vendor_name) { toast.error("Vendor required"); return; }
    try {
      await api.post("/payables/vendor-payments", form);
      toast.success("Payment posted + JE created"); setOpen(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Vendor Payments <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={openCreate} data-testid="pay-vpay-add"><Plus className="h-3.5 w-3.5 mr-1" />New Payment</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Payment #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Vendor</th><th className="text-left px-3 py-2">Mode</th><th className="text-left px-3 py-2">UTR</th><th className="text-right px-3 py-2">Amount</th><th className="text-right px-3 py-2">Retn</th><th className="text-right px-3 py-2">Settled</th><th className="text-left px-3 py-2">JE</th></tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`pay-vpay-row-${r.payment_no}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.payment_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.payment_date}</td>
                  <td className="px-3 py-1.5">{r.vendor_name}</td>
                  <td className="px-3 py-1.5 text-xs">{r.mode}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.utr || r.cheque_no || "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.amount)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.retention_held)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.total_settled)}</td>
                  <td className="px-3 py-1.5 font-mono text-[10px]">{r.je_voucher_number || "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={9} className="text-center py-6 text-xs text-slate-400">No payments.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>New Vendor Payment</DialogTitle></DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Date *"><Input type="date" value={form.payment_date} onChange={e => setForm({ ...form, payment_date: e.target.value })} /></Field>
            <Field label="Vendor *"><Input value={form.vendor_name} onChange={e => setForm({ ...form, vendor_name: e.target.value })} data-testid="pay-vpay-vendor" /></Field>
            <Field label="Mode *">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.mode} onChange={e => setForm({ ...form, mode: e.target.value })}>
                {["Bank", "Cash", "UPI", "NEFT", "RTGS", "IMPS", "Cheque"].map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Bank Account"><Input value={form.bank_account} onChange={e => setForm({ ...form, bank_account: e.target.value })} /></Field>
            <Field label="UTR / Cheque #"><Input value={form.utr} onChange={e => setForm({ ...form, utr: e.target.value })} /></Field>
          </div>

          {form.vendor_name && eligible.length > 0 && (
            <div className="mt-2">
              <Label className="text-[10px] uppercase tracking-wider mb-1 block">Approved Bills · select to settle</Label>
              <div className="max-h-32 overflow-y-auto border rounded-md text-xs">
                {eligible.map(b => (
                  <label key={b.id} className="flex items-center gap-2 px-2 py-1 hover:bg-slate-50 border-b">
                    <input type="checkbox" checked={form.bill_ids.includes(b.id)} onChange={e => setForm({ ...form, bill_ids: e.target.checked ? [...form.bill_ids, b.id] : form.bill_ids.filter(x => x !== b.id) })} />
                    <span className="font-mono">{b.bill_no}</span>
                    <span className="text-slate-500">{b.invoice_no}</span>
                    {b.bank_verified ? <Shield className="h-3 w-3 text-emerald-700" /> : <ShieldOff className="h-3 w-3 text-rose-700" />}
                    <span className="ml-auto tabular-nums">Outstanding: {fmt(b.outstanding)}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-3 gap-2 mt-2">
            <Field label="Amount Paid *"><Input type="number" value={form.amount} onChange={e => setForm({ ...form, amount: Number(e.target.value) })} data-testid="pay-vpay-amount" /></Field>
            <Field label="Retention Held"><Input type="number" value={form.retention_held} onChange={e => setForm({ ...form, retention_held: Number(e.target.value) })} /></Field>
            <Field label="Other Deduction"><Input type="number" value={form.other_deduction} onChange={e => setForm({ ...form, other_deduction: Number(e.target.value) })} /></Field>
          </div>
          <div className="border rounded-md p-2 bg-slate-50 text-sm mt-2">
            <span className="text-[10px] uppercase text-slate-500">Total Settled:</span>
            <span className="ml-2 font-bold tabular-nums">{fmt(totalSet)}</span>
          </div>
          <Field label="Excess Reason"><Input value={form.excess_reason} onChange={e => setForm({ ...form, excess_reason: e.target.value })} /></Field>
          <Field label="Remarks"><Input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} /></Field>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} data-testid="pay-vpay-save">Post Payment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════ Vendor Outstanding (Payable Aging) ═══════════════════ */
export function VendorOutstandingView() {
  const [data, setData] = useState({ buckets: { "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0 }, total_outstanding: 0, vendors: [] });
  const load = () => api.get("/payables/reports/vendor-outstanding").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Vendor Outstanding · Payable Aging</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-2 mb-4">
          {Object.entries(data.buckets).map(([k, v]) => (
            <div key={k} className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">{k} days</div><div className="text-lg font-bold tabular-nums text-amber-700">{fmt(v)}</div></div>
          ))}
          <div className="p-3 rounded-md border-2 border-slate-400 bg-white"><div className="text-[10px] uppercase text-slate-500">Total Payable</div><div className="text-lg font-bold tabular-nums">{fmt(data.total_outstanding)}</div></div>
        </div>
        <div className="space-y-3">
          {(data.vendors || []).map(v => (
            <div key={v.vendor_name} className="border rounded-md">
              <div className="flex justify-between px-3 py-2 bg-slate-100 font-semibold text-sm"><span>{v.vendor_name}</span><span className="tabular-nums">{fmt(v.total_outstanding)}</span></div>
              <table className="w-full text-sm">
                <thead className="text-xs text-slate-500"><tr><th className="text-left px-3 py-1">Bill #</th><th className="text-left px-3 py-1">Date</th><th className="text-left px-3 py-1">PO/GRN</th><th className="text-right px-3 py-1">Outstanding</th><th className="text-center px-3 py-1">Bucket</th></tr></thead>
                <tbody>
                  {v.bills.map(b => (
                    <tr key={b.bill_no} className="border-t">
                      <td className="px-3 py-1 font-mono text-xs">{b.bill_no}</td>
                      <td className="px-3 py-1 font-mono text-xs">{b.invoice_date}</td>
                      <td className="px-3 py-1 text-xs">{b.po_number || "—"}{b.grn_number ? ` / ${b.grn_number}` : ""}</td>
                      <td className="px-3 py-1 text-right tabular-nums">{fmt(b.outstanding)}</td>
                      <td className="px-3 py-1 text-center text-xs">{b.bucket} · {b.days_overdue}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {data.vendors?.length === 0 && <div className="text-center py-6 text-xs text-slate-400">Nothing payable.</div>}
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ GST Purchase Register ═══════════════════ */
export function GSTPurchaseRegisterView() {
  const [data, setData] = useState({ rows: [], totals: {} });
  const load = () => api.get("/payables/reports/gst-purchase-register").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">GST Purchase Register</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Bill #</th><th className="text-left px-3 py-2">Vendor Inv #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Vendor</th><th className="text-left px-3 py-2">GSTIN</th><th className="text-right px-3 py-2">Taxable</th><th className="text-right px-3 py-2">CGST</th><th className="text-right px-3 py-2">SGST</th><th className="text-right px-3 py-2">IGST</th><th className="text-right px-3 py-2">Gross</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.bill_no} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.bill_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_date}</td>
                  <td className="px-3 py-1.5">{r.vendor_name}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.vendor_gstin || "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.taxable)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.cgst)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.sgst)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.igst)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.gross)}</td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={10} className="text-center py-6 text-xs text-slate-400">No purchases.</td></tr>}
            </tbody>
            <tfoot className="bg-slate-100 font-semibold text-sm">
              <tr>
                <td colSpan={5} className="px-3 py-2 text-right">Totals</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.taxable)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.cgst)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.sgst)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.igst)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.gross)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ TDS Payable ═══════════════════ */
export function TDSPayableView() {
  const [data, setData] = useState({ rows: [], by_section: [], total_tds: 0 });
  const load = () => api.get("/payables/reports/tds-payable").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">TDS Payable <span className="ml-2 text-sm text-slate-500 font-normal">Total: {fmt(data.total_tds)}</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-2 mb-3">
          {(data.by_section || []).map(s => (
            <div key={s.section} className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Section {s.section}</div><div className="text-lg font-bold tabular-nums text-rose-700">{fmt(s.amount)}</div></div>
          ))}
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Bill #</th><th className="text-left px-3 py-2">Vendor Inv #</th><th className="text-left px-3 py-2">Vendor</th><th className="text-left px-3 py-2">Section</th><th className="text-right px-3 py-2">Rate</th><th className="text-right px-3 py-2">Amount</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.bill_no} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.bill_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5">{r.vendor_name}</td>
                  <td className="px-3 py-1.5 text-xs">{r.tds_section || "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{r.tds_rate}%</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.tds_amount)}</td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={6} className="text-center py-6 text-xs text-slate-400">No TDS payable.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Retention Payable ═══════════════════ */
export function RetentionPayableView() {
  const [data, setData] = useState({ vendors: [], total_retention: 0 });
  const load = () => api.get("/payables/reports/retention-payable").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Retention Payable <span className="ml-2 text-sm text-slate-500 font-normal">Total: {fmt(data.total_retention)}</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        {(data.vendors || []).map(v => (
          <div key={v.vendor_name} className="border rounded-md mb-2">
            <div className="flex justify-between px-3 py-2 bg-slate-100 font-semibold text-sm"><span>{v.vendor_name}</span><span className="tabular-nums">{fmt(v.retention_held)}</span></div>
          </div>
        ))}
        {data.vendors?.length === 0 && <div className="text-center py-6 text-xs text-slate-400">No retention withheld yet.</div>}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Payment Due ═══════════════════ */
export function PaymentDueView() {
  const [data, setData] = useState({ rows: [], total_due: 0 });
  const [days, setDays] = useState(7);
  const load = () => api.get(`/payables/reports/payment-due?days_ahead=${days}`).then(r => setData(r.data));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Payment Due <span className="ml-2 text-sm text-slate-500 font-normal">{fmt(data.total_due)} due</span></CardTitle>
        <div className="flex gap-2">
          <Input type="number" value={days} onChange={e => setDays(Number(e.target.value))} className="h-8 w-24" placeholder="Days" />
          <Button size="sm" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Bill #</th><th className="text-left px-3 py-2">Vendor</th><th className="text-left px-3 py-2">Due</th><th className="text-right px-3 py-2">Days</th><th className="text-right px-3 py-2">Outstanding</th><th className="text-center px-3 py-2">Priority</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.bill_no} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.bill_no}</td>
                  <td className="px-3 py-1.5">{r.vendor_name}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.due_date}</td>
                  <td className={`px-3 py-1.5 text-right tabular-nums font-semibold ${r.overdue_days > 30 ? "text-rose-700" : r.overdue_days > 0 ? "text-amber-700" : "text-slate-700"}`}>{r.overdue_days > 0 ? `+${r.overdue_days}d overdue` : `${-r.overdue_days}d remaining`}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.outstanding)}</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${PRIORITY_COLORS[r.payment_priority] || ""}`}>{r.payment_priority}</span></td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={6} className="text-center py-6 text-xs text-slate-400">No payments due.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ GRN Pending Invoice ═══════════════════ */
export function GRNPendingInvoiceView() {
  const [data, setData] = useState({ rows: [], total_value: 0, count: 0 });
  const load = () => api.get("/payables/reports/grn-pending-invoice").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  const createBill = (r) => {
    sessionStorage.setItem("vb_prefill_grn", r.grn_number);
    window.dispatchEvent(new CustomEvent("accounts:set-tab", { detail: "vendor_bills" }));
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">GRN Pending Invoice <span className="ml-2 text-sm text-slate-500 font-normal">{data.count} pending · {fmt(data.total_value)}</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">GRN #</th><th className="text-left px-3 py-2">PO #</th><th className="text-left px-3 py-2">Vendor</th><th className="text-left px-3 py-2">Received</th><th className="text-right px-3 py-2">Value</th><th className="text-right px-3 py-2">Action</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.grn_number} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.grn_number}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.po_number || "—"}</td>
                  <td className="px-3 py-1.5">{r.vendor_name}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.received_at?.slice(0, 10)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.total_accepted)}</td>
                  <td className="px-3 py-1.5 text-right">
                    <Button size="sm" variant="outline" className="h-7" onClick={() => createBill(r)} data-testid={`grn-create-bill-${r.grn_number}`}>
                      <Plus className="h-3 w-3 mr-1" />Create Bill
                    </Button>
                  </td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={6} className="text-center py-6 text-xs text-slate-400">All GRNs invoiced.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
