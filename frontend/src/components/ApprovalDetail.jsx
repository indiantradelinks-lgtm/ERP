import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, MessageSquare, Clock, ChevronRight, ShieldCheck, FileQuestion, RotateCcw, Paperclip, GitCompare, FileDown, ExternalLink } from "lucide-react";
import { StatusBadge } from "@/components/DataTableShell";
import VersionCompare from "@/components/VersionCompare";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

function statusTone(status) {
  if (status === "approved") return "success";
  if (status === "rejected" || status === "rejected_revision_required") return "danger";
  if (status === "additional_info_required") return "warning";
  if (status === "resubmitted") return "info";
  return "warning";
}

function statusLabel(status) {
  const map = {
    rejected_revision_required: "Rejected — Revision Required",
    additional_info_required: "Additional Info Required",
    in_progress: "In Progress",
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
    resubmitted: "Resubmitted",
  };
  return map[status] || status || "pending";
}

const TERMINAL = new Set(["approved"]);   // Iter 50: rejection is NOT terminal
const BOUNCED_BACK = new Set(["rejected_revision_required", "additional_info_required", "rejected"]);

function stepState(step, idx, currentIdx, terminal) {
  return {
    isCurrent: idx === currentIdx && !terminal,
    isDone: idx < currentIdx || step.status === "approved",
    isRejected: step.status === "rejected",
    isInfoRequested: step.status === "info_requested",
  };
}

function ChainStep({ step, idx, currentIdx, terminal }) {
  const { isCurrent, isDone, isRejected } = stepState(step, idx, currentIdx, terminal);
  const badgeCls = cn(
    "h-7 w-7 rounded-sm grid place-items-center text-xs font-bold",
    isCurrent && "bg-primary text-primary-foreground",
    isDone && !isCurrent && "bg-success text-success-foreground",
    isRejected && "bg-destructive text-destructive-foreground",
    !isCurrent && !isDone && !isRejected && "bg-muted text-muted-foreground"
  );
  let icon = idx + 1;
  if (isDone) icon = <CheckCircle2 className="h-3.5 w-3.5" />;
  else if (isRejected) icon = <XCircle className="h-3.5 w-3.5" />;
  return (
    <div
      data-testid={`approval-chain-step-${idx}`}
      className={cn(
        "flex items-center gap-3 p-2.5 border rounded-sm text-sm",
        isCurrent && "border-primary/60 bg-primary/5",
        isDone && "border-success/40 bg-success/5",
        isRejected && "border-destructive/40 bg-destructive/5"
      )}
    >
      <div className={badgeCls}>{icon}</div>
      <div className="flex-1">
        <div className="font-semibold text-xs">{step.label}</div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {step.role?.replaceAll("_", " ")}
        </div>
      </div>
      {step.approver && (
        <div className="text-right text-[10px] text-muted-foreground">
          <div className="font-semibold text-foreground">{step.approver}</div>
          <div>{step.at?.slice(0, 16).replace("T", " ")}</div>
        </div>
      )}
    </div>
  );
}

function historyIcon(action) {
  if (action === "approve") return <CheckCircle2 className="h-3.5 w-3.5" />;
  if (action === "reject") return <XCircle className="h-3.5 w-3.5" />;
  if (action === "request_info") return <FileQuestion className="h-3.5 w-3.5" />;
  if (action === "resubmit") return <RotateCcw className="h-3.5 w-3.5" />;
  return <MessageSquare className="h-3.5 w-3.5" />;
}

function historyTone(action) {
  if (action === "approve") return "bg-success/15 text-success";
  if (action === "reject") return "bg-destructive/15 text-destructive";
  if (action === "request_info") return "bg-amber-100 text-amber-700";
  if (action === "resubmit") return "bg-blue-100 text-blue-700";
  return "bg-muted text-muted-foreground";
}

