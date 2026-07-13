/**
 * Site Expenses & Project Costing Views · Phase 4
 * ================================================
 * Endpoints under `/api/costing/*`.
 */
import { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, RefreshCcw, CheckCircle2, AlertCircle, Package } from "lucide-react";
import { fmt } from "./AccountsViews";
import { ProjectSelect } from "@/components/MasterSelect";

const SE_CATS = [
  "local_purchase", "conveyance", "fuel", "food", "labour_welfare", "tools",
  "safety_items", "loading_unloading", "accommodation", "vehicle_expense",
  "petty_cash", "repair", "misc",
];

const SETTLEMENT_LABELS = {
  petty_cash: "Paid from Petty Cash",
  employee_reimbursement: "Reimburse Employee",
  vendor_payable: "Vendor Payable",
};

const STATUS_COLORS = {
  draft: "bg-slate-100 text-slate-700",
  pm_verified: "bg-blue-100 text-blue-800",
  approved: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-rose-100 text-rose-800",
};

function Field({ label, children }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      {children}
    </div>
  );
}

/* ═══════════════════ Site Expenses ═══════════════════ */
export function SiteExpensesView() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ status: "", category: "" });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(newFormState());

  function newFormState() {
    return {
      project_code: "", site_location: "",
      expense_date: new Date().toISOString().slice(0, 10),
      category: "fuel",
      paid_by_employee_name: "",
      payment_mode: "Cash", settlement_mode: "petty_cash",
      amount: 0, bill_no: "", remarks: "",
      attachments: [], force_no_attachment: false,
      expected_budget: 0,
    };
  }

  const load = () => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v));
    api.get(`/costing/site-expenses?${params}`).then(r => setRows(r.data || []));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filter.status, filter.category]);

  const submit = async () => {
    if (!form.project_code) { toast.error("Project code required"); return; }
    if (form.amount <= 0) { toast.error("Amount must be > 0"); return; }
    try {
      await api.post("/costing/site-expenses", {
        ...form,
        attachments: form.force_no_attachment ? [] : (form.attachments.length ? form.attachments : [{ name: "bill-photo" }]),
      });
      toast.success("Site expense created");
      setOpen(false); setForm(newFormState()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const verify = async (r) => {
    try { await api.post(`/costing/site-expenses/${r.id}/verify-pm`); toast.success("PM verified"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const approve = async (r) => {
    if (!window.confirm(`Approve ${r.expense_no}? Posts JE.`)) return;
    try { await api.post(`/costing/site-expenses/${r.id}/approve`); toast.success("Approved + JE posted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Site Expenses <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={filter.status} onChange={e => setFilter({ ...filter, status: e.target.value })}>
            <option value="">All statuses</option>
            <option value="draft">Draft</option><option value="pm_verified">PM-Verified</option>
            <option value="approved">Approved</option><option value="cancelled">Cancelled</option>
          </select>
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={filter.category} onChange={e => setFilter({ ...filter, category: e.target.value })}>
            <option value="">All categories</option>
            {SE_CATS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setOpen(true)} data-testid="cost-se-add"><Plus className="h-3.5 w-3.5 mr-1" />New Expense</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Expense #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Category</th><th className="text-left px-3 py-2">Paid by</th><th className="text-left px-3 py-2">Settlement</th><th className="text-right px-3 py-2">Amount</th><th className="text-center px-3 py-2">Status</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`cost-se-row-${r.expense_no}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {r.expense_no}
                    {r.duplicate_warning && <span title={r.duplicate_warning} className="ml-1 text-amber-600">⚠</span>}
                    {r.over_budget && <span title="Over budget" className="ml-1 text-rose-600">▲</span>}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.expense_date}</td>
                  <td className="px-3 py-1.5 text-xs">{r.project_code || r.project_id?.slice(0, 8)}</td>
                  <td className="px-3 py-1.5 text-xs">{r.category}</td>
                  <td className="px-3 py-1.5 text-xs">{r.paid_by_employee_name || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{SETTLEMENT_LABELS[r.settlement_mode] || r.settlement_mode}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.amount)}</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[r.status] || ""}`}>{r.status}</span></td>
                  <td className="px-3 py-1.5 text-right">
                    {r.status === "draft" && <Button size="sm" variant="outline" onClick={() => verify(r)} data-testid={`cost-se-verify-${r.expense_no}`}><CheckCircle2 className="h-3 w-3 mr-1" />PM Verify</Button>}
                    {(r.status === "draft" || r.status === "pm_verified") && <Button size="sm" onClick={() => approve(r)} className="ml-1" data-testid={`cost-se-approve-${r.expense_no}`}><CheckCircle2 className="h-3 w-3 mr-1" />Approve</Button>}
                    {r.je_voucher_number && <span className="text-[10px] text-slate-500 font-mono ml-1">{r.je_voucher_number}</span>}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={9} className="text-center py-6 text-xs text-slate-400">No expenses.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>New Site Expense</DialogTitle></DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Project Code *"><ProjectSelect value={form.project_code} valueKey="code" label={null} testid="cost-se-project" onChange={(v) => setForm({ ...form, project_code: v })} /></Field>
            <Field label="Site Location"><Input value={form.site_location} onChange={e => setForm({ ...form, site_location: e.target.value })} /></Field>
            <Field label="Date *"><Input type="date" value={form.expense_date} onChange={e => setForm({ ...form, expense_date: e.target.value })} /></Field>
            <Field label="Category *">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} data-testid="cost-se-category">
                {SE_CATS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Paid by Employee"><Input value={form.paid_by_employee_name} onChange={e => setForm({ ...form, paid_by_employee_name: e.target.value })} /></Field>
            <Field label="Payment Mode">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.payment_mode} onChange={e => setForm({ ...form, payment_mode: e.target.value })}>
                {["Cash", "UPI", "Personal Card", "Bank"].map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Settlement Mode">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.settlement_mode} onChange={e => setForm({ ...form, settlement_mode: e.target.value })} data-testid="cost-se-settlement">
                <option value="petty_cash">Paid from Petty Cash</option>
                <option value="employee_reimbursement">Reimburse Employee</option>
                <option value="vendor_payable">Vendor Payable</option>
              </select>
            </Field>
            <Field label="Amount *"><Input type="number" value={form.amount} onChange={e => setForm({ ...form, amount: Number(e.target.value) })} data-testid="cost-se-amount" /></Field>
            <Field label="Expected Budget"><Input type="number" value={form.expected_budget} onChange={e => setForm({ ...form, expected_budget: Number(e.target.value) })} /></Field>
            <Field label="Bill #"><Input value={form.bill_no} onChange={e => setForm({ ...form, bill_no: e.target.value })} /></Field>
          </div>
          <Field label="Remarks"><Input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={form.force_no_attachment} onChange={e => setForm({ ...form, force_no_attachment: e.target.checked })} />
            <span>Force-override: submit without attachment (requires admin)</span>
          </label>
          {!form.force_no_attachment && <div className="text-xs text-slate-500">Bill photo/document will be auto-attached as bill-photo placeholder.</div>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} data-testid="cost-se-save">Submit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════ Payroll Posting ═══════════════════ */
export function PayrollPostingView() {
  const [form, setForm] = useState({
    period: new Date().toISOString().slice(0, 7),
    attendance_locked: false,
    salary_expense: 0, salary_payable: 0, pf_payable: 0, esic_payable: 0,
    tds_payable: 0, advance_recovered: 0,
    project_code: "",
  });

  const totals = useMemo(() => {
    const credits = Number(form.salary_payable) + Number(form.pf_payable) + Number(form.esic_payable) + Number(form.tds_payable) + Number(form.advance_recovered);
    return { credits, balanced: Math.abs(Number(form.salary_expense) - credits) < 0.01 && Number(form.salary_expense) > 0 };
  }, [form]);

  const post = async () => {
    if (!form.attendance_locked) { toast.error("Lock attendance first"); return; }
    if (!totals.balanced) { toast.error("Salary expense must equal sum of credit legs"); return; }
    try {
      const r = await api.post("/costing/payroll/post", form);
      toast.success(`Posted ${r.data.voucher_number}`);
      setForm({ ...form, salary_expense: 0, salary_payable: 0, pf_payable: 0, esic_payable: 0, tds_payable: 0, advance_recovered: 0 });
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const pay = async () => {
    const amount = prompt("Salary amount to release:");
    if (!amount) return;
    try {
      const r = await api.post("/costing/payroll/pay-salary", {
        period: form.period, amount: Number(amount), mode: "Bank", payroll_approved: true,
      });
      toast.success(`Payment posted ${r.data.voucher_number}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Payroll Posting</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2">
          <Field label="Period *"><Input placeholder="2026-05" value={form.period} onChange={e => setForm({ ...form, period: e.target.value })} data-testid="cost-payroll-period" /></Field>
          <Field label="Project Code (optional)"><ProjectSelect value={form.project_code} valueKey="code" label={null} testid={null} onChange={(v) => setForm({ ...form, project_code: v })} /></Field>
          <Field label="Attendance Locked *">
            <label className="flex items-center gap-2 h-9 text-xs">
              <input type="checkbox" checked={form.attendance_locked} onChange={e => setForm({ ...form, attendance_locked: e.target.checked })} data-testid="cost-payroll-attlock" />
              <span className={form.attendance_locked ? "text-emerald-700 font-semibold" : "text-rose-700"}>{form.attendance_locked ? "✓ Locked" : "Lock attendance"}</span>
            </label>
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Field label="Salary Expense (DR) *"><Input type="number" value={form.salary_expense} onChange={e => setForm({ ...form, salary_expense: Number(e.target.value) })} data-testid="cost-payroll-expense" /></Field>
          <Field label="Salary Payable (CR)"><Input type="number" value={form.salary_payable} onChange={e => setForm({ ...form, salary_payable: Number(e.target.value) })} /></Field>
          <Field label="PF Payable (CR)"><Input type="number" value={form.pf_payable} onChange={e => setForm({ ...form, pf_payable: Number(e.target.value) })} /></Field>
          <Field label="ESIC Payable (CR)"><Input type="number" value={form.esic_payable} onChange={e => setForm({ ...form, esic_payable: Number(e.target.value) })} /></Field>
          <Field label="TDS Payable (CR)"><Input type="number" value={form.tds_payable} onChange={e => setForm({ ...form, tds_payable: Number(e.target.value) })} /></Field>
          <Field label="Advance Recovered (CR)"><Input type="number" value={form.advance_recovered} onChange={e => setForm({ ...form, advance_recovered: Number(e.target.value) })} /></Field>
        </div>
        <div className="border rounded-md p-3 bg-slate-50">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">DR={fmt(form.salary_expense)} · CR={fmt(totals.credits)}</span>
          {totals.balanced
            ? <span className="ml-3 text-emerald-700 font-semibold text-sm">✓ Balanced</span>
            : Number(form.salary_expense) > 0 && <span className="ml-3 text-rose-700 font-semibold text-sm flex items-center gap-1 inline-flex"><AlertCircle className="h-3 w-3" />Diff {fmt(Math.abs(Number(form.salary_expense) - totals.credits))}</span>}
        </div>
        <div className="flex gap-2">
          <Button disabled={!totals.balanced || !form.attendance_locked} onClick={post} data-testid="cost-payroll-post">Post Payroll JE</Button>
          <Button variant="outline" onClick={pay}>Release Salary Payment</Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Material Movement ═══════════════════ */
export function MaterialMovementView() {
  const [form, setForm] = useState({
    move_type: "issue", project_code: "", material: "",
    quantity: 1, unit: "Nos", unit_cost: 0,
    sale_amount: 0, gst_amount: 0,
    date: new Date().toISOString().slice(0, 10), notes: "",
  });

  const submit = async () => {
    try {
      const r = await api.post("/costing/material-movement", form);
      toast.success(`Posted ${r.data.voucher_number}`);
      setForm({ ...form, material: "", quantity: 1, unit_cost: 0, sale_amount: 0, gst_amount: 0 });
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Package className="h-4 w-4" />Material Movement Posting</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-4 gap-2">
          <Field label="Move Type *">
            <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.move_type} onChange={e => setForm({ ...form, move_type: e.target.value })} data-testid="cost-mat-type">
              <option value="issue">Issue to Project</option>
              <option value="return">Return from Project</option>
              <option value="damage">Damage</option>
              <option value="loss">Loss</option>
              <option value="scrap_sale">Scrap Sale</option>
            </select>
          </Field>
          <Field label="Project Code"><ProjectSelect value={form.project_code} valueKey="code" label={null} testid={null} onChange={(v) => setForm({ ...form, project_code: v })} /></Field>
          <Field label="Material *"><Input value={form.material} onChange={e => setForm({ ...form, material: e.target.value })} /></Field>
          <Field label="Date"><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></Field>
          <Field label="Quantity"><Input type="number" value={form.quantity} onChange={e => setForm({ ...form, quantity: Number(e.target.value) })} /></Field>
          <Field label="Unit"><Input value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })} /></Field>
          <Field label="Unit Cost"><Input type="number" value={form.unit_cost} onChange={e => setForm({ ...form, unit_cost: Number(e.target.value) })} /></Field>
          {form.move_type === "scrap_sale" && (
            <>
              <Field label="Sale Amount *"><Input type="number" value={form.sale_amount} onChange={e => setForm({ ...form, sale_amount: Number(e.target.value) })} /></Field>
              <Field label="GST Amount"><Input type="number" value={form.gst_amount} onChange={e => setForm({ ...form, gst_amount: Number(e.target.value) })} /></Field>
            </>
          )}
        </div>
        <div className="text-xs text-slate-500">Computed value: {fmt(form.move_type === "scrap_sale" ? form.sale_amount : form.quantity * form.unit_cost)}</div>
        <Button onClick={submit} data-testid="cost-mat-post">Post JE</Button>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Project Cost Summary ═══════════════════ */
export function ProjectCostSummaryView() {
  const [data, setData] = useState({ projects: [] });
  const load = () => api.get("/costing/reports/project-cost-summary").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Project Cost Summary</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Project</th><th className="text-right px-3 py-2">Site Exp</th><th className="text-right px-3 py-2">Vendor Bills</th><th className="text-right px-3 py-2">Payroll</th><th className="text-right px-3 py-2">Material</th><th className="text-right px-3 py-2">Logistics</th><th className="text-right px-3 py-2">Safety</th><th className="text-right px-3 py-2">Total</th></tr>
            </thead>
            <tbody>
              {(data.projects || []).map(p => (
                <tr key={p.project_code} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{p.project_code}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.site_expense)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.vendor_bills)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.payroll)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.material)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.logistics)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.safety)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-bold">{fmt(p.total)}</td>
                </tr>
              ))}
              {(data.projects || []).length === 0 && <tr><td colSpan={8} className="text-center py-6 text-xs text-slate-400">No project costs captured yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Site Expense Report ═══════════════════ */
export function SiteExpenseReportView() {
  const [data, setData] = useState({ rows: [], total: 0, by_category: [] });
  const load = () => api.get("/costing/reports/site-expense").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Site Expense Report <span className="ml-2 text-sm text-slate-500 font-normal">Total: {fmt(data.total)}</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-2 mb-3">
          {(data.by_category || []).map(c => (
            <div key={c.category} className="p-3 rounded-md border bg-slate-50">
              <div className="text-[10px] uppercase text-slate-500">{c.category}</div>
              <div className="text-lg font-bold tabular-nums">{fmt(c.amount)}</div>
            </div>
          ))}
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Expense #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Project</th><th className="text-left px-3 py-2">Category</th><th className="text-right px-3 py-2">Amount</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.expense_no}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.expense_date}</td>
                  <td className="px-3 py-1.5 text-xs">{r.project_code || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{r.category}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.amount)}</td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={5} className="text-center py-6 text-xs text-slate-400">No site expenses.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Salary/Advance Side-panels ═══════════════════ */
export function SalaryPayableView() {
  const [d, setD] = useState({ outstanding: 0, debit_total: 0, credit_total: 0 });
  const [adv, setAdv] = useState({ employees: [] });
  useEffect(() => {
    api.get("/costing/reports/salary-payable").then(r => setD(r.data));
    api.get("/costing/reports/employee-advance").then(r => setAdv(r.data));
  }, []);
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Salary Payable & Employee Advances</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 rounded-md border bg-rose-50"><div className="text-[10px] uppercase text-slate-500">Salary Payable Outstanding</div><div className="text-lg font-bold tabular-nums text-rose-700">{fmt(d.outstanding)}</div></div>
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Total Debits</div><div className="text-lg font-bold tabular-nums">{fmt(d.debit_total)}</div></div>
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Total Credits</div><div className="text-lg font-bold tabular-nums">{fmt(d.credit_total)}</div></div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-600 font-semibold mb-2">Employee Advances Outstanding</div>
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-3 py-2">Employee</th><th className="text-right px-3 py-2">Outstanding</th></tr></thead>
              <tbody>
                {(adv.employees || []).map((e, i) => (
                  <tr key={i} className="border-t"><td className="px-3 py-1.5">{e.employee_name}</td><td className="px-3 py-1.5 text-right tabular-nums">{fmt(e.outstanding)}</td></tr>
                ))}
                {(adv.employees || []).length === 0 && <tr><td colSpan={2} className="text-center py-4 text-xs text-slate-400">No advances outstanding.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
