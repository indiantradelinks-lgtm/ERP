import { useEffect, useState } from "react";
import { CalendarClock, AlertTriangle, Briefcase, Search, RefreshCw, Plus, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function ProjectOps() {
  const [tab, setTab] = useState("expiring");
  return (
    <div className="space-y-6" data-testid="project-ops-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Briefcase className="h-3 w-3" /> Operations · Commercial
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Project Operations &amp; Commercial</h1>
        <p className="text-sm text-muted-foreground mt-1">Client PO expiry &amp; utilization · per-project snapshots · delay &amp; extra-work registers · profitability indicator.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant={tab === "expiring" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("expiring")} data-testid="ops-tab-expiring"><CalendarClock className="h-3.5 w-3.5 mr-1.5" /> Expiring POs</Button>
        <Button variant={tab === "snapshot" ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setTab("snapshot")} data-testid="ops-tab-snapshot"><Briefcase className="h-3.5 w-3.5 mr-1.5" /> Project Snapshot</Button>
      </div>

      {tab === "expiring" && <ExpiringPOs />}
      {tab === "snapshot" && <ProjectSnapshot />}
    </div>
  );
}

function ExpiringPOs() {
  const [days, setDays] = useState(30);
  const [rows, setRows] = useState([]);
  const [util, setUtil] = useState(null);
  const load = async () => {
    try { const r = await api.get(`/orders/expiring-soon?days=${days}`); setRows(r.data?.rows || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const showUtil = async (order) => {
    try { const r = await api.get(`/orders/${order.id}/utilization`); setUtil({ order, ...r.data }); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="bg-card border border-border rounded-sm" data-testid="ops-expiring">
      <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
        <Label className="text-xs">Horizon (days):</Label>
        <Input type="number" value={days} onChange={(e) => setDays(Number(e.target.value) || 30)} className="h-9 rounded-sm w-24" data-testid="ops-expiring-days" />
        <Button size="sm" className="h-9 rounded-sm" onClick={load} data-testid="ops-expiring-go"><Search className="h-3.5 w-3.5 mr-1" /> Search</Button>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Order #</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Customer</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Contract Value</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Validity</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
          <TableHead className="text-right">Action</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10 text-sm">No POs expiring in next {days} days.</TableCell></TableRow>}
          {rows.map((o) => (
            <TableRow key={o.id} data-testid={`ops-expiring-row-${o.id}`}>
              <TableCell className="font-mono-data text-sm font-bold">{o.order_no}</TableCell>
              <TableCell className="text-xs">{o.customer || "—"}</TableCell>
              <TableCell className="font-mono-data tabular text-sm">{inr(o.contract_value)}</TableCell>
              <TableCell className="text-xs text-warning font-bold">{o.validity_date}</TableCell>
              <TableCell><StatusBadge text={o.status} tone="warning" /></TableCell>
              <TableCell className="text-right">
                <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => showUtil(o)} data-testid={`ops-util-${o.id}`}>Utilization</Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {util && (
        <Dialog open onOpenChange={() => setUtil(null)}>
          <DialogContent className="max-w-md rounded-sm" data-testid="ops-util-dialog">
            <DialogHeader><DialogTitle className="font-display">PO Utilization · {util.order_no}</DialogTitle><DialogDescription className="sr-only">PO value utilization</DialogDescription></DialogHeader>
            <div className="grid grid-cols-2 gap-3 py-2 text-xs">
              <KV label="Contract Value" v={inr(util.contract_value)} />
              <KV label="Billed (gross)" v={inr(util.billed_gross)} />
              <KV label="Paid Received" v={inr(util.paid_received)} />
              <KV label="Balance PO Value" v={inr(util.balance_po_value)} />
              <KV label="Retention Held" v={inr(util.retention_held)} />
              <KV label="Validity Date" v={util.validity_date} />
              <KV label="Days to Expiry" v={util.days_to_expiry ?? "—"} />
              <KV label="Utilisation %" v={`${util.utilisation_pct}%`} />
            </div>
            <DialogFooter><Button variant="outline" className="rounded-sm" onClick={() => setUtil(null)}>Close</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function ProjectSnapshot() {
  const [projects, setProjects] = useState([]);
  const [picked, setPicked] = useState("");
  const [snap, setSnap] = useState(null);
  const [profit, setProfit] = useState(null);
  const [delayOpen, setDelayOpen] = useState(false);
  const [extraOpen, setExtraOpen] = useState(false);
  const [delayForm, setDelayForm] = useState({ hours: 1, category: "weather", reason: "" });
  const [extraForm, setExtraForm] = useState({ description: "", estimated_value: 0, client_approved: false });

  useEffect(() => { api.get("/projects").then((r) => setProjects(r.data || [])); }, []);
  const load = async (code) => {
    setSnap(null); setProfit(null);
    try {
      const [s, p] = await Promise.all([api.get(`/projects/${code}/ops/snapshot`), api.get(`/projects/${code}/ops/profitability`)]);
      setSnap(s.data); setProfit(p.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { if (picked) load(picked); /* eslint-disable-next-line */ }, [picked]);

  const addDelay = async () => {
    if (!delayForm.reason.trim()) { toast.error("Reason required"); return; }
    try {
      await api.post(`/projects/${picked}/ops/delay-events`, { ...delayForm, hours: Number(delayForm.hours) });
      toast.success("Delay logged"); setDelayOpen(false); setDelayForm({ hours: 1, category: "weather", reason: "" }); load(picked);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const delDelay = async (id) => {
    try { await api.delete(`/projects/${picked}/ops/delay-events/${id}`); toast.success("Removed"); load(picked); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const addExtra = async () => {
    if (!extraForm.description.trim()) { toast.error("Description required"); return; }
    try {
      await api.post(`/projects/${picked}/ops/extra-works`, { ...extraForm, estimated_value: Number(extraForm.estimated_value) || null });
      toast.success("Extra work logged"); setExtraOpen(false); setExtraForm({ description: "", estimated_value: 0, client_approved: false }); load(picked);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const delExtra = async (id) => {
    try { await api.delete(`/projects/${picked}/ops/extra-works/${id}`); toast.success("Removed"); load(picked); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-4" data-testid="ops-snapshot">
      <div className="bg-card border border-border rounded-sm p-4">
        <Label className="text-[10px] uppercase tracking-wider">Pick a project</Label>
        <select value={picked} onChange={(e) => setPicked(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="ops-project-select">
          <option value="">— Select —</option>
          {projects.map((p) => <option key={p.id} value={p.code}>{p.code} · {p.name}</option>)}
        </select>
      </div>
      {picked && snap && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Kpi label="Progress %" value={`${snap.progress_pct}%`} tone="primary" testid="ops-snap-progress" />
            <Kpi label="DPRs Approved" value={`${snap.dpr.approved} / ${snap.dpr.total}`} tone="info" testid="ops-snap-dprs" />
            <Kpi label="Measurement Billable" value={inr(snap.measurement_billable_value)} tone="success" testid="ops-snap-billable" />
            <Kpi label="Delay Hours" value={`${snap.delay_hours}h`} tone={snap.delay_hours > 0 ? "warning" : "neutral"} testid="ops-snap-delay" />
            <Kpi label="Extras Value" value={inr(snap.extras_value)} tone="info" testid="ops-snap-extras" />
          </div>
          {profit && (
            <div className="bg-card border border-border rounded-sm p-4 grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="ops-profitability">
              <KV label="Revenue (Gross)" v={inr(profit.revenue.gross)} />
              <KV label="Material Cost" v={inr(profit.cost.material)} />
              <KV label="Labour Cost" v={inr(profit.cost.labour)} />
              <KV label="Total Cost" v={inr(profit.cost.total)} />
              <div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">Gross Margin</div><div className={`font-display font-black text-xl tabular ${profit.gross_margin >= 0 ? "text-success" : "text-destructive"}`}>{inr(profit.gross_margin)}<span className="text-xs ml-1">({profit.margin_pct}%)</span></div></div>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Register title="Delay Register" rows={snap.delay_events} cols={["date", "category", "hours", "reason"]} onDelete={delDelay} onAdd={() => setDelayOpen(true)} testidPrefix="ops-delay" />
            <Register title="Extra Work Register" rows={snap.extra_works} cols={["date", "description", "estimated_value", "client_approved"]} onDelete={delExtra} onAdd={() => setExtraOpen(true)} testidPrefix="ops-extra" />
          </div>
        </>
      )}
      <DelayDialog open={delayOpen} setOpen={setDelayOpen} form={delayForm} setForm={setDelayForm} onSave={addDelay} />
      <ExtraDialog open={extraOpen} setOpen={setExtraOpen} form={extraForm} setForm={setExtraForm} onSave={addExtra} />
    </div>
  );
}

function Register({ title, rows, cols, onDelete, onAdd, testidPrefix }) {
  return (
    <div className="bg-card border border-border rounded-sm" data-testid={testidPrefix}>
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{title}</div>
        <Button size="sm" className="h-7 rounded-sm" onClick={onAdd} data-testid={`${testidPrefix}-add`}><Plus className="h-3 w-3 mr-1" /> Add</Button>
      </div>
      <div className="max-h-72 overflow-y-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            {cols.map((c) => <TableHead key={c} className="text-[10px] uppercase tracking-wider">{c.replaceAll("_", " ")}</TableHead>)}
            <TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={cols.length + 1} className="text-center text-muted-foreground py-4 text-xs">Empty.</TableCell></TableRow>}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`${testidPrefix}-row-${r.id}`}>
                {cols.map((c) => (
                  <TableCell key={c} className="text-xs">
                    {c === "estimated_value" ? (r[c] != null ? inr(r[c]) : "—")
                      : c === "client_approved" ? (r[c] ? "✓" : "—")
                      : (r[c] ?? "—")}
                  </TableCell>
                ))}
                <TableCell><Button size="sm" variant="outline" className="h-6 rounded-sm" onClick={() => onDelete(r.id)}><X className="h-3 w-3" /></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function DelayDialog({ open, setOpen, form, setForm, onSave }) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md rounded-sm" data-testid="ops-delay-dialog">
        <DialogHeader><DialogTitle className="font-display">Log Delay Event</DialogTitle><DialogDescription className="sr-only">Add delay record</DialogDescription></DialogHeader>
        <div className="space-y-2 py-2">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Hours" type="number" value={form.hours} onChange={(v) => setForm({ ...form, hours: v })} testid="ops-delay-hours" />
            <SelectField label="Category" value={form.category} options={["weather", "client_hold", "manpower", "material", "safety", "other"]} onChange={(v) => setForm({ ...form, category: v })} testid="ops-delay-category" />
          </div>
          <TextArea label="Reason *" value={form.reason} onChange={(v) => setForm({ ...form, reason: v })} testid="ops-delay-reason" />
        </div>
        <DialogFooter><Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button><Button className="rounded-sm" onClick={onSave} data-testid="ops-delay-save">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ExtraDialog({ open, setOpen, form, setForm, onSave }) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md rounded-sm" data-testid="ops-extra-dialog">
        <DialogHeader><DialogTitle className="font-display">Log Extra Work</DialogTitle><DialogDescription className="sr-only">Add extra work record</DialogDescription></DialogHeader>
        <div className="space-y-2 py-2">
          <TextArea label="Description *" value={form.description} onChange={(v) => setForm({ ...form, description: v })} testid="ops-extra-desc" />
          <div className="grid grid-cols-2 gap-2">
            <Field label="Estimated value" type="number" value={form.estimated_value} onChange={(v) => setForm({ ...form, estimated_value: v })} testid="ops-extra-value" />
            <label className="flex items-center gap-2 text-sm self-end pb-2">
              <input type="checkbox" checked={form.client_approved} onChange={(e) => setForm({ ...form, client_approved: e.target.checked })} data-testid="ops-extra-approved" /> Client approved
            </label>
          </div>
        </div>
        <DialogFooter><Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button><Button className="rounded-sm" onClick={onSave} data-testid="ops-extra-save">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Kpi({ label, value, tone, testid }) {
  const c = { success: "text-success", warning: "text-warning", danger: "text-destructive", info: "text-chart-3", neutral: "text-primary", primary: "text-primary" }[tone] || "text-primary";
  return <div className="bg-card border border-border rounded-sm p-3" data-testid={testid}><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className={`font-display font-black text-2xl tabular mt-1 ${c}`}>{value ?? 0}</div></div>;
}
function Field({ label, value, onChange, type = "text", testid }) { return (<div><Label className="text-[10px] uppercase tracking-wider">{label}</Label><Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} /></div>); }
function TextArea({ label, value, onChange, testid }) { return (<div><Label className="text-[10px] uppercase tracking-wider">{label}</Label><Textarea value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="rounded-sm mt-1 min-h-[60px]" data-testid={testid} /></div>); }
function SelectField({ label, value, options, onChange, testid }) { return (<div><Label className="text-[10px] uppercase tracking-wider">{label}</Label><select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid={testid}>{options.map((o) => <option key={o} value={o}>{(o || "").replaceAll("_", " ")}</option>)}</select></div>); }
function KV({ label, v }) { return <div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="font-mono-data tabular">{v ?? "—"}</div></div>; }
