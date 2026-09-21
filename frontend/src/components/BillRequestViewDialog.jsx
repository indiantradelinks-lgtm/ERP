import { useEffect, useState } from "react";
import { FileText, Download, Paperclip, ExternalLink } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtDT } from "@/lib/datetime";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const HIDDEN = new Set(["id", "_id", "approval_id", "bill_id", "items", "chain", "current_step", "requested_by_id", "created_by"]);
const label = (k) => k.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const show = (k, v) => {
  if (v === null || v === undefined || v === "") return "—";
  if (/amount|total|value|rate/.test(k) && typeof v === "number") return inr(v);
  if (/_at$|created_at|generated_at/.test(k)) return fmtDT(v);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};

function KV({ data, testid }) {
  const entries = Object.entries(data || {}).filter(([k, v]) => !HIDDEN.has(k) && (v === null || typeof v !== "object"));
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-2" data-testid={testid}>
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label(k)}</div>
          <div className="text-sm break-words">{show(k, v)}</div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children, testid }) {
  return (
    <div data-testid={testid}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">{title}</div>
      <div className="border border-border rounded-sm p-3">{children}</div>
    </div>
  );
}

/** Read-only 360° view of a bill request (as submitted) + approval trail + generated bill/file. */
export default function BillRequestViewDialog({ requestId, open, onOpenChange }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!open || !requestId) return;
    setData(null);
    api.get(`/bill-requests/${requestId}/full`).then((r) => setData(r.data)).catch(() => setData({ error: true }));
  }, [open, requestId]);

  const base = process.env.REACT_APP_BACKEND_URL;
  const r = data?.request;
  const items = r?.items || r?.line_items || [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="br-view-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><FileText className="h-4 w-4 text-primary" /> Bill Request {r?.request_no || ""} <span className="text-xs font-normal text-muted-foreground ml-2">read-only</span></DialogTitle>
          <DialogDescription className="text-xs">Everything submitted at creation, the approval trail, and the generated bill. Viewing does not change the workflow.</DialogDescription>
        </DialogHeader>
        {!data && <div className="text-sm text-muted-foreground py-8">Loading…</div>}
        {data?.error && <div className="text-sm text-rose-600 py-8">Could not load this bill request.</div>}
        {r && (
          <div className="space-y-5">
            <Section title="Request details (as submitted)" testid="br-view-request"><KV data={r} testid="br-view-request-kv" /></Section>
            {items.length > 0 && (
              <Section title={`Line items (${items.length})`} testid="br-view-items">
                <Table>
                  <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                    {Object.keys(items[0]).filter((k) => !HIDDEN.has(k)).map((k) => <TableHead key={k} className="text-[10px] uppercase">{label(k)}</TableHead>)}
                  </TableRow></TableHeader>
                  <TableBody>
                    {items.map((it, i) => (
                      <TableRow key={i}>{Object.keys(items[0]).filter((k) => !HIDDEN.has(k)).map((k) => <TableCell key={k} className="text-xs">{show(k, it[k])}</TableCell>)}</TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Section>
            )}
            <Section title="Approval trail" testid="br-view-approval">
              {!data.approval && <div className="text-xs text-muted-foreground">No approval record linked.</div>}
              {data.approval && (
                <div className="space-y-1.5">
                  <div className="text-xs">Status: <b>{data.approval.status}</b> · Step {Number(data.approval.current_step || 0) + 1} of {(data.approval.chain || []).length}</div>
                  {(data.approval.chain || []).map((st, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs" data-testid={`br-view-step-${i}`}>
                      <span className={`h-2 w-2 rounded-full ${st.status === "approved" ? "bg-success" : st.status === "rejected" ? "bg-destructive" : "bg-muted-foreground/40"}`} />
                      <span className="font-medium">{st.label || st.role}</span>
                      <span className="text-muted-foreground">{st.status || "pending"}{st.by ? ` · ${st.by}` : ""}{st.at ? ` · ${fmtDT(st.at)}` : ""}</span>
                      {st.comment && <span className="italic text-muted-foreground">“{st.comment}”</span>}
                    </div>
                  ))}
                </div>
              )}
            </Section>
            <Section title="Generated bill" testid="br-view-bill">
              {!data.bill && <div className="text-xs text-muted-foreground">{r.bill_number ? `Bill ${r.bill_number} is no longer available.` : "Bill not generated yet."}</div>}
              {data.bill && (
                <div className="space-y-3">
                  <KV data={{ bill_number: data.bill.bill_number, bill_type: data.bill.bill_type, bill_date: data.bill.bill_date || data.bill.date, status: data.bill.status,
                    total_amount: data.bill.total_amount ?? data.bill.grand_total ?? data.bill.amount, client_name: data.bill.client_name, project_code: data.bill.project_code,
                    generated_at: r.generated_at, generated_by: r.generated_by }} testid="br-view-bill-kv" />
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" className="rounded-sm" asChild>
                      <a href={`${base}${data.bill_pdf_url}`} target="_blank" rel="noreferrer" data-testid="br-view-bill-pdf"><ExternalLink className="h-3.5 w-3.5 mr-1" /> Open bill PDF</a>
                    </Button>
                  </div>
                  <iframe title="Bill PDF" src={`${base}${data.bill_pdf_url}#toolbar=0`} className="w-full h-[420px] border border-border rounded-sm bg-white" data-testid="br-view-bill-frame" />
                </div>
              )}
            </Section>
            <Section title={`Attachments (${data.files.length})`} testid="br-view-files">
              {data.files.length === 0 && <div className="text-xs text-muted-foreground">No files attached.</div>}
              {data.files.map((f) => (
                <div key={f.id} className="flex items-center gap-2 text-xs py-1" data-testid={`br-view-file-${f.id}`}>
                  <Paperclip className="h-3 w-3 text-muted-foreground" />
                  <span className="flex-1 truncate">{f.title || f.original_filename}</span>
                  <span className="text-muted-foreground">{f.uploaded_by} · {fmtDT(f.created_at)}</span>
                  <a className="text-primary inline-flex items-center gap-1" href={`${base}/api/files/${f.id}/download`} target="_blank" rel="noreferrer"><Download className="h-3 w-3" /> Download</a>
                </div>
              ))}
            </Section>
            {data.history.length > 0 && (
              <Section title="Activity" testid="br-view-history">
                {data.history.map((h, i) => (
                  <div key={i} className="text-xs py-0.5"><span className="text-muted-foreground">{fmtDT(h.ts)}</span> · <b>{h.action?.replaceAll("_", " ")}</b> · {h.actor_name}</div>
                ))}
              </Section>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