function HistoryEntry({ h, idx }) {
  return (
    <li data-testid={`approval-history-entry-${idx}`} className="p-2.5 flex items-start gap-3 text-xs">
      <div className={cn("h-6 w-6 rounded-sm grid place-items-center shrink-0", historyTone(h.action))}>
        {historyIcon(h.action)}
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold">{h.by}</span>
          <span className="text-muted-foreground">{(h.by_role || "").replaceAll("_", " ")}</span>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="capitalize">{(h.action || "").replaceAll("_", " ")}</span>
          {h.step_label && <span className="text-muted-foreground">· {h.step_label}</span>}
          {h.version && <Badge variant="outline" className="text-[9px] py-0 px-1 h-4">v{h.version}</Badge>}
        </div>
        {h.comment && <div className="text-muted-foreground mt-0.5 italic">"{h.comment}"</div>}
        {(h.required_documents?.length > 0) && (
          <div className="mt-1 text-[10px]">
            <span className="text-muted-foreground">Required:</span>{" "}
            {h.required_documents.map((d) => (
              <Badge key={d} variant="outline" className="ml-1 text-[9px] py-0 px-1 h-4">{d}</Badge>
            ))}
            {h.deadline && <span className="ml-2 text-amber-600">· due {h.deadline}</span>}
          </div>
        )}
        {(h.file_ids?.length > 0) && (
          <div className="mt-1 text-[10px] text-muted-foreground flex items-center gap-1">
            <Paperclip className="h-3 w-3" /> {h.file_ids.length} attachment{h.file_ids.length > 1 ? "s" : ""}
          </div>
        )}
      </div>
      <div className="text-[10px] text-muted-foreground flex items-center gap-1 shrink-0">
        <Clock className="h-3 w-3" /> {h.at?.slice(0, 16).replace("T", " ")}
      </div>
    </li>
  );
}

function Row({ label, value, valueNode }) {
  return (
    <div className="flex items-center justify-between text-sm border-b border-border pb-2">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      {valueNode || <span className="font-semibold">{value}</span>}
    </div>
  );
}

function ActionFooter({ busy, isMyTurn, comment, step, onAct, onClose, onOpenReject, onOpenRequestInfo }) {
  const blockedTitle = !isMyTurn ? `Only ${step?.role?.replaceAll("_", " ")} can act on this step` : undefined;
  return (
    <>
      <Button variant="outline" className="rounded-sm" onClick={() => onAct("comment")} disabled={busy || !comment} data-testid="approval-comment-btn">
        <MessageSquare className="h-4 w-4 mr-1.5" /> Comment
      </Button>
      <Button
        variant="outline"
        className="rounded-sm border-amber-300 text-amber-700 hover:bg-amber-50"
        onClick={onOpenRequestInfo}
        disabled={busy || !isMyTurn}
        data-testid="approval-request-info-btn"
        title={blockedTitle}
      >
        <FileQuestion className="h-4 w-4 mr-1.5" /> Request Info
      </Button>
      <Button
        variant="outline"
        className="rounded-sm border-destructive/50 text-destructive hover:bg-destructive/10"
        onClick={onOpenReject}
        disabled={busy || !isMyTurn}
        data-testid="approval-reject-btn"
        title={blockedTitle}
      >
        <XCircle className="h-4 w-4 mr-1.5" /> Reject
      </Button>
      <Button
        className="rounded-sm bg-success text-success-foreground hover:opacity-90"
        onClick={() => onAct("approve")}
        disabled={busy || !isMyTurn}
        data-testid="approval-approve-btn"
        title={blockedTitle}
      >
        <CheckCircle2 className="h-4 w-4 mr-1.5" /> Approve
      </Button>
      <Button variant="ghost" onClick={onClose} className="rounded-sm">Close</Button>
    </>
  );
}

