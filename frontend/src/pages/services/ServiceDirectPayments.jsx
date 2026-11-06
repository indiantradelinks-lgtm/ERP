import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Paperclip, Eye, Banknote, AlertTriangle, History } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import RowAttachments from "@/components/RowAttachments";
import { StatusChip, inr, dt } from "./shared";
import DirectPaymentForm from "./DirectPaymentForm";

const STATUSES = ["", "pending_approval", "payment_pending", "paid", "rejected", "withdrawn"];

export default function ServiceDirectPayments() {
  const [params, setParams] = useSearchParams();
  const [meta, setMeta] = useState({ can_raise: false, can_approve: false, vendors: [] });
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState({ status: "", vendor: "", q: "" });
  const [editing, setEditing] = useState(null);     // null | {} (new) | row
  const [viewing, setViewing] = useState(null);
  const [history, setHistory] = useState([]);
  const [deciding, setDeciding] = useState(null);   // {row, action}
  const [remarks, setRemarks] = useState("");
  const [docsFor, setDocsFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const qs = new URLSearchParams(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))).toString();
    try {
      const [m, r] = await Promise.all([api.get("/service-direct-payments/meta"), api.get(`/service-direct-payments?${qs}`)]);
      setMeta(m.data); setRows(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [filters]);
  useEffect(() => { load(); }, [load]);

  const openDetail = useCallback(async (id) => {
    try {
      const { data } = await api.get(`/service-direct-payments/${id}`);
      setViewing(data);
      const h = await api.get(`/service-direct-payments/vendors/${data.vendor_id}/history`);
      setHistory(h.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, []);

  useEffect(() => {
    if (params.get("new") === "1" && meta.can_raise) { setEditing({}); setParams({}, { replace: true }); }
    const id = params.get("id");
    if (id) { openDetail(id); setParams({}, { replace: true }); }
  }, [params, meta.can_raise, openDetail, setParams]);

  const decide = async () => {
    if (!deciding) return;
    if (deciding.action === "reject" && !remarks.trim()) { toast.error("Remarks are required to reject"); return; }
    setBusy(true);
    try {
      await api.post(`/service-direct-payments/${deciding.row.id}/action`, { action: deciding.action, remarks });
      toast.success(`${deciding.row.dp_no} ${deciding.action === "approve" ? "approved — sent to Payment Processing" : deciding.action === "reject" ? "rejected" : "withdrawn"}`);
      setDeciding(null); setRemarks(""); setViewing(null); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const totals = useMemo(() => ({
    open: rows.filter((r) => r.status === "pending_approval").length,
    queue: rows.filter((r) => r.status === "payment_pending").length,
    paid: rows.filter((r) => r.status === "paid").reduce((s, r) => s + Number(r.payment_amount || 0), 0),
  }), [rows]);

  return (
    <div className="p-4 md:p-6 space-y-4" data-testid="svc-direct-payments-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Banknote className="h-5 w-5" /> Direct Payments</h1>
          <p className="text-xs text-muted-foreground">Repeat payments to vendors already paid through the Service workflow — no new SR / RFQ / PO / SRN. Every request needs <b>Super Admin approval</b> and then moves to the Payment Processing Center automatically.</p>
        </div>
        {meta.can_raise && <Button onClick={() => setEditing({})} data-testid="svc-dp-new-btn"><Plus className="h-4 w-4 mr-1" /> New Direct Payment</Button>}
      </div>

      <div className="grid grid-cols-3 gap-3 max-w-xl text-sm">
        <div className="border rounded-md bg-white p-3" data-testid="svc-dp-tile-open"><div className="text-[10px] uppercase text-muted-foreground">Awaiting approval</div><div className="text-2xl font-bold">{totals.open}</div></div>
        <div className="border rounded-md bg-white p-3" data-testid="svc-dp-tile-queue"><div className="text-[10px] uppercase text-muted-foreground">In payment queue</div><div className="text-2xl font-bold">{totals.queue}</div></div>
        <div className="border rounded-md bg-white p-3" data-testid="svc-dp-tile-paid"><div className="text-[10px] uppercase text-muted-foreground">Paid (listed)</div><div className="text-2xl font-bold">{inr(totals.paid)}</div></div>
      </div>

      <div className="flex flex-wrap gap-3 items-end">
        <div><Label className="text-[10px] uppercase">Status</Label>
          <select className="h-9 border rounded-sm px-2 text-sm block" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} data-testid="svc-dp-filter-status">
            {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, " ") : "All"}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase">Vendor</Label>
          <select className="h-9 border rounded-sm px-2 text-sm block min-w-[220px]" value={filters.vendor} onChange={(e) => setFilters({ ...filters, vendor: e.target.value })} data-testid="svc-dp-filter-vendor">
            <option value="">All</option>{meta.vendors.map((v) => <option key={v.id} value={v.id}>{v.name}{v.code ? ` (${v.code})` : v.gst ? ` · ${v.gst}` : ""}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase">Search</Label>
          <Input className="h-9 w-64" placeholder="DP no / invoice / PO / period" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} data-testid="svc-dp-filter-q" /></div>
      </div>

      <div className="border rounded-md bg-white overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>DP No</TableHead><TableHead>Date</TableHead><TableHead>Vendor</TableHead><TableHead>Period</TableHead>
            <TableHead>Vendor Inv</TableHead><TableHead>Ref PO</TableHead><TableHead className="text-right">Net</TableHead>
            <TableHead className="text-right">Payment</TableHead><TableHead>Status</TableHead><TableHead>Raised by</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={11} className="text-center text-sm text-muted-foreground py-8" data-testid="svc-dp-empty">No Direct Payment requests yet.</TableCell></TableRow>}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`svc-dp-row-${r.id}`}>
                <TableCell className="font-medium text-primary cursor-pointer" onClick={() => openDetail(r.id)}>{r.dp_no}</TableCell>
                <TableCell>{dt(r.created_at)}</TableCell>
                <TableCell>{r.vendor_name}</TableCell>
                <TableCell>{r.service_period || "—"}</TableCell>
                <TableCell>{r.vendor_invoice_no || "—"}</TableCell>
                <TableCell>{r.ref_po_no || "—"}</TableCell>
                <TableCell className="text-right">{inr(r.net_payable)}</TableCell>
                <TableCell className="text-right font-semibold">{inr(r.payment_amount)}</TableCell>
                <TableCell><div className="flex items-center gap-1"><StatusChip status={r.status} />{r.warnings?.length > 0 && <AlertTriangle className="h-3.5 w-3.5 text-amber-600" title={r.warnings.join("; ")} />}</div></TableCell>
                <TableCell className="text-xs">{r.created_by}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => openDetail(r.id)} data-testid={`svc-dp-view-${r.id}`}><Eye className="h-4 w-4" /></Button>
                  <Button size="sm" variant="ghost" className="h-7" onClick={() => setDocsFor(r)} data-testid={`svc-dp-docs-${r.id}`}><Paperclip className="h-4 w-4" /></Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {editing && <DirectPaymentForm row={editing.id ? editing : null} vendors={meta.vendors}
        onClose={() => setEditing(null)} onSaved={(saved, isNew) => { setEditing(null); load(); if (isNew) setDocsFor(saved); }} />}

      <Dialog open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-dp-detail-dialog">
          {viewing && (
            <>
              <DialogHeader><DialogTitle className="flex items-center gap-2">{viewing.dp_no} <StatusChip status={viewing.status} testid="svc-dp-detail-status" />{viewing.queue_stage && <Badge variant="outline" className="text-[10px]">queue: {viewing.queue_stage.replace(/_/g, " ")}</Badge>}</DialogTitle></DialogHeader>
              <div className="grid md:grid-cols-3 gap-x-6 gap-y-2 text-sm">
                <div><span className="text-muted-foreground text-xs block">Vendor</span>{viewing.vendor_name} <span className="text-xs text-muted-foreground">{viewing.vendor_gstin}</span></div>
                <div><span className="text-muted-foreground text-xs block">Service period</span>{viewing.service_period || "—"}</div>
                <div><span className="text-muted-foreground text-xs block">Reference PO / SR</span>{viewing.ref_po_no || "—"} {viewing.ref_sr_no ? `· ${viewing.ref_sr_no}` : ""}</div>
                <div><span className="text-muted-foreground text-xs block">Project</span>{viewing.project_code || "—"} {viewing.project_name || ""}</div>
                <div><span className="text-muted-foreground text-xs block">Vendor invoice</span>{viewing.vendor_invoice_no || "—"} · {dt(viewing.invoice_date)}</div>
                <div><span className="text-muted-foreground text-xs block">Due date</span>{dt(viewing.due_date)}</div>
                <div><span className="text-muted-foreground text-xs block">Invoice / GST / Other / TDS</span>{inr(viewing.invoice_amount)} / {inr(viewing.tax_amount)} / {inr(viewing.other_charges)} / {inr(viewing.tds_amount)}</div>
                <div><span className="text-muted-foreground text-xs block">Net payable</span>{inr(viewing.net_payable)}</div>
                <div><span className="text-muted-foreground text-xs block">Payment amount</span><b data-testid="svc-dp-detail-payment">{inr(viewing.payment_amount)}</b></div>
                <div className="md:col-span-3"><span className="text-muted-foreground text-xs block">Description / remarks</span>{viewing.description || "—"} {viewing.remarks ? `· ${viewing.remarks}` : ""}</div>
                {viewing.warnings?.length > 0 && <div className="md:col-span-3 text-amber-800 bg-amber-50 border border-amber-200 rounded-sm p-2 text-xs flex gap-2" data-testid="svc-dp-detail-warnings"><AlertTriangle className="h-4 w-4 shrink-0" /><div>{viewing.warnings.map((w, i) => <div key={i}>{w}</div>)}</div></div>}
                {viewing.approval && <div className="md:col-span-3 text-xs" data-testid="svc-dp-detail-approval"><b>{viewing.approval.action}</b> by {viewing.approval.by} ({viewing.approval.role}) on {dt(viewing.approval.at)} {viewing.approval.remarks ? `— ${viewing.approval.remarks}` : ""}</div>}
                {viewing.payment && <div className="md:col-span-3 text-xs text-emerald-700">Paid · UTR {viewing.payment.utr_no} · {dt(viewing.payment.paid_date)}</div>}
              </div>
              <div className="border-t pt-3">
                <div className="text-xs font-semibold mb-1 flex items-center gap-1"><History className="h-3.5 w-3.5" /> Request history</div>
                <ul className="text-xs space-y-0.5" data-testid="svc-dp-detail-history">
                  {(viewing.history || []).map((h, i) => <li key={i}>{dt(h.at)} · <b>{h.action}</b> by {h.by} {h.remarks ? `— ${h.remarks}` : ""}</li>)}
                </ul>
              </div>
              <div className="border-t pt-3">
                <div className="text-xs font-semibold mb-1">Vendor payment history ({history.length})</div>
                <div className="max-h-48 overflow-y-auto border rounded-sm">
                  <table className="w-full text-xs"><tbody>
                    {history.map((h, i) => (
                      <tr key={i} className="border-t"><td className="px-2 py-1">{h.ref}</td><td className="px-2 py-1">{h.kind.replace("_", " ")}</td><td className="px-2 py-1">{h.service_period || dt(h.date)}</td><td className="px-2 py-1 text-right">{inr(h.amount)}</td><td className="px-2 py-1"><StatusChip status={h.status} /></td><td className="px-2 py-1">{h.utr_no || ""}</td></tr>
                    ))}
                  </tbody></table>
                </div>
              </div>
              <DialogFooter className="flex-wrap gap-2">
                <Button variant="outline" onClick={() => setDocsFor(viewing)} data-testid="svc-dp-detail-docs"><Paperclip className="h-4 w-4 mr-1" /> Documents</Button>
                {viewing.status === "pending_approval" && meta.can_raise && (
                  <Button variant="outline" onClick={() => { setEditing(viewing); setViewing(null); }} data-testid="svc-dp-detail-edit">Edit</Button>
                )}
                {viewing.status === "pending_approval" && (
                  <Button variant="outline" onClick={() => setDeciding({ row: viewing, action: "withdraw" })} data-testid="svc-dp-detail-withdraw">Withdraw</Button>
                )}
                {viewing.status === "pending_approval" && meta.can_approve && (
                  <>
                    <Button variant="destructive" onClick={() => setDeciding({ row: viewing, action: "reject" })} data-testid="svc-dp-detail-reject">Reject</Button>
                    <Button onClick={() => setDeciding({ row: viewing, action: "approve" })} data-testid="svc-dp-detail-approve">Approve → Payment Processing</Button>
                  </>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!deciding} onOpenChange={(o) => !o && setDeciding(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="svc-dp-decide-dialog">
          <DialogHeader><DialogTitle>{deciding?.action === "approve" ? "Approve" : deciding?.action === "reject" ? "Reject" : "Withdraw"} {deciding?.row?.dp_no}</DialogTitle></DialogHeader>
          <p className="text-sm">{deciding?.row?.vendor_name} · <b>{inr(deciding?.row?.payment_amount)}</b></p>
          <Label className="text-xs">Remarks {deciding?.action === "reject" ? "(required)" : "(optional)"}</Label>
          <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="svc-dp-decide-remarks" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeciding(null)}>Cancel</Button>
            <Button disabled={busy} variant={deciding?.action === "reject" ? "destructive" : "default"} onClick={decide} data-testid="svc-dp-decide-confirm">Confirm</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_direct_payments" parentId={docsFor?.id} recordTitle={docsFor?.dp_no} testidPrefix="svc-dp-attach" />
    </div>
  );
}
