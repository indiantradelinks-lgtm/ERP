/**
 * Billing & Receivables Views · Phase 2
 * ======================================
 * Sub-views rendered inside the Accounts module shell.
 * Endpoints under `/api/billing/*`.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Plus, RefreshCcw, CheckCircle2, AlertCircle, FileSpreadsheet, X, Paperclip, Eye, Upload, ExternalLink, FileText } from "lucide-react";
import FileUploader from "@/components/FileUploader";
import { fmt } from "./AccountsViews";

const INVOICE_TYPE_OPTS = [
  ["TAX", "Tax Invoice"], ["PROF", "Proforma Invoice"], ["RA", "RA Bill"],
  ["FINAL", "Final Bill"], ["MOB", "Mobilization Advance"], ["RETN", "Retention Invoice"],
  ["EXTRA", "Extra Work Invoice"], ["REIMB", "Reimbursement"],
  ["DN", "Debit Note"], ["CN", "Credit Note"],
];

const SERVICE_TYPE_OPTS = [
  ["scaffolding", "Scaffolding"], ["painting", "Painting"], ["roof_sheeting", "Roof Sheeting"],
  ["rope_access", "Rope Access"], ["manpower", "Manpower Supply"], ["material_supply", "Material Supply"],
  ["other", "Other"],
];

const STATUS_COLORS = {
  draft: "bg-slate-100 text-slate-700",
  approved: "bg-emerald-100 text-emerald-800",
  partially_paid: "bg-amber-100 text-amber-800",
  paid: "bg-green-100 text-green-800",
  cancelled: "bg-rose-100 text-rose-800",
};

function Field({ label, children, className = "" }) {
  return (
    <div className={className}>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      {children}
    </div>
  );
}

/* ═══════════════════ Client Invoices ═══════════════════ */
export function ClientInvoicesView() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ invoice_type: "", status: "" });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(newInvoiceFormState());

  function newInvoiceFormState() {
    return {
      invoice_type: "RA",
      invoice_date: new Date().toISOString().slice(0, 10),
      client_name: "",
      client_gstin: "",
      billing_address: "",
      site_address: "",
      project_code: "",
      work_order_no: "",
      contract_value: 0,
      billing_period_from: "",
      billing_period_to: "",
      service_type: "scaffolding",
      description: "",
      lines: [{ description: "", quantity: 1, unit: "Lot", rate: 0 }],
      gst_rate: 18,
      is_intra_state: true,
      tds_rate: 2,
      retention_rate: 5,
      due_days: 30,
    };
  }

  const load = () => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v));
    api.get(`/billing/invoices?${params}`).then(r => setRows(r.data || []));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filter.invoice_type, filter.status]);

  const totals = useMemo(() => {
    const taxable = form.lines.reduce((a, l) => a + Number(l.quantity || 0) * Number(l.rate || 0), 0);
    const gst = taxable * (form.gst_rate || 0) / 100;
    const gross = taxable + gst;
    const tds = taxable * (form.tds_rate || 0) / 100;
    const retn = taxable * (form.retention_rate || 0) / 100;
    return { taxable, gst, gross, tds, retn, net: gross - tds - retn };
  }, [form.lines, form.gst_rate, form.tds_rate, form.retention_rate]);

  const submit = async () => {
    if (!form.client_name) { toast.error("Client name required"); return; }
    if (["RA","FINAL","MOB","RETN","EXTRA"].includes(form.invoice_type) && !form.project_code) {
      toast.error(`Project Code is required for ${form.invoice_type} invoices`);
      return;
    }
    try {
      await api.post("/billing/invoices", form);
      toast.success("Invoice created");
      setOpen(false); setForm(newInvoiceFormState()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const approve = async (r) => {
    if (!window.confirm(`Approve ${r.invoice_no}? This will post the JE and lock the invoice.`)) return;
    try {
      await api.post(`/billing/invoices/${r.id}/approve`);
      toast.success("Invoice approved + JE posted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Client Invoices <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={filter.invoice_type} onChange={e => setFilter({ ...filter, invoice_type: e.target.value })}>
            <option value="">All types</option>
            {INVOICE_TYPE_OPTS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={filter.status} onChange={e => setFilter({ ...filter, status: e.target.value })}>
            <option value="">All statuses</option>
            <option value="draft">Draft</option><option value="approved">Approved</option>
            <option value="partially_paid">Partially Paid</option><option value="paid">Paid</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setOpen(true)} data-testid="bill-inv-add"><Plus className="h-3.5 w-3.5 mr-1" />New Invoice</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Invoice #</th>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Date</th>
                <th className="text-left px-3 py-2">Client</th>
                <th className="text-left px-3 py-2">WO</th>
                <th className="text-right px-3 py-2">Taxable</th>
                <th className="text-right px-3 py-2">Gross</th>
                <th className="text-right px-3 py-2">Outstanding</th>
                <th className="text-center px-3 py-2">Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`bill-inv-row-${r.invoice_no}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5 text-xs"><span className="inline-block px-1.5 py-0.5 rounded border text-[10px] bg-slate-50">{r.invoice_type}</span></td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_date}</td>
                  <td className="px-3 py-1.5">{r.client_name}</td>
                  <td className="px-3 py-1.5 text-xs">{r.work_order_no || "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.totals?.taxable_value)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.totals?.gross_value)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.outstanding)}</td>
                  <td className="px-3 py-1.5 text-center">
                    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[r.status] || ""}`}>{r.status}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {r.status === "draft" && (
                      <Button size="sm" onClick={() => approve(r)} data-testid={`bill-inv-approve-${r.invoice_no}`}>
                        <CheckCircle2 className="h-3 w-3 mr-1" />Approve
                      </Button>
                    )}
                    {r.je_voucher_number && <span className="text-[10px] text-slate-500 font-mono">{r.je_voucher_number}</span>}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={10} className="text-center py-6 text-xs text-slate-400">No invoices.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Client Invoice</DialogTitle></DialogHeader>
          <div className="grid grid-cols-4 gap-2">
            <Field label="Type *">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.invoice_type} onChange={e => setForm({ ...form, invoice_type: e.target.value })} data-testid="bill-inv-type">
                {INVOICE_TYPE_OPTS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Invoice Date *"><Input type="date" value={form.invoice_date} onChange={e => setForm({ ...form, invoice_date: e.target.value })} /></Field>
            <Field label="Service Type *">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.service_type} onChange={e => setForm({ ...form, service_type: e.target.value })} data-testid="bill-inv-service">
                {SERVICE_TYPE_OPTS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Due Days"><Input type="number" value={form.due_days} onChange={e => setForm({ ...form, due_days: Number(e.target.value) })} /></Field>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-2">
            <Field label="Client *"><Input value={form.client_name} onChange={e => setForm({ ...form, client_name: e.target.value })} data-testid="bill-inv-client" /></Field>
            <Field label="Client GSTIN"><Input value={form.client_gstin} onChange={e => setForm({ ...form, client_gstin: e.target.value })} /></Field>
            <Field label={["RA","FINAL","MOB","RETN","EXTRA"].includes(form.invoice_type) ? "Project Code *" : "Project Code"}>
              <Input value={form.project_code} onChange={e => setForm({ ...form, project_code: e.target.value })} data-testid="bill-inv-project" />
            </Field>
            <Field label={["RA","FINAL"].includes(form.invoice_type) ? "Work Order # *" : "Work Order #"}>
              <Input value={form.work_order_no} onChange={e => setForm({ ...form, work_order_no: e.target.value })} />
            </Field>
            <Field label="Contract Value"><Input type="number" value={form.contract_value} onChange={e => setForm({ ...form, contract_value: Number(e.target.value) })} /></Field>
            <Field label="Billing Address"><Input value={form.billing_address} onChange={e => setForm({ ...form, billing_address: e.target.value })} /></Field>
          </div>

          <div className="mt-3">
            <Label className="text-[10px] uppercase tracking-wider mb-1 block">Lines</Label>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs">
                  <tr><th className="text-left px-2 py-1">Description</th><th className="text-right px-2 py-1">Qty</th><th className="text-left px-2 py-1">Unit</th><th className="text-right px-2 py-1">Rate</th><th className="text-right px-2 py-1">Amount</th><th></th></tr>
                </thead>
                <tbody>
                  {form.lines.map((ln, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1"><Input value={ln.description} onChange={e => { const lines = [...form.lines]; lines[i].description = e.target.value; setForm({ ...form, lines }); }} className="h-8" data-testid={`bill-inv-line-${i}-desc`} /></td>
                      <td className="px-2 py-1"><Input type="number" value={ln.quantity} onChange={e => { const lines = [...form.lines]; lines[i].quantity = Number(e.target.value); setForm({ ...form, lines }); }} className="h-8 text-right w-20" /></td>
                      <td className="px-2 py-1"><Input value={ln.unit} onChange={e => { const lines = [...form.lines]; lines[i].unit = e.target.value; setForm({ ...form, lines }); }} className="h-8 w-20" /></td>
                      <td className="px-2 py-1"><Input type="number" value={ln.rate} onChange={e => { const lines = [...form.lines]; lines[i].rate = Number(e.target.value); setForm({ ...form, lines }); }} className="h-8 text-right" data-testid={`bill-inv-line-${i}-rate`} /></td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(Number(ln.quantity || 0) * Number(ln.rate || 0))}</td>
                      <td><Button size="sm" variant="ghost" onClick={() => setForm({ ...form, lines: form.lines.filter((_, x) => x !== i) })}><X className="h-3 w-3" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button variant="outline" size="sm" className="mt-2" onClick={() => setForm({ ...form, lines: [...form.lines, { description: "", quantity: 1, unit: "Lot", rate: 0 }] })}>+ Line</Button>
          </div>

          <div className="grid grid-cols-4 gap-2 mt-3">
            <Field label="GST Rate %"><Input type="number" value={form.gst_rate} onChange={e => setForm({ ...form, gst_rate: Number(e.target.value) })} /></Field>
            <Field label="Tax Type">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.is_intra_state ? "intra" : "inter"} onChange={e => setForm({ ...form, is_intra_state: e.target.value === "intra" })}>
                <option value="intra">Intra-state (CGST+SGST)</option>
                <option value="inter">Inter-state (IGST)</option>
              </select>
            </Field>
            <Field label="TDS %"><Input type="number" value={form.tds_rate} onChange={e => setForm({ ...form, tds_rate: Number(e.target.value) })} /></Field>
            <Field label="Retention %"><Input type="number" value={form.retention_rate} onChange={e => setForm({ ...form, retention_rate: Number(e.target.value) })} /></Field>
          </div>

          <div className="border rounded-md p-3 bg-slate-50 mt-3">
            <div className="grid grid-cols-6 gap-2 text-sm">
              <div><div className="text-[10px] uppercase text-slate-500">Taxable</div><div className="font-semibold tabular-nums">{fmt(totals.taxable)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">GST ({form.gst_rate}%)</div><div className="font-semibold tabular-nums">{fmt(totals.gst)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">Gross</div><div className="font-semibold tabular-nums text-blue-700">{fmt(totals.gross)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">TDS Expected</div><div className="font-semibold tabular-nums text-rose-700">−{fmt(totals.tds)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">Retention</div><div className="font-semibold tabular-nums text-rose-700">−{fmt(totals.retn)}</div></div>
              <div><div className="text-[10px] uppercase text-slate-500">Net Receivable</div><div className="font-bold tabular-nums text-emerald-700">{fmt(totals.net)}</div></div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} data-testid="bill-inv-save">Create Draft</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════ Receipts ═══════════════════ */
export function ReceiptsView() {
  const [rows, setRows] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [form, setForm] = useState(newReceiptFormState());

  function newReceiptFormState() {
    return {
      receipt_date: new Date().toISOString().slice(0, 10),
      client_id: "", client_name: "", project_id: "", project_code: "",
      invoice_ids: [], mode: "Bank", bank_account: "",
      txn_reference: "", amount: 0, tds_deducted: 0,
      retention_deducted: 0, other_deduction: 0,
      excess_reason: "", remarks: "",
    };
  }

  const load = () => api.get("/billing/receipts").then(r => setRows(r.data || []));
  const loadInvoices = () => api.get("/billing/invoices?status=approved").then(r => setInvoices(r.data || []));
  const loadClients = () => api.get("/clients").then(r => setClients(r.data || [])).catch(() => {});
  const loadProjects = () => api.get("/projects").then(r => setProjects(r.data || [])).catch(() => {});
  useEffect(() => { load(); loadClients(); loadProjects(); }, []);

  const openCreate = () => {
    loadInvoices();
    setForm(newReceiptFormState());
    setUploadedFiles([]);
    setOpen(true);
  };

  const openDetail = async (r) => {
    try {
      const { data } = await api.get(`/billing/receipts/${r.id}`);
      setDetail(data);
    } catch { setDetail(r); }
  };

  const totalAdj = Number(form.amount || 0) + Number(form.tds_deducted || 0) + Number(form.retention_deducted || 0) + Number(form.other_deduction || 0);

  const selectClient = (cid) => {
    const c = clients.find(x => x.id === cid);
    setForm(prev => ({ ...prev, client_id: cid, client_name: c?.name || "", project_id: "", project_code: "", invoice_ids: [] }));
  };

  const selectProject = (pid) => {
    const p = projects.find(x => x.id === pid);
    setForm(prev => ({ ...prev, project_id: pid, project_code: p?.code || "" }));
  };

  const submit = async () => {
    if (!form.client_name && !form.client_id) { toast.error("Select a client"); return; }
    if (!form.amount && !form.tds_deducted && !form.retention_deducted) { toast.error("Enter amount or deduction"); return; }
    try {
      const payload = { ...form, file_ids: uploadedFiles.map(f => f.id) };
      await api.post("/billing/receipts", payload);
      toast.success("Receipt posted + JE created");
      setOpen(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const clientProjects = projects.filter(p => !form.client_id || (p.client_id === form.client_id || p.client === form.client_name));
  const eligibleInvoices = invoices.filter(i => {
    if (form.client_id && i.client_id !== form.client_id && i.client_name !== form.client_name) return false;
    if (!form.client_id && form.client_name && i.client_name !== form.client_name) return false;
    return true;
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Receipts <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={openCreate} data-testid="bill-rcpt-add"><Plus className="h-3.5 w-3.5 mr-1" />New Receipt</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Receipt #</th>
                <th className="text-left px-3 py-2">Created</th>
                <th className="text-left px-3 py-2">Date</th>
                <th className="text-left px-3 py-2">Client</th>
                <th className="text-left px-3 py-2">Project</th>
                <th className="text-left px-3 py-2">Mode</th>
                <th className="text-left px-3 py-2">UTR/Ref</th>
                <th className="text-right px-3 py-2">Amount</th>
                <th className="text-right px-3 py-2">TDS</th>
                <th className="text-right px-3 py-2">Retention</th>
                <th className="text-right px-3 py-2">Adjusted</th>
                <th className="text-center px-3 py-2">Files</th>
                <th className="text-left px-3 py-2">JE</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50 cursor-pointer" data-testid={`bill-rcpt-row-${r.receipt_no}`} onClick={() => openDetail(r)}>
                  <td className="px-3 py-1.5 font-mono text-xs text-blue-700 underline">{r.receipt_no}</td>
                  <td className="px-3 py-1.5 text-xs whitespace-nowrap">{r.created_at ? <>{r.created_at.slice(0, 10)}<div className="text-[10px] text-muted-foreground">{r.created_at.slice(11, 16)}</div></> : "—"}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.receipt_date}</td>
                  <td className="px-3 py-1.5 text-xs">{r.client_name}</td>
                  <td className="px-3 py-1.5 font-mono text-[10px]">{r.project_code || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{r.mode}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.txn_reference || "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.amount)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.tds_deducted)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.retention_deducted)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.total_adjusted)}</td>
                  <td className="px-3 py-1.5 text-center">{(r.file_ids?.length || 0) > 0 ? <Paperclip className="h-3.5 w-3.5 text-amber-600 inline" /> : "—"}</td>
                  <td className="px-3 py-1.5 font-mono text-[10px]">{r.je_voucher_number || "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={13} className="text-center py-6 text-xs text-slate-400">No receipts yet. Click "New Receipt" to record a payment received.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>

      {/* ─── New Receipt Dialog ─── */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Receipt</DialogTitle><DialogDescription>Record a payment received from a client against open invoices.</DialogDescription></DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Date *"><Input type="date" value={form.receipt_date} onChange={e => setForm({ ...form, receipt_date: e.target.value })} data-testid="bill-rcpt-date" /></Field>
            <Field label="Client *">
              <select className="h-9 w-full rounded-sm border bg-background px-2 text-sm" value={form.client_id}
                onChange={e => selectClient(e.target.value)} data-testid="bill-rcpt-client">
                <option value="">— select client —</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Project">
              <select className="h-9 w-full rounded-sm border bg-background px-2 text-sm" value={form.project_id}
                onChange={e => selectProject(e.target.value)} data-testid="bill-rcpt-project">
                <option value="">— select project —</option>
                {clientProjects.map(p => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </Field>
            <Field label="Mode *">
              <select className="h-9 w-full rounded-sm border bg-background px-2 text-sm" value={form.mode} onChange={e => setForm({ ...form, mode: e.target.value })} data-testid="bill-rcpt-mode">
                {["Bank", "Cash", "UPI", "NEFT", "RTGS", "IMPS", "Cheque"].map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Bank Account"><Input value={form.bank_account} onChange={e => setForm({ ...form, bank_account: e.target.value })} data-testid="bill-rcpt-bank" /></Field>
            <Field label="UTR / Cheque #"><Input value={form.txn_reference} onChange={e => setForm({ ...form, txn_reference: e.target.value })} data-testid="bill-rcpt-utr" /></Field>
          </div>

          {/* Invoice selection */}
          {(form.client_id || form.client_name) && eligibleInvoices.length > 0 && (
            <div className="mt-3">
              <Label className="text-[10px] uppercase tracking-wider mb-1 block">Apply to invoices (unpaid / partially paid)</Label>
              <div className="max-h-40 overflow-y-auto border rounded-md text-xs">
                {eligibleInvoices.map(i => (
                  <label key={i.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-slate-50 border-b" data-testid={`bill-rcpt-inv-${i.id}`}>
                    <input type="checkbox" checked={form.invoice_ids.includes(i.id)}
                      onChange={e => setForm({ ...form, invoice_ids: e.target.checked ? [...form.invoice_ids, i.id] : form.invoice_ids.filter(x => x !== i.id) })} />
                    <span className="font-mono">{i.invoice_no}</span>
                    <span className="text-slate-500">{i.invoice_date}</span>
                    <span className="text-slate-400">{i.invoice_type}</span>
                    <span className="ml-auto tabular-nums font-semibold text-emerald-700">Outstanding: {fmt(i.outstanding)}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-4 gap-2 mt-3">
            <Field label="Amount Received *"><Input type="number" value={form.amount} onChange={e => setForm({ ...form, amount: Number(e.target.value) })} data-testid="bill-rcpt-amount" /></Field>
            <Field label="TDS Deducted"><Input type="number" value={form.tds_deducted} onChange={e => setForm({ ...form, tds_deducted: Number(e.target.value) })} data-testid="bill-rcpt-tds" /></Field>
            <Field label="Retention Held"><Input type="number" value={form.retention_deducted} onChange={e => setForm({ ...form, retention_deducted: Number(e.target.value) })} data-testid="bill-rcpt-retention" /></Field>
            <Field label="Other Deduction"><Input type="number" value={form.other_deduction} onChange={e => setForm({ ...form, other_deduction: Number(e.target.value) })} data-testid="bill-rcpt-other" /></Field>
          </div>
          <div className="border rounded-md p-2 bg-slate-50 text-sm mt-2">
            <span className="text-[10px] uppercase text-slate-500">Total Adjusted Against Outstanding:</span>
            <span className="ml-2 font-bold tabular-nums">{fmt(totalAdj)}</span>
          </div>
          <Field label="Excess Reason (if total > outstanding)"><Input value={form.excess_reason} onChange={e => setForm({ ...form, excess_reason: e.target.value })} data-testid="bill-rcpt-excess" /></Field>
          <Field label="Remarks"><Input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} data-testid="bill-rcpt-remarks" /></Field>

          {/* File upload */}
          <div className="mt-3">
            <Label className="text-[10px] uppercase tracking-wider mb-1 block">Payment Proof / Receipt Attachment</Label>
            <FileUploader folder="billing" parent_type="receipt" parent_id="new"
              accept=".pdf,.jpg,.jpeg,.png,.webp" files={uploadedFiles}
              onUploaded={(f) => setUploadedFiles(prev => [...prev, f])}
              onDeleted={(fid) => setUploadedFiles(prev => prev.filter(x => x.id !== fid))}
              testidPrefix="bill-rcpt-upload" compact />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} data-testid="bill-rcpt-save">Post Receipt</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── Receipt Detail Dialog ─── */}
      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          {detail && (<>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                Receipt {detail.receipt_no}
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-normal">{detail.status}</span>
              </DialogTitle>
              <DialogDescription>Receipt detail and allocation summary.</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              {[
                ["Receipt Date", detail.receipt_date],
                ["Created", detail.created_at ? `${detail.created_at.slice(0, 10)} ${detail.created_at.slice(11, 16)}` : "—"],
                ["Client", detail.client_name],
                ["Project", detail.project_code || "—"],
                ["Mode", detail.mode],
                ["Bank Account", detail.bank_account || "—"],
                ["UTR / Ref", detail.txn_reference || "—"],
                ["Created By", detail.created_by || "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b py-1">
                  <span className="text-slate-500 text-xs">{k}</span>
                  <span className="font-mono text-xs">{v}</span>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-2 mt-3 p-3 rounded-md bg-slate-50 border">
              {[["Amount Received", detail.amount], ["TDS Deducted", detail.tds_deducted], ["Retention", detail.retention_deducted], ["Total Adjusted", detail.total_adjusted]].map(([k, v]) => (
                <div key={k}>
                  <div className="text-[10px] uppercase text-slate-500">{k}</div>
                  <div className="font-bold tabular-nums text-base">{fmt(v)}</div>
                </div>
              ))}
            </div>
            {detail.other_deduction > 0 && <div className="text-xs text-slate-600">Other Deduction: {fmt(detail.other_deduction)}</div>}
            {detail.excess_reason && <div className="text-xs text-amber-700">Excess Reason: {detail.excess_reason}</div>}
            {detail.remarks && <div className="text-xs text-slate-600 italic mt-1">Remarks: {detail.remarks}</div>}

            {/* Applied invoices */}
            {detail.invoices?.length > 0 && (
              <div className="mt-3">
                <Label className="text-[10px] uppercase tracking-wider">Applied Invoices</Label>
                <div className="border rounded-md mt-1 text-xs">
                  {detail.invoices.map(i => (
                    <div key={i.id} className="flex items-center justify-between px-3 py-1.5 border-b last:border-b-0">
                      <span className="font-mono">{i.invoice_no}</span>
                      <span className="text-slate-400">{i.invoice_date}</span>
                      <span className={`font-semibold ${i.status === "paid" ? "text-emerald-600" : "text-amber-600"}`}>{i.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Attached files */}
            {detail.files?.length > 0 && (
              <div className="mt-3">
                <Label className="text-[10px] uppercase tracking-wider">Attached Files</Label>
                <div className="space-y-1 mt-1">
                  {detail.files.map(f => (
                    <a key={f.id} href={f.file_url} target="_blank" rel="noreferrer"
                      className="flex items-center gap-2 px-3 py-2 border rounded-md hover:bg-slate-50 text-xs">
                      <FileText className="h-4 w-4 text-blue-600" />
                      <span className="flex-1 truncate">{f.title}</span>
                      <ExternalLink className="h-3 w-3 text-slate-400" />
                    </a>
                  ))}
                </div>
              </div>
            )}

            {detail.je_voucher_number && (
              <div className="mt-3 text-xs text-slate-500">Journal Entry: <span className="font-mono">{detail.je_voucher_number}</span></div>
            )}
          </>)}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════ Client Outstanding ═══════════════════ */
export function ClientOutstandingView() {
  const [data, setData] = useState({ buckets: { "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0 }, total_outstanding: 0, clients: [] });
  const load = () => api.get("/billing/reports/client-outstanding").then(r => setData(r.data));
  useEffect(() => { load(); }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Client Outstanding</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-2 mb-4">
          {Object.entries(data.buckets).map(([k, v]) => (
            <div key={k} className="p-3 rounded-md border bg-slate-50">
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{k} days</div>
              <div className="text-lg font-bold tabular-nums text-emerald-700">{fmt(v)}</div>
            </div>
          ))}
          <div className="p-3 rounded-md border-2 border-slate-400 bg-white">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Total Outstanding</div>
            <div className="text-lg font-bold tabular-nums">{fmt(data.total_outstanding)}</div>
          </div>
        </div>
        <div className="space-y-3">
          {(data.clients || []).map(c => (
            <div key={c.client_name} className="border rounded-md">
              <div className="flex justify-between px-3 py-2 bg-slate-100 font-semibold text-sm">
                <span>{c.client_name}</span><span className="tabular-nums">{fmt(c.total_outstanding)}</span>
              </div>
              <table className="w-full text-sm">
                <thead className="text-xs text-slate-500">
                  <tr><th className="text-left px-3 py-1">Invoice #</th><th className="text-left px-3 py-1">Date</th><th className="text-left px-3 py-1">WO</th><th className="text-right px-3 py-1">Outstanding</th><th className="text-center px-3 py-1">Bucket</th></tr>
                </thead>
                <tbody>
                  {c.invoices.map(i => (
                    <tr key={i.invoice_no} className="border-t">
                      <td className="px-3 py-1 font-mono text-xs">{i.invoice_no}</td>
                      <td className="px-3 py-1 font-mono text-xs">{i.invoice_date}</td>
                      <td className="px-3 py-1 text-xs">{i.work_order_no || "—"}</td>
                      <td className="px-3 py-1 text-right tabular-nums">{fmt(i.outstanding)}</td>
                      <td className="px-3 py-1 text-center text-xs">{i.bucket} · {i.days_overdue}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {data.clients?.length === 0 && <div className="text-center py-6 text-xs text-slate-400">Nothing outstanding.</div>}
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ GST Sales Register ═══════════════════ */
export function GSTSalesRegisterView() {
  const [data, setData] = useState({ rows: [], totals: {} });
  const [f, setF] = useState({ start: "", end: "" });
  const run = () => {
    const params = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    api.get(`/billing/reports/gst-sales-register?${params}`).then(r => setData(r.data));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run(); }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">GST Sales Register</CardTitle>
        <div className="flex gap-2">
          <Input type="date" className="h-8 w-36" value={f.start} onChange={e => setF({ ...f, start: e.target.value })} />
          <Input type="date" className="h-8 w-36" value={f.end} onChange={e => setF({ ...f, end: e.target.value })} />
          <Button size="sm" onClick={run}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
          <Button size="sm" variant="outline" onClick={() => window.print()}><FileSpreadsheet className="h-3.5 w-3.5 mr-1" />Print</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Inv #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Client</th><th className="text-left px-3 py-2">GSTIN</th><th className="text-left px-3 py-2">Service</th><th className="text-right px-3 py-2">Taxable</th><th className="text-right px-3 py-2">CGST</th><th className="text-right px-3 py-2">SGST</th><th className="text-right px-3 py-2">IGST</th><th className="text-right px-3 py-2">Gross</th></tr>
            </thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.invoice_no} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_date}</td>
                  <td className="px-3 py-1.5">{r.client_name}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.client_gstin || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{r.service_type}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.taxable_value)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.cgst)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.sgst)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.igst)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.gross_value)}</td>
                </tr>
              ))}
              {data.rows.length === 0 && <tr><td colSpan={10} className="text-center py-6 text-xs text-slate-400">No GST invoices in this period.</td></tr>}
            </tbody>
            <tfoot className="bg-slate-100 font-semibold text-sm">
              <tr>
                <td colSpan={5} className="px-3 py-2 text-right">Totals</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.taxable)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.cgst)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.sgst)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.igst)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals?.gross)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ TDS Receivable ═══════════════════ */
export function TDSReceivableView() {
  const [data, setData] = useState({ clients: [], total_tds: 0 });
  const load = () => api.get("/billing/reports/tds-receivable").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">TDS Receivable <span className="ml-2 text-sm text-slate-500 font-normal">Total: {fmt(data.total_tds)}</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        {(data.clients || []).map(c => (
          <div key={c.client_name} className="border rounded-md mb-2">
            <div className="flex justify-between px-3 py-2 bg-slate-100 font-semibold text-sm">
              <span>{c.client_name}</span><span className="tabular-nums">{fmt(c.tds_deducted)}</span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {c.receipts.map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-3 py-1 font-mono text-xs w-32">{r.receipt_no}</td>
                    <td className="px-3 py-1 font-mono text-xs w-28">{r.receipt_date}</td>
                    <td className="px-3 py-1 text-right tabular-nums">{fmt(r.tds_deducted)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {data.clients?.length === 0 && <div className="text-center py-6 text-xs text-slate-400">No TDS deducted yet.</div>}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Retention Receivable ═══════════════════ */
export function RetentionReceivableView() {
  const [data, setData] = useState({ clients: [], total_retention: 0 });
  const load = () => api.get("/billing/reports/retention-receivable").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Retention Receivable <span className="ml-2 text-sm text-slate-500 font-normal">Total: {fmt(data.total_retention)}</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        {(data.clients || []).map(c => (
          <div key={c.client_name} className="border rounded-md mb-2">
            <div className="flex justify-between px-3 py-2 bg-slate-100 font-semibold text-sm">
              <span>{c.client_name}</span><span className="tabular-nums">{fmt(c.retention_deducted)}</span>
            </div>
          </div>
        ))}
        {data.clients?.length === 0 && <div className="text-center py-6 text-xs text-slate-400">No retention withheld yet.</div>}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Collection Report ═══════════════════ */
export function CollectionReportView() {
  const [data, setData] = useState({ rows: [], totals: {} });
  const load = () => api.get("/billing/reports/collection").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Collection Report</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Total Adjusted</div><div className="text-lg font-bold tabular-nums">{fmt(data.totals?.total_adjusted)}</div></div>
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Cash Received</div><div className="text-lg font-bold tabular-nums text-emerald-700">{fmt(data.totals?.amount_received)}</div></div>
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">TDS Deducted</div><div className="text-lg font-bold tabular-nums text-amber-700">{fmt(data.totals?.tds_deducted)}</div></div>
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Retention Held</div><div className="text-lg font-bold tabular-nums text-amber-700">{fmt(data.totals?.retention_deducted)}</div></div>
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Receipt #</th><th className="text-left px-3 py-2">Created</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Client</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Mode</th><th className="text-right px-3 py-2">Amount</th><th className="text-right px-3 py-2">TDS</th><th className="text-right px-3 py-2">Retn</th><th className="text-right px-3 py-2">Total</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.receipt_no}</td>
                  <td className="px-3 py-1.5 text-xs whitespace-nowrap">{r.created_at ? <>{r.created_at.slice(0, 10)}<div className="text-[10px] text-muted-foreground">{r.created_at.slice(11, 16)}</div></> : "—"}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.receipt_date}</td>
                  <td className="px-3 py-1.5">{r.client_name}</td>
                  <td className="px-3 py-1.5 font-mono text-[10px]">{r.project_code || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{r.mode}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.amount)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.tds_deducted)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.retention_deducted)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.total_adjusted)}</td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={10} className="text-center py-6 text-xs text-slate-400">No collections.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Overdue Invoices ═══════════════════ */
export function OverdueInvoicesView() {
  const [data, setData] = useState({ rows: [], total_outstanding: 0 });
  const load = () => api.get("/billing/reports/overdue").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Overdue Invoices <span className="ml-2 text-sm text-slate-500 font-normal">{fmt(data.total_outstanding)} outstanding</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Inv #</th><th className="text-left px-3 py-2">Client</th><th className="text-left px-3 py-2">Due Date</th><th className="text-right px-3 py-2">Overdue Days</th><th className="text-right px-3 py-2">Outstanding</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.invoice_no} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5">{r.client_name}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.due_date}</td>
                  <td className={`px-3 py-1.5 text-right tabular-nums font-semibold ${r.overdue_days > 90 ? "text-rose-700" : r.overdue_days > 60 ? "text-amber-700" : "text-slate-700"}`}>{r.overdue_days} days</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.outstanding)}</td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={5} className="text-center py-6 text-xs text-slate-400">No overdue invoices.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