function RejectDialog({ open, onClose, onConfirm, busy }) {
  const [comment, setComment] = useState("");
  const valid = comment.trim().length >= 5;
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg rounded-sm" data-testid="approval-reject-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2 text-destructive">
            <XCircle className="h-5 w-5" /> Reject — Revision Required
          </DialogTitle>
          <DialogDescription>
            The request will return to the originator with your remarks. A clear reason is mandatory (min 5 characters).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <Label className="text-xs uppercase tracking-wider">Rejection reason & required corrections *</Label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="e.g. Budget allocation does not match approved project estimate. Please revise manpower cost and upload revised cost sheet."
            className="w-full min-h-[100px] rounded-sm border border-input bg-background p-2 text-sm"
            data-testid="approval-reject-reason"
          />
          <div className="text-[10px] text-muted-foreground">
            {comment.trim().length}/5 characters minimum
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button
            className="rounded-sm bg-destructive text-destructive-foreground"
            disabled={!valid || busy}
            onClick={() => { onConfirm(comment.trim()); setComment(""); }}
            data-testid="approval-reject-confirm"
          >
            Send back for revision
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RequestInfoDialog({ open, onClose, onConfirm, busy }) {
  const [comment, setComment] = useState("");
  const [docs, setDocs] = useState("");
  const [deadline, setDeadline] = useState("");
  const valid = comment.trim().length >= 5;
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg rounded-sm" data-testid="approval-request-info-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2 text-amber-700">
            <FileQuestion className="h-5 w-5" /> Request Additional Documents
          </DialogTitle>
          <DialogDescription>
            The request will return to the originator. Specify what's needed (min 5-char remark required).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <Label className="text-xs uppercase tracking-wider">Clarification / remark *</Label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="What do you need from the originator?"
              className="mt-1 w-full min-h-[80px] rounded-sm border border-input bg-background p-2 text-sm"
              data-testid="approval-request-info-comment"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Required documents (comma-separated)</Label>
            <Input
              value={docs}
              onChange={(e) => setDocs(e.target.value)}
              placeholder="Vendor PAN, Last 3 invoices, BOQ"
              data-testid="approval-request-info-docs"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Deadline (optional)</Label>
            <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} data-testid="approval-request-info-deadline" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button
            className="rounded-sm bg-amber-600 text-white hover:bg-amber-700"
            disabled={!valid || busy}
            onClick={() => {
              const docList = docs.split(",").map((d) => d.trim()).filter(Boolean);
              onConfirm({ comment: comment.trim(), required_documents: docList, deadline: deadline || null });
              setComment(""); setDocs(""); setDeadline("");
            }}
            data-testid="approval-request-info-confirm"
          >
            Send request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResubmitDialog({ open, onClose, onConfirm, busy, approval }) {
  const [comment, setComment] = useState("");
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg rounded-sm" data-testid="approval-resubmit-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2 text-blue-700">
            <RotateCcw className="h-5 w-5" /> Resubmit for Approval
          </DialogTitle>
          <DialogDescription>
            Submits a revised version (v{approval?.version || "1.0"} → next). Previous approval & rejection history is preserved.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {approval?.last_reject_reason && (
            <div className="p-2 border rounded-sm bg-rose-50 border-rose-200 text-xs">
              <div className="font-semibold text-rose-700">Original rejection:</div>
              <div className="italic mt-1">"{approval.last_reject_reason}"</div>
            </div>
          )}
          <div>
            <Label className="text-xs uppercase tracking-wider">Resubmission note</Label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Briefly describe what you've changed since the rejection / info request."
              className="mt-1 w-full min-h-[80px] rounded-sm border border-input bg-background p-2 text-sm"
              data-testid="approval-resubmit-comment"
            />
          </div>
          <div className="text-[10px] text-muted-foreground">
            Tip: upload any new supporting docs separately via the Attachments tab before resubmitting.
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button
            className="rounded-sm bg-blue-600 text-white hover:bg-blue-700"
            disabled={busy}
            onClick={() => { onConfirm(comment.trim()); setComment(""); }}
            data-testid="approval-resubmit-confirm"
          >
            Resubmit for approval
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RecordDocumentsPanel({ preview }) {
  if (!preview) return (
    <div className="text-[11px] text-muted-foreground py-2">Loading record documents…</div>
  );
  const docs = preview.documents || [];
  const pdfUrl = preview.pdf_url;
  if (docs.length === 0 && !pdfUrl) return null;
  const base = process.env.REACT_APP_BACKEND_URL;
  return (
    <div data-testid="approval-documents-panel">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Supporting Documents</div>
        {pdfUrl && (
          <a
            href={`${base}${pdfUrl}`}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-medium text-blue-700 hover:underline flex items-center gap-1"
            data-testid="approval-record-pdf"
          >
            <FileDown className="h-3 w-3" /> View {preview.type?.replaceAll("_", " ")} PDF
          </a>
        )}
      </div>
      {docs.length > 0 ? (
        <div className="border border-border rounded-sm divide-y divide-border max-h-44 overflow-y-auto">
          {docs.map((d) => {
            const url = `${base}/api/files/${d.file_id}/download`;
            const kb = d.size ? `${(d.size / 1024).toFixed(1)} KB` : "";
            return (
              <div key={d.file_id} className="flex items-center gap-2 px-2 py-1.5 text-xs" data-testid={`approval-doc-${d.file_id}`}>
                <Paperclip className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="flex-1 truncate">
                  <span className="font-medium">{d.name || d.file_id}</span>
                  {d.type && <span className="ml-2 text-[10px] uppercase tracking-wider text-muted-foreground">[{d.type}]</span>}
                  {d.expiry && <span className="ml-2 text-amber-700">· exp {d.expiry}</span>}
                </span>
                <span className="text-[10px] text-muted-foreground tabular">{kb}</span>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="h-6 px-2 grid place-items-center rounded-sm border bg-white text-blue-700 hover:bg-blue-50"
                  title="Open / preview"
                  data-testid={`approval-doc-${d.file_id}-preview`}
                >
                  <ExternalLink className="h-3 w-3" />
                </a>
                <a
                  href={url}
                  download={d.name || "file"}
                  className="h-6 w-6 grid place-items-center rounded-sm border bg-white"
                  title="Download"
                  data-testid={`approval-doc-${d.file_id}-download`}
                >
                  <FileDown className="h-3 w-3" />
                </a>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-[11px] text-muted-foreground italic py-1">No attachments uploaded on this record.</div>
      )}
    </div>
  );
}



export default function ApprovalDetail({ approval, open, onOpenChange, onUpdated }) {
  const { user } = useAuth();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [resubmitOpen, setResubmitOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!open || !approval?.id) { setPreview(null); return; }
    (async () => {
      try {
        const { data } = await api.get(`/approvals/${approval.id}/record-preview`);
        setPreview(data);
      } catch {
        setPreview({ documents: [] });
      }
    })();
  }, [open, approval?.id]);

  if (!approval) return null;

  const chain = approval.chain || [];
  const history = approval.history || [];
  const idx = approval.current_step ?? 0;
  const step = chain[idx];
  const terminal = TERMINAL.has(approval.status);
  const bouncedBack = BOUNCED_BACK.has(approval.status);
  const isMyTurn = !terminal && !bouncedBack && step && (user?.role === "super_admin" || user?.role === step.role);
  // Originator can resubmit if status is bounced-back AND they own this approval
  const me = user?.name || user?.email || user?.id;
  const isCreator = (approval.created_by === me) || (approval.requested_by === me) ||
                    (approval.created_by_email === user?.email);
  const canResubmit = bouncedBack && (isCreator || user?.role === "super_admin" || user?.role === "hr_executive");

  const act = async (action, extra = {}) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/approvals/${approval.id}/action`, { action, comment: comment || extra.comment || null, ...extra });
      let msg = "Comment added";
      if (action === "approve") msg = "Approved";
      else if (action === "reject") msg = "Sent back for revision";
      else if (action === "request_info") msg = "Information request sent";
      toast.success(msg);
      setComment("");
      setRejectOpen(false);
      setInfoOpen(false);
      onUpdated?.(data);
      if (action !== "comment") onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const doReject = (reason) => act("reject", { comment: reason });
  const doRequestInfo = ({ comment: c, required_documents, deadline }) =>
    act("request_info", { comment: c, required_documents, deadline });

  const doResubmit = async (note) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/approvals/${approval.id}/resubmit`, { comment: note });
      toast.success(`Resubmitted as v${data.version}`);
      setResubmitOpen(false);
      onUpdated?.(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Resubmit failed");
    } finally {
      setBusy(false);
    }
  };

  const amount = approval.amount ? "₹ " + Number(approval.amount).toLocaleString("en-IN") : "—";
  const stepLabel = step ? `${idx + 1} / ${chain.length} · ${step.label}` : "—";
  let placeholder = "Add a note (any approver in the chain can comment)";
  if (isMyTurn) placeholder = "Optional comment with your action…";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl rounded-sm" data-testid="approval-detail">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-primary" />
            {approval.title}
            {approval.version && approval.version !== "1.0" && (
              <>
                <Badge variant="outline" className="text-xs">v{approval.version}</Badge>
                <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]" onClick={() => setCompareOpen(true)} data-testid="open-version-compare">
                  <GitCompare className="h-3 w-3 mr-1" /> Compare
                </Button>
              </>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Approval workflow detail — review chain, history and take action on this request.
          </DialogDescription>
        </DialogHeader>

        {bouncedBack && (
          <div className="p-3 border rounded-sm bg-amber-50 border-amber-200 text-xs space-y-1" data-testid="approval-bounced-banner">
            <div className="font-semibold text-amber-900">
              {approval.status === "additional_info_required" ? "Additional information requested" : "Revision required"}
              {approval.last_reject_by && <span className="font-normal"> by {approval.last_reject_by}</span>}
            </div>
            {approval.last_reject_reason && <div className="italic text-amber-800">"{approval.last_reject_reason}"</div>}
            {approval.last_info_request?.required_documents?.length > 0 && (
              <div>
                <span className="text-amber-900 font-medium">Documents needed:</span>
                {" "}{approval.last_info_request.required_documents.join(", ")}
                {approval.last_info_request.deadline && <span className="ml-2">· due {approval.last_info_request.deadline}</span>}
              </div>
            )}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6 py-2">
          <div className="space-y-3">
            <Row label="Type" value={approval.type?.replaceAll("_", " ")} />
            <Row label="Reference" value={approval.reference || approval.record_id || "—"} />
            <Row label="Amount" value={amount} />
            <Row label="Requested By" value={approval.requested_by || approval.created_by || "—"} />
            <Row label="Version" value={`v${approval.version || "1.0"}${approval.resubmit_count ? ` · ${approval.resubmit_count} revision${approval.resubmit_count > 1 ? "s" : ""}` : ""}`} />
            <Row label="Status" valueNode={<StatusBadge text={statusLabel(approval.status)} tone={statusTone(approval.status)} />} />
            <Row label="Current Step" value={stepLabel} />
          </div>

          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">Approval Chain</div>
            <div className="space-y-1.5">
              {chain.map((s, i) => (
                <ChainStep key={`${s.role}-${i}`} step={s} idx={i} currentIdx={idx} terminal={terminal} />
              ))}
            </div>
          </div>
        </div>

        {/* Record documents (Iter 57) — files uploaded with the underlying record + composed PDF if available */}
        <RecordDocumentsPanel preview={preview} />

        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">History</div>
          <div className="border border-border rounded-sm max-h-48 overflow-y-auto">
            {history.length === 0 ? (
              <div className="p-4 text-center text-xs text-muted-foreground">No activity yet.</div>
            ) : (
              <ul className="divide-y divide-border">
                {history.map((h, i) => (
                  <HistoryEntry key={`${h.at || ""}-${h.by_id || i}`} h={h} idx={i} />
                ))}
              </ul>
            )}
          </div>
        </div>

        {!terminal && !bouncedBack && (
          <div className="pt-2">
            <Label className="text-xs uppercase tracking-wider">Comment</Label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={placeholder}
              className="mt-1.5 w-full min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm"
              data-testid="approval-comment"
            />
          </div>
        )}

        <DialogFooter className="flex-wrap gap-2">
          {terminal && <Button variant="ghost" onClick={() => onOpenChange(false)} className="rounded-sm">Close</Button>}
          {canResubmit && (
            <>
              <Button
                className="rounded-sm bg-blue-600 text-white hover:bg-blue-700"
                onClick={() => setResubmitOpen(true)}
                disabled={busy}
                data-testid="approval-resubmit-btn"
              >
                <RotateCcw className="h-4 w-4 mr-1.5" /> Resubmit for Approval
              </Button>
              <Button variant="ghost" onClick={() => onOpenChange(false)} className="rounded-sm">Close</Button>
            </>
          )}
          {!terminal && !bouncedBack && (
            <ActionFooter
              busy={busy}
              isMyTurn={isMyTurn}
              comment={comment}
              step={step}
              onAct={act}
              onClose={() => onOpenChange(false)}
              onOpenReject={() => setRejectOpen(true)}
              onOpenRequestInfo={() => setInfoOpen(true)}
            />
          )}
        </DialogFooter>

        <RejectDialog open={rejectOpen} onClose={() => setRejectOpen(false)} onConfirm={doReject} busy={busy} />
        <RequestInfoDialog open={infoOpen} onClose={() => setInfoOpen(false)} onConfirm={doRequestInfo} busy={busy} />
        <ResubmitDialog open={resubmitOpen} onClose={() => setResubmitOpen(false)} onConfirm={doResubmit} busy={busy} approval={approval} />
        <VersionCompare approvalId={approval.id} open={compareOpen} onClose={() => setCompareOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}
