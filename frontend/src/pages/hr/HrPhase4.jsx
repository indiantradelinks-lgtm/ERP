// HR Phase 4 — Salary Structure · Loans · Reimbursements · Store Recovery
// · Finance Approval · Accounts Posting · Statutory Reports · Project Cost
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api, apiErrorMessage } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import { EmployeeSearchSelect } from "@/components/EmployeeSearchSelect";
import { ProjectSelect } from "@/components/MasterSelect";
import { toast } from "sonner";
import {
  DollarSign, Banknote, Receipt, Wrench, Building2, FileText,
  Plus, Check, X, RefreshCw, ShieldCheck, Upload, Download,
} from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const monthIso = () => new Date().toISOString().slice(0, 7);
const today = () => new Date().toISOString().slice(0, 10);
const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const Field = ({ label, children }) => (
  <div className="space-y-1"><Label className="text-xs">{label}</Label>{children}</div>
);

function Tile({ label, value, testid, color = "text-slate-900" }) {
  return (
    <Card data-testid={testid}><CardContent className="p-4">
      <div className="text-[11px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value ?? "—"}</div>
    </CardContent></Card>
  );
}

const StatusBadge = ({ value }) => {
  const tone = {
    pending: "bg-amber-100 text-amber-900",
    approved: "bg-emerald-100 text-emerald-900",
    rejected: "bg-rose-100 text-rose-900",
    paid: "bg-blue-100 text-blue-900",
    unpaid: "bg-slate-100 text-slate-700",
    posted: "bg-emerald-100 text-emerald-900",
    draft: "bg-slate-100 text-slate-700",
    active: "bg-emerald-100 text-emerald-900",
    committed: "bg-blue-100 text-blue-900",
  }[value] || "bg-slate-100 text-slate-700";
  return <Badge className={`text-xs border ${tone}`} data-testid={`status-${value}`}>{value || "—"}</Badge>;
};

