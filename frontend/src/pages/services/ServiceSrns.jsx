import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Paperclip, ClipboardCheck } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import RowAttachments from "@/components/RowAttachments";
import { StatusChip, dt, useSvcMeta } from "./shared";

export default function ServiceSrns() {
  const nav = useNavigate();
  const meta = useSvcMeta();
  const caps = meta?.role_caps || {};
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ status: "", q: "" });
  const [verifying, setVerifying] = useState(null);
  const [remarks, setRemarks] = useState("");
  const [docsFor, setDocsFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
      setRows((await api.get(`/service-workflow/srns?${qs}`)).data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const submit = async (r) => {
    try { await api.post(`/service-workflow/srns/${r.id}/submit`); toast.success(`${r.srn_no} submitted for verification`); load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decide = async (action) => {
    setBusy(true);
    try {
      await api.post(`/service-workflow/srns/${verifying.id}/action`, { action, remarks });
      toast.success(`${verifying.srn_no} ${action}d`);
      setVerifying(null); setRemarks(""); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="p-4 space-y-4" data-testid="svc-srns-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><ClipboardCheck className="h-5 w-5" /> Service Receipt Notes (SRN)</h1>
          <p className="text-xs text-muted-foreground">Record staged/full service completion against issued POs — only approved SRNs move to invoicing</p>
        </div>
        <div className="flex items-end gap-2">
          <select className="h-8 rounded-sm border border-input bg-background px-2 text-sm" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="svc-srn-status-filter">
            <option value="">All statuses</option>
            {["draft", "submitted", "approved", "rejected"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Input className="h-8 w-48" placeholder="SRN / PO / SR" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="svc-srn-search" />
        </div>
      </div>

      <div className="border rounded-md bg-white overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>SRN No</TableHead><TableHead>PO</TableHead><TableHead>SR</TableHead>
            <TableHead>Vendor</TableHead><TableHead>Receipt Date</TableHead><TableHead>Completed</TableHead>
            <TableHead>Accepted</TableHead><TableHead>Type</TableHead><TableHead>Quality</TableHead>
            <TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`svc-srn-row-${r.srn_no}`}>
                <TableCell className="font-medium text-primary">{r.srn_no}</TableCell>
                <TableCell className="text-xs">{r.po_no}</TableCell>
                <TableCell className="text-xs text-primary cursor-pointer" onClick={() => nav(`/app/services/requests/${r.sr_id}`)}>{r.sr_no}</TableCell>
                <TableCell className="text-xs">{r.vendor_name}</TableCell>
                <TableCell>{dt(r.receipt_date)}</TableCell>
                <TableCell className="tabular-nums">{r.completed_pct}%</TableCell>
                <TableCell className="tabular-nums font-medium">{r.accepted_pct}%</TableCell>
                <TableCell><Badge variant="outline" className="text-[10px]">{r.receipt_type}</Badge></TableCell>
                <TableCell className="text-xs">{(r.quality_status || "").replace(/_/g, " ")}</TableCell>
                <TableCell><StatusChip status={r.status} testid={`svc-srn-status-${r.srn_no}`} /></TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {r.status === "draft" &&
                    <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => submit(r)} data-testid={`svc-srn-submit-${r.srn_no}`}>Submit</Button>}
                  {(caps.sr_approver || caps.procurement) && r.status === "submitted" &&
                    <Button size="sm" className="h-7 text-xs ml-1" onClick={() => { setVerifying(r); setRemarks(""); }} data-testid={`svc-srn-verify-${r.srn_no}`}>Verify</Button>}
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDocsFor(r)} data-testid={`svc-srn-docs-${r.srn_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
                </TableCell>
              </TableRow>
            ))}
            {!rows.length && <TableRow><TableCell colSpan={11} className="text-center text-sm text-muted-foreground py-8">No SRNs yet — create one from an issued Service PO</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!verifying} onOpenChange={(o) => !o && setVerifying(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="svc-srn-verify-dialog">
          <DialogHeader><DialogTitle>Verify {verifying?.srn_no}</DialogTitle></DialogHeader>
          {verifying && (
            <div className="text-sm border rounded-md p-3 bg-muted/30 space-y-1">
              <div>PO: <b>{verifying.po_no}</b> · Vendor: <b>{verifying.vendor_name}</b></div>
              <div>Completed {verifying.completed_pct}% · Accepted {verifying.accepted_pct}% ({verifying.receipt_type})</div>
              <div>Quality: {(verifying.quality_status || "").replace(/_/g, " ")}</div>
              {verifying.service_details && <div className="text-xs text-muted-foreground">{verifying.service_details}</div>}
            </div>
          )}
          <div><Label className="text-xs">Remarks (required to reject)</Label><Textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="svc-srn-verify-remarks" /></div>
          <DialogFooter className="gap-2">
            <Button variant="destructive" disabled={busy} onClick={() => decide("reject")} data-testid="svc-srn-reject-confirm">Reject</Button>
            <Button disabled={busy} onClick={() => decide("approve")} data-testid="svc-srn-approve-confirm">Approve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_srns" parentId={docsFor?.id} recordTitle={docsFor?.srn_no} testidPrefix="svc-srn-attach" />
    </div>
  );
}
