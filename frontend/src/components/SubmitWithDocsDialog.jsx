/**
 * SubmitWithDocsDialog — single shared dialog for any "Submit / Send for Approval"
 * flow that needs to satisfy the universal approval-docs gate.
 *
 * Usage:
 *   <SubmitWithDocsDialog
 *     open={!!submitFor} onOpenChange={(o) => !o && setSubmitFor(null)}
 *     title="Submit Purchase Requisition"
 *     description={submitFor && `${submitFor.pr_number} · ₹ ${submitFor.total}`}
 *     endpoint={submitFor ? `/procurement/prs/${submitFor.id}/submit` : null}
 *     parentType="purchase_requisitions"
 *     parentId={submitFor?.id}
 *     onSuccess={() => { setSubmitFor(null); load(); }}
 *   />
 */
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ShieldCheck, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import ApprovalDocsGate, { validateApprovalDocs, emptyApprovalDocs } from "@/components/ApprovalDocsGate";

export default function SubmitWithDocsDialog({
  open,
  onOpenChange,
  title = "Submit for Approval",
  description,
  endpoint,
  method = "POST",
  parentType,
  parentId,
  extraPayload = {},
  ctaLabel = "Submit",
  onSuccess,
  testidPrefix = "submit-docs",
}) {
  const [value, setValue] = useState(emptyApprovalDocs());
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) setValue(emptyApprovalDocs()); }, [open]);

  const handleSubmit = async () => {
    const err = validateApprovalDocs(value);
    if (err) { toast.error(err); return; }
    if (!endpoint) { toast.error("Missing endpoint"); return; }
    setBusy(true);
    try {
      const payload = { ...extraPayload, ...value };
      const fn = method === "PUT" ? api.put : api.post;
      const r = await fn(endpoint, payload);
      toast.success("Submitted for approval");
      onSuccess?.(r.data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Submission failed");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" /> {title}
          </DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <ApprovalDocsGate
          parentType={parentType}
          parentId={parentId}
          value={value}
          onChange={setValue}
          testidPrefix={testidPrefix}
        />
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button className="rounded-sm" onClick={handleSubmit} disabled={busy} data-testid={`${testidPrefix}-confirm`}>
            <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> {busy ? "Submitting…" : ctaLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
