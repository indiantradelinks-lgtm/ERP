/**
 * RFQ Bulk Email Dialog
 * Sends the RFQ + PDF to ALL shortlisted vendors in one click.
 * Backend: POST /api/email/send-rfq-bulk/{rfq_id}
 */
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Mails, Send, CheckCircle2, XCircle } from "lucide-react";

export default function RfqBulkEmailDialog({ rfq, onClose }) {
  const [subjectOverride, setSubjectOverride] = useState("");
  const [bodyOverride, setBodyOverride] = useState("");
  const [cc, setCc] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const vendors = rfq.vendors || [];

  const send = async () => {
    setSending(true);
    setResult(null);
    try {
      const payload = {
        attach_pdf: true,
        skip_vendors_without_email: true,
        cc: cc.split(",").map((s) => s.trim()).filter(Boolean),
      };
      if (subjectOverride.trim()) payload.subject_override = subjectOverride.trim();
      if (bodyOverride.trim()) payload.body_override = bodyOverride.trim();
      const { data } = await api.post(`/email/send-rfq-bulk/${rfq.id}`, payload);
      setResult(data);
      if (data.queued > 0) {
        toast.success(`Queued ${data.queued} email(s) · skipped ${data.skipped}`);
      } else {
        toast.error(`Nothing queued · ${data.skipped} skipped`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Bulk send failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={true} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm" data-testid="rfq-bulk-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Mails className="h-5 w-5" /> Bulk Send · {rfq.rfq_number}
          </DialogTitle>
          <DialogDescription>
            Will email RFQ + PDF to <strong>{vendors.length}</strong> shortlisted vendor(s). One email per vendor (BCC-style isolation).
          </DialogDescription>
        </DialogHeader>

        {!result && (
          <div className="space-y-3 py-1">
            <div className="bg-slate-50 p-2 rounded-sm text-xs">
              <div className="font-medium mb-1">Vendors that will receive:</div>
              <div className="flex flex-wrap gap-1">
                {vendors.length === 0 && <span className="text-slate-400">No shortlisted vendors</span>}
                {vendors.map((v) => (
                  <Badge key={v.vendor_id} variant="outline" className="text-xs">
                    {v.vendor_name || v.vendor_id}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-xs">Subject (optional override — default uses RFQ number)</Label>
              <Input value={subjectOverride} onChange={(e) => setSubjectOverride(e.target.value)} placeholder={`Request for Quotation ${rfq.rfq_number} — INDIAN TRADE LINKS`} data-testid="bulk-subject" />
            </div>
            <div>
              <Label className="text-xs">Body (optional override)</Label>
              <Textarea rows={5} value={bodyOverride} onChange={(e) => setBodyOverride(e.target.value)} placeholder="Leave blank to use the standard cover-note." data-testid="bulk-body" />
            </div>
            <div>
              <Label className="text-xs">CC (comma-separated, optional)</Label>
              <Input value={cc} onChange={(e) => setCc(e.target.value)} placeholder="procurement@itl.in, finance@itl.in" data-testid="bulk-cc" />
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-2 py-1 max-h-[400px] overflow-y-auto">
            <div className="text-sm font-medium">Result: {result.queued} queued · {result.skipped} skipped</div>
            <table className="w-full text-xs">
              <thead className="bg-slate-50">
                <tr><th className="p-1 text-left">Vendor</th><th className="p-1 text-left">To</th><th className="p-1 text-left">Status</th></tr>
              </thead>
              <tbody>
                {(result.results || []).map((row, i) => (
                  <tr key={i} className="border-b" data-testid={`bulk-result-${i}`}>
                    <td className="p-1">{row.vendor_name || row.vendor_id}</td>
                    <td className="p-1 font-mono">{row.to || "—"}</td>
                    <td className="p-1">
                      {row.status === "queued" ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 className="h-3 w-3" /> queued</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-700" title={row.reason}><XCircle className="h-3 w-3" /> {row.reason}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <DialogFooter>
          {!result && (
            <>
              <Button variant="outline" onClick={onClose} disabled={sending}>Cancel</Button>
              <Button onClick={send} disabled={sending || vendors.length === 0} data-testid="bulk-send">
                <Send className="h-3.5 w-3.5 mr-1" /> {sending ? "Sending…" : `Send to ${vendors.length} vendor(s)`}
              </Button>
            </>
          )}
          {result && <Button onClick={onClose} data-testid="bulk-close">Close</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
