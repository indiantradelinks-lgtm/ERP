import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { fmtD } from "@/lib/datetime";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const TONE = { won: "success", lost: "danger", open: "info", sent: "primary", submitted: "primary", under_review: "warning", invoiced: "success" };

function Section({ title, count, children, testid }) {
  return (
    <div data-testid={testid}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">{title} <span className="text-muted-foreground">({count})</span></div>
      <div className="border border-border rounded-sm overflow-x-auto">{children}</div>
    </div>
  );
}

/** Drill-down: which enquiries / quotes made up a salesperson's month. */
export default function LeaderboardDetail({ userId, month, open, onOpenChange }) {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open || !userId) return;
    setData(null);
    api.get(`/sales/leaderboard/${userId}/details?month=${month}`).then((r) => setData(r.data)).catch(() => setData({ error: true }));
  }, [open, userId, month]);

  const go = (path) => { onOpenChange(false); navigate(path); };
  const enq = [...(data?.enquiries || []), ...(data?.decided_earlier || [])];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl rounded-sm max-h-[85vh] overflow-y-auto" data-testid="leaderboard-detail">
        <DialogHeader>
          <DialogTitle className="font-display">{data?.user?.name || "Salesperson"} · {month}</DialogTitle>
          <DialogDescription className="text-xs">Records behind this month's numbers. Click a row to open it.</DialogDescription>
        </DialogHeader>
        {!data && <div className="text-sm text-muted-foreground py-6">Loading…</div>}
        {data?.error && <div className="text-sm text-rose-600 py-6">Could not load details.</div>}
        {data && !data.error && (
          <div className="space-y-5">
            <Section title="Enquiries" count={enq.length} testid="leaderboard-detail-enquiries">
              <Table>
                <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase">Enquiry #</TableHead><TableHead className="text-[10px] uppercase">Client / Site</TableHead>
                  <TableHead className="text-[10px] uppercase">Created</TableHead><TableHead className="text-[10px] uppercase">Status</TableHead>
                  <TableHead className="text-[10px] uppercase">Decided this month</TableHead><TableHead className="text-[10px] uppercase text-right">Expected</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {enq.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-xs text-muted-foreground py-6">No enquiries this month.</TableCell></TableRow>}
                  {enq.map((e) => (
                    <TableRow key={e.id} className="cursor-pointer hover:bg-muted/30" onClick={() => go(`/app/enquiries?hl=${e.id}`)} data-testid={`lb-detail-enq-${e.id}`}>
                      <TableCell className="font-mono-data text-xs">{e.enquiry_no} <ExternalLink className="inline h-3 w-3 text-muted-foreground" /></TableCell>
                      <TableCell className="text-sm">{e.customer || e.client_name || "—"}<div className="text-[10px] text-muted-foreground">{e.site_name || ""}</div></TableCell>
                      <TableCell className="text-xs">{e.created_at ? fmtD(e.created_at) : "—"}</TableCell>
                      <TableCell><StatusBadge text={e.status || "open"} tone={TONE[e.status] || "neutral"} /></TableCell>
                      <TableCell>{e.decided_in_month ? <StatusBadge text={e.decided_in_month} tone={TONE[e.decided_in_month]} /> : <span className="text-xs text-muted-foreground">—</span>}</TableCell>
                      <TableCell className="text-right tabular-nums text-xs">{e.expected_value ? inr(e.expected_value) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
            <Section title="Quotes sent" count={(data.quotes || []).length} testid="leaderboard-detail-quotes">
              <Table>
                <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase">Quote #</TableHead><TableHead className="text-[10px] uppercase">Client</TableHead>
                  <TableHead className="text-[10px] uppercase">Created</TableHead><TableHead className="text-[10px] uppercase">Status</TableHead>
                  <TableHead className="text-[10px] uppercase text-right">Value</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.quotes || []).length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-xs text-muted-foreground py-6">No quotes sent this month.</TableCell></TableRow>}
                  {(data.quotes || []).map((q) => (
                    <TableRow key={q.id} className="cursor-pointer hover:bg-muted/30" onClick={() => go(`/app/quotations?hl=${q.id}`)} data-testid={`lb-detail-quote-${q.id}`}>
                      <TableCell className="font-mono-data text-xs">{q.quote_no || q.quotation_no || q.id.slice(0, 8)}{q.revision_no ? ` · Rev${q.revision_no}` : ""} <ExternalLink className="inline h-3 w-3 text-muted-foreground" /></TableCell>
                      <TableCell className="text-sm">{q.client || q.client_name || q.customer || "—"}<div className="text-[10px] text-muted-foreground truncate max-w-[260px]">{q.title || q.enquiry_no || ""}</div></TableCell>
                      <TableCell className="text-xs">{q.created_at ? fmtD(q.created_at) : "—"}</TableCell>
                      <TableCell><StatusBadge text={q.status} tone={TONE[q.status] || "neutral"} /></TableCell>
                      <TableCell className="text-right tabular-nums text-xs">{inr(q.total ?? q.grand_total ?? q.amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
