import { useEffect, useMemo, useState } from "react";
import { Plus, Search, FileText, CheckCircle2, XCircle, Send, Trash2, Eye, RefreshCw, X, Receipt, Banknote, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import SendEmailDialog from "@/components/SendEmailDialog";

const STATUS_TONE = {
  draft: "neutral", submitted: "warning", approved: "info", invoiced: "primary",
  paid: "success", cancelled: "danger",
};
const APPROVE_ROLES = new Set(["super_admin", "director", "general_manager", "dept_head", "accounts_executive", "billing_executive"]);
const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const blankBill = (defaults = {}) => ({
  bill_type: "running", bill_date: new Date().toISOString().slice(0, 10),
  client_id: "", client_name: "", project_code: "", site_name: "",
  po_id: "", po_number: "",
  items: [{ description: "", quantity: 1, unit: "m²", rate: 0 }],
  gst_pct: defaults.gst_pct ?? 18,
  retention_pct: defaults.retention_pct ?? 0,
  tds_pct: defaults.tds_pct ?? 0,
  other_deductions: [], advance_recovery: 0, previous_bill_value: 0,
  notes: "", submit: false,
});

export default function RaBills() {
  const { user } = useAuth();
  const canApprove = user && APPROVE_ROLES.has(user.role);
  const [rows, setRows] = useState([]);
  const [kpis, setKpis] = useState({});
  const [defaults, setDefaults] = useState({ gst_pct: 18, retention_pct: 0, tds_pct: 0, due_days: 30, currency_symbol: "₹", locale: "en-IN" });
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blankBill());
  const [viewing, setViewing] = useState(null);
  const [fromMeasOpen, setFromMeasOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(null);
  const [emailFor, setEmailFor] = useState(null);

  const load = async () => {
    try {
      const params = statusFilter ? `?status=${statusFilter}` : "";
      const [r1, r2, r3] = await Promise.all([
        api.get(`/ra-bills${params}`), api.get("/ra-bills/dashboard"),
        api.get("/admin/billing-defaults"),
      ]);
      setRows(r1.data || []); setKpis(r2.data?.kpis || {}); setDefaults(r3.data || defaults);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load bills"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter]);

  const create = async () => {
    if (!form.items.length) { toast.error("Add at least one item"); return; }
    try {
      const { data } = await api.post("/ra-bills", { ...form, items: form.items.map((i) => ({ ...i, quantity: Number(i.quantity) || 0, rate: Number(i.rate) || 0 })) });
      toast.success(`${data.bill_number} saved`);
      setOpen(false); setForm(blankBill()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const submit = async (b) => { try { await api.post(`/ra-bills/${b.id}/submit`); toast.success("Submitted"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  const approve = async (b) => { try { await api.post(`/ra-bills/${b.id}/approve`); toast.success("Approved · measurements flipped to billed"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  const issue = async (b) => { const days = window.prompt("Due days from issue date?", String(defaults.due_days || 30)); if (!days) return; try { await api.post(`/ra-bills/${b.id}/issue-invoice`, { due_days: Number(days) || 30 }); toast.success("Invoiced"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  const cancelBill = async (b) => { const reason = window.prompt("Cancellation reason (required)") || ""; if (!reason.trim()) return; try { await api.post(`/ra-bills/${b.id}/cancel`, { reason }); toast.success("Cancelled"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  const remove = async (b) => { if (!window.confirm(`Delete ${b.bill_number}?`)) return; try { await api.delete(`/ra-bills/${b.id}`); toast.success("Deleted"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.bill_number, r.client_name, r.project_code, r.po_number, r.status, r.bill_type]
      .some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="ra-bills-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Receipt className="h-3 w-3" /> Accounts · Billing
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Running Bills (RA)</h1>
        <p className="text-sm text-muted-foreground mt-1">Generate running, final, supplementary bills + debit/credit notes from certified measurements. Retention · TDS · GST · approval workflow.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Total Bills" value={kpis.total_bills} tone="neutral" testid="ra-kpi-total" />
        <Kpi label="Billed This Month" value={inr(kpis.billed_this_month)} tone="success" testid="ra-kpi-billed" />
        <Kpi label="Retention Held" value={inr(kpis.retention_held)} tone="info" testid="ra-kpi-retention" />
        <Kpi label="TDS Deducted" value={inr(kpis.tds_deducted)} tone="warning" testid="ra-kpi-tds" />
        <Kpi label="Net Due" value={inr(kpis.net_due)} tone={kpis.net_due ? "danger" : "neutral"} testid="ra-kpi-due" />
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search bill #, client, project…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="ra-search" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ra-status-filter">
            <option value="">All</option>
            {["draft", "submitted", "approved", "invoiced", "paid", "cancelled"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={load}><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" className="h-9 rounded-sm" onClick={() => setFromMeasOpen(true)} data-testid="ra-from-meas"><FileText className="h-4 w-4 mr-1" /> From Measurements</Button>
            <Button className="h-9 rounded-sm" onClick={() => { setForm(blankBill(defaults)); setOpen(true); }} data-testid="ra-add"><Plus className="h-4 w-4 mr-1" /> New RA Bill</Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Bill #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Client · Project</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Type</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Gross</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Net Payable</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {filtered.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10 text-sm">No RA bills yet.</TableCell></TableRow>}
              {filtered.map((b) => (
                <TableRow key={b.id} data-testid={`ra-row-${b.id}`}>
                  <TableCell className="font-mono-data text-sm font-bold">{b.bill_number}</TableCell>
                  <TableCell className="text-xs">{b.bill_date}</TableCell>
                  <TableCell className="text-xs">
                    <div className="font-semibold">{b.client_name || "—"}</div>
                    <div className="text-muted-foreground">{b.project_code || "—"}</div>
                  </TableCell>
                  <TableCell className="text-xs">{(b.bill_type || "running").replaceAll("_", " ")}</TableCell>
                  <TableCell className="font-mono-data text-sm tabular">{inr(b.gross_value)}</TableCell>
                  <TableCell className="font-mono-data text-sm tabular font-bold">{inr(b.net_payable)}{b.balance_due != null && b.balance_due !== b.net_payable && <div className="text-[10px] text-warning">Bal: {inr(b.balance_due)}</div>}</TableCell>
                  <TableCell><StatusBadge text={(b.status || "").replaceAll("_", " ")} tone={STATUS_TONE[b.status] || "neutral"} /></TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1 flex-wrap justify-end">
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setViewing(b)} data-testid={`ra-view-${b.id}`}><Eye className="h-3 w-3" /></Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setEmailFor(b)} data-testid={`ra-email-${b.id}`}><Mail className="h-3 w-3 mr-1" />Email</Button>
                      {b.status === "draft" && <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => submit(b)} data-testid={`ra-submit-${b.id}`}><Send className="h-3 w-3 mr-1" />Submit</Button>}
                      {canApprove && b.status === "submitted" && <Button size="sm" className="h-7 rounded-sm bg-success text-success-foreground hover:bg-success/90" onClick={() => approve(b)} data-testid={`ra-approve-${b.id}`}><CheckCircle2 className="h-3 w-3 mr-1" />Approve</Button>}
                      {canApprove && b.status === "approved" && <Button size="sm" className="h-7 rounded-sm" onClick={() => issue(b)} data-testid={`ra-issue-${b.id}`}><Receipt className="h-3 w-3 mr-1" />Invoice</Button>}
                      {canApprove && b.status === "invoiced" && <Button size="sm" className="h-7 rounded-sm bg-success text-success-foreground hover:bg-success/90" onClick={() => setPaymentOpen(b)} data-testid={`ra-pay-${b.id}`}><Banknote className="h-3 w-3 mr-1" />Receive</Button>}
                      {canApprove && ["approved", "invoiced"].includes(b.status) && <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => cancelBill(b)} data-testid={`ra-cancel-${b.id}`}><XCircle className="h-3 w-3 mr-1" />Cancel</Button>}
                      {["draft", "cancelled"].includes(b.status) && canApprove && <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(b)} data-testid={`ra-delete-${b.id}`}><Trash2 className="h-3 w-3" /></Button>}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {open && <FormDialog form={form} setForm={setForm} onClose={() => setOpen(false)} onSave={create} />}
      {fromMeasOpen && <FromMeasurementsDialog defaults={defaults} onClose={() => { setFromMeasOpen(false); load(); }} />}
      {viewing && <ViewDialog bill={viewing} onClose={() => setViewing(null)} />}
      {paymentOpen && <PaymentDialog bill={paymentOpen} onClose={() => { setPaymentOpen(null); load(); }} />}
      <SendEmailDialog
        open={!!emailFor}
        onOpenChange={(o) => !o && setEmailFor(null)}
        module="ra_bill"
        recordId={emailFor?.id}
      />
    </div>
  );
}

function FormDialog({ form, setForm, onClose, onSave }) {
  const setItem = (i, patch) => setForm({ ...form, items: form.items.map((x, ix) => ix === i ? { ...x, ...patch } : x) });
  const subtotal = form.items.reduce((a, i) => a + (Number(i.quantity) || 0) * (Number(i.rate) || 0), 0);
  const gst = subtotal * (Number(form.gst_pct) || 0) / 100;
  const gross = subtotal + gst;
  const ret = subtotal * (Number(form.retention_pct) || 0) / 100;
  const tds = subtotal * (Number(form.tds_pct) || 0) / 100;
  const net = gross - ret - tds - (Number(form.advance_recovery) || 0);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="ra-form-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">New RA Bill</DialogTitle>
          <DialogDescription className="sr-only">Create a running, final, supplementary, debit or credit bill.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SelectField label="Bill type" value={form.bill_type} options={["running", "final", "supplementary", "debit_note", "credit_note"]} onChange={(v) => setForm({ ...form, bill_type: v })} testid="ra-form-type" />
            <Field label="Bill date" type="date" value={form.bill_date} onChange={(v) => setForm({ ...form, bill_date: v })} testid="ra-form-date" />
            <Field label="Client name" value={form.client_name} onChange={(v) => setForm({ ...form, client_name: v })} testid="ra-form-client" />
            <Field label="Project code" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} testid="ra-form-project" />
            <Field label="PO number" value={form.po_number} onChange={(v) => setForm({ ...form, po_number: v })} />
            <Field label="Site name" value={form.site_name} onChange={(v) => setForm({ ...form, site_name: v })} />
            {(form.bill_type === "debit_note" || form.bill_type === "credit_note") && (
              <>
                <Field label="Against RA Bill ID *" value={form.against_ra_bill_id || ""} onChange={(v) => setForm({ ...form, against_ra_bill_id: v })} testid="ra-form-against" />
                <Field label="Reason *" value={form.reason || ""} onChange={(v) => setForm({ ...form, reason: v })} testid="ra-form-reason" />
              </>
            )}
          </div>

          <div className="border border-border rounded-sm">
            <div className="flex items-center justify-between p-2.5 border-b border-border">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Line items</div>
              <Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: [...form.items, { description: "", quantity: 1, unit: "m²", rate: 0 }] })} data-testid="ra-form-add-line"><Plus className="h-3 w-3 mr-1" /> Add</Button>
            </div>
            <Table>
              <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
                <TableHead className="text-[10px] uppercase tracking-wider">Description</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Amount</TableHead>
                <TableHead></TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {form.items.map((it, i) => (
                  <TableRow key={`it-${i}`}>
                    <TableCell><Input value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} className="h-8 rounded-sm" data-testid={`ra-form-desc-${i}`} /></TableCell>
                    <TableCell><Input type="number" value={it.quantity} onChange={(e) => setItem(i, { quantity: e.target.value })} className="h-8 rounded-sm w-20 tabular" data-testid={`ra-form-qty-${i}`} /></TableCell>
                    <TableCell><Input value={it.unit} onChange={(e) => setItem(i, { unit: e.target.value })} className="h-8 rounded-sm w-20" /></TableCell>
                    <TableCell><Input type="number" value={it.rate} onChange={(e) => setItem(i, { rate: e.target.value })} className="h-8 rounded-sm w-24 tabular" data-testid={`ra-form-rate-${i}`} /></TableCell>
                    <TableCell className="font-mono-data tabular text-xs font-bold">{inr((Number(it.quantity) || 0) * (Number(it.rate) || 0))}</TableCell>
                    <TableCell><Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: form.items.filter((_, ix) => ix !== i) })}><X className="h-3 w-3" /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="GST %" type="number" value={form.gst_pct} onChange={(v) => setForm({ ...form, gst_pct: v })} testid="ra-form-gst" />
            <Field label="Retention %" type="number" value={form.retention_pct} onChange={(v) => setForm({ ...form, retention_pct: v })} testid="ra-form-retention" />
            <Field label="TDS %" type="number" value={form.tds_pct} onChange={(v) => setForm({ ...form, tds_pct: v })} testid="ra-form-tds" />
            <Field label="Advance recovery" type="number" value={form.advance_recovery} onChange={(v) => setForm({ ...form, advance_recovery: v })} testid="ra-form-adv" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 bg-muted/30 border border-border rounded-sm p-3">
            <Tot label="Subtotal" v={inr(subtotal)} />
            <Tot label={`GST (${form.gst_pct}%)`} v={inr(gst)} />
            <Tot label="Gross" v={inr(gross)} />
            <Tot label="Deductions" v={inr(ret + tds + (Number(form.advance_recovery) || 0))} tone="warning" />
            <Tot label="Net Payable" v={inr(net)} tone="success" />
          </div>

          <TextArea label="Notes" value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={onSave} data-testid="ra-form-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FromMeasurementsDialog({ defaults = {}, onClose }) {
  const [list, setList] = useState([]);
  const [picked, setPicked] = useState(new Set());
  const [gst, setGst] = useState(defaults.gst_pct ?? 18);
  const [ret, setRet] = useState(defaults.retention_pct ?? 0);
  const [tds, setTds] = useState(defaults.tds_pct ?? 0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/measurements?status=approved_for_billing").then((r) => setList(r.data || [])).catch(() => setList([]));
  }, []);
  const toggle = (id) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const go = async () => {
    if (!picked.size) { toast.error("Pick at least one measurement"); return; }
    setBusy(true);
    try {
      const first = list.find((m) => picked.has(m.id));
      const { data } = await api.post("/ra-bills/from-measurements", {
        measurement_ids: Array.from(picked),
        client_name: first?.client_name, project_code: first?.project_code,
        gst_pct: Number(gst), retention_pct: Number(ret), tds_pct: Number(tds),
      });
      toast.success(`${data.bill_number} drafted — net ${inr(data.net_payable)}`);
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="ra-from-meas-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Draft Bill from Approved Measurements</DialogTitle>
          <DialogDescription className="sr-only">Pick measurements approved for billing and stamp tax + retention.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="grid grid-cols-3 gap-3">
            <Field label="GST %" type="number" value={gst} onChange={setGst} />
            <Field label="Retention %" type="number" value={ret} onChange={setRet} />
            <Field label="TDS %" type="number" value={tds} onChange={setTds} />
          </div>
          {list.length === 0 ? (
            <div className="text-center text-sm text-muted-foreground py-6">No approved-for-billing measurements available.</div>
          ) : (
            <Table>
              <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead></TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">MEAS #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Lines</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Billable</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {list.map((m) => (
                  <TableRow key={m.id} className={picked.has(m.id) ? "bg-primary/10" : ""}>
                    <TableCell><input type="checkbox" checked={picked.has(m.id)} onChange={() => toggle(m.id)} data-testid={`ra-pick-${m.id}`} /></TableCell>
                    <TableCell className="font-mono-data text-xs font-bold">{m.measurement_no}</TableCell>
                    <TableCell className="text-xs">{m.project_code}</TableCell>
                    <TableCell className="text-xs">{(m.items || []).length}</TableCell>
                    <TableCell className="font-mono-data text-xs font-bold">{inr(m.billable_value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={go} disabled={busy || !picked.size} data-testid="ra-from-meas-go">{busy ? "…" : "Draft Bill"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ViewDialog({ bill, onClose }) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="ra-view-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-3">
            {bill.bill_number} <StatusBadge text={(bill.status || "").replaceAll("_", " ")} tone={STATUS_TONE[bill.status] || "neutral"} />
          </DialogTitle>
          <DialogDescription className="sr-only">Bill detail.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <KV label="Bill Date" v={bill.bill_date} />
            <KV label="Type" v={bill.bill_type} />
            <KV label="Client" v={bill.client_name} />
            <KV label="Project" v={bill.project_code} />
            <KV label="PO #" v={bill.po_number} />
            <KV label="Issue Date" v={bill.issue_date} />
            <KV label="Due Date" v={bill.due_date} />
            <KV label="Invoice #" v={bill.invoice_no} />
          </div>
          <Table>
            <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead className="text-[10px] uppercase tracking-wider">Description</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Amount</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(bill.items || []).map((it, i) => (
                <TableRow key={`bi-${i}`}>
                  <TableCell className="text-xs">{it.description}{it.measurement_no && <div className="text-[10px] text-muted-foreground">From {it.measurement_no}</div>}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs">{it.quantity}</TableCell>
                  <TableCell className="text-xs">{it.unit}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs">{inr(it.rate)}</TableCell>
                  <TableCell className="font-mono-data tabular text-xs font-bold">{inr(it.amount)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-muted/30 border border-border rounded-sm p-3 text-xs">
            <KV label="Subtotal" v={inr(bill.subtotal)} />
            <KV label="GST" v={inr(bill.gst_amount)} />
            <KV label="Gross" v={inr(bill.gross_value)} />
            <KV label="Retention" v={inr(bill.retention_amount)} />
            <KV label="TDS" v={inr(bill.tds_amount)} />
            <KV label="Other Deductions" v={inr(bill.other_deductions_total)} />
            <KV label="Advance Recovery" v={inr(bill.advance_recovery)} />
            <div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">Net Payable</div><div className="font-display font-black text-lg text-success tabular">{inr(bill.net_payable)}</div></div>
            {bill.paid_amount > 0 && <KV label="Paid" v={inr(bill.paid_amount)} />}
            {bill.balance_due != null && <KV label="Balance Due" v={inr(bill.balance_due)} />}
          </div>
          {(bill.payments || []).length > 0 && (
            <div className="border border-border rounded-sm p-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">Payments</div>
              {bill.payments.map((p, i) => <div key={`p-${i}`} className="text-xs flex justify-between"><span className="font-mono-data">{p.payment_no}</span><span>{p.date}</span><span className="tabular font-bold">{inr(p.amount)}</span><span className="text-muted-foreground">{p.mode}</span></div>)}
            </div>
          )}
          {bill.notes && <div className="border border-border rounded-sm p-2.5 text-xs"><div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1">Notes</div>{bill.notes}</div>}
          {bill.cancel_reason && <div className="bg-destructive/10 border border-destructive/40 rounded-sm p-2.5 text-xs text-destructive"><strong>Cancelled:</strong> {bill.cancel_reason}</div>}
        </div>
        <DialogFooter><Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PaymentDialog({ bill, onClose }) {
  const [amount, setAmount] = useState(bill.balance_due ?? bill.net_payable);
  const [mode, setMode] = useState("bank_transfer");
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!Number(amount)) { toast.error("Amount required"); return; }
    setBusy(true);
    try {
      await api.post("/payments-in", {
        client_id: bill.client_id, client_name: bill.client_name,
        amount: Number(amount), mode, reference_no: ref,
        allocations: [{ ra_bill_id: bill.id, amount: Number(amount) }],
      });
      toast.success("Payment recorded");
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md rounded-sm" data-testid="ra-pay-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Receive Payment · {bill.bill_number}</DialogTitle>
          <DialogDescription className="sr-only">Record inbound payment.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Field label="Amount" type="number" value={amount} onChange={setAmount} testid="ra-pay-amount" />
          <SelectField label="Mode" value={mode} options={["bank_transfer", "cheque", "cash", "upi", "rtgs", "neft"]} onChange={setMode} testid="ra-pay-mode" />
          <Field label="Reference / UTR" value={ref} onChange={setRef} testid="ra-pay-ref" />
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={go} disabled={busy} data-testid="ra-pay-go">{busy ? "…" : "Record"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Kpi({ label, value, tone, testid }) {
  const c = { success: "text-success", warning: "text-warning", danger: "text-destructive", info: "text-chart-3", neutral: "text-primary" }[tone] || "text-primary";
  return (
    <div className="bg-card border border-border rounded-sm p-3" data-testid={testid}>
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-display font-black text-2xl tabular mt-1 ${c}`}>{value ?? 0}</div>
    </div>
  );
}
function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
function TextArea({ label, value, onChange, testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Textarea value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="rounded-sm mt-1 min-h-[60px]" data-testid={testid} />
    </div>
  );
}
function SelectField({ label, value, options, onChange, testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid={testid}>
        {options.map((o) => <option key={o} value={o}>{(o || "").replaceAll("_", " ")}</option>)}
      </select>
    </div>
  );
}
function Tot({ label, v, tone }) {
  const c = { success: "text-success", warning: "text-warning", danger: "text-destructive" }[tone] || "text-foreground";
  return <div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className={`font-mono-data tabular text-sm font-bold ${c}`}>{v}</div></div>;
}
function KV({ label, v }) {
  return <div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="font-mono-data tabular">{v ?? "—"}</div></div>;
}
