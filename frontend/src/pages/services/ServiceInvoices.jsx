import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Plus, Paperclip, Receipt, AlertTriangle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import RowAttachments from "@/components/RowAttachments";
import { StatusChip, inr, dt, useSvcMeta } from "./shared";

const INV_STATUSES = ["exception_review", "pending_approval", "payment_pending", "paid", "rejected"];
const blankInv = () => ({ po_id: "", srn_id: "", vendor_invoice_no: "", invoice_date: "", invoice_amount: "", tax_amount: "", other_charges: 0, tds_amount: 0, due_date: "", remarks: "" });

export default function ServiceInvoices() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const meta = useSvcMeta();
  const caps = meta?.role_caps || {};
  const [tab, setTab] = useState(sp.get("tab") === "payments" ? "payments" : "invoices");
  const [rows, setRows] = useState([]);
  const [payments, setPayments] = useState([]);
  const [pos, setPos] = useState([]);
  const [srns, setSrns] = useState([]);
  const [f, setF] = useState({ status: sp.get("status") || "", q: "" });
  const [creating, setCreating] = useState(null);
  const [matchFor, setMatchFor] = useState(null);
  const [deciding, setDeciding] = useState(null); // {row, mode: approve|exception}
  const [remarks, setRemarks] = useState("");
  const [docsFor, setDocsFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
      const [a, b] = await Promise.all([
        api.get(`/service-workflow/invoices?${qs}`),
        api.get("/service-workflow/payments"),
      ]);
      setRows(a.data); setPayments(b.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const openCreate = async () => {
    setCreating(blankInv());
    try {
      const [p, s] = await Promise.all([
        api.get("/service-workflow/pos"),
        api.get("/service-workflow/srns?status=approved"),
      ]);
      setPos(p.data.filter((x) => ["issued", "in_progress", "completed"].includes(x.status)));
      setSrns(s.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const poSrns = useMemo(() => srns.filter((s) => s.po_id === creating?.po_id), [srns, creating?.po_id]);
  const selPo = useMemo(() => pos.find((p) => p.id === creating?.po_id), [pos, creating?.po_id]);
  const net = (Number(creating?.invoice_amount) || 0) + (Number(creating?.tax_amount) || 0) + (Number(creating?.other_charges) || 0) - (Number(creating?.tds_amount) || 0);

  const saveInvoice = async () => {
    setBusy(true);
    try {
      const r = await api.post("/service-workflow/invoices", {
        ...creating,
        invoice_amount: Number(creating.invoice_amount) || 0, tax_amount: Number(creating.tax_amount) || 0,
        other_charges: Number(creating.other_charges) || 0, tds_amount: Number(creating.tds_amount) || 0,
      });
      if (r.data.match?.ok) toast.success(`${r.data.inv_no} recorded — 3-way match OK, pending approval`);
      else toast.warning(`${r.data.inv_no} recorded with ${r.data.match.mismatches.length} mismatch(es) — sent to exception review`);
      setCreating(null); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const decide = async (action) => {
    setBusy(true);
    try {
      if (deciding.mode === "exception" && action === "resolve") {
        await api.post(`/service-workflow/invoices/${deciding.row.id}/resolve-exception`, { action: "resolve", remarks });
        toast.success("Exception resolved — invoice moved to pending approval");
      } else {
        await api.post(`/service-workflow/invoices/${deciding.row.id}/action`, { action, remarks });
        toast.success(action === "approve"
          ? `${deciding.row.inv_no} approved — pushed to Accounts Payment Processing Center`
          : `${deciding.row.inv_no} rejected`);
      }
      setDeciding(null); setRemarks(""); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const MatchBadge = ({ r }) => r.match?.ok
    ? <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-300 text-[10px] cursor-pointer" onClick={() => setMatchFor(r)} data-testid={`svc-inv-match-${r.inv_no}`}><CheckCircle2 className="h-3 w-3 mr-0.5" /> Matched</Badge>
    : <Badge variant="outline" className="bg-red-50 text-red-700 border-red-300 text-[10px] cursor-pointer" onClick={() => setMatchFor(r)} data-testid={`svc-inv-match-${r.inv_no}`}><AlertTriangle className="h-3 w-3 mr-0.5" /> {r.match?.mismatches?.length || 0} mismatch</Badge>;

  return (
    <div className="p-4 space-y-4" data-testid="svc-invoices-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Receipt className="h-5 w-5" /> Service Invoices & Payments</h1>
          <p className="text-xs text-muted-foreground">3-way matching (PO ↔ SRN ↔ Invoice) · approved invoices flow to the Accounts Payment Processing Center</p>
        </div>
        {(caps.accounts || caps.procurement) && <Button onClick={openCreate} data-testid="svc-inv-new-btn"><Plus className="h-4 w-4 mr-1" /> Submit Vendor Invoice</Button>}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="invoices" data-testid="svc-inv-tab-invoices">Invoices</TabsTrigger>
          <TabsTrigger value="payments" data-testid="svc-inv-tab-payments">Payment Queue</TabsTrigger>
        </TabsList>

        <TabsContent value="invoices" className="space-y-3">
          <div className="flex items-end gap-2">
            <select className="h-8 rounded-sm border border-input bg-background px-2 text-sm" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="svc-inv-status-filter">
              <option value="">All statuses</option>
              {INV_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </select>
            <Input className="h-8 w-56" placeholder="Invoice / PO / SR no" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="svc-inv-search" />
          </div>
          <div className="border rounded-md bg-white overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Ref</TableHead><TableHead>Vendor Inv No</TableHead><TableHead>Vendor</TableHead>
                <TableHead>PO / SRN</TableHead><TableHead>Amount</TableHead><TableHead>Tax</TableHead>
                <TableHead>TDS</TableHead><TableHead>Net Payable</TableHead><TableHead>3-Way Match</TableHead>
                <TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id} data-testid={`svc-inv-row-${r.inv_no}`}>
                    <TableCell className="font-medium text-primary cursor-pointer" onClick={() => nav(`/app/services/requests/${r.sr_id}`)}>{r.inv_no}</TableCell>
                    <TableCell className="text-xs">{r.vendor_invoice_no}<div className="text-muted-foreground">{dt(r.invoice_date)}</div></TableCell>
                    <TableCell className="text-xs">{r.vendor_name}</TableCell>
                    <TableCell className="text-xs">{r.po_no}<div className="text-muted-foreground">{r.srn_no}</div></TableCell>
                    <TableCell className="tabular-nums">{inr(r.invoice_amount)}</TableCell>
                    <TableCell className="tabular-nums text-xs">{inr(r.tax_amount)}</TableCell>
                    <TableCell className="tabular-nums text-xs">{inr(r.tds_amount)}</TableCell>
                    <TableCell className="tabular-nums font-semibold">{inr(r.net_payable)}</TableCell>
                    <TableCell><MatchBadge r={r} /></TableCell>
                    <TableCell><StatusChip status={r.status} testid={`svc-inv-status-${r.inv_no}`} /></TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      {caps.accounts && r.status === "exception_review" &&
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => { setDeciding({ row: r, mode: "exception" }); setRemarks(""); }} data-testid={`svc-inv-resolve-${r.inv_no}`}>Resolve Exception</Button>}
                      {caps.accounts && r.status === "pending_approval" &&
                        <Button size="sm" className="h-7 text-xs ml-1" onClick={() => { setDeciding({ row: r, mode: "approve" }); setRemarks(""); }} data-testid={`svc-inv-approve-${r.inv_no}`}>Approve / Reject</Button>}
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDocsFor(r)} data-testid={`svc-inv-docs-${r.inv_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
                {!rows.length && <TableRow><TableCell colSpan={11} className="text-center text-sm text-muted-foreground py-8">No invoices yet — submit one against an approved SRN</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="payments">
          <div className="border rounded-md bg-white overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Vendor</TableHead><TableHead>Invoice</TableHead><TableHead>PO / SRN</TableHead>
                <TableHead>Net Payable</TableHead><TableHead>Due Date</TableHead><TableHead>Queue Stage</TableHead>
                <TableHead>UTR / Ref</TableHead><TableHead>Paid Date</TableHead><TableHead>Status</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {payments.map((r) => {
                  const overdue = r.status === "payment_pending" && r.due_date && r.due_date < new Date().toISOString().slice(0, 10);
                  return (
                    <TableRow key={r.id} className={overdue ? "bg-red-50/50" : ""} data-testid={`svc-pay-row-${r.inv_no}`}>
                      <TableCell className="text-xs">{r.vendor_name}</TableCell>
                      <TableCell className="text-xs">{r.vendor_invoice_no}<div className="text-muted-foreground">{r.inv_no}</div></TableCell>
                      <TableCell className="text-xs">{r.po_no}<div className="text-muted-foreground">{r.srn_no}</div></TableCell>
                      <TableCell className="tabular-nums font-semibold">{inr(r.net_payable)}</TableCell>
                      <TableCell className={overdue ? "text-red-600 font-medium" : ""}>{dt(r.due_date)}{overdue ? " ⚠" : ""}</TableCell>
                      <TableCell className="text-xs">{(r.queue_stage || "—").replace(/_/g, " ")}</TableCell>
                      <TableCell className="text-xs">{r.utr_no || "—"}</TableCell>
                      <TableCell>{dt(r.paid_date)}</TableCell>
                      <TableCell><StatusChip status={r.status} testid={`svc-pay-status-${r.inv_no}`} /></TableCell>
                    </TableRow>
                  );
                })}
                {!payments.length && <TableRow><TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-8">Nothing in the payment queue</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">Payments are executed by Accounts in the <b>Payment Processing Center</b>. Status here auto-updates once the payment is marked paid (UTR captured there).</p>
        </TabsContent>
      </Tabs>

      {/* Create invoice */}
      <Dialog open={!!creating} onOpenChange={(o) => !o && setCreating(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-inv-create-dialog">
          <DialogHeader><DialogTitle>Submit Vendor Invoice</DialogTitle></DialogHeader>
          {creating && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Service PO *</Label>
                <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={creating.po_id} onChange={(e) => setCreating({ ...creating, po_id: e.target.value, srn_id: "" })} data-testid="svc-inv-form-po">
                  <option value="">— select —</option>
                  {pos.map((p) => <option key={p.id} value={p.id}>{p.po_no} · {p.vendor_name} · {inr(p.total_value)}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Approved SRN *</Label>
                <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={creating.srn_id} onChange={(e) => setCreating({ ...creating, srn_id: e.target.value })} disabled={!creating.po_id} data-testid="svc-inv-form-srn">
                  <option value="">— select —</option>
                  {poSrns.map((s) => <option key={s.id} value={s.id}>{s.srn_no} · {s.accepted_pct}% accepted · {dt(s.receipt_date)}</option>)}
                </select>
                {creating.po_id && !poSrns.length && <p className="text-[11px] text-red-600 mt-1">No approved SRN against this PO yet</p>}
              </div>
              <div><Label className="text-xs">Vendor Invoice Number *</Label><Input value={creating.vendor_invoice_no} onChange={(e) => setCreating({ ...creating, vendor_invoice_no: e.target.value })} data-testid="svc-inv-form-no" /></div>
              <div><Label className="text-xs">Invoice Date</Label><Input type="date" value={creating.invoice_date} onChange={(e) => setCreating({ ...creating, invoice_date: e.target.value })} data-testid="svc-inv-form-date" /></div>
              <div><Label className="text-xs">Invoice Amount (pre-tax) *</Label><Input type="number" min="0" value={creating.invoice_amount} onChange={(e) => setCreating({ ...creating, invoice_amount: e.target.value })} data-testid="svc-inv-form-amount" /></div>
              <div><Label className="text-xs">Tax / GST (₹) {selPo ? `— PO rate ${selPo.tax_pct}%` : ""}</Label><Input type="number" min="0" value={creating.tax_amount} onChange={(e) => setCreating({ ...creating, tax_amount: e.target.value })} data-testid="svc-inv-form-tax" /></div>
              <div><Label className="text-xs">Other Charges (₹)</Label><Input type="number" min="0" value={creating.other_charges} onChange={(e) => setCreating({ ...creating, other_charges: e.target.value })} data-testid="svc-inv-form-other" /></div>
              <div><Label className="text-xs">TDS / Deductions (₹)</Label><Input type="number" min="0" value={creating.tds_amount} onChange={(e) => setCreating({ ...creating, tds_amount: e.target.value })} data-testid="svc-inv-form-tds" /></div>
              <div><Label className="text-xs">Payment Due Date</Label><Input type="date" value={creating.due_date} onChange={(e) => setCreating({ ...creating, due_date: e.target.value })} data-testid="svc-inv-form-due" /></div>
              <div><Label className="text-xs">Remarks</Label><Input value={creating.remarks} onChange={(e) => setCreating({ ...creating, remarks: e.target.value })} data-testid="svc-inv-form-remarks" /></div>
              <div className="md:col-span-2 border rounded-md p-2 bg-muted/30 text-sm flex justify-between">
                <span>Net Payable</span><b className="tabular-nums" data-testid="svc-inv-form-net">{inr(net)}</b>
              </div>
              <p className="md:col-span-2 text-[11px] text-muted-foreground">On save, the system runs 3-way matching (PO ↔ SRN ↔ Invoice). Mismatches route to the exception queue. Attach the invoice PDF via the paperclip after saving.</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(null)}>Cancel</Button>
            <Button disabled={busy || !creating?.po_id || !creating?.srn_id} onClick={saveInvoice} data-testid="svc-inv-form-save">Save & Run 3-Way Match</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Match detail */}
      <Dialog open={!!matchFor} onOpenChange={(o) => !o && setMatchFor(null)}>
        <DialogContent className="max-w-lg rounded-sm" data-testid="svc-inv-match-dialog">
          <DialogHeader><DialogTitle>3-Way Match — {matchFor?.inv_no}</DialogTitle></DialogHeader>
          {matchFor && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-3 gap-2 text-center">
                {[["PO", matchFor.po_no], ["SRN", matchFor.srn_no], ["Invoice", matchFor.vendor_invoice_no]].map(([k, v]) => (
                  <div key={k} className="border rounded-md p-2"><div className="text-[10px] uppercase text-muted-foreground">{k}</div><div className="font-medium text-xs">{v}</div></div>
                ))}
              </div>
              {matchFor.match?.ok
                ? <p className="text-emerald-700 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" /> All checks passed — quantity/completion, rate, tax, vendor and PO reference match.</p>
                : <ul className="space-y-1">{(matchFor.match?.mismatches || []).map((m, i) => <li key={i} className="text-red-700 flex gap-1 text-xs"><AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" /> {m}</li>)}</ul>}
              {matchFor.exception_resolution && <p className="text-xs text-muted-foreground border-t pt-2">Exception resolved by {matchFor.exception_resolution.by}: “{matchFor.exception_resolution.remarks}”</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Approve / resolve */}
      <Dialog open={!!deciding} onOpenChange={(o) => !o && setDeciding(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="svc-inv-decide-dialog">
          <DialogHeader><DialogTitle>{deciding?.mode === "exception" ? "Resolve Exception" : "Approve Invoice"} — {deciding?.row?.inv_no}</DialogTitle></DialogHeader>
          {deciding && (
            <div className="text-sm border rounded-md p-3 bg-muted/30 space-y-1">
              <div>Vendor: <b>{deciding.row.vendor_name}</b> · Net: <b>{inr(deciding.row.net_payable)}</b></div>
              <div className="text-xs text-muted-foreground">PO {deciding.row.po_no} · SRN {deciding.row.srn_no} · SR {deciding.row.sr_no}</div>
              {!deciding.row.match?.ok && <ul className="text-xs text-red-700 list-disc pl-4">{(deciding.row.match?.mismatches || []).map((m, i) => <li key={i}>{m}</li>)}</ul>}
            </div>
          )}
          <div><Label className="text-xs">Remarks {deciding?.mode === "exception" ? "* (resolution note)" : "(required to reject)"}</Label>
            <Textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="svc-inv-decide-remarks" /></div>
          <DialogFooter className="gap-2">
            {deciding?.mode === "exception"
              ? <>
                <Button variant="destructive" disabled={busy || !remarks.trim()} onClick={() => decide("reject")} data-testid="svc-inv-exception-reject">Reject Invoice</Button>
                <Button disabled={busy || !remarks.trim()} onClick={() => decide("resolve")} data-testid="svc-inv-resolve-confirm">Mark Resolved → Pending Approval</Button>
              </>
              : <>
                <Button variant="destructive" disabled={busy} onClick={() => decide("reject")} data-testid="svc-inv-reject-confirm">Reject</Button>
                <Button disabled={busy} onClick={() => decide("approve")} data-testid="svc-inv-approve-confirm">Approve → Payment Queue</Button>
              </>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_invoices" parentId={docsFor?.id} recordTitle={docsFor?.inv_no} testidPrefix="svc-inv-attach" />
    </div>
  );
}
