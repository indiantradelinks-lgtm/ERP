import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { CheckCircle2, XCircle, MessageSquare, Clock, ChevronRight, ShieldCheck } from "lucide-react";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

export default function ApprovalDetail({ approval, open, onOpenChange, onUpdated }) {
  const { user } = useAuth();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  if (!approval) return null;

  const chain = approval.chain || [];
  const history = approval.history || [];
  const idx = approval.current_step ?? 0;
  const step = chain[idx];
  const terminal = approval.status === "approved" || approval.status === "rejected";
  const isMyTurn = !terminal && step && (user?.role === "super_admin" || user?.role === step.role);

  const act = async (action) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/approvals/${approval.id}/action`, { action, comment: comment || null });
      toast.success(action === "approve" ? "Approved" : action === "reject" ? "Rejected" : "Comment added");
      setComment("");
      onUpdated?.(data);
      if (action !== "comment") onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl rounded-sm" data-testid="approval-detail">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-primary" />
            {approval.title}
          </DialogTitle>
        </DialogHeader>

        <div className="grid md:grid-cols-2 gap-6 py-2">
          <div className="space-y-3">
            <Row label="Type" value={approval.type?.replaceAll("_", " ")} />
            <Row label="Reference" value={approval.reference || "—"} />
            <Row label="Amount" value={approval.amount ? "₹ " + Number(approval.amount).toLocaleString("en-IN") : "—"} />
            <Row label="Requested By" value={approval.requested_by || "—"} />
            <Row label="Status" valueNode={<StatusBadge text={approval.status || "pending"} tone={approval.status === "approved" ? "success" : approval.status === "rejected" ? "danger" : "warning"} />} />
            <Row label="Current Step" value={step ? `${idx + 1} / ${chain.length} · ${step.label}` : "—"} />
          </div>

          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">Approval Chain</div>
            <div className="space-y-1.5">
              {chain.map((s, i) => {
                const isCurrent = i === idx && !terminal;
                const isDone = i < idx || s.status === "approved";
                const isRejected = s.status === "rejected";
                return (
                  <div
                    key={i}
                    className={cn(
                      "flex items-center gap-3 p-2.5 border rounded-sm text-sm",
                      isCurrent && "border-primary/60 bg-primary/5",
                      isDone && "border-success/40 bg-success/5",
                      isRejected && "border-destructive/40 bg-destructive/5"
                    )}
                  >
                    <div className={cn(
                      "h-7 w-7 rounded-sm grid place-items-center text-xs font-bold",
                      isCurrent ? "bg-primary text-primary-foreground" :
                      isDone ? "bg-success text-success-foreground" :
                      isRejected ? "bg-destructive text-destructive-foreground" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {isDone ? <CheckCircle2 className="h-3.5 w-3.5" /> : isRejected ? <XCircle className="h-3.5 w-3.5" /> : i + 1}
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-xs">{s.label}</div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{s.role?.replaceAll("_", " ")}</div>
                    </div>
                    {s.approver && (
                      <div className="text-right text-[10px] text-muted-foreground">
                        <div className="font-semibold text-foreground">{s.approver}</div>
                        <div>{s.at?.slice(0, 16).replace("T", " ")}</div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">History</div>
          <div className="border border-border rounded-sm max-h-48 overflow-y-auto">
            {history.length === 0 ? (
              <div className="p-4 text-center text-xs text-muted-foreground">No activity yet.</div>
            ) : (
              <ul className="divide-y divide-border">
                {history.map((h, i) => (
                  <li key={i} className="p-2.5 flex items-start gap-3 text-xs">
                    <div className={cn(
                      "h-6 w-6 rounded-sm grid place-items-center shrink-0",
                      h.action === "approve" ? "bg-success/15 text-success" :
                      h.action === "reject" ? "bg-destructive/15 text-destructive" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {h.action === "approve" ? <CheckCircle2 className="h-3.5 w-3.5" /> : h.action === "reject" ? <XCircle className="h-3.5 w-3.5" /> : <MessageSquare className="h-3.5 w-3.5" />}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{h.by}</span>
                        <span className="text-muted-foreground">{(h.by_role || "").replaceAll("_", " ")}</span>
                        <ChevronRight className="h-3 w-3 text-muted-foreground" />
                        <span className="capitalize">{h.action}</span>
                        <span className="text-muted-foreground">· {h.step_label}</span>
                      </div>
                      {h.comment && <div className="text-muted-foreground mt-0.5">"{h.comment}"</div>}
                    </div>
                    <div className="text-[10px] text-muted-foreground flex items-center gap-1 shrink-0">
                      <Clock className="h-3 w-3" /> {h.at?.slice(0, 16).replace("T", " ")}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {!terminal && (
          <div className="pt-2">
            <Label className="text-xs uppercase tracking-wider">Comment</Label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={isMyTurn ? "Optional comment with your action…" : "Add a note (any approver in the chain can comment)"}
              className="mt-1.5 w-full min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm"
              data-testid="approval-comment"
            />
          </div>
        )}

        <DialogFooter className="flex-wrap gap-2">
          {!terminal && (
            <>
              <Button variant="outline" className="rounded-sm" onClick={() => act("comment")} disabled={busy || !comment} data-testid="approval-comment-btn">
                <MessageSquare className="h-4 w-4 mr-1.5" /> Comment
              </Button>
              <Button
                variant="outline"
                className="rounded-sm border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={() => act("reject")}
                disabled={busy || !isMyTurn}
                data-testid="approval-reject-btn"
                title={!isMyTurn ? `Only ${step?.role?.replaceAll("_", " ")} can act on this step` : undefined}
              >
                <XCircle className="h-4 w-4 mr-1.5" /> Reject
              </Button>
              <Button
                className="rounded-sm bg-success text-success-foreground hover:opacity-90"
                onClick={() => act("approve")}
                disabled={busy || !isMyTurn}
                data-testid="approval-approve-btn"
                title={!isMyTurn ? `Only ${step?.role?.replaceAll("_", " ")} can act on this step` : undefined}
              >
                <CheckCircle2 className="h-4 w-4 mr-1.5" /> Approve
              </Button>
            </>
          )}
          <Button variant="ghost" onClick={() => onOpenChange(false)} className="rounded-sm">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