// ─────────── DASHBOARD ───────────
function DashboardView() {
  const [d, setD] = useState(null);
  useEffect(() => { (async () => {
    try { setD((await api.get("/hr4/dashboard")).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  })(); }, []);
  if (!d) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <Tile label="Structures Pending" value={d.salary_structures_pending} testid="hr4-tile-structures" />
        <Tile label="Active Loans" value={d.loans_active} testid="hr4-tile-loans" />
        <Tile label="Reimbursements Pending" value={d.reimbursements_pending} testid="hr4-tile-reimb" />
        <Tile label="Store Recoveries" value={d.store_recoveries_pending} testid="hr4-tile-recovery" />
        <Tile label="Last Run" value={d.last_payroll_month || "—"} testid="hr4-tile-last-month" />
        <Tile label="Last Net Pay" value={d.last_total_net ? inr(d.last_total_net) : "—"} testid="hr4-tile-last-net" />
      </div>
      <Card>
        <CardHeader><CardTitle className="text-sm">Last Run Workflow Status</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
            <div>HR Status: <StatusBadge value={d.last_payroll_status} /></div>
            <div>Finance Approval: <StatusBadge value={d.last_finance_approval} /></div>
            <div>Accounts Posting: <StatusBadge value={d.last_accounts_posting} /></div>
            <div>Payment: <StatusBadge value={d.last_payment_status} /></div>
            <div>Payslips: <span className="font-semibold">{d.last_payslip_count || 0}</span></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─────────── SALARY STRUCTURE BULK UPLOAD ───────────
function SalaryBulkUpload({ onDone }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const res = await api.get("/hr4/salary-structures/bulk/template", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `salary-structure-template-${today()}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Template downloaded — every active employee is pre-filled");
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const upload = async () => {
    if (!file) { toast.error("Choose the filled .xlsx file"); return; }
    setBusy(true); setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post("/hr4/salary-structures/bulk/import", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setResult(res.data);
      toast.success(`${res.data.created} structure(s) created & synced to payroll · ${res.data.skipped} skipped`);
      onDone?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const close = () => { setOpen(false); setFile(null); setResult(null); };

  return (
    <>
      <Button size="sm" variant="outline" onClick={downloadTemplate} data-testid="ss-bulk-template-btn">
        <Download className="h-4 w-4 mr-1" /> Template
      </Button>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="ss-bulk-upload-btn">
        <Upload className="h-4 w-4 mr-1" /> Bulk Upload
      </Button>

      <Dialog open={open} onOpenChange={(v) => (v ? setOpen(true) : close())}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="ss-bulk-dialog">
          <DialogHeader>
            <DialogTitle>Bulk Upload Salary Structures</DialogTitle>
            <DialogDescription>
              Upload one Excel file to create or update the salary breakup of many employees at once, matched on Employee ID.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 text-sm">
            <div className="rounded-md border bg-slate-50 p-3 text-xs space-y-1">
              <div className="font-semibold">How it works</div>
              <div>1. Download the template — it lists every active employee with their current breakup.</div>
              <div>2. Edit the amount columns. Match key is <span className="font-mono">employee_id</span> (e.g. EMPITL162).</div>
              <div>3. Each row creates a NEW effective-dated version; the previous one is end-dated so history stays intact.</div>
              <div>4. Uploaded structures are auto-approved and synced straight to the payroll master.</div>
              <div>5. Bad rows (unknown Employee ID, negative amount, bad date) are skipped and listed below.</div>
            </div>

            <div className="flex items-center gap-2">
              <Input type="file" accept=".xlsx,.xlsm" data-testid="ss-bulk-file"
                onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} />
              <Button onClick={upload} disabled={busy || !file} data-testid="ss-bulk-submit">
                {busy ? "Uploading…" : "Upload"}
              </Button>
            </div>

            {result && (
              <div className="space-y-2" data-testid="ss-bulk-summary">
                <div className="grid grid-cols-4 gap-2">
                  {[["Rows Read", result.total_rows, "text-slate-900"],
                    ["Created", result.created, "text-emerald-700"],
                    ["Superseded", result.superseded, "text-blue-700"],
                    ["Skipped", result.skipped, "text-rose-700"]].map(([l, v, c]) => (
                    <div key={l} className="rounded-md border p-2 bg-white">
                      <div className="text-[10px] uppercase text-muted-foreground">{l}</div>
                      <div className={`text-lg font-semibold ${c}`}>{v ?? 0}</div>
                    </div>
                  ))}
                </div>

                {result.errors?.length > 0 && (
                  <div className="rounded-md border border-rose-200 overflow-hidden" data-testid="ss-bulk-errors">
                    <div className="bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-800">
                      Failed rows ({result.errors.length})
                    </div>
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 text-[10px] uppercase text-muted-foreground">
                        <tr><th className="text-left px-3 py-1">Row</th><th className="text-left px-3 py-1">Employee ID</th><th className="text-left px-3 py-1">Reason</th></tr>
                      </thead>
                      <tbody>
                        {result.errors.map((e, i) => (
                          <tr key={i} className="border-t">
                            <td className="px-3 py-1 font-mono">{e.row}</td>
                            <td className="px-3 py-1 font-mono">{e.employee_id || "—"}</td>
                            <td className="px-3 py-1 text-rose-700">{e.error}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {result.rows?.filter(r => r.action === "created").length > 0 && (
                  <div className="rounded-md border overflow-hidden max-h-64 overflow-y-auto" data-testid="ss-bulk-created">
                    <div className="bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800">
                      Imported successfully ({result.created})
                    </div>
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 text-[10px] uppercase text-muted-foreground">
                        <tr><th className="text-left px-3 py-1">Row</th><th className="text-left px-3 py-1">Employee ID</th><th className="text-left px-3 py-1">Name</th><th className="text-left px-3 py-1">SS No</th><th className="text-right px-3 py-1">Basic</th><th className="text-right px-3 py-1">Gross</th><th className="text-left px-3 py-1 pl-4">Eff From</th></tr>
                      </thead>
                      <tbody>
                        {result.rows.filter(r => r.action === "created").map((r, i) => (
                          <tr key={i} className="border-t">
                            <td className="px-3 py-1 font-mono">{r.row}</td>
                            <td className="px-3 py-1 font-mono">{r.employee_id}</td>
                            <td className="px-3 py-1">{r.employee_name}</td>
                            <td className="px-3 py-1 font-mono">{r.structure_no}</td>
                            <td className="px-3 py-1 text-right">{inr(r.basic)}</td>
                            <td className="px-3 py-1 text-right font-semibold">{inr(r.gross)}</td>
                            <td className="px-3 py-1 pl-4 font-mono">{r.effective_from}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={close} data-testid="ss-bulk-close">Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ─────────── SALARY STRUCTURES ───────────
function StructuresView() {
  const { rows, pagination, search, setSearch, reload: load } = usePagedList("/hr4/salary-structures", {}, {
    viewKey: "hr_salary_structures", errorLabel: "salary structures", defaultSort: { by: "effective_from", dir: "desc" },
    searchKeys: "employee_name,employee_code,employee_id,department,designation,approval_status,wage_type",
  });
  const [open, setOpen] = useState(false);
  const [employees, setEmployees] = useState([]);
  const [form, setForm] = useState({
    wage_type: "monthly", pf_applicable: true, esic_applicable: false, tds_applicable: false,
    effective_from: today(), basic: 0, hra: 0, da: 0, conveyance: 0, site_allowance: 0,
    food_allowance: 0, other_allowance: 0, overtime_rate: 0, professional_tax: 200,
    attendance_bonus_applicable: false, attendance_bonus_amount: 0,
  });
  useEffect(() => {
    if (!open || employees.length) return;
    lookupGet("/employees").then((r) => setEmployees(r.data || [])).catch(() => {});
  }, [open]);
  const save = async () => {
    if (!form.employee_id) { toast.error("Select an employee"); return; }
    try {
      await api.post("/hr4/salary-structures", form);
      toast.success("Salary structure created — pending approval");
      setOpen(false); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const decide = async (sid, decision) => {
    try {
      await api.post(`/hr4/salary-structures/${sid}/approve`, { decision });
      toast.success(`Structure ${decision}d → synced to payroll_master`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><DollarSign className="h-4 w-4" /> Salary / Wage Structures</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="h-8 w-52" placeholder="Search employee, dept…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="hr4-ss-search" />
          <TableViewsMenu pagination={pagination} testidPrefix="hr4-ss" />
          <SalaryBulkUpload onDone={load} />
          <Button size="sm" onClick={() => setOpen(true)} data-testid="hr4-ss-new"><Plus className="h-4 w-4 mr-1" /> New Structure</Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>SS No</TableHead><TableHead>Employee</TableHead>
            <TableHead>Type</TableHead><TableHead>Basic</TableHead>
            <TableHead>HRA</TableHead><TableHead>Allowances</TableHead>
            <TableHead>OT Rate</TableHead><TableHead>PF/ESI/TDS</TableHead>
            <TableHead>Eff From</TableHead><TableHead>Status</TableHead>
            <TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={11} className="text-center text-sm text-muted-foreground py-6">No structures</TableCell></TableRow>}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`ss-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.structure_no}</TableCell>
                <TableCell>{r.employee_name}</TableCell>
                <TableCell>{r.wage_type}</TableCell>
                <TableCell>{inr(r.basic)}</TableCell>
                <TableCell>{inr(r.hra)}</TableCell>
                <TableCell className="text-xs">
                  {r.da > 0 && <>DA {inr(r.da)} · </>}Site {inr(r.site_allowance)} · Food {inr(r.food_allowance)} · Other {inr(r.other_allowance)}{r.attendance_bonus_applicable && <> · Att.Bonus {inr(r.attendance_bonus_amount)}</>}
                </TableCell>
                <TableCell>{inr(r.overtime_rate)}</TableCell>
                <TableCell className="text-xs">
                  {r.pf_applicable ? "PF" : "–"} / {r.esic_applicable ? "ESI" : "–"} / {r.tds_applicable ? "TDS" : "–"}
                </TableCell>
                <TableCell>{r.effective_from}</TableCell>
                <TableCell><StatusBadge value={r.approval_status} /></TableCell>
                <TableCell className="flex gap-1">
                  {r.approval_status === "pending" && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => decide(r.id, "approve")} data-testid={`ss-approve-${r.id}`}><Check className="h-3 w-3" /></Button>
                      <Button size="sm" variant="outline" onClick={() => decide(r.id, "reject")} data-testid={`ss-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="pt-2"><TablePager pagination={pagination} testidPrefix="hr4-ss" /></div>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>New Salary / Wage Structure</DialogTitle></DialogHeader>
          <div className="grid grid-cols-3 gap-3">
            <EmployeeSearchSelect employees={employees} value={form.employee_id}
              onChange={(id) => setForm({ ...form, employee_id: id })}
              label="Employee" required testid="ss-emp-id" />
            <Field label="Wage Type">
              <Select value={form.wage_type} onValueChange={v => setForm({ ...form, wage_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["monthly", "daily", "hourly", "shift", "piece_rate"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Effective From"><Input type="date" value={form.effective_from} onChange={e => setForm({ ...form, effective_from: e.target.value })} /></Field>
            <Field label="Basic"><Input type="number" value={form.basic} onChange={e => setForm({ ...form, basic: parseFloat(e.target.value) || 0 })} data-testid="ss-basic" /></Field>
            <Field label="HRA"><Input type="number" value={form.hra} onChange={e => setForm({ ...form, hra: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="DA (Dearness Allowance)"><Input type="number" value={form.da} onChange={e => setForm({ ...form, da: parseFloat(e.target.value) || 0 })} data-testid="ss-da" /></Field>
            <Field label="Conveyance"><Input type="number" value={form.conveyance} onChange={e => setForm({ ...form, conveyance: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="Site Allowance"><Input type="number" value={form.site_allowance} onChange={e => setForm({ ...form, site_allowance: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="Food Allowance"><Input type="number" value={form.food_allowance} onChange={e => setForm({ ...form, food_allowance: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="Other Allowance"><Input type="number" value={form.other_allowance} onChange={e => setForm({ ...form, other_allowance: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="Overtime Rate / hour"><Input type="number" value={form.overtime_rate} onChange={e => setForm({ ...form, overtime_rate: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="Professional Tax"><Input type="number" value={form.professional_tax} onChange={e => setForm({ ...form, professional_tax: parseFloat(e.target.value) || 0 })} /></Field>
            <Field label="Effective To"><Input type="date" value={form.effective_to || ""} onChange={e => setForm({ ...form, effective_to: e.target.value })} /></Field>
            <div className="col-span-3 p-2 border rounded bg-amber-50/60 border-amber-200 grid grid-cols-2 gap-3 items-center">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!!form.attendance_bonus_applicable}
                  onChange={e => setForm({ ...form, attendance_bonus_applicable: e.target.checked })}
                  data-testid="ss-att-bonus-flag" />
                Attendance Bonus Applicable
              </label>
              <Field label="Bonus Amount (₹/month, paid when zero LOP)">
                <Input type="number" value={form.attendance_bonus_amount || 0} disabled={!form.attendance_bonus_applicable}
                  onChange={e => setForm({ ...form, attendance_bonus_amount: parseFloat(e.target.value) || 0 })}
                  data-testid="ss-att-bonus-amount" />
              </Field>
            </div>
            <div className="col-span-3 grid grid-cols-3 gap-2">
              {["pf_applicable", "esic_applicable", "tds_applicable"].map(k => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form[k]} onChange={e => setForm({ ...form, [k]: e.target.checked })} data-testid={`ss-${k}`} />
                  {k.replace(/_/g, " ")}
                </label>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="ss-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── LOANS ───────────
function LoansView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ tenure_months: 12, recovery_start_month: monthIso() });
  const load = async () => { try { setRows((await api.get("/hr4/loans")).data || []); } catch (e) { toast.error(apiErrorMessage(e)); } };
  useEffect(() => { load(); }, []);
  const save = async () => { try { await api.post("/hr4/loans", form); toast.success("Loan request created"); setOpen(false); load(); } catch (e) { toast.error(apiErrorMessage(e)); } };
  const act = async (lid, action) => {
    try {
      if (action === "approve" || action === "reject") {
        await api.post(`/hr4/loans/${lid}/approve`, { decision: action });
      } else if (action === "pay") {
        await api.post(`/hr4/loans/${lid}/mark-paid`);
      }
      toast.success(`Loan ${action}d`); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Banknote className="h-4 w-4" /> Employee Loans</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr4-loan-new"><Plus className="h-4 w-4 mr-1" /> New Loan</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Loan No</TableHead><TableHead>Employee</TableHead>
            <TableHead>Amount</TableHead><TableHead>EMI</TableHead>
            <TableHead>Balance</TableHead><TableHead>From</TableHead>
            <TableHead>Approval</TableHead><TableHead>Payment</TableHead>
            <TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-6">No loans</TableCell></TableRow>}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`loan-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.loan_no}</TableCell>
                <TableCell>{r.employee_name}</TableCell>
                <TableCell>{inr(r.loan_amount)}</TableCell>
                <TableCell>{inr(r.emi_amount)}</TableCell>
                <TableCell>{inr(r.balance_amount)}</TableCell>
                <TableCell>{r.recovery_start_month}</TableCell>
                <TableCell><StatusBadge value={r.approval_status} /></TableCell>
                <TableCell><StatusBadge value={r.payment_status} /></TableCell>
                <TableCell className="flex gap-1">
                  {r.approval_status === "pending" && <>
                    <Button size="sm" variant="outline" onClick={() => act(r.id, "approve")} data-testid={`loan-approve-${r.id}`}><Check className="h-3 w-3" /></Button>
                    <Button size="sm" variant="outline" onClick={() => act(r.id, "reject")} data-testid={`loan-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                  </>}
                  {r.approval_status === "approved" && r.payment_status !== "paid" &&
                    <Button size="sm" variant="outline" onClick={() => act(r.id, "pay")} data-testid={`loan-pay-${r.id}`}>Pay</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Loan Request</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employee ID"><Input value={form.employee_id || ""} onChange={e => setForm({ ...form, employee_id: e.target.value })} data-testid="loan-emp-id" /></Field>
            <Field label="Loan Amount"><Input type="number" value={form.loan_amount || ""} onChange={e => setForm({ ...form, loan_amount: parseFloat(e.target.value) || 0 })} data-testid="loan-amount" /></Field>
            <Field label="EMI Amount"><Input type="number" value={form.emi_amount || ""} onChange={e => setForm({ ...form, emi_amount: parseFloat(e.target.value) || 0 })} data-testid="loan-emi" /></Field>
            <Field label="Tenure (months)"><Input type="number" value={form.tenure_months} onChange={e => setForm({ ...form, tenure_months: parseInt(e.target.value) || 12 })} /></Field>
            <Field label="Recovery Start Month"><Input value={form.recovery_start_month} onChange={e => setForm({ ...form, recovery_start_month: e.target.value })} placeholder="YYYY-MM" /></Field>
            <div className="col-span-2"><Field label="Reason"><Textarea rows={2} value={form.reason || ""} onChange={e => setForm({ ...form, reason: e.target.value })} /></Field></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="loan-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── REIMBURSEMENTS ───────────
function ReimbursementsView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({});
  const load = async () => { try { setRows((await api.get("/hr4/reimbursements")).data || []); } catch (e) { toast.error(apiErrorMessage(e)); } };
  useEffect(() => { load(); }, []);
  const save = async () => { try { await api.post("/hr4/reimbursements", form); toast.success("Reimbursement created"); setOpen(false); load(); } catch (e) { toast.error(apiErrorMessage(e)); } };
  const act = async (rid, action) => {
    try {
      if (action === "approve" || action === "reject") {
        await api.post(`/hr4/reimbursements/${rid}/approve`, { decision: action });
      } else if (action === "pay") {
        await api.post(`/hr4/reimbursements/${rid}/mark-paid`);
      }
      toast.success(`Reimbursement ${action}d`); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Receipt className="h-4 w-4" /> Reimbursements</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr4-reimb-new"><Plus className="h-4 w-4 mr-1" /> New</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>RMB No</TableHead><TableHead>Employee</TableHead>
            <TableHead>Project</TableHead><TableHead>Type</TableHead>
            <TableHead>Amount</TableHead><TableHead>Approval</TableHead>
            <TableHead>Payment</TableHead><TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-6">No reimbursements</TableCell></TableRow>}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`reimb-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.reimbursement_no}</TableCell>
                <TableCell>{r.employee_name}</TableCell>
                <TableCell className="font-mono text-xs">{r.project_code || "—"}</TableCell>
                <TableCell>{r.expense_type}</TableCell>
                <TableCell>{inr(r.amount)}</TableCell>
                <TableCell><StatusBadge value={r.approval_status} /></TableCell>
                <TableCell><StatusBadge value={r.payment_status} /></TableCell>
                <TableCell className="flex gap-1">
                  {r.approval_status === "pending" && <>
                    <Button size="sm" variant="outline" onClick={() => act(r.id, "approve")} data-testid={`reimb-approve-${r.id}`}><Check className="h-3 w-3" /></Button>
                    <Button size="sm" variant="outline" onClick={() => act(r.id, "reject")} data-testid={`reimb-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                  </>}
                  {r.approval_status === "approved" && r.payment_status !== "paid" &&
                    <Button size="sm" variant="outline" onClick={() => act(r.id, "pay")} data-testid={`reimb-pay-${r.id}`}>Pay</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Reimbursement</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employee ID"><Input value={form.employee_id || ""} onChange={e => setForm({ ...form, employee_id: e.target.value })} data-testid="reimb-emp-id" /></Field>
            <Field label="Project Code"><ProjectSelect value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} valueKey="code" label={null} /></Field>
            <Field label="Expense Type"><Input value={form.expense_type || ""} onChange={e => setForm({ ...form, expense_type: e.target.value })} data-testid="reimb-type" /></Field>
            <Field label="Amount"><Input type="number" value={form.amount || ""} onChange={e => setForm({ ...form, amount: parseFloat(e.target.value) || 0 })} data-testid="reimb-amount" /></Field>
            <Field label="Expense Date"><Input type="date" value={form.expense_date || ""} onChange={e => setForm({ ...form, expense_date: e.target.value })} /></Field>
            <Field label="Bill URL"><Input value={form.bill_attachment_url || ""} onChange={e => setForm({ ...form, bill_attachment_url: e.target.value })} /></Field>
            <div className="col-span-2"><Field label="Description"><Textarea rows={2} value={form.description || ""} onChange={e => setForm({ ...form, description: e.target.value })} /></Field></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="reimb-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── STORE RECOVERIES ───────────
function StoreRecoveriesView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ reason: "lost", recovery_month: monthIso() });
  const load = async () => { try { setRows((await api.get("/hr4/store-recoveries")).data || []); } catch (e) { toast.error(apiErrorMessage(e)); } };
  useEffect(() => { load(); }, []);
  const save = async () => { try { await api.post("/hr4/store-recoveries", form); toast.success("Recovery created"); setOpen(false); load(); } catch (e) { toast.error(apiErrorMessage(e)); } };
  const decide = async (id, decision) => { try { await api.post(`/hr4/store-recoveries/${id}/approve`, { decision }); toast.success(`Recovery ${decision}d`); load(); } catch (e) { toast.error(apiErrorMessage(e)); } };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Wrench className="h-4 w-4" /> Store Recoveries (PPE / Tool / Asset)</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr4-recovery-new"><Plus className="h-4 w-4 mr-1" /> New</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>STR No</TableHead><TableHead>Employee</TableHead>
            <TableHead>Item</TableHead><TableHead>Reason</TableHead>
            <TableHead>Amount</TableHead><TableHead>Month</TableHead>
            <TableHead>Approval</TableHead><TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-6">No recoveries</TableCell></TableRow>}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`recovery-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.recovery_no}</TableCell>
                <TableCell>{r.employee_name}</TableCell>
                <TableCell>{r.item}</TableCell>
                <TableCell>{r.reason}</TableCell>
                <TableCell>{inr(r.amount)}</TableCell>
                <TableCell>{r.recovery_month}</TableCell>
                <TableCell><StatusBadge value={r.approval_status} /></TableCell>
                <TableCell className="flex gap-1">
                  {r.approval_status === "pending" && <>
                    <Button size="sm" variant="outline" onClick={() => decide(r.id, "approve")} data-testid={`recovery-approve-${r.id}`}><Check className="h-3 w-3" /></Button>
                    <Button size="sm" variant="outline" onClick={() => decide(r.id, "reject")} data-testid={`recovery-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                  </>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Store Recovery</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employee ID"><Input value={form.employee_id || ""} onChange={e => setForm({ ...form, employee_id: e.target.value })} data-testid="recovery-emp-id" /></Field>
            <Field label="Project Code"><ProjectSelect value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} valueKey="code" label={null} /></Field>
            <Field label="Item"><Input value={form.item || ""} onChange={e => setForm({ ...form, item: e.target.value })} data-testid="recovery-item" /></Field>
            <Field label="Reason">
              <Select value={form.reason} onValueChange={v => setForm({ ...form, reason: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["lost", "damaged", "unreturned"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Amount"><Input type="number" value={form.amount || ""} onChange={e => setForm({ ...form, amount: parseFloat(e.target.value) || 0 })} data-testid="recovery-amount" /></Field>
            <Field label="Recovery Month"><Input value={form.recovery_month} onChange={e => setForm({ ...form, recovery_month: e.target.value })} placeholder="YYYY-MM" /></Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="recovery-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── PAYROLL POSTING WORKFLOW ───────────
function PostingView() {
  const [month, setMonth] = useState(monthIso());
  const action = async (endpoint) => {
    try {
      const r = await api.post(endpoint, { month });
      toast.success(`OK: ${endpoint.split("/").pop()}`);
      console.log(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Payroll Posting Workflow</CardTitle></CardHeader>
      <CardContent>
        <div className="flex gap-2 items-end mb-4">
          <Field label="Month (YYYY-MM)"><Input value={month} onChange={e => setMonth(e.target.value)} className="w-32" data-testid="post-month" /></Field>
        </div>
        <ol className="text-sm space-y-2 list-decimal list-inside">
          <li>HR commits the run via existing <code>/api/payroll/run/commit</code> (Payroll page).</li>
          <li>
            <Button size="sm" variant="outline" onClick={() => action("/hr4/payroll/finance-approve")} data-testid="post-fin-approve">
              Finance Approve
            </Button>
          </li>
          <li>
            <Button size="sm" variant="outline" onClick={() => action("/hr4/payroll/post-to-accounts")} data-testid="post-accounts">
              Post to Accounts (creates JV)
            </Button>
          </li>
          <li>
            <Button size="sm" variant="outline" onClick={() => action("/hr4/payroll/mark-paid")} data-testid="post-mark-paid">
              Mark Paid (Bank disbursement JV)
            </Button>
          </li>
        </ol>
      </CardContent>
    </Card>
  );
}

// ─────────── STATUTORY ───────────
function StatutoryView() {
  const [month, setMonth] = useState(monthIso());
  const [pf, setPf] = useState(null);
  const [esi, setEsi] = useState(null);
  const [tds, setTds] = useState(null);
  const load = async () => {
    try {
      const [a, b, c] = await Promise.all([
        api.get(`/hr4/statutory/pf?month=${month}`),
        api.get(`/hr4/statutory/esic?month=${month}`),
        api.get(`/hr4/statutory/tds?month=${month}`),
      ]);
      setPf(a.data); setEsi(b.data); setTds(c.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-sm">Statutory Liability Reports</CardTitle>
          <div className="flex gap-2">
            <Input value={month} onChange={e => setMonth(e.target.value)} className="w-32" data-testid="stat-month" />
            <Button size="sm" onClick={load} data-testid="stat-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Reload</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            <Card data-testid="stat-pf-tile"><CardContent className="p-3">
              <div className="text-xs uppercase">PF Payable</div>
              <div className="text-xl font-semibold mt-1">{inr(pf?.totals?.grand_total || 0)}</div>
              <div className="text-[10px] text-muted-foreground">Employee {inr(pf?.totals?.employee_total)} + Employer {inr(pf?.totals?.employer_total)}</div>
            </CardContent></Card>
            <Card data-testid="stat-esi-tile"><CardContent className="p-3">
              <div className="text-xs uppercase">ESIC Payable</div>
              <div className="text-xl font-semibold mt-1">{inr(esi?.totals?.grand_total || 0)}</div>
              <div className="text-[10px] text-muted-foreground">Employee {inr(esi?.totals?.employee_total)} + Employer {inr(esi?.totals?.employer_total)}</div>
            </CardContent></Card>
            <Card data-testid="stat-tds-tile"><CardContent className="p-3">
              <div className="text-xs uppercase">TDS Payable</div>
              <div className="text-xl font-semibold mt-1">{inr(tds?.total_tds || 0)}</div>
              <div className="text-[10px] text-muted-foreground">{tds?.rows?.length || 0} employee(s)</div>
            </CardContent></Card>
          </div>
        </CardContent>
      </Card>

      {pf?.rows?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">PF — Detail</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Employee</TableHead><TableHead>Wage</TableHead>
                <TableHead>Employee</TableHead><TableHead>Employer</TableHead>
                <TableHead>Total Payable</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {pf.rows.map((r, i) => (
                  <TableRow key={i} data-testid={`pf-row-${i}`}>
                    <TableCell>{r.employee_name}</TableCell>
                    <TableCell>{inr(r.wage_for_pf)}</TableCell>
                    <TableCell>{inr(r.employee_contribution)}</TableCell>
                    <TableCell>{inr(r.employer_contribution)}</TableCell>
                    <TableCell className="font-semibold">{inr(r.pf_payable)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─────────── PROJECT MANPOWER COST ───────────
function ProjectCostView() {
  const [month, setMonth] = useState(monthIso());
  const [rows, setRows] = useState([]);
  const load = async () => {
    try {
      const r = await api.get(`/hr4/project-cost?month=${month}`);
      setRows(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Building2 className="h-4 w-4" /> Project-wise Manpower Cost</CardTitle>
        <div className="flex gap-2">
          <Input value={month} onChange={e => setMonth(e.target.value)} className="w-32" data-testid="pc-month" />
          <Button size="sm" onClick={load} data-testid="pc-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Reload</Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Project</TableHead><TableHead>Headcount</TableHead>
            <TableHead>Gross</TableHead><TableHead>Net Pay</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-sm text-muted-foreground py-6">No payslip data for {month}</TableCell></TableRow>}
            {rows.map((r, i) => (
              <TableRow key={i} data-testid={`pc-row-${i}`}>
                <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                <TableCell>{r.headcount}</TableCell>
                <TableCell>{inr(r.gross)}</TableCell>
                <TableCell>{inr(r.net_pay)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─────────── PARENT HUB ───────────
export default function HrPhase4() {
  const [tab, setTab] = useState("dashboard");
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <FileText className="h-5 w-5" /> Salary · Payroll · Statutory · Accounts Posting
        </h1>
        <p className="text-sm text-muted-foreground">Phase 4 — salary structures, loans, reimbursements, store recovery, finance approval and Accounts JV posting</p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="dashboard" data-testid="hr4-tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="structures" data-testid="hr4-tab-salary-structures">Salary Structures</TabsTrigger>
          <TabsTrigger value="loans" data-testid="hr4-tab-loans">Loans</TabsTrigger>
          <TabsTrigger value="reimbursements" data-testid="hr4-tab-reimbursements">Reimbursements</TabsTrigger>
          <TabsTrigger value="recoveries" data-testid="hr4-tab-store-recoveries">Store Recoveries</TabsTrigger>
          <TabsTrigger value="posting" data-testid="hr4-tab-posting">Posting Workflow</TabsTrigger>
          <TabsTrigger value="statutory" data-testid="hr4-tab-statutory">Statutory (PF/ESI/TDS)</TabsTrigger>
          <TabsTrigger value="project-cost" data-testid="hr4-tab-project-cost">Project Cost</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><DashboardView /></TabsContent>
        <TabsContent value="structures"><StructuresView /></TabsContent>
        <TabsContent value="loans"><LoansView /></TabsContent>
        <TabsContent value="reimbursements"><ReimbursementsView /></TabsContent>
        <TabsContent value="recoveries"><StoreRecoveriesView /></TabsContent>
        <TabsContent value="posting"><PostingView /></TabsContent>
        <TabsContent value="statutory"><StatutoryView /></TabsContent>
        <TabsContent value="project-cost"><ProjectCostView /></TabsContent>
      </Tabs>
    </div>
  );
}
