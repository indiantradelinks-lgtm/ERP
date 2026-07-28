import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Wallet, CheckCircle2, XCircle, Clock, FileSpreadsheet, FileText, BadgeCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect } from "@/components/MasterSelect";
import FileUploader from "@/components/FileUploader";
import RowAttachments from "@/components/RowAttachments";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const PAY_ROLES = new Set(["super_admin", "director", "accounts_executive", "billing_executive"]);
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
const blank = () => ({ id: newId(), project_code: "", project_id: "", cost_center_id: "", expense_type: "",
  expense_date: new Date().toISOString().slice(0, 10), amount: "", description: "", bill_no: "",
  paid_to: "", payment_mode: "Cash", settlement_mode: "petty_cash", remarks: "" });

const STATUS_BADGE = {
  pending_approval: <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">Pending Approval</Badge>,
  approved_for_payment: <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Approved — For Payment</Badge>,
  paid: <Badge className="rounded-sm bg-blue-100 text-blue-900 border-blue-300">Paid</Badge>,
  rejected: <Badge variant="destructive" className="rounded-sm">Rejected</Badge>,
};

export default function ProjectExpenses() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [types, setTypes] = useState([]);
  const [threshold, setThreshold] = useState(10000);
  const [filters, setFilters] = useState({ project_code: "", status: "", expense_type: "" });
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blank());
  const [ccList, setCcList] = useState([]);
  const [attFiles, setAttFiles] = useState([]);
  const [attachFor, setAttachFor] = useState(null);
  const [payFor, setPayFor] = useState(null);
  const [payRef, setPayRef] = useState("");

  const load = async () => {
    try {
      const params = {};
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const [r, s] = await Promise.all([
        api.get("/project-expenses", { params }),
        api.get("/project-expenses/summary", { params: filters.project_code ? { project_code: filters.project_code } : {} }),
      ]);
      setRows(r.data || []); setSummary(s.data);
    } catch { toast.error("Failed to load expenses"); }
  };
  useEffect(() => {
    api.get("/project-expenses/types").then((r) => setTypes(r.data || [])).catch(() => {});
    api.get("/project-expenses/settings").then((r) => setThreshold(r.data?.large_threshold || 10000)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [filters]); // eslint-disable-line

  const onProjectPicked = async (code, row) => {
    setForm((f) => ({ ...f, project_code: code, project_id: row?.id || "", cost_center_id: "" }));
    setCcList([]);
    if (!row?.id) return;
    try {
      const r = await api.get(`/procurement/master/cost-centers?project_id=${row.id}`);
      setCcList((r.data || []).filter((c) => c.active !== false));
    } catch { /* cost centers optional */ }
  };

  const create = async () => {
    if (!form.project_code) { toast.error("Select a project"); return; }
    if (!form.expense_type) { toast.error("Select expense type"); return; }
    if (!Number(form.amount)) { toast.error("Enter amount"); return; }
    try {
      const r = await api.post("/project-expenses", { ...form, amount: Number(form.amount) });
      toast.success(`${r.data.expense_no} booked — ${r.data.is_large_value ? "LARGE value: extra GM + Director approval applies" : "standard approval chain"}`);
      setCreating(false); setForm(blank()); setAttFiles([]); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Booking failed"); }
  };

  const act = async (r, action) => {
    let remarks = null;
    if (action === "reject") {
      remarks = window.prompt("Rejection reason?");
      if (remarks === null) return;
    }
    try {
      await api.post(`/project-expenses/${r.id}/${action}`, { remarks });
      toast.success(action === "approve" ? "Approved" : "Rejected"); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Action failed"); }
  };

  const markPaid = async () => {
    try {
      await api.post(`/project-expenses/${payFor.id}/mark-paid`, { payment_ref: payRef });
      toast.success(`${payFor.expense_no} marked paid`); setPayFor(null); setPayRef(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const download = async (fmt) => {
    try {
      const params = {};
      if (filters.project_code) params.project_code = filters.project_code;
      if (filters.status) params.status = filters.status;
      const { data } = await api.get(`/project-expenses/export.${fmt}`, { responseType: "blob", params });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a"); a.href = url; a.download = `project_expenses.${fmt}`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const kpis = useMemo(() => summary ? [
    ["Booked Today", inr(summary.booked_today)], ["Pending Approval", summary.pending],
    ["Approved — For Payment", summary.approved], ["Paid", summary.paid],
    ["Total Approved Value", inr(summary.total_amount)],
  ] : [], [summary]);

  return (
    <div className="space-y-5" data-testid="project-expenses-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Wallet className="h-3 w-3" /> Cost Center Booking
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Daily Expense Booking</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Project team books all daily expenses (fuel, PPE, scaffolding material, manpower, accommodation, travelling…)
            against the project's Cost Centers. Flow: PM Verify → Dept Head → Accounts{" "}
            <b>→ GM → Director when above {inr(threshold)}</b> → Payment.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="pex-reload"><RefreshCw className="h-4 w-4" /></Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="pex-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1.5" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="pex-export-pdf"><FileText className="h-4 w-4 mr-1.5" /> PDF</Button>
          <Button className="h-9 rounded-sm" onClick={() => { setForm(blank()); setCcList([]); setAttFiles([]); setCreating(true); }} data-testid="pex-new">
            <Plus className="h-4 w-4 mr-1.5" /> Book Expense
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {kpis.map(([label, v]) => (
          <div key={label} className="bg-card border border-border rounded-sm p-3" data-testid={`pex-kpi-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            <div className="text-xl font-black tabular">{v}</div>
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center gap-2 p-3 border-b border-border flex-wrap">
          <ProjectSelect label="" value={filters.project_code} onChange={(v) => setFilters({ ...filters, project_code: v })}
            className="w-56" testid="pex-filter-project" placeholder="— all projects —" />
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="pex-filter-status">
            <option value="">All statuses</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="approved_for_payment">Approved — For Payment</option>
            <option value="paid">Paid</option>
            <option value="rejected">Rejected</option>
          </select>
          <select value={filters.expense_type} onChange={(e) => setFilters({ ...filters, expense_type: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="pex-filter-type">
            <option value="">All types</option>
            {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </div>
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Expense # / Date</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Project / Cost Center</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Type / Description</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Amount</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Approval Progress</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            <TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                No expenses booked yet. Use Book Expense to record today's site costs.
              </TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`pex-row-${r.id}`}>
                <TableCell>
                  <div className="font-mono-data text-xs font-bold">{r.expense_no}</div>
                  <div className="text-[10px] text-muted-foreground">{r.expense_date} · {r.created_by}</div>
                </TableCell>
                <TableCell>
                  <div className="font-semibold text-sm">{r.project_code}</div>
                  <div className="text-[11px] text-muted-foreground">{r.category_name || "— no cost center —"}</div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="rounded-sm text-[10px]">{r.expense_type_label}</Badge>
                  <div className="text-[11px] text-muted-foreground mt-0.5 max-w-[220px] truncate">{r.description}</div>
                  {(r.attachment_count || 0) > 0 && (
                    <button className="text-[10px] underline text-muted-foreground" onClick={() => setAttachFor(r)} data-testid={`pex-atts-${r.id}`}>{r.attachment_count} doc(s)</button>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono-data tabular text-sm font-bold">
                  {inr(r.amount)}
                  {r.is_large_value && <div className="text-[9px] text-amber-700 font-sans font-bold uppercase">Large value</div>}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1 flex-wrap" data-testid={`pex-chain-${r.id}`}>
                    {(r.chain || []).map((s, i) => (
                      <span key={i} title={`${s.label}: ${s.status}${s.by ? ` by ${s.by}` : ""}`}
                        className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-sm border
                          ${s.status === "approved" ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                            : s.status === "rejected" ? "bg-rose-50 border-rose-300 text-rose-800"
                            : i === r.current_step && r.status === "pending_approval" ? "bg-amber-50 border-amber-300 text-amber-900"
                            : "bg-secondary border-border text-muted-foreground"}`}>
                        {s.status === "approved" ? <CheckCircle2 className="h-2.5 w-2.5" />
                          : s.status === "rejected" ? <XCircle className="h-2.5 w-2.5" />
                          : <Clock className="h-2.5 w-2.5" />}
                        {s.label}
                      </span>
                    ))}
                  </div>
                </TableCell>
                <TableCell>{STATUS_BADGE[r.status] || r.status}
                  {r.status === "paid" && r.payment_ref && <div className="text-[10px] font-mono-data text-muted-foreground">{r.payment_ref}</div>}
                </TableCell>
                <TableCell className="text-right">
                  {r.status === "pending_approval" && (user?.role === (r.chain || [])[r.current_step]?.role || user?.role === "super_admin") && (
                    <div className="flex gap-1.5 justify-end">
                      <Button size="sm" className="h-7 rounded-sm" onClick={() => act(r, "approve")} data-testid={`pex-approve-${r.id}`}>Approve</Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive" onClick={() => act(r, "reject")} data-testid={`pex-reject-${r.id}`}>Reject</Button>
                    </div>
                  )}
                  {r.status === "approved_for_payment" && PAY_ROLES.has(user?.role) && (
                    <Button size="sm" className="h-7 rounded-sm" onClick={() => setPayFor(r)} data-testid={`pex-pay-${r.id}`}>
                      <BadgeCheck className="h-3 w-3 mr-1" /> Mark Paid
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-3xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Book Daily Expense</DialogTitle>
            <DialogDescription>
              Booked to the project's cost center. Above {inr(threshold)} the approval chain extends to GM → Director.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-1">
            <ProjectSelect label="Project *" value={form.project_code} onChange={onProjectPicked} testid="pex-form-project" />
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Cost Center</Label>
              <select value={form.cost_center_id} onChange={(e) => setForm({ ...form, cost_center_id: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="pex-form-cc">
                <option value="">— select cost center —</option>
                {ccList.map((c) => <option key={c.id} value={c.id}>{c.category_name} · budget {inr(c.budget)} · spent {inr(c.actual)}</option>)}
              </select>
              {form.project_code && ccList.length === 0 && (
                <p className="text-[10px] text-amber-700 mt-0.5">No cost centers on this project — ask admin to auto-provision them (Admin → Cost Centers).</p>
              )}
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Expense Type *</Label>
              <select value={form.expense_type} onChange={(e) => setForm({ ...form, expense_type: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="pex-form-type">
                <option value="">— select —</option>
                {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Expense Date *</Label>
              <Input type="date" value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="pex-form-date" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Amount (₹) *</Label>
              <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="pex-form-amount" />
              {Number(form.amount) > threshold && (
                <p className="text-[10px] text-amber-700 font-bold mt-0.5">Large value — GM + Director approval will apply</p>
              )}
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Paid To (vendor / person)</Label>
              <Input value={form.paid_to} onChange={(e) => setForm({ ...form, paid_to: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="pex-form-paidto" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Bill / Voucher #</Label>
              <Input value={form.bill_no} onChange={(e) => setForm({ ...form, bill_no: e.target.value })} className="h-9 rounded-sm mt-1 font-mono-data" data-testid="pex-form-billno" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Settlement</Label>
              <select value={form.settlement_mode} onChange={(e) => setForm({ ...form, settlement_mode: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1">
                <option value="petty_cash">Petty Cash</option>
                <option value="employee_reimbursement">Employee Reimbursement</option>
                <option value="vendor_payable">Vendor Payable</option>
              </select>
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Description *</Label>
              <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="pex-form-desc" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Bill / Receipt Attachments</Label>
              <div className="mt-1">
                <FileUploader folder="documents" parent_type="project_expenses" parent_id={form.id}
                  category="expense_bill" compact
                  files={attFiles} onUploaded={(f) => setAttFiles((p) => [...p, f])}
                  onDeleted={(fid) => setAttFiles((p) => p.filter((x) => x.id !== fid))}
                  testidPrefix="pex-uploader" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="pex-form-submit">Book Expense</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!payFor} onOpenChange={(o) => !o && setPayFor(null)}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Mark Paid — {payFor?.expense_no}</DialogTitle>
            <DialogDescription>{payFor?.expense_type_label} · {inr(payFor?.amount)} · {payFor?.paid_to || "—"}</DialogDescription>
          </DialogHeader>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Payment Reference (UTR / voucher #)</Label>
            <Input value={payRef} onChange={(e) => setPayRef(e.target.value)} className="h-9 rounded-sm mt-1 font-mono-data" data-testid="pex-pay-ref" />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setPayFor(null)}>Cancel</Button>
            <Button className="rounded-sm" onClick={markPaid} data-testid="pex-pay-confirm">Confirm Payment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!attachFor} onOpenChange={() => setAttachFor(null)}
        parentType="project_expenses" parentId={attachFor?.id} recordTitle={`Documents — ${attachFor?.expense_no || ""}`} />
    </div>
  );
}
