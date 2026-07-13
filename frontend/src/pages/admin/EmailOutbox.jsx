import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Inbox, RefreshCw, Search, Eye, Paperclip } from "lucide-react";
import { toast } from "sonner";

const STATUS_LABEL = {
  queued: { variant: "outline", label: "Queued" },
  sending: { variant: "secondary", label: "Sending…" },
  sent: { variant: "default", label: "Sent" },
  failed: { variant: "destructive", label: "Failed" },
};

export default function EmailOutbox() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("all");
  const [sender, setSender] = useState("all");
  const [q, setQ] = useState("");
  const [skip, setSkip] = useState(0);
  const [detail, setDetail] = useState(null);
  const limit = 50;

  const load = async () => {
    setLoading(true);
    const params = { limit, skip };
    if (status !== "all") params.status = status;
    if (sender !== "all") params.sender = sender;
    if (q) params.q = q;
    try {
      const { data } = await api.get("/email/outbox", { params });
      setRows(data.rows || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load outbox");
    } finally {
      setLoading(false);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [status, sender, skip]);

  const onSearch = (e) => {
    e.preventDefault();
    setSkip(0);
    load();
  };

  const openDetail = async (id) => {
    try {
      const { data } = await api.get(`/email/outbox/${id}`);
      setDetail(data);
    } catch (e) {
      toast.error("Could not open outbox record");
    }
  };

  const retry = async (id) => {
    try {
      await api.post(`/email/outbox/${id}/retry`);
      toast.success("Re-queued. Refreshing…");
      setTimeout(load, 1200);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Retry failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="email-outbox-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Inbox className="h-3 w-3" /> M365 SMTP
        </div>
        <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Email Outbox</h1>
        <p className="text-sm text-muted-foreground mt-1">Every email sent from the ERP — queued, sent, or failed — with retry, attachments and audit trail.</p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSearch} className="flex flex-wrap items-end gap-2">
            <div className="min-w-[160px]">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Status</div>
              <Select value={status} onValueChange={(v) => { setStatus(v); setSkip(0); }}>
                <SelectTrigger data-testid="outbox-filter-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="queued">Queued</SelectItem>
                  <SelectItem value="sending">Sending</SelectItem>
                  <SelectItem value="sent">Sent</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-[160px]">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Sender</div>
              <Select value={sender} onValueChange={(v) => { setSender(v); setSkip(0); }}>
                <SelectTrigger data-testid="outbox-filter-sender"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All senders</SelectItem>
                  <SelectItem value="shared">Shared mailbox</SelectItem>
                  <SelectItem value="user">Per-user mailbox</SelectItem>
                  <SelectItem value="me">My sends</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 min-w-[200px]">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Search</div>
              <div className="flex gap-1">
                <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Subject, recipient or sender…" data-testid="outbox-search" />
                <Button type="submit" variant="outline" size="icon" data-testid="outbox-search-btn"><Search className="h-3.5 w-3.5" /></Button>
              </div>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={load} data-testid="outbox-refresh">
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[110px]">Status</TableHead>
                <TableHead className="w-[170px]">When</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>To</TableHead>
                <TableHead className="w-[140px]">From</TableHead>
                <TableHead className="w-[80px] text-center">Att.</TableHead>
                <TableHead className="w-[80px] text-center">Attempts</TableHead>
                <TableHead className="w-[120px] text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow><TableCell colSpan={8} className="text-center text-xs text-muted-foreground py-8">Loading…</TableCell></TableRow>
              )}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center text-xs text-muted-foreground py-8">No emails yet</TableCell></TableRow>
              )}
              {rows.map((r) => {
                const s = STATUS_LABEL[r.status] || STATUS_LABEL.queued;
                const attCount = (r.attachments_summary?.length || 0) + (r.file_ids?.length || 0);
                return (
                  <TableRow key={r.id} data-testid={`outbox-row-${r.id}`}>
                    <TableCell><Badge variant={s.variant}>{s.label}</Badge></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{r.sent_at || r.created_at || "—"}</TableCell>
                    <TableCell className="text-xs font-medium">{r.subject}</TableCell>
                    <TableCell className="text-xs text-muted-foreground truncate max-w-[200px]">{(r.to || []).join(", ")}</TableCell>
                    <TableCell className="text-xs text-muted-foreground truncate max-w-[140px]" title={r.sender_email}>
                      <Badge variant="outline" className="text-[10px] mr-1">{r.sender_type}</Badge>
                      {r.sender_email}
                    </TableCell>
                    <TableCell className="text-center">{attCount > 0 ? <span className="inline-flex items-center gap-1 text-xs"><Paperclip className="h-3 w-3" />{attCount}</span> : "—"}</TableCell>
                    <TableCell className="text-center text-xs">{r.attempts || 0}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => openDetail(r.id)} data-testid={`outbox-view-${r.id}`}><Eye className="h-3.5 w-3.5" /></Button>
                        {r.status !== "sent" && (
                          <Button size="sm" variant="outline" onClick={() => retry(r.id)} data-testid={`outbox-retry-${r.id}`}>
                            <RefreshCw className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div>{total} total · showing {skip + 1}–{Math.min(skip + limit, total)}</div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - limit))}>Previous</Button>
          <Button size="sm" variant="outline" disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)}>Next</Button>
        </div>
      </div>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-display">Email detail</DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-2 text-sm" data-testid="outbox-detail">
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div><div className="text-muted-foreground">Status</div><div className="font-medium">{detail.status}</div></div>
                <div><div className="text-muted-foreground">Attempts</div><div className="font-medium">{detail.attempts || 0}</div></div>
                <div><div className="text-muted-foreground">Sender type</div><div className="font-medium">{detail.sender_type}</div></div>
                <div><div className="text-muted-foreground">From</div><div className="font-mono text-[11px] break-all">{detail.sender_email}</div></div>
                <div className="col-span-2"><div className="text-muted-foreground">To</div><div className="font-mono text-[11px] break-all">{(detail.to || []).join(", ")}</div></div>
                {detail.cc?.length > 0 && <div className="col-span-3"><div className="text-muted-foreground">CC</div><div className="font-mono text-[11px] break-all">{detail.cc.join(", ")}</div></div>}
                {detail.bcc?.length > 0 && <div className="col-span-3"><div className="text-muted-foreground">BCC</div><div className="font-mono text-[11px] break-all">{detail.bcc.join(", ")}</div></div>}
              </div>
              <div className="border-t pt-2">
                <div className="text-xs text-muted-foreground mb-1">Subject</div>
                <div className="font-medium">{detail.subject}</div>
              </div>
              <div className="border-t pt-2">
                <div className="text-xs text-muted-foreground mb-1">Body</div>
                <pre className="text-xs whitespace-pre-wrap font-sans bg-muted/30 p-2 rounded-sm max-h-48 overflow-auto">{detail.body_text || "(empty)"}</pre>
              </div>
              {detail.attachments_summary?.length > 0 && (
                <div className="border-t pt-2">
                  <div className="text-xs text-muted-foreground mb-1">Attachments ({detail.attachments_summary.length})</div>
                  <ul className="text-xs">
                    {detail.attachments_summary.map((a, i) => (
                      <li key={i} className="flex items-center gap-2"><Paperclip className="h-3 w-3" /> {a.filename} <span className="text-muted-foreground">({Math.round((a.size||0)/1024)} KB)</span></li>
                    ))}
                  </ul>
                </div>
              )}
              {detail.last_error && (
                <div className="border-t pt-2">
                  <div className="text-xs text-destructive mb-1">Error</div>
                  <pre className="text-xs whitespace-pre-wrap font-sans bg-destructive/10 text-destructive p-2 rounded-sm">{detail.last_error}</pre>
                </div>
              )}
              {detail.smtp_response && (
                <div className="border-t pt-2">
                  <div className="text-xs text-muted-foreground mb-1">SMTP response</div>
                  <pre className="text-xs whitespace-pre-wrap font-mono bg-muted/30 p-2 rounded-sm">{detail.smtp_response}</pre>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
