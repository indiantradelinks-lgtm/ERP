import { useState, useEffect } from "react";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Mail, Network, FileDown, History, ListChecks, Table2, Send, FilePen, Loader2, GitCompareArrows, MailCheck, MailOpen } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import SendEmailDialog from "@/components/SendEmailDialog";
import EmailHistoryDialog from "@/components/EmailHistoryDialog";
import LineageTrail from "@/components/LineageTrail";
import POTermsDialog from "@/components/POTermsDialog";
import POItemsDialog from "@/components/POItemsDialog";
import AmendmentCompareDialog from "@/components/AmendmentCompareDialog";
import { downloadPdf } from "@/lib/exports";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { lookupGet } from "@/lib/lookups";

const PO_STATUS_TONE = {
  approved: "success", rejected: "danger", received: "info", partially_received: "warning",
  pending_approval: "warning", submitted: "warning", pending_revision: "danger",
  amendment_in_progress: "info", sent_to_vendor: "info", draft: "neutral",
};
const SUBMITTABLE = ["draft", "pending_revision", "amendment_in_progress", "rejected"];
const AMENDABLE = ["approved", "sent_to_vendor", "received", "partially_received"];
const EMAIL_READY = ["approved", "sent_to_vendor", "received", "partially_received"];

export default function PurchaseOrders() {
  const r = useResource("purchase-orders");
  const [projMap, setProjMap] = useState({});
  useEffect(() => {
    lookupGet("/projects").then((res) => {
      const m = {};
      (res.data || []).forEach((p) => {
        const info = { code: p.code || p.project_code, name: p.name, manager: p.manager || p.project_manager_name };
        if (info.code) m[info.code] = info;
        m[p.id] = info;
      });
      setProjMap(m);
    }).catch(() => {});
  }, []);
  const [emailFor, setEmailFor] = useState(null);
  const [historyFor, setHistoryFor] = useState(null);
  const [lineageFor, setLineageFor] = useState(null);
  const [termsFor, setTermsFor] = useState(null);
  const [itemsFor, setItemsFor] = useState(null);
  const [amendFor, setAmendFor] = useState(null);
  const [compareFor, setCompareFor] = useState(null);
  const [amendReason, setAmendReason] = useState("");
  const [busyId, setBusyId] = useState(null);

  const submitPO = async (row) => {
    setBusyId(row.id);
    try {
      await api.post(`/procurement/pos/${row.id}/submit`);
      toast.success(`PO ${row.po_number} submitted for multi-level approval`);
      r.reload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to submit PO"));
    } finally {
      setBusyId(null);
    }
  };

  const requestAmendment = async () => {
    setBusyId(amendFor.id);
    try {
      await api.post(`/procurement/pos/${amendFor.id}/request-amendment`, { reason: amendReason });
      toast.success("Amendment request submitted — editing unlocks after approval");
      setAmendFor(null);
      setAmendReason("");
      r.reload?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to raise amendment request"));
    } finally {
      setBusyId(null);
    }
  };

  const columns = [
    {
      key: "po_number", label: "PO #",
      render: (row) => (
        <span>{row.po_number}
          {Number(row.revision) > 0 && <span className="ml-1 text-[10px] bg-amber-100 text-amber-800 px-1 py-0.5 rounded-sm align-middle" data-testid={`po-rev-${row.id}`}>Rev {row.revision}</span>}
        </span>
      ),
    },
    { key: "vendor", label: "Vendor" },
    { key: "pr_number", label: "PR #", render: (row) => row.pr_number || "—" },
    {
      key: "project", label: "Project",
      render: (row) => {
        const p = projMap[row.project] || projMap[row.project_code] || projMap[row.project_id];
        const code = p?.code || row.project || row.project_code;
        if (!code) return "—";
        return (
          <div data-testid={`po-project-${row.id}`}>
            <div className="font-medium">{code}</div>
            {p?.name && <div className="text-[11px] text-muted-foreground max-w-[180px] truncate" title={p.name}>{p.name}</div>}
            {p?.manager && <div className="text-[10px] text-muted-foreground">PM: {p.manager}</div>}
          </div>
        );
      },
    },
    { key: "total", label: "Total", render: (row) => "₹ " + Number(row.total || row.amount || 0).toLocaleString("en-IN") },
    { key: "paid", label: "Paid", render: (row) => (row.paid ? "Yes" : "No") },
    {
      key: "_vendor_ack", label: "Vendor Ack",
      render: (row) => {
        const a = row.vendor_ack || {};
        if (a.acknowledged_at) return <span className="inline-flex items-center gap-1 text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded-sm bg-emerald-100 text-emerald-700" title={`Acknowledged by ${a.acknowledged_by || "vendor"} on ${String(a.acknowledged_at).slice(0, 10)}`} data-testid={`po-ack-status-${row.id}`}><MailCheck className="h-3 w-3" /> Acked</span>;
        if (a.opened_at) return <span className="inline-flex items-center gap-1 text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded-sm bg-sky-100 text-sky-700" title={`Email opened ${String(a.opened_at).slice(0, 10)} — not yet acknowledged`} data-testid={`po-ack-status-${row.id}`}><MailOpen className="h-3 w-3" /> Opened</span>;
        if (a.sent_at) return <span className="inline-flex items-center gap-1 text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded-sm bg-slate-100 text-slate-600" title={`Sent ${String(a.sent_at).slice(0, 10)} — not opened yet`} data-testid={`po-ack-status-${row.id}`}><Mail className="h-3 w-3" /> Sent</span>;
        return <span className="text-muted-foreground" data-testid={`po-ack-status-${row.id}`}>—</span>;
      },
    },
    {
      key: "status", label: "Status",
      render: (row) => (
        <div>
          <span className={`inline-block text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded-sm ${{
            success: "bg-emerald-100 text-emerald-700", danger: "bg-red-100 text-red-700",
            info: "bg-sky-100 text-sky-700", warning: "bg-amber-100 text-amber-700", neutral: "bg-slate-100 text-slate-600",
          }[toneFor(PO_STATUS_TONE, row.status, "warning")]}`}>{(row.status || "").replaceAll("_", " ")}</span>
          {row.amendment_status === "requested" && <div className="text-[10px] text-amber-700 mt-0.5">Amendment requested</div>}
          {row.status === "pending_revision" && row.reject_reason && (
            <div className="text-[10px] text-red-600 mt-0.5 max-w-[180px] truncate" title={`Rejected: ${row.reject_reason}`} data-testid={`po-reject-reason-${row.id}`}>✗ {row.reject_reason}</div>
          )}
        </div>
      ),
    },
    {
      key: "_actions",
      label: "Actions",
      render: (row) => {
        const emailReady = EMAIL_READY.includes(row.status);
        return (
          <div className="inline-flex gap-1">
            {SUBMITTABLE.includes(row.status) && (
              <Button size="sm" className="h-7 px-2 rounded-sm" onClick={() => submitPO(row)} disabled={busyId === row.id} data-testid={`po-submit-${row.id}`} title="Submit PO for multi-level approval">
                {busyId === row.id ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Send className="h-3 w-3 mr-1" />} Submit
              </Button>
            )}
            {AMENDABLE.includes(row.status) && row.amendment_status !== "requested" && (
              <Button size="sm" variant="outline" className="h-7 px-2 rounded-sm" onClick={() => { setAmendFor(row); setAmendReason(""); }} data-testid={`po-amend-${row.id}`} title="Request amendment (requires approval before editing unlocks)">
                <FilePen className="h-3 w-3 mr-1" /> Amend
              </Button>
            )}
            {((row.amendments || []).some((a) => a.before) || (row.status === "amendment_in_progress" && row.pre_amendment_snapshot)) && (
              <Button size="sm" variant="ghost" className="h-7 px-2 text-amber-700" onClick={() => setCompareFor(row)} data-testid={`po-compare-${row.id}`} title="Compare old vs new values across amendments">
                <GitCompareArrows className="h-3 w-3 mr-1" /> Compare
              </Button>
            )}
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setItemsFor(row)} data-testid={`po-items-${row.id}`} title="Preview / edit line items, GST, terms">
              <Table2 className="h-3 w-3 mr-1" /> Items
            </Button>
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setLineageFor(row)} data-testid={`po-lineage-${row.id}`} title="View end-to-end procurement lineage">
              <Network className="h-3 w-3 mr-1" /> Lineage
            </Button>
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setTermsFor(row)} data-testid={`po-terms-${row.id}`} title="Terms & Conditions (printed on PO PDF, fetched into vendor bill)">
              <ListChecks className="h-3 w-3 mr-1" /> Terms
            </Button>
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/procurement/pos/${row.id}/pdf`, `${row.po_number || row.id}.pdf`)} data-testid={`po-pdf-${row.id}`} title="Download PO PDF">
              <FileDown className="h-3 w-3 mr-1" /> PDF
            </Button>
            <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => emailReady && setEmailFor(row)} disabled={!emailReady} data-testid={`purchase-email-${row.id}`} title={emailReady ? "Send PO to vendor" : "Available after final approval of all levels"}>
              <Mail className="h-3 w-3 mr-1" /> Email
            </Button>
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setHistoryFor(row)} data-testid={`po-history-${row.id}`} title="Email send history">
              <History className="h-3 w-3" />
            </Button>
          </div>
        );
      },
    },
  ];
  const fields = [
    { key: "pr_number", label: "PR Number (mandatory — no PO without PR)", full: true },
    { key: "vendor", label: "Vendor Name", full: true },
    { key: "project", label: "Project" },
    { key: "date", label: "Date", type: "date" },
    { key: "total", label: "Total (INR)", type: "number" },
    { key: "paid", label: "Paid (true/false)", type: "select", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] },
  ];
  return (
    <>
      <DataTableShell title="Purchase Orders" description="Requisition → RFQ → PO → GRN. Multi-level approvals. POs lock after final approval — amendments need an approved request." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="purchase" exportResource={r.exportResource} canWrite={r.canWrite} pagination={r.pagination} canDelete={r.canDelete} attachmentsParentType="purchase_orders" />
      <SendEmailDialog
        open={!!emailFor}
        onOpenChange={(o) => !o && setEmailFor(null)}
        module="purchase_order"
        recordId={emailFor?.id}
      />
      {historyFor && (
        <EmailHistoryDialog
          module="purchase_order"
          recordId={historyFor.id}
          recordLabel={historyFor.po_number}
          onClose={() => setHistoryFor(null)}
        />
      )}
      {termsFor && <POTermsDialog po={termsFor} onClose={(saved) => { setTermsFor(null); if (saved) r.reload?.(); }} />}
      {itemsFor && <POItemsDialog po={itemsFor} canWrite={r.canWrite} onClose={(saved) => { setItemsFor(null); if (saved) r.reload?.(); }} />}
      {compareFor && <AmendmentCompareDialog po={compareFor} onClose={() => setCompareFor(null)} />}
      <Dialog open={!!amendFor} onOpenChange={(o) => !o && setAmendFor(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="po-amend-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Request Amendment — {amendFor?.po_number}</DialogTitle>
            <DialogDescription>Justification is mandatory. Purchase Manager & Director must approve before editing unlocks. The amended PO will carry Rev {(Number(amendFor?.revision) || 0) + 1} and re-enter the full approval chain.</DialogDescription>
          </DialogHeader>
          <Textarea rows={3} placeholder="Reason / justification for amendment (min 5 characters)" value={amendReason} onChange={(e) => setAmendReason(e.target.value)} className="rounded-sm" data-testid="po-amend-reason-input" />
          <div className="flex justify-end gap-2">
            <Button variant="outline" className="rounded-sm" onClick={() => setAmendFor(null)} data-testid="po-amend-cancel-btn">Cancel</Button>
            <Button className="rounded-sm" onClick={requestAmendment} disabled={amendReason.trim().length < 5 || busyId === amendFor?.id} data-testid="po-amend-submit-btn">
              {busyId === amendFor?.id && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />} Raise Request
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={!!lineageFor} onOpenChange={(o) => !o && setLineageFor(null)}>
        <DialogContent className="max-w-5xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Procurement Lineage — {lineageFor?.po_number}</DialogTitle>
            <DialogDescription>Full traceability from the originating PR to every GRN posted against this PO.</DialogDescription>
          </DialogHeader>
          {lineageFor && <LineageTrail kind="po" recordId={lineageFor.id} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
