import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Paperclip, Send, FileSignature, PackageCheck, Printer, BookText, Mail } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage, API } from "@/lib/api";
import RowAttachments from "@/components/RowAttachments";
import TermsMasterDialog from "./TermsMasterDialog";
import { StatusChip, inr, dt, useSvcMeta } from "./shared";

const PO_STATUSES = ["draft", "pending_approval", "approved", "issued", "in_progress", "completed", "closed"];
const blankSrn = () => ({ receipt_date: "", service_details: "", completed_pct: "", accepted_pct: "", receipt_type: "partial", quality_status: "accepted", remarks: "", submit: true });

export default function ServicePos() {
  const nav = useNavigate();
  const meta = useSvcMeta();
  const caps = meta?.role_caps || {};
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ status: "", q: "" });
  const [approving, setApproving] = useState(null);
  const [remarks, setRemarks] = useState("");
  const [srnFor, setSrnFor] = useState(null);
  const [srn, setSrn] = useState(blankSrn());
  const [docsFor, setDocsFor] = useState(null);
  const [tncOpen, setTncOpen] = useState(false);
  const [mailFor, setMailFor] = useState(null);
  const [mail, setMail] = useState({ to: "", message: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
      setRows((await api.get(`/service-workflow/pos?${qs}`)).data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const act = async (url, msg) => {
    try { await api.post(url); toast.success(msg); load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decide = async (action) => {
    setBusy(true);
    try {
      await api.post(`/service-workflow/pos/${approving.id}/action`, { action, remarks });
      toast.success(`PO ${approving.po_no} ${action}d`);
      setApproving(null); setRemarks(""); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const openMail = (r) => {
    const v = (meta?.vendors || []).find((x) => x.id === r.vendor_id);
    setMail({ to: v?.email || "", message: "" });
    setMailFor(r);
  };

  const sendMail = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/service-workflow/pos/${mailFor.id}/email`, mail);
      toast.success(`${mailFor.po_no} PDF emailed to ${res.data.to}`);
      setMailFor(null); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const createSrn = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/service-workflow/pos/${srnFor.id}/srn`, {
        ...srn, completed_pct: Number(srn.completed_pct) || 0, accepted_pct: Number(srn.accepted_pct) || 0,
      });
      toast.success(`SRN ${r.data.srn_no} created${srn.submit ? " & submitted for verification" : ""}`);
      setSrnFor(null); setSrn(blankSrn()); load();
      nav("/app/services/srns");
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="p-4 space-y-4" data-testid="svc-pos-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><FileSignature className="h-5 w-5" /> Service Purchase Orders</h1>
          <p className="text-xs text-muted-foreground">Draft → Pending Approval → Approved → Issued → In Progress → Completed / Closed</p>
        </div>
        <div className="flex items-end gap-2">
          {caps.procurement &&
            <Button variant="outline" size="sm" className="h-8" onClick={() => setTncOpen(true)} data-testid="svc-po-manage-tnc"><BookText className="h-3.5 w-3.5 mr-1" /> Manage T&amp;C</Button>}
          <select className="h-8 rounded-sm border border-input bg-background px-2 text-sm" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="svc-po-status-filter">
            <option value="">All statuses</option>
            {PO_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
          <Input className="h-8 w-48" placeholder="PO / SR / vendor" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="svc-po-search" />
        </div>
      </div>

      <div className="border rounded-md bg-white overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>PO No</TableHead><TableHead>Date</TableHead><TableHead>Vendor</TableHead>
            <TableHead>SR / RFQ</TableHead><TableHead>Total Value</TableHead><TableHead>Received %</TableHead>
            <TableHead>Status</TableHead><TableHead>Payment</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`svc-po-row-${r.po_no}`}>
                <TableCell className="font-medium text-primary">{r.po_no}{r.exception_note ? <span className="ml-1 text-[9px] text-red-600 uppercase">exception</span> : null}</TableCell>
                <TableCell>{dt(r.po_date)}</TableCell>
                <TableCell className="text-xs">{r.vendor_name}</TableCell>
                <TableCell className="text-xs">
                  <span className="text-primary cursor-pointer" onClick={() => nav(`/app/services/requests/${r.sr_id}`)}>{r.sr_no}</span>
                  <span className="text-muted-foreground"> / {r.rfq_no}</span>
                </TableCell>
                <TableCell className="tabular-nums font-medium">{inr(r.total_value)}</TableCell>
                <TableCell className="tabular-nums">{r.accepted_pct_total || 0}%</TableCell>
                <TableCell><StatusChip status={r.status} testid={`svc-po-status-${r.po_no}`} /></TableCell>
                <TableCell><StatusChip status={r.payment_status} />{(r.paid_amount || 0) > 0 && <div className="text-[10px] text-muted-foreground tabular-nums">{inr(r.paid_amount)} paid</div>}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {!["draft", "pending_approval"].includes(r.status) &&
                    <Button variant="ghost" size="icon" className="h-7 w-7" title="Print / View PO PDF" onClick={() => window.open(`${API}/service-workflow/pos/${r.id}/pdf`, "_blank")} data-testid={`svc-po-pdf-${r.po_no}`}><Printer className="h-3.5 w-3.5" /></Button>}
                  {caps.procurement && !["draft", "pending_approval"].includes(r.status) &&
                    <Button variant="ghost" size="icon" className={`h-7 w-7 ${r.emailed_at ? "text-emerald-600" : ""}`} title={r.emailed_at ? `Emailed to ${r.emailed_to} on ${dt(r.emailed_at)} — send again` : "Email PO PDF to vendor"} onClick={() => openMail(r)} data-testid={`svc-po-email-${r.po_no}`}><Mail className="h-3.5 w-3.5" /></Button>}
                  {caps.procurement && r.status === "draft" &&
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => act(`/service-workflow/pos/${r.id}/submit`, `${r.po_no} submitted for approval`)} data-testid={`svc-po-submit-${r.po_no}`}>Submit</Button>}
                  {caps.sr_approver && r.status === "pending_approval" &&
                    <Button size="sm" className="h-7 text-xs ml-1" onClick={() => { setApproving(r); setRemarks(""); }} data-testid={`svc-po-approve-${r.po_no}`}>Approve / Reject</Button>}
                  {caps.procurement && r.status === "approved" &&
                    <Button variant="outline" size="sm" className="h-7 text-xs ml-1" onClick={() => act(`/service-workflow/pos/${r.id}/issue`, `${r.po_no} issued to ${r.vendor_name}`)} data-testid={`svc-po-issue-${r.po_no}`}><Send className="h-3 w-3 mr-1" /> Issue to Vendor</Button>}
                  {(caps.srn || caps.procurement) && ["issued", "in_progress"].includes(r.status) &&
                    <Button variant="outline" size="sm" className="h-7 text-xs ml-1" onClick={() => { setSrnFor(r); setSrn(blankSrn()); }} data-testid={`svc-po-srn-${r.po_no}`}><PackageCheck className="h-3 w-3 mr-1" /> Create SRN</Button>}
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDocsFor(r)} data-testid={`svc-po-docs-${r.po_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
                </TableCell>
              </TableRow>
            ))}
            {!rows.length && <TableRow><TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-8">No service POs yet</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {/* Approve / Reject */}
      <Dialog open={!!approving} onOpenChange={(o) => !o && setApproving(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="svc-po-approve-dialog">
          <DialogHeader><DialogTitle>Approve PO {approving?.po_no}</DialogTitle></DialogHeader>
          {approving && (
            <div className="text-sm space-y-1 border rounded-md p-3 bg-muted/30">
              <div>Vendor: <b>{approving.vendor_name}</b></div>
              <div>Value: <b>{inr(approving.total_value)}</b> ({approving.quantity} {approving.unit} × {inr(approving.rate)} + {approving.tax_pct}% tax)</div>
              <div>Completion: {dt(approving.completion_date)}</div>
              {approving.exception_note && <div className="text-red-600 text-xs">Exception: {approving.exception_note}</div>}
            </div>
          )}
          <div><Label className="text-xs">Remarks</Label><Textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="svc-po-approve-remarks" /></div>
          <DialogFooter className="gap-2">
            <Button variant="destructive" disabled={busy} onClick={() => decide("reject")} data-testid="svc-po-reject-confirm">Reject</Button>
            <Button disabled={busy} onClick={() => decide("approve")} data-testid="svc-po-approve-confirm">Approve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create SRN */}
      <Dialog open={!!srnFor} onOpenChange={(o) => !o && setSrnFor(null)}>
        <DialogContent className="max-w-xl rounded-sm" data-testid="svc-po-srn-dialog">
          <DialogHeader><DialogTitle>Create SRN — {srnFor?.po_no} · {srnFor?.vendor_name}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><Label className="text-xs">Service Receipt Date</Label><Input type="date" value={srn.receipt_date} onChange={(e) => setSrn({ ...srn, receipt_date: e.target.value })} data-testid="svc-srn-date" /></div>
            <div>
              <Label className="text-xs">Receipt Type</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={srn.receipt_type} onChange={(e) => setSrn({ ...srn, receipt_type: e.target.value, ...(e.target.value === "full" ? { completed_pct: 100, accepted_pct: Math.max(0, 100 - (srnFor?.accepted_pct_total || 0)) } : {}) })} data-testid="svc-srn-type">
                <option value="partial">Partial receipt</option><option value="full">Full receipt</option>
              </select>
            </div>
            <div><Label className="text-xs">Completed % *</Label><Input type="number" min="0" max="100" value={srn.completed_pct} onChange={(e) => setSrn({ ...srn, completed_pct: e.target.value })} data-testid="svc-srn-completed" /></div>
            <div><Label className="text-xs">Accepted % * <span className="text-muted-foreground">(remaining: {100 - (srnFor?.accepted_pct_total || 0)}%)</span></Label><Input type="number" min="0" max="100" value={srn.accepted_pct} onChange={(e) => setSrn({ ...srn, accepted_pct: e.target.value })} data-testid="svc-srn-accepted" /></div>
            <div>
              <Label className="text-xs">Quality / Acceptance</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={srn.quality_status} onChange={(e) => setSrn({ ...srn, quality_status: e.target.value })} data-testid="svc-srn-quality">
                <option value="accepted">Accepted</option><option value="accepted_with_remarks">Accepted with remarks</option><option value="rejected">Rejected</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Save as</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={srn.submit ? "submit" : "draft"} onChange={(e) => setSrn({ ...srn, submit: e.target.value === "submit" })} data-testid="svc-srn-saveas">
                <option value="submit">Submit for verification</option><option value="draft">Draft</option>
              </select>
            </div>
            <div className="md:col-span-2"><Label className="text-xs">Service Details</Label><Textarea rows={2} value={srn.service_details} onChange={(e) => setSrn({ ...srn, service_details: e.target.value })} data-testid="svc-srn-details" /></div>
            <div className="md:col-span-2"><Label className="text-xs">Remarks</Label><Input value={srn.remarks} onChange={(e) => setSrn({ ...srn, remarks: e.target.value })} data-testid="svc-srn-remarks" /></div>
            <p className="md:col-span-2 text-[11px] text-muted-foreground">Attach completion photos / supporting documents from the SRN paperclip after saving. Partial SRNs are allowed for staged services.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSrnFor(null)}>Cancel</Button>
            <Button disabled={busy} onClick={createSrn} data-testid="svc-srn-create-confirm">Create SRN</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_pos" parentId={docsFor?.id} recordTitle={docsFor?.po_no} testidPrefix="svc-po-attach" />
      <TermsMasterDialog open={tncOpen} onOpenChange={setTncOpen} />

      <Dialog open={!!mailFor} onOpenChange={(o) => !o && setMailFor(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="svc-po-mail-dialog">
          <DialogHeader><DialogTitle>Email {mailFor?.po_no} to {mailFor?.vendor_name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-xs">Recipient Email *</Label>
              <Input type="email" value={mail.to} onChange={(e) => setMail({ ...mail, to: e.target.value })} placeholder="vendor@company.com" data-testid="svc-po-mail-to" /></div>
            <div><Label className="text-xs">Message (optional, added to the email body)</Label>
              <Textarea rows={2} value={mail.message} onChange={(e) => setMail({ ...mail, message: e.target.value })} data-testid="svc-po-mail-message" /></div>
            <p className="text-[11px] text-muted-foreground">The PO PDF (with Terms &amp; Conditions) is attached automatically and sent from the company mailbox.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMailFor(null)}>Cancel</Button>
            <Button disabled={busy || !mail.to.includes("@")} onClick={sendMail} data-testid="svc-po-mail-send"><Mail className="h-3.5 w-3.5 mr-1" /> Send PO</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
