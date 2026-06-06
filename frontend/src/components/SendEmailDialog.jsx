/**
 * Reusable Send-via-Email dialog used by Quotations, POs, RFQs, RA Bills, HR Letters.
 *
 * Usage:
 *   const [open, setOpen] = useState(false);
 *   <Button onClick={() => setOpen(true)}>Email</Button>
 *   <SendEmailDialog
 *     open={open}
 *     onOpenChange={setOpen}
 *     module="quotation"
 *     recordId={quotation.id}
 *     onSent={(outboxId) => toast.success("Sent")}
 *   />
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Paperclip, Sparkles, Send, Mail, Info } from "lucide-react";
import { toast } from "sonner";

export default function SendEmailDialog({ open, onOpenChange, module, recordId, onSent }) {
  const [ctx, setCtx] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [bcc, setBcc] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachPdf, setAttachPdf] = useState(true);
  const [tone, setTone] = useState("professional");

  useEffect(() => {
    if (!open || !module || !recordId) return;
    setLoading(true);
    setCtx(null);
    api.get(`/email/entity-context/${module}/${recordId}`)
      .then(({ data }) => {
        setCtx(data);
        setTo((data.to || []).join(", "));
        setSubject(data.subject || "");
        setBody(data.body || "");
        setCc("");
        setBcc("");
        setAttachPdf(true);
      })
      .catch((e) => {
        toast.error(e.response?.data?.detail || "Could not load record context");
        onOpenChange(false);
      })
      .finally(() => setLoading(false));
  }, [open, module, recordId, onOpenChange]);

  const draft = async () => {
    setDrafting(true);
    try {
      const { data } = await api.post(`/email/ai-draft`, { module, record_id: recordId, tone });
      setSubject(data.subject || subject);
      setBody(data.body || body);
      toast.success("AI cover-note drafted");
    } catch (e) {
      toast.error(e.response?.data?.detail || "AI draft failed");
    } finally {
      setDrafting(false);
    }
  };

  const send = async () => {
    const toList = to.split(",").map((s) => s.trim()).filter(Boolean);
    if (toList.length === 0) {
      toast.error("Recipient required");
      return;
    }
    if (!subject.trim() || !body.trim()) {
      toast.error("Subject and body are required");
      return;
    }
    setSending(true);
    try {
      const { data } = await api.post(`/email/send-entity/${module}/${recordId}`, {
        to: toList,
        cc: cc.split(",").map((s) => s.trim()).filter(Boolean),
        bcc: bcc.split(",").map((s) => s.trim()).filter(Boolean),
        subject,
        body_text: body,
        attach_pdf: attachPdf,
      });
      toast.success(`Queued via ${data.sender_type} mailbox${(data.attached || []).length ? " · PDF attached" : ""}`);
      if (onSent) onSent(data.outbox_id);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Send failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="send-email-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Send {ctx?.module_label || module} · {ctx?.record_no || ""}
          </DialogTitle>
          <DialogDescription>
            {ctx ? (
              <span className="text-xs flex flex-wrap items-center gap-2 mt-1">
                <Badge variant="outline">{ctx.to_label}</Badge>
                <Badge variant={ctx.sender_type === "user" ? "default" : "secondary"}>
                  From {ctx.sender_type === "user" ? "your mailbox" : "shared mailbox"}
                </Badge>
                {ctx.sender_fallback_reason && (
                  <span className="text-warning inline-flex items-center gap-1">
                    <Info className="h-3 w-3" /> {ctx.sender_fallback_reason}
                  </span>
                )}
              </span>
            ) : "Loading…"}
          </DialogDescription>
        </DialogHeader>

        {loading && <div className="py-8 text-sm text-muted-foreground text-center">Loading record…</div>}

        {!loading && ctx && (
          <div className="space-y-3 pt-1">
            <div className="rounded-sm border border-violet-500/30 bg-violet-500/5 p-3 flex flex-wrap items-end gap-2">
              <div className="flex-1 min-w-[140px]">
                <Label className="text-[10px] uppercase tracking-wider text-violet-600 flex items-center gap-1">
                  <Sparkles className="h-3 w-3" /> AI Cover-Note (Claude Sonnet 4.5)
                </Label>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  Replaces the subject and body with a polished business email based on the record details.
                </div>
              </div>
              <div className="min-w-[140px]">
                <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Tone</Label>
                <Select value={tone} onValueChange={setTone}>
                  <SelectTrigger data-testid="ai-tone-select" className="h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="professional">Professional</SelectItem>
                    <SelectItem value="friendly">Friendly</SelectItem>
                    <SelectItem value="firm">Firm</SelectItem>
                    <SelectItem value="concise">Concise</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" type="button" onClick={draft} disabled={drafting} data-testid="ai-draft-btn">
                <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                {drafting ? "Drafting…" : "✨ Draft with AI"}
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">To</Label>
                <Input value={to} onChange={(e) => setTo(e.target.value)} placeholder="someone@example.com, …" data-testid="send-email-to" />
              </div>
              <div>
                <Label className="text-xs">CC (optional, comma-separated)</Label>
                <Input value={cc} onChange={(e) => setCc(e.target.value)} placeholder="cc@example.com" data-testid="send-email-cc" />
              </div>
            </div>
            <div>
              <Label className="text-xs">BCC (optional)</Label>
              <Input value={bcc} onChange={(e) => setBcc(e.target.value)} placeholder="bcc@example.com" data-testid="send-email-bcc" />
            </div>

            <div>
              <Label className="text-xs">Subject</Label>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} data-testid="send-email-subject" />
            </div>
            <div>
              <Label className="text-xs">Body</Label>
              <Textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)} data-testid="send-email-body" />
            </div>

            <div className="rounded-sm border bg-muted/40 p-2.5 text-xs flex items-center justify-between" data-testid="send-email-attachment">
              <div className="flex items-center gap-2">
                <Paperclip className="h-3.5 w-3.5 text-muted-foreground" />
                <span>{ctx.auto_attachment?.filename_hint}</span>
                <Badge variant="outline" className="text-[9px]">auto</Badge>
              </div>
              <label className="text-[11px] inline-flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={attachPdf} onChange={(e) => setAttachPdf(e.target.checked)} data-testid="send-email-attach-toggle" />
                <span>Attach</span>
              </label>
            </div>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="send-email-cancel">Cancel</Button>
          <Button onClick={send} disabled={loading || sending || !ctx} data-testid="send-email-send-btn">
            <Send className="h-3.5 w-3.5 mr-1.5" />
            {sending ? "Sending…" : "Send"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
