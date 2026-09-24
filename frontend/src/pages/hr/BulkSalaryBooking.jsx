/**
 * HR · Payroll → Bulk Salary Booking
 * Month-wise bulk salary booking with project-wise expense allocation.
 * Download pre-filled sheet (Attendance + Salary Breakup + Advances) → upload →
 * preview → commit → record payments → booked/paid/pending dashboard & reports.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertTriangle, BadgeIndianRupee, Building2, CheckCircle2, Download, FileUp, Upload, Wallet } from "lucide-react";
import { toast } from "sonner";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const currentMonth = () => new Date().toISOString().slice(0, 7);

const STATUS_TONE = {
  paid: "bg-emerald-100 text-emerald-800 border-emerald-300",
  partial: "bg-amber-100 text-amber-800 border-amber-300",
  unpaid: "bg-slate-100 text-slate-700 border-slate-300",
};

export default function BulkSalaryBooking() {
  const [month, setMonth] = useState(currentMonth());
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [summary, setSummary] = useState(null);
  const [filters, setFilters] = useState({ project_code: "", department: "", payment_status: "", employee_q: "" });
  const [payOpen, setPayOpen] = useState(false);
  const [selected, setSelected] = useState([]);
  const fileRef = useRef(null);

  const loadSummary = useCallback(async () => {
    try {
      const { data } = await api.get("/payroll/bulk-booking/summary", { params: { month, ...filters } });
      setSummary(data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [month, filters]);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const downloadTemplate = async () => {
    setBusy("template");
    try {
      const r = await api.get("/payroll/bulk-booking/template", { params: { month }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = `salary-booking-${month}.xlsx`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Sheet downloaded — pre-filled from Attendance, Salary Breakup & Advances");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(""); }
  };

  const exportBooked = async () => {
    try {
      const r = await api.get("/payroll/bulk-booking/export", { params: { month }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = `salary-booked-${month}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const upload = async (file) => {
    if (!file) return;
    setBusy("upload"); setPreview(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("month", month);
      const { data } = await api.post("/payroll/bulk-booking/preview", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(data);
      const msg = `${data.totals.count} employee(s) ready · ${data.by_project.length} project(s) · net ${inr(data.totals.net)}`;
      (data.skipped.length || data.warnings.length) ? toast.warning(msg) : toast.success(msg);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  };

  const commit = async (overwrite) => {
    setBusy("commit");
    try {
      const { data } = await api.post(`/payroll/bulk-booking/${preview.id}/commit`, { overwrite });
      toast.success(`Booked ${data.booked_count} employee(s) — ${data.booking.booking_no}`);
      setPreview(null);
      loadSummary();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(""); }
  };

  const t = summary?.totals || { headcount: 0, gross: 0, booked: 0, paid: 0, pending: 0 };

  return (
    <div className="space-y-4" data-testid="bulk-salary-booking-tab">
      {/* ── Step 1 · Month + sheet ───────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <BadgeIndianRupee className="h-4 w-4 text-emerald-600" /> Month-wise Bulk Salary Booking
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Pick the month, download the sheet pre-filled from Attendance (Pay/Present days + OT), Salary Breakup,
            Advances and Salary Payable, fill your project-wise allocation, upload it and book the whole month in one go.
            Uploaded amounts are final — differences against the system calculation are shown as warnings.
          </p>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div>
            <Label className="text-xs">Salary Month</Label>
            <Input type="month" value={month} onChange={(e) => { setMonth(e.target.value); setPreview(null); }}
              className="w-44" data-testid="bsb-month-input" />
          </div>
          <Button variant="outline" onClick={downloadTemplate} disabled={busy === "template"} data-testid="bsb-template-btn">
            <Download className="h-4 w-4 mr-1.5" /> {busy === "template" ? "Preparing…" : "Download Salary Format"}
          </Button>
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden"
            onChange={(e) => upload(e.target.files?.[0])} data-testid="bsb-file-input" />
          <Button onClick={() => fileRef.current?.click()} disabled={busy === "upload"} data-testid="bsb-upload-btn">
            <FileUp className="h-4 w-4 mr-1.5" /> {busy === "upload" ? "Reading sheet…" : "Upload Filled Sheet"}
          </Button>
          {summary?.booking && (
            <Button variant="ghost" onClick={exportBooked} data-testid="bsb-export-btn">
              <Upload className="h-4 w-4 mr-1.5 rotate-180" /> Export Booked Sheet
            </Button>
          )}
        </CardContent>
      </Card>

      {/* ── Step 2 · Preview ─────────────────────────────────────────── */}
      {preview && (
        <Card data-testid="bsb-preview">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Preview — {preview.month}</CardTitle>
            <div className="flex flex-wrap items-center gap-3 text-sm pt-1">
              <span className="font-semibold" data-testid="bsb-preview-count">{preview.totals.count} employee(s)</span>
              <span>Gross <b>{inr(preview.totals.gross)}</b></span>
              <span>Deductions <b>{inr(preview.totals.deductions)}</b></span>
              <span className="text-emerald-700">Net Payable <b data-testid="bsb-preview-net">{inr(preview.totals.net)}</b></span>
              {preview.skipped.length > 0 && <span className="text-red-600" data-testid="bsb-preview-skipped">{preview.skipped.length} row(s) skipped</span>}
              {preview.warnings.length > 0 && <span className="text-amber-700" data-testid="bsb-preview-warnings">{preview.warnings.length} warning(s)</span>}
              <div className="ml-auto flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setPreview(null)} data-testid="bsb-cancel-btn">Cancel</Button>
                <Button size="sm" onClick={() => commit(preview.already_booked || preview.payroll_run_exists)}
                  disabled={busy === "commit"} data-testid="bsb-commit-btn">
                  <CheckCircle2 className="h-4 w-4 mr-1.5" />
                  {busy === "commit" ? "Booking…" : (preview.already_booked ? "Replace & Book Month" : "Confirm & Book Month")}
                </Button>
              </div>
            </div>
            {(preview.already_booked || preview.payroll_run_exists) && (
              <p className="text-xs text-amber-700 pt-1" data-testid="bsb-already-booked">
                <AlertTriangle className="h-3 w-3 inline mr-1" />
                {preview.already_booked
                  ? `Salary for ${preview.month} is already booked (${preview.already_booked_no}). Confirming will replace it.`
                  : `A payroll run for ${preview.month} already exists. Confirming will replace its payslips.`}
              </p>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Project-wise totals */}
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">Project-wise Allocation</div>
              <div className="overflow-x-auto border rounded-sm">
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Project</TableHead><TableHead>Code</TableHead>
                    <TableHead className="text-right">Headcount</TableHead>
                    <TableHead className="text-right">Gross</TableHead>
                    <TableHead className="text-right">Deductions</TableHead>
                    <TableHead className="text-right">Net</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {preview.by_project.map((p) => (
                      <TableRow key={p.project_code} data-testid={`bsb-preview-project-${p.project_code}`}>
                        <TableCell className="font-medium">{p.project_name || p.project_code}
                          {!p.matched && <Badge variant="outline" className="ml-2 text-[10px] bg-amber-50 text-amber-800 border-amber-300">not in master</Badge>}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{p.project_code}</TableCell>
                        <TableCell className="text-right">{p.headcount}</TableCell>
                        <TableCell className="text-right">{inr(p.gross)}</TableCell>
                        <TableCell className="text-right">{inr(p.deductions)}</TableCell>
                        <TableCell className="text-right font-semibold">{inr(p.net)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            {/* Employee rows */}
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">Employee-wise Rows</div>
              <div className="overflow-x-auto border rounded-sm max-h-80">
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Emp ID</TableHead><TableHead>Name</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead className="text-right">Pay Days</TableHead>
                    <TableHead className="text-right">Present</TableHead>
                    <TableHead className="text-right">Gross</TableHead>
                    <TableHead className="text-right">PF</TableHead>
                    <TableHead className="text-right">Advance</TableHead>
                    <TableHead className="text-right">Net</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {preview.rows.map((r) => (
                      <TableRow key={r.emp_id} data-testid={`bsb-preview-row-${r.emp_id}`}>
                        <TableCell className="font-mono text-xs">{r.emp_id}</TableCell>
                        <TableCell>{r.employee_name}</TableCell>
                        <TableCell className="text-xs">{r.project_name || r.project_code}</TableCell>
                        <TableCell className="text-right">{r.pay_days}</TableCell>
                        <TableCell className="text-right">{r.present_days}</TableCell>
                        <TableCell className="text-right">{inr(r.total_earning)}</TableCell>
                        <TableCell className="text-right">{inr(r.pf)}</TableCell>
                        <TableCell className="text-right">{inr(r.advance)}</TableCell>
                        <TableCell className="text-right font-semibold">{inr(r.net_amount)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            {preview.skipped.length > 0 && (
              <div className="border border-red-200 bg-red-50 rounded-sm p-3" data-testid="bsb-skipped-list">
                <div className="text-xs font-semibold text-red-800 mb-1">Skipped rows (not booked)</div>
                <ul className="text-xs text-red-700 space-y-0.5 max-h-40 overflow-y-auto">
                  {preview.skipped.map((s, i) => <li key={i}>{s.emp_id} {s.employee_name ? `· ${s.employee_name}` : ""} — {s.reason}</li>)}
                </ul>
              </div>
            )}
            {preview.warnings.length > 0 && (
              <div className="border border-amber-200 bg-amber-50 rounded-sm p-3" data-testid="bsb-warning-list">
                <div className="text-xs font-semibold text-amber-800 mb-1">Warnings (sheet values are used as-is)</div>
                <ul className="text-xs text-amber-800 space-y-0.5 max-h-40 overflow-y-auto">
                  {preview.warnings.map((w, i) => <li key={i}>{w.emp_id} · {w.employee_name} — {w.message}</li>)}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Step 3 · Booked / Paid / Pending dashboard ───────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Wallet className="h-4 w-4 text-emerald-600" /> Salary Booked / Paid / Pending — {month}
            {summary?.booking && <Badge variant="outline" className="font-mono text-[10px]" data-testid="bsb-booking-no">{summary.booking.booking_no}</Badge>}
            {summary?.booking && <Badge variant="outline" className={STATUS_TONE[summary.booking.payment_status] || ""}>{summary.booking.payment_status}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Stat label="Employees" value={t.headcount} testid="bsb-stat-headcount" plain />
            <Stat label="Gross Expense" value={inr(t.gross)} testid="bsb-stat-gross" />
            <Stat label="Booked (Net)" value={inr(t.booked)} testid="bsb-stat-booked" tone="text-sky-700" />
            <Stat label="Paid" value={inr(t.paid)} testid="bsb-stat-paid" tone="text-emerald-700" />
            <Stat label="Pending" value={inr(t.pending)} testid="bsb-stat-pending" tone="text-amber-700" />
          </div>

          {summary?.finance && (summary.finance.finance_approval_status || summary.finance.accounts_posting_status) && (
            <div className="text-xs text-muted-foreground" data-testid="bsb-finance-status">
              Finance approval: <b>{summary.finance.finance_approval_status || "pending"}</b> · Accounts posting: <b>{summary.finance.accounts_posting_status || "not posted"}</b>
              {summary.finance.accounts_je_number ? ` · JE ${summary.finance.accounts_je_number}` : ""}
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap items-end gap-2 border-t pt-3">
            <div>
              <Label className="text-xs">Project</Label>
              <select value={filters.project_code} onChange={(e) => setFilters((f) => ({ ...f, project_code: e.target.value }))}
                className="h-9 w-48 border rounded-sm px-2 text-sm bg-background" data-testid="bsb-filter-project">
                <option value="">All projects</option>
                {(summary?.by_project || []).map((p) => <option key={p.project_code} value={p.project_code}>{p.project_name || p.project_code}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs">Payment Status</Label>
              <select value={filters.payment_status} onChange={(e) => setFilters((f) => ({ ...f, payment_status: e.target.value }))}
                className="h-9 w-36 border rounded-sm px-2 text-sm bg-background" data-testid="bsb-filter-status">
                <option value="">All</option><option value="unpaid">Unpaid</option>
                <option value="partial">Partial</option><option value="paid">Paid</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Department</Label>
              <Input value={filters.department} onChange={(e) => setFilters((f) => ({ ...f, department: e.target.value }))}
                placeholder="Department" className="w-40" data-testid="bsb-filter-department" />
            </div>
            <div>
              <Label className="text-xs">Employee</Label>
              <Input value={filters.employee_q} onChange={(e) => setFilters((f) => ({ ...f, employee_q: e.target.value }))}
                placeholder="Name or Emp ID" className="w-44" data-testid="bsb-filter-employee" />
            </div>
            <Button variant="outline" size="sm" onClick={() => setFilters({ project_code: "", department: "", payment_status: "", employee_q: "" })}
              data-testid="bsb-filter-clear">Clear</Button>
            <div className="ml-auto flex gap-2">
              <Button size="sm" variant="outline" disabled={!selected.length} onClick={() => setPayOpen("selected")}
                data-testid="bsb-pay-selected-btn">Pay Selected ({selected.length})</Button>
              <Button size="sm" disabled={t.pending <= 0} onClick={() => setPayOpen("month")} data-testid="bsb-pay-month-btn">
                <Wallet className="h-4 w-4 mr-1.5" /> Record Salary Payment
              </Button>
            </div>
          </div>

          {/* Project-wise expense */}
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground mb-1 flex items-center gap-1">
              <Building2 className="h-3 w-3" /> Project-wise Salary Expense
            </div>
            <div className="overflow-x-auto border rounded-sm">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Project</TableHead><TableHead>Code</TableHead>
                  <TableHead className="text-right">Headcount</TableHead>
                  <TableHead className="text-right">Gross Expense</TableHead>
                  <TableHead className="text-right">Booked</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead className="text-right">Pending</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(summary?.by_project || []).length === 0 && (
                    <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6" data-testid="bsb-no-project-rows">
                      No salary booked for this month yet.
                    </TableCell></TableRow>
                  )}
                  {(summary?.by_project || []).map((p) => (
                    <TableRow key={p.project_code} data-testid={`bsb-project-${p.project_code}`}>
                      <TableCell className="font-medium">{p.project_name || p.project_code}</TableCell>
                      <TableCell className="font-mono text-xs">{p.project_code}</TableCell>
                      <TableCell className="text-right">{p.headcount}</TableCell>
                      <TableCell className="text-right">{inr(p.gross)}</TableCell>
                      <TableCell className="text-right">{inr(p.booked)}</TableCell>
                      <TableCell className="text-right text-emerald-700">{inr(p.paid)}</TableCell>
                      <TableCell className="text-right text-amber-700">{inr(p.pending)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* Employee-wise expense/payment */}
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">Employee-wise Salary Expense & Payment</div>
            <div className="overflow-x-auto border rounded-sm max-h-96">
              <Table>
                <TableHeader><TableRow>
                  <TableHead className="w-8"></TableHead>
                  <TableHead>Emp ID</TableHead><TableHead>Name</TableHead>
                  <TableHead>Project</TableHead><TableHead>Department</TableHead>
                  <TableHead className="text-right">Gross</TableHead>
                  <TableHead className="text-right">Booked (Net)</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead className="text-right">Pending</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(summary?.employees || []).length === 0 && (
                    <TableRow><TableCell colSpan={10} className="text-center text-sm text-muted-foreground py-6" data-testid="bsb-no-employee-rows">
                      Nothing booked yet for this month / filter.
                    </TableCell></TableRow>
                  )}
                  {(summary?.employees || []).map((r) => (
                    <TableRow key={r.employee_id} data-testid={`bsb-emp-${r.emp_code}`}>
                      <TableCell>
                        <input type="checkbox" checked={selected.includes(r.employee_id)}
                          onChange={(e) => setSelected((s) => e.target.checked ? [...s, r.employee_id] : s.filter((x) => x !== r.employee_id))}
                          disabled={Number(r.pending_amount || 0) <= 0}
                          data-testid={`bsb-emp-check-${r.emp_code}`} />
                      </TableCell>
                      <TableCell className="font-mono text-xs">{r.emp_code}</TableCell>
                      <TableCell>{r.employee_name}</TableCell>
                      <TableCell className="text-xs">{r.project_name || r.project_code}</TableCell>
                      <TableCell className="text-xs">{r.department}</TableCell>
                      <TableCell className="text-right">{inr(r.gross)}</TableCell>
                      <TableCell className="text-right">{inr(r.net)}</TableCell>
                      <TableCell className="text-right text-emerald-700">{inr(r.paid_amount)}</TableCell>
                      <TableCell className="text-right text-amber-700">{inr(r.pending_amount)}</TableCell>
                      <TableCell><Badge variant="outline" className={STATUS_TONE[r.payment_status] || ""}>{r.payment_status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </CardContent>
      </Card>

      <PaymentDialog open={!!payOpen} mode={payOpen} month={month} pending={t.pending}
        employeeIds={payOpen === "selected" ? selected : []}
        onClose={() => setPayOpen(false)}
        onDone={() => { setPayOpen(false); setSelected([]); loadSummary(); }} />
    </div>
  );
}

function Stat({ label, value, testid, tone = "", plain = false }) {
  return (
    <div className="border rounded-sm p-3 bg-card" data-testid={testid}>
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className={`font-bold ${plain ? "text-lg" : "text-lg"} ${tone}`}>{value}</div>
    </div>
  );
}

function PaymentDialog({ open, mode, month, pending, employeeIds, onClose, onDone }) {
  const [form, setForm] = useState({ amount: "", payment_date: new Date().toISOString().slice(0, 10), mode: "bank", reference: "", note: "" });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/payroll/bulk-booking/payments", {
        month,
        employee_ids: employeeIds,
        amount: Number(form.amount || 0),
        payment_date: form.payment_date,
        mode: form.mode,
        reference: form.reference,
        note: form.note,
      });
      toast.success(`Paid ${"₹" + Number(data.paid_now).toLocaleString("en-IN")} to ${data.employees_paid} employee(s) — pending ${"₹" + Number(data.pending).toLocaleString("en-IN")}`);
      onDone();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="bsb-payment-dialog">
        <DialogHeader>
          <DialogTitle>Record Salary Payment — {month}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            {mode === "selected"
              ? `${employeeIds.length} selected employee(s). Leave the amount blank to clear their full pending salary.`
              : `Pending for the month: ${inr(pending)}. Leave the amount blank to pay everyone in full, or enter a part amount to distribute employee-wise.`}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Amount (blank = full pending)</Label>
              <Input type="number" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
                placeholder="0.00" data-testid="bsb-pay-amount" />
            </div>
            <div>
              <Label className="text-xs">Payment Date</Label>
              <Input type="date" value={form.payment_date} onChange={(e) => setForm((f) => ({ ...f, payment_date: e.target.value }))}
                data-testid="bsb-pay-date" />
            </div>
            <div>
              <Label className="text-xs">Mode</Label>
              <select value={form.mode} onChange={(e) => setForm((f) => ({ ...f, mode: e.target.value }))}
                className="h-9 w-full border rounded-sm px-2 text-sm bg-background" data-testid="bsb-pay-mode">
                <option value="bank">Bank Transfer</option><option value="cash">Cash</option><option value="cheque">Cheque</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Reference / UTR</Label>
              <Input value={form.reference} onChange={(e) => setForm((f) => ({ ...f, reference: e.target.value }))}
                data-testid="bsb-pay-reference" />
            </div>
          </div>
          <div>
            <Label className="text-xs">Note</Label>
            <Input value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} data-testid="bsb-pay-note" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="bsb-pay-cancel">Cancel</Button>
          <Button onClick={submit} disabled={saving} data-testid="bsb-pay-submit">{saving ? "Saving…" : "Record Payment"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
