/**
 * Enquiry Follow-Up & Status Tracker — Iter 120
 * Sales module dedicated page. Views: Today / Upcoming / Overdue / New / Critical / All.
 * Backend: /api/enquiry-followups/inbox · /api/enquiry-followups/dashboard
 *          /api/enquiries/{id}/followups · /api/enquiries/{id}/reminders
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CalendarClock, RefreshCcw, Phone, Mail, Users, Send, AlertTriangle, Download, CheckCircle2 } from "lucide-react";

const fmt = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

const BUCKET_BADGE = {
  overdue: { variant: "destructive", label: "Overdue" },
  today: { variant: "default", label: "Today" },
  upcoming: { variant: "secondary", label: "Upcoming" },
  no_date: { variant: "outline", label: "No date" },
};
const PRIORITY_CLASS = {
  critical: "text-red-500 font-semibold",
  high: "text-orange-500 font-semibold",
  medium: "",
  low: "text-muted-foreground",
};
const STATUS_BADGE = {
  new: "outline", under_review: "outline", quotation_pending: "secondary",
  quotation_submitted: "default", client_approval_pending: "secondary",
  commercial_negotiation: "secondary", po_awaited: "secondary",
  won: "default", lost: "destructive", dropped: "destructive", on_hold: "outline",
};

export default function EnquiryFollowUpTracker() {
  const [view, setView] = useState("today");
  const [data, setData] = useState({ rows: [], count: 0 });
  const [kpis, setKpis] = useState(null);
  const [dlgOpen, setDlgOpen] = useState(false);
  const [currentEnq, setCurrentEnq] = useState(null);
  const [history, setHistory] = useState([]);
  const [form, setForm] = useState({ mode: "Call", remarks: "", next_followup_date: "", next_action: "", action_owner: "", reminder_date: "", priority: "" });
  const [quickEnqId, setQuickEnqId] = useState("");

  // Iter 122 — picker-driven mobile quick action
  const quickActionPicked = (action) => {
    const enq = data.rows.find((r) => r.id === quickEnqId);
    if (!enq) { toast.error("Pick an enquiry first"); return; }
    quickAction(enq, action);
  };

  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get(`/enquiry-followups/inbox?view=${view}`),
        api.get("/enquiry-followups/dashboard"),
      ]);
      setData(a.data); setKpis(b.data);
    } catch (e) { toast.error("Failed to load follow-ups"); }
  };
  useEffect(() => { load(); /* eslint-disable-line */ }, [view]);
  useEffect(() => {
    // Iter 122 — auto-select first row when view results change
    if (data.rows.length && !data.rows.find((r) => r.id === quickEnqId)) {
      setQuickEnqId(data.rows[0].id);
    }
    // eslint-disable-next-line
  }, [data.rows]);

  const openHistory = async (enq) => {
    setCurrentEnq(enq);
    try {
      const r = await api.get(`/enquiries/${enq.id}/followups`);
      setHistory(r.data || []);
      setDlgOpen(true);
      setForm({ mode: "Call", remarks: "", next_followup_date: "", next_action: "", action_owner: "", reminder_date: "", priority: enq.priority || "" });
    } catch (e) { toast.error("Failed to load history"); }
  };

  const saveFollowup = async () => {
    if (!currentEnq) return;
    if ((form.remarks || "").length < 3) { toast.error("Remarks min 3 chars"); return; }
    try {
      await api.post(`/enquiries/${currentEnq.id}/followups`, form);
      toast.success("Follow-up recorded");
      setDlgOpen(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  // Iter 121 — quick mobile actions: post a follow-up + status change in one tap
  const quickAction = async (enq, action) => {
    const presets = {
      fu_done:         { mode: "Call",  remarks: "Follow-up done · mobile quick action" },
      quot_submitted:  { mode: "Email", remarks: "Quotation submitted · mobile quick action", status: "quotation_submitted" },
      client_pending:  { mode: "Email", remarks: "Awaiting client response · mobile quick action", status: "client_approval_pending" },
      po_received:     { mode: "Email", remarks: "PO received · mobile quick action", status: "po_awaited" },
    }[action];
    if (!presets) return;
    try {
      await api.post(`/enquiries/${enq.id}/followups`, { mode: presets.mode, remarks: presets.remarks });
      if (presets.status) await api.post(`/enquiries/${enq.id}/status`, { status: presets.status }).catch(() => {});
      toast.success("Updated");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  // Excel exports
  const exportCsv = () => {
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/enquiry-followups/export.csv?view=${view}`;
    window.open(url, "_blank");
    toast.success("CSV export started");
  };
  const exportXlsx = () => {
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/enquiry-followups/export.xlsx?view=${view}`;
    window.open(url, "_blank");
    toast.success("Excel export started");
  };

  return (
    <div className="space-y-4" data-testid="page-enquiry-followup-tracker">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Enquiry Follow-Up & Status Tracker</h1>
          <p className="text-sm text-muted-foreground">Daily review · reminders · follow-up history</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={exportXlsx} data-testid="btn-export-xlsx"><Download className="h-4 w-4 mr-1" /> Excel</Button>
          <Button variant="outline" size="sm" onClick={exportCsv} data-testid="btn-export-csv">CSV</Button>
          <Button variant="outline" onClick={load} data-testid="btn-reload"><RefreshCcw className="h-4 w-4 mr-1" /> Reload</Button>
        </div>
      </div>

      {/* Iter 121/122 — Mobile-friendly quick-update buttons with per-row picker */}
      {data.rows.length > 0 && (
        <Card className="md:hidden" data-testid="quick-actions-mobile">
          <CardContent className="p-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Quick actions</div>
            <Select value={quickEnqId} onValueChange={setQuickEnqId}>
              <SelectTrigger className="mb-2" data-testid="quick-pick-enquiry"><SelectValue placeholder="Pick an enquiry…" /></SelectTrigger>
              <SelectContent>
                {data.rows.slice(0, 50).map((r) => (
                  <SelectItem key={r.id} value={r.id}>{r.client_name || "-"} · {r.enquiry_number || r.id.slice(0, 6)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="grid grid-cols-2 gap-2">
              <QuickButton label="Follow-Up Done" testid="qa-fu-done" onClick={() => quickActionPicked("fu_done")} />
              <QuickButton label="Quotation Submitted" testid="qa-qs" onClick={() => quickActionPicked("quot_submitted")} />
              <QuickButton label="Client Pending" testid="qa-cp" onClick={() => quickActionPicked("client_pending")} />
              <QuickButton label="PO Received" testid="qa-po" onClick={() => quickActionPicked("po_received")} />
            </div>
          </CardContent>
        </Card>
      )}

      {kpis && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { l: "Open", v: kpis.open, t: "kpi-open" },
            { l: "Due Today", v: kpis.due_today, t: "kpi-today", emph: "yellow" },
            { l: "Overdue", v: kpis.overdue, t: "kpi-overdue", emph: "red" },
            { l: "Quotations Pending", v: kpis.quotations_pending, t: "kpi-qp" },
            { l: "High Priority", v: kpis.high_priority, t: "kpi-hp" },
            { l: "Won", v: kpis.won, t: "kpi-won" },
            { l: "Lost", v: kpis.lost, t: "kpi-lost" },
            { l: "Pipeline ₹", v: fmt(kpis.pipeline_value), t: "kpi-pipe" },
            { l: "New (7d)", v: kpis.new_7d, t: "kpi-new" },
            { l: "Quot Submitted", v: kpis.quotations_submitted, t: "kpi-qs" },
          ].map((k, i) => (
            <Card key={i} data-testid={k.t}>
              <CardContent className="p-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k.l}</div>
                <div className={`text-xl font-semibold mt-1 ${k.emph === "red" ? "text-red-500" : k.emph === "yellow" ? "text-amber-500" : ""}`}>{k.v}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs value={view} onValueChange={setView}>
        <TabsList>
          <TabsTrigger value="today" data-testid="tab-today">Today</TabsTrigger>
          <TabsTrigger value="upcoming" data-testid="tab-upcoming">Upcoming</TabsTrigger>
          <TabsTrigger value="overdue" data-testid="tab-overdue">Overdue</TabsTrigger>
          <TabsTrigger value="new" data-testid="tab-new">New</TabsTrigger>
          <TabsTrigger value="critical" data-testid="tab-critical">Critical</TabsTrigger>
          <TabsTrigger value="all" data-testid="tab-all">All Open</TabsTrigger>
        </TabsList>
        <TabsContent value={view} className="mt-3">
          <Card><CardContent className="p-3">
            {data.rows.length === 0
              ? <div className="text-sm text-muted-foreground p-4 text-center">No enquiries match this view.</div>
              : <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
                      <tr><th className="text-left py-2">Enq #</th><th className="text-left">Client</th><th className="text-left">Service</th><th className="text-right">Value</th><th className="text-left">Status</th><th className="text-left">Priority</th><th className="text-left">Next FU</th><th>Bucket</th><th></th></tr>
                    </thead>
                    <tbody>
                      {data.rows.map((r) => {
                        const b = BUCKET_BADGE[r._bucket] || BUCKET_BADGE.no_date;
                        return (
                          <tr key={r.id} className={`border-b border-border/50 hover:bg-muted/30 ${r._bucket === "overdue" ? "bg-red-500/5" : r._bucket === "today" ? "bg-amber-500/5" : ""}`} data-testid={`row-${r.id}`}>
                            <td className="py-2 font-mono text-xs">{r.enquiry_number || r.id.slice(0, 8)}</td>
                            <td>{r.client_name || "-"}</td>
                            <td className="text-xs">{r.service_type || r.scope_summary || "-"}</td>
                            <td className="text-right">{fmt(r.estimated_value)}</td>
                            <td><Badge variant={STATUS_BADGE[r.status] || "outline"}>{(r.status || "").replaceAll("_", " ")}</Badge></td>
                            <td><span className={PRIORITY_CLASS[(r.priority || "").toLowerCase()] || ""}>{r.priority || "-"}</span></td>
                            <td className="text-xs">{r.next_followup_date || "-"}</td>
                            <td><Badge variant={b.variant}>{b.label}</Badge></td>
                            <td className="text-right">
                              <Button size="sm" variant="outline" onClick={() => openHistory(r)} data-testid={`btn-followup-${r.id}`}>
                                <CalendarClock className="h-3.5 w-3.5 mr-1" /> Follow-up
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>}
          </CardContent></Card>
        </TabsContent>
      </Tabs>

      {/* Follow-up dialog */}
      <Dialog open={dlgOpen} onOpenChange={setDlgOpen}>
        <DialogContent className="max-w-2xl" data-testid="dialog-followup">
          <DialogHeader>
            <DialogTitle>Follow-Up · {currentEnq?.client_name} · {currentEnq?.enquiry_number || currentEnq?.id?.slice(0, 8)}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Select value={form.mode} onValueChange={(v) => setForm({ ...form, mode: v })}>
                <SelectTrigger data-testid="sel-mode"><SelectValue placeholder="Mode" /></SelectTrigger>
                <SelectContent>
                  {["Call", "Email", "Meeting", "WhatsApp", "Client Visit", "Tender Portal"].map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={form.priority || ""} onValueChange={(v) => setForm({ ...form, priority: v })}>
                <SelectTrigger data-testid="sel-priority"><SelectValue placeholder="Priority" /></SelectTrigger>
                <SelectContent>
                  {["low", "medium", "high", "critical"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
              <div><label className="text-xs text-muted-foreground">Next follow-up date</label>
                <Input type="date" value={form.next_followup_date} onChange={(e) => setForm({ ...form, next_followup_date: e.target.value })} data-testid="input-next-date" /></div>
              <div><label className="text-xs text-muted-foreground">Action owner</label>
                <Input value={form.action_owner} onChange={(e) => setForm({ ...form, action_owner: e.target.value })} data-testid="input-owner" /></div>
              <div className="col-span-2"><label className="text-xs text-muted-foreground">Next action</label>
                <Input value={form.next_action} onChange={(e) => setForm({ ...form, next_action: e.target.value })} placeholder="Send revised quotation / send reminder / schedule meeting" data-testid="input-next-action" /></div>
              <div><label className="text-xs text-muted-foreground">Reminder date (opt)</label>
                <Input type="date" value={form.reminder_date} onChange={(e) => setForm({ ...form, reminder_date: e.target.value })} data-testid="input-reminder" /></div>
            </div>
            <Textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} placeholder="Remarks · what was discussed · commitments…" data-testid="input-remarks" rows={3} />
            {history.length > 0 && (
              <div className="mt-2 border-t pt-3">
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Previous follow-ups ({history.length})</div>
                <div className="max-h-48 overflow-y-auto space-y-2">
                  {history.map((h) => (
                    <div key={h.id} className="text-xs p-2 bg-muted/40 rounded-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{h.mode} · {h.done_by}</span>
                        <span className="text-muted-foreground">{(h.done_at || "").slice(0, 16)}</span>
                      </div>
                      <div className="text-muted-foreground mt-1">{h.remarks}</div>
                      {h.next_followup_date && <div className="text-[10px] mt-1">→ Next FU: <span className="text-foreground">{h.next_followup_date}</span></div>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlgOpen(false)}>Cancel</Button>
            <Button onClick={saveFollowup} data-testid="btn-save-followup"><Send className="h-4 w-4 mr-1" /> Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function QuickButton({ label, onClick, testid }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} data-testid={testid} className="h-10 text-xs">
      <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> {label}
    </Button>
  );
}
