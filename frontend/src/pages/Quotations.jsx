import { useState } from "react";
import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { GitBranch, Sparkles, Mail, ShieldCheck, Send, CheckCircle2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { toneFor } from "@/lib/statusTone";
import { useNavigate } from "react-router-dom";
import SendEmailDialog from "@/components/SendEmailDialog";
import ApprovalDocsGate, { validateApprovalDocs, emptyApprovalDocs } from "@/components/ApprovalDocsGate";

const QUOTE_STATUS_TONE = {
  invoiced: "success", won: "success", sent: "info", submitted: "info",
  under_review: "warning", costing_pending: "warning", revised: "primary",
  lost: "danger", cancelled: "neutral", draft: "neutral",
};
const APPROVAL_TONE = {
  approved: "success", pending: "warning", in_progress: "warning",
  rejected: "danger", rejected_revision_required: "danger",
  additional_info_required: "warning", not_sent: "neutral",
};
const APPROVAL_LABEL = {
  approved: "Approved", pending: "Pending", in_progress: "In Progress",
  rejected: "Rejected", rejected_revision_required: "Revision Required",
  additional_info_required: "Info Needed", not_sent: "Not Sent",
};
const NEXT_STATUS_OPTIONS = {
  draft: ["under_review", "costing_pending", "submitted", "cancelled"],
  under_review: ["costing_pending", "submitted", "draft", "cancelled"],
  costing_pending: ["under_review", "submitted", "draft", "cancelled"],
  submitted: ["revised", "won", "lost", "cancelled"],
  revised: ["submitted", "won", "lost", "cancelled"],
  won: [],
  lost: [],
  cancelled: [],
};

export default function Quotations() {
  const r = useResource("quotations");
  const navigate = useNavigate();
  const [revOpen, setRevOpen] = useState(false);
  const [revRows, setRevRows] = useState([]);
  const [revTitle, setRevTitle] = useState("");
  const [emailFor, setEmailFor] = useState(null);
  const [statusFor, setStatusFor] = useState(null);
  const [statusVal, setStatusVal] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [sendFor, setSendFor] = useState(null);          // { row, isResend }
  const [docsValue, setDocsValue] = useState(emptyApprovalDocs());
  const [sendBusy, setSendBusy] = useState(false);

  const openRevisions = async (row) => {
    try {
      const { data } = await api.get(`/quotations/${row.id}/revisions`);
      setRevRows(data);
      setRevTitle(row.quote_number || row.id);
      setRevOpen(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load revisions");
    }
  };

  const revise = async (row) => {
    if (!window.confirm(`Create a new revision of ${row.quote_number}?`)) return;
    try {
      const { data } = await api.post(`/quotations/${row.id}/revise`);
      toast.success(`Revision ${data.revision_no} created (${data.quote_number})`);
      r.reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Revise failed");
    }
  };

  const openSendDialog = (row, isResend = false) => {
    setSendFor({ row, isResend });
    setDocsValue(emptyApprovalDocs());
  };
  const submitSend = async () => {
    if (!sendFor) return;
    const err = validateApprovalDocs(docsValue);
    if (err) { toast.error(err); return; }
    setSendBusy(true);
    try {
      const { data } = await api.post(`/quotations/${sendFor.row.id}/send-for-approval`, docsValue);
      toast.success(`${sendFor.isResend ? "Re-sent" : "Sent"} for approval — chain restarted from step 1.`);
      setSendFor(null);
      r.reload();
      void data;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Send for approval failed");
    } finally { setSendBusy(false); }
  };

  const openStatus = (row) => {
    setStatusFor(row);
    setStatusVal("");
    setStatusNote("");
  };
  const submitStatus = async () => {
    if (!statusVal) { toast.error("Pick a new status"); return; }
    setStatusBusy(true);
    try {
      const { data } = await api.post(`/quotations/${statusFor.id}/status`, { status: statusVal, note: statusNote || null });
      let msg = `Status → ${statusVal.replaceAll("_", " ")}`;
      if (data?.auto_handover?.handover_no) {
        msg = `Status → won · Handover ${data.auto_handover.handover_no} auto-created`;
      }
      toast.success(msg, { duration: 6000 });
      setStatusFor(null);
      r.reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Status change failed");
    } finally { setStatusBusy(false); }
  };

  const columns = [
    { key: "quote_number", label: "Quote #" },
    { key: "enquiry_no", label: "Enquiry", render: (row) => row.enquiry_no ? <StatusBadge text={row.enquiry_no} tone="info" /> : "—" },
    { key: "revision_no", label: "Rev", render: (row) => <StatusBadge text={`R${row.revision_no || 0}`} tone={row.revision_no ? "primary" : "neutral"} /> },
    { key: "client", label: "Client" },
    { key: "project", label: "Project" },
    { key: "date", label: "Date" },
    { key: "total", label: "Total", render: (row) => "₹ " + Number(row.total || row.amount || 0).toLocaleString("en-IN") },
    {
      key: "approval_status",
      label: "Internal Approval",
      render: (row) => {
        const a = row.approval_status || "not_sent";
        const stepLabel = row.approval_current_step_label;
        const stepIdx = row.approval_current_step_index;
        const stepTotal = row.approval_total_steps;
        // Compose subline only when meaningful
        let sub = null;
        if ((a === "pending" || a === "in_progress") && stepLabel) {
          sub = `Pending at ${stepLabel}${stepTotal ? ` (Step ${(stepIdx ?? 0) + 1}/${stepTotal})` : ""}`;
        } else if (a === "approved") {
          sub = "All steps cleared";
        } else if (a === "rejected" || a === "rejected_revision_required") {
          sub = stepLabel || "Rejected — please re-send";
        } else if (a === "additional_info_required") {
          sub = stepLabel || "Approver requested info";
        }
        return (
          <div className="leading-tight">
            <StatusBadge text={APPROVAL_LABEL[a] || a} tone={APPROVAL_TONE[a] || "neutral"} />
            {sub && <div className="text-[10px] text-muted-foreground mt-0.5 max-w-[180px] truncate" title={sub}>{sub}</div>}
            {(a === "rejected" || a === "rejected_revision_required") && row.approval_reject_reason && (
              <div className="text-[10px] text-destructive mt-0.5 max-w-[180px] truncate" title={row.approval_reject_reason}>
                Reason: {row.approval_reject_reason}
              </div>
            )}
          </div>
        );
      },
    },
    { key: "status", label: "Pipeline", badge: (row) => ({ text: (row.status || "draft").replaceAll("_", " "), tone: toneFor(QUOTE_STATUS_TONE, row.status, "warning") }) },
    {
      key: "_rev_actions",
      label: "Workflow",
      render: (row) => {
        const a = row.approval_status || "not_sent";
        const isRejected = a === "rejected" || a === "rejected_revision_required";
        const canSend = (row.status === "draft" || row.status === "under_review" || row.status === "costing_pending") && a !== "pending" && a !== "in_progress" && a !== "approved";
        return (
          <div className="inline-flex gap-1 flex-wrap">
            <Button size="sm" className="h-7 rounded-sm bg-primary/10 text-primary hover:bg-primary/20 border border-primary/30" onClick={() => navigate(`/app/quotations/${row.id}/builder`)} data-testid={`quotations-builder-${row.id}`}>
              <Sparkles className="h-3 w-3 mr-1" /> AI Builder
            </Button>
            {r.canWrite && canSend && (
              <Button
                size="sm"
                variant="outline"
                className={`h-7 rounded-sm ${isRejected ? "border-destructive text-destructive hover:bg-destructive/5" : "border-amber-400 text-amber-700 hover:bg-amber-50"}`}
                onClick={() => openSendDialog(row, isRejected)}
                data-testid={isRejected ? `quotations-resend-approval-${row.id}` : `quotations-send-approval-${row.id}`}
              >
                <ShieldCheck className="h-3 w-3 mr-1" /> {isRejected ? "Re-send for Approval" : "Send for Approval"}
              </Button>
            )}
            {r.canWrite && a === "approved" && row.status !== "submitted" && row.status !== "won" && row.status !== "lost" && (
              <Button size="sm" className="h-7 rounded-sm" onClick={() => openStatus(row)} data-testid={`quotations-status-${row.id}`}>
                <Send className="h-3 w-3 mr-1" /> Change Status
              </Button>
            )}
            {r.canWrite && (row.status === "submitted" || row.status === "revised") && (
              <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openStatus(row)} data-testid={`quotations-status-${row.id}`}>
                <Send className="h-3 w-3 mr-1" /> Status
              </Button>
            )}
            <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openRevisions(row)} data-testid={`quotations-revisions-${row.id}`}>
              <GitBranch className="h-3 w-3 mr-1" /> History
            </Button>
            <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setEmailFor(row)} data-testid={`quotations-email-${row.id}`}>
              <Mail className="h-3 w-3 mr-1" /> Email
            </Button>
            {r.canWrite && (
              <Button size="sm" className="h-7 rounded-sm" onClick={() => revise(row)} data-testid={`quotations-revise-${row.id}`}>+ Rev</Button>
            )}
          </div>
        );
      },
    },
  ];
  // No status / no manual create — those flows now run through Enquiry + /status endpoint
  const fields = [
    { key: "quote_number", label: "Quote Number" },
    { key: "client", label: "Client" },
    { key: "project", label: "Project / Scope", full: true },
    { key: "date", label: "Date", type: "date" },
    { key: "valid_until", label: "Valid Until", type: "date" },
    { key: "total", label: "Total (INR)", type: "number" },
  ];

  return (
    <>
      <div className="mb-3 px-1 text-xs text-muted-foreground flex items-center gap-1.5" data-testid="quotations-policy-note">
        <AlertCircle className="h-3.5 w-3.5 text-amber-600" />
        Quotations are auto-generated from Enquiries. Visit <button className="underline text-primary" onClick={() => navigate("/app/enquiries")}>Enquiries</button> to register a new one.
      </div>
      <DataTableShell
        title="Sales & Quotations"
        description="Lead → Enquiry → Internal Approval → Quote → Win → Invoice. Direct quote creation is disabled."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={null}
        onUpdate={r.update}
        onDelete={r.remove}
        testidPrefix="quotations"
        exportResource={r.exportResource}
        canWrite={r.canWrite}
        canDelete={r.canDelete}
        attachmentsParentType="quotations"
      />
      <Dialog open={revOpen} onOpenChange={setRevOpen}>
        <DialogContent className="max-w-2xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><GitBranch className="h-4 w-4 text-primary" /> Revisions — {revTitle}</DialogTitle>
            <DialogDescription className="sr-only">All revisions of this quotation chain.</DialogDescription>
          </DialogHeader>
          <ul className="divide-y divide-border max-h-96 overflow-y-auto">
            {revRows.map((rev) => (
              <li key={rev.id} className="py-2.5 flex items-center gap-3 text-sm" data-testid={`revision-${rev.id}`}>
                <StatusBadge text={`R${rev.revision_no || 0}`} tone={rev.revision_no ? "primary" : "neutral"} />
                <div className="flex-1">
                  <div className="font-semibold">{rev.quote_number}</div>
                  <div className="text-[11px] text-muted-foreground">{rev.date} · {rev.client}</div>
                </div>
                <div className="text-sm tabular">₹ {Number(rev.total || 0).toLocaleString("en-IN")}</div>
                <StatusBadge text={rev.status} tone={toneFor(QUOTE_STATUS_TONE, rev.status, "warning")} />
              </li>
            ))}
            {revRows.length === 0 && <li className="text-center text-xs text-muted-foreground py-6">No revisions found.</li>}
          </ul>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRevOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Status change dialog */}
      <Dialog open={!!statusFor} onOpenChange={(o) => !o && setStatusFor(null)}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Send className="h-4 w-4 text-primary" />Change Quotation Status</DialogTitle>
            <DialogDescription>
              {statusFor && (
                <span>
                  {statusFor.quote_number} · current: <b>{statusFor.status}</b>
                  {statusFor.approval_status && (<span> · approval: <b>{statusFor.approval_status}</b></span>)}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          {statusFor && (
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground">New Status</label>
                <select
                  value={statusVal}
                  onChange={(e) => setStatusVal(e.target.value)}
                  className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm"
                  data-testid="quotations-status-select"
                >
                  <option value="">— select —</option>
                  {(NEXT_STATUS_OPTIONS[statusFor.status] || []).map((s) => (
                    <option key={s} value={s}>{s.replaceAll("_", " ")}</option>
                  ))}
                </select>
                {statusFor.approval_status !== "approved" && (
                  <div className="text-xs text-amber-700 mt-1.5 flex items-start gap-1">
                    <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                    Internal approval required before status can move to <b>submitted</b>.
                  </div>
                )}
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Note (optional)</label>
                <textarea
                  className="w-full min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm mt-1"
                  value={statusNote}
                  onChange={(e) => setStatusNote(e.target.value)}
                  data-testid="quotations-status-note"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setStatusFor(null)}>Cancel</Button>
            <Button className="rounded-sm" disabled={statusBusy || !statusVal} onClick={submitStatus} data-testid="quotations-status-confirm">
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <SendEmailDialog
        open={!!emailFor}
        onOpenChange={(o) => !o && setEmailFor(null)}
        module="quotation"
        recordId={emailFor?.id}
      />

      {/* Iter 63 — Send/Re-send for Approval dialog with universal docs gate */}
      <Dialog open={!!sendFor} onOpenChange={(o) => !o && setSendFor(null)}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              {sendFor?.isResend ? "Re-send for Approval" : "Send for Approval"}
            </DialogTitle>
            <DialogDescription>
              {sendFor && (
                <span>
                  {sendFor.row.quote_number} · {sendFor.row.client || "—"} · ₹ {Number(sendFor.row.total || 0).toLocaleString("en-IN")}
                  {sendFor.isResend && <span className="block text-amber-700 mt-1">A new approval will be created — the chain restarts from step 1.</span>}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          {sendFor && (
            <ApprovalDocsGate
              parentType="quotations"
              parentId={sendFor.row.id}
              value={docsValue}
              onChange={setDocsValue}
              testidPrefix="quote-send-docs"
            />
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setSendFor(null)} disabled={sendBusy}>Cancel</Button>
            <Button className="rounded-sm" onClick={submitSend} disabled={sendBusy} data-testid="quote-send-confirm">
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> {sendBusy ? "Sending…" : (sendFor?.isResend ? "Re-send" : "Send for Approval")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
