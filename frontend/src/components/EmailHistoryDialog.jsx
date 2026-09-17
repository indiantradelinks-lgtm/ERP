/**
 * Email Send History Dialog
 * Shows every email_outbox row for a given record (PO, RFQ, quotation, …).
 * Backend: GET /api/email/send-history/{module}/{record_id}
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { History, RefreshCcw, Paperclip } from "lucide-react";
import { fmtDT } from "@/lib/datetime";

const STATUS_TONE = {
  sent: "bg-emerald-100 text-emerald-700",
  queued: "bg-blue-100 text-blue-700",
  sending: "bg-blue-100 text-blue-700",
  failed: "bg-rose-100 text-rose-700",
};

export default function EmailHistoryDialog({ module, recordId, recordLabel, onClose }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/email/send-history/${module}/${recordId}`);
      setRows(data?.rows || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load history");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [module, recordId]);

  return (
    <Dialog open={true} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl rounded-sm" data-testid="email-history-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <History className="h-5 w-5" /> Email Send History · {recordLabel || recordId}
          </DialogTitle>
          <DialogDescription>Every email queued / sent for this record, including failures with retry-eligible errors.</DialogDescription>
        </DialogHeader>

        <div className="max-h-[500px] overflow-y-auto">
          {loading && <div className="py-8 text-center text-slate-400">Loading…</div>}
          {!loading && rows.length === 0 && <div className="py-12 text-center text-slate-400">No emails sent for this record yet.</div>}
          {!loading && rows.length > 0 && (
            <table className="w-full text-xs">
              <thead className="bg-slate-50 sticky top-0">
                <tr>
                  <th className="p-1.5 text-left">Sent / Queued at</th>
                  <th className="p-1.5 text-left">To</th>
                  <th className="p-1.5 text-left">Subject</th>
                  <th className="p-1.5 text-left">From</th>
                  <th className="p-1.5 text-left">Status</th>
                  <th className="p-1.5 text-center">Att</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b" data-testid={`history-row-${r.id}`}>
                    <td className="p-1.5 whitespace-nowrap font-mono text-[10px]">{fmtDT(r.sent_at || r.created_at)}</td>
                    <td className="p-1.5">{(r.to || []).join(", ")}</td>
                    <td className="p-1.5 max-w-[280px] truncate" title={r.subject}>{r.subject}</td>
                    <td className="p-1.5 text-[10px]">{r.sender_email}</td>
                    <td className="p-1.5">
                      <Badge className={STATUS_TONE[r.status] || "bg-slate-100 text-slate-700"}>{r.status}</Badge>
                      {r.last_error && (
                        <div className="text-[10px] text-rose-600 mt-0.5" title={r.last_error}>
                          {r.error_type}: {r.last_error.slice(0, 60)}…
                        </div>
                      )}
                    </td>
                    <td className="p-1.5 text-center">
                      {((r.attachments_summary || []).length > 0) && (
                        <span className="inline-flex items-center gap-1" title={(r.attachments_summary || []).map(a => a.filename).join(", ")}>
                          <Paperclip className="h-3 w-3" />{(r.attachments_summary || []).length}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={load} data-testid="history-refresh"><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button onClick={onClose} data-testid="history-close">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
