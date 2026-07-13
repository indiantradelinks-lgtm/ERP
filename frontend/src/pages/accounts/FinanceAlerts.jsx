/**
 * Finance Alerts & Follow-up Centre · Phase 8
 * Tabs: Alerts feed · Follow-up inbox (auto-classified) · Active follow-ups
 * Backend: /api/finance/alerts/feed · /api/finance/followups/inbox · /api/finance/followups
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Bell, Inbox, ListChecks, RefreshCcw, ArrowUpCircle } from "lucide-react";

const fmt = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const sevColor = { critical: "destructive", warning: "secondary", info: "outline" };
const kindLabel = {
  overdue: "Overdue", due_soon: "Due Soon", partly_paid: "Partly Paid",
  tds_unrec: "TDS Pending", retention_due: "Retention Due",
};

export default function FinanceAlerts() {
  const [tab, setTab] = useState("alerts");
  const [feed, setFeed] = useState(null);
  const [inbox, setInbox] = useState(null);
  const [followups, setFollowups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createFor, setCreateFor] = useState(null);
  const [remarks, setRemarks] = useState("");
  const [nextDate, setNextDate] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [f, i, fu] = await Promise.all([
        api.get("/finance/alerts/feed"),
        api.get("/finance/followups/inbox?days_ahead=7"),
        api.get(`/finance/followups${statusFilter ? `?status=${statusFilter}` : ""}`),
      ]);
      setFeed(f.data); setInbox(i.data); setFollowups(fu.data || []);
    } catch (e) { toast.error("Failed to load alerts"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-line */ }, [statusFilter]);

  const createFollowup = async () => {
    if (!createFor) return;
    try {
      await api.post("/finance/followups", {
        invoice_id: createFor.invoice_id,
        client_id: createFor.client_id,
        client_name: createFor.client_name,
        remarks, next_followup_date: nextDate || null,
        status: "pending",
      });
      toast.success("Follow-up created");
      setCreateOpen(false); setRemarks(""); setNextDate(""); setCreateFor(null);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Create failed"); }
  };

  const updateFollowup = async (id, status) => {
    try {
      await api.post(`/finance/followups/${id}/update`, { status });
      toast.success(`Marked ${status}`);
      load();
    } catch (e) { toast.error("Update failed"); }
  };

  const escalateStale = async () => {
    try {
      const r = await api.post("/finance/followups/escalate-stale?stale_days=14");
      toast.success(`Escalated ${r.data.escalated} stale follow-ups`);
      load();
    } catch (e) { toast.error("Escalation failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-finance-alerts">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Finance Alerts & Follow-ups</h1>
          <p className="text-sm text-slate-400">Receivable workbench, unified alerts and escalation</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={escalateStale} data-testid="btn-escalate-stale">
            <ArrowUpCircle className="h-4 w-4 mr-1" /> Escalate Stale (14d)
          </Button>
          <Button variant="outline" onClick={load} data-testid="btn-reload-alerts">
            <RefreshCcw className="h-4 w-4 mr-1" /> Reload
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="alerts" data-testid="tab-alerts"><Bell className="h-4 w-4 mr-1" /> Alerts Feed</TabsTrigger>
          <TabsTrigger value="inbox" data-testid="tab-inbox"><Inbox className="h-4 w-4 mr-1" /> Follow-up Inbox</TabsTrigger>
          <TabsTrigger value="active" data-testid="tab-active"><ListChecks className="h-4 w-4 mr-1" /> Active Follow-ups</TabsTrigger>
        </TabsList>

        <TabsContent value="alerts" className="mt-4">
          <Card><CardContent className="p-4">
            {!feed ? <div className="text-slate-400">Loading…</div> :
              feed.alerts.length === 0 ? <div className="text-slate-400 text-sm">No active alerts. All clear.</div> :
              <div className="space-y-2">
                <div className="text-sm text-slate-300 mb-3">
                  <span className="font-semibold text-red-400">{feed.critical}</span> critical events of {feed.total}
                </div>
                {feed.alerts.map((a, i) => (
                  <div key={i} className="flex items-center justify-between p-3 border border-slate-700 rounded-lg" data-testid={`alert-row-${i}`}>
                    <div className="flex items-center gap-3">
                      <Badge variant={sevColor[a.severity] || "outline"}>{a.severity}</Badge>
                      <span>{a.title}</span>
                    </div>
                    {a.link && <a href={a.link} className="text-xs text-blue-400 underline">Open →</a>}
                  </div>
                ))}
              </div>}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="inbox" className="mt-4">
          <Card><CardContent className="p-4">
            {!inbox ? <div className="text-slate-400">Loading…</div> :
              inbox.rows.length === 0 ? <div className="text-slate-400 text-sm">Inbox clear. No invoices need follow-up.</div> :
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400 border-b border-slate-700">
                  <tr><th className="text-left py-2">Kind</th><th className="text-left">Invoice</th><th className="text-left">Client</th><th className="text-right">Outstanding</th><th className="text-left">Due</th><th className="text-right">Age</th><th></th></tr>
                </thead>
                <tbody>
                  {inbox.rows.map((r, i) => (
                    <tr key={i} className="border-b border-slate-800" data-testid={`inbox-row-${i}`}>
                      <td className="py-2"><Badge variant={r.kind === "overdue" ? "destructive" : "secondary"}>{kindLabel[r.kind] || r.kind}</Badge></td>
                      <td>{r.invoice_number}</td>
                      <td>{r.client_name || "-"}</td>
                      <td className="text-right">{fmt(r.amount_outstanding)}</td>
                      <td>{r.due_date}</td>
                      <td className="text-right">{r.age_days ?? "-"}</td>
                      <td className="text-right">
                        {r.has_followup
                          ? <Badge variant="outline">Assigned</Badge>
                          : <Button size="sm" variant="outline" onClick={() => { setCreateFor(r); setCreateOpen(true); }} data-testid={`btn-assign-${i}`}>Assign</Button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="active" className="mt-4">
          <Card><CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
                <SelectTrigger className="w-48" data-testid="filter-status"><SelectValue placeholder="All statuses" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="committed">Committed</SelectItem>
                  <SelectItem value="disputed">Disputed</SelectItem>
                  <SelectItem value="escalated">Escalated</SelectItem>
                  <SelectItem value="received">Received</SelectItem>
                </SelectContent>
              </Select>
              <span className="text-xs text-slate-400">{followups.length} record(s)</span>
            </div>
            {followups.length === 0 ? <div className="text-slate-400 text-sm">No follow-ups.</div> :
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400 border-b border-slate-700">
                  <tr><th className="text-left py-2">Invoice</th><th className="text-left">Client</th><th className="text-left">Status</th><th className="text-left">Assigned To</th><th className="text-left">Updated</th><th></th></tr>
                </thead>
                <tbody>
                  {followups.map((f) => (
                    <tr key={f.id} className="border-b border-slate-800" data-testid={`followup-row-${f.id}`}>
                      <td className="py-2">{f.invoice_number}</td>
                      <td>{f.client_name || "-"}</td>
                      <td><Badge>{f.status}</Badge></td>
                      <td>{f.assigned_to || "-"}</td>
                      <td className="text-xs text-slate-400">{(f.updated_at || "").slice(0, 16)}</td>
                      <td className="text-right space-x-1">
                        <Button size="sm" variant="ghost" onClick={() => updateFollowup(f.id, "committed")} data-testid={`btn-commit-${f.id}`}>Commit</Button>
                        <Button size="sm" variant="ghost" onClick={() => updateFollowup(f.id, "received")} data-testid={`btn-received-${f.id}`}>Received</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>}
          </CardContent></Card>
        </TabsContent>
      </Tabs>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent data-testid="dialog-create-followup">
          <DialogHeader><DialogTitle>Assign Follow-up: {createFor?.invoice_number}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400">Next Follow-up Date</label>
              <Input type="date" value={nextDate} onChange={(e) => setNextDate(e.target.value)} data-testid="input-next-date" />
            </div>
            <div>
              <label className="text-xs text-slate-400">Remarks</label>
              <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="Plan / commitment / concerns" data-testid="input-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={createFollowup} data-testid="btn-save-followup">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
