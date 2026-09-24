import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import { downloadPdf } from "@/lib/exports";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Wallet, Play, Eye, Download, Upload, Users, Calculator, AlertCircle, CheckCircle2, Mail, BadgeIndianRupee } from "lucide-react";
import { toast } from "sonner";
import { lookupGet } from "@/lib/lookups";
import BulkSalaryBooking from "./BulkSalaryBooking";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const currentMonth = () => new Date().toISOString().slice(0, 7);

export default function Payroll() {
  const [tab, setTab] = useState("run");
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="payroll-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Calculator className="h-6 w-6 text-emerald-600" /> Payroll
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Monthly salary processing with attendance preflight + automatic advance EMI recovery.
        </p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="run" data-testid="tab-run"><Play className="h-4 w-4 mr-1" />Monthly Run</TabsTrigger>
          <TabsTrigger value="bulk-booking" data-testid="tab-bulk-booking"><BadgeIndianRupee className="h-4 w-4 mr-1" />Bulk Salary Booking</TabsTrigger>
          <TabsTrigger value="payslips" data-testid="tab-payslips">Payslips</TabsTrigger>
          <TabsTrigger value="master" data-testid="tab-master"><Users className="h-4 w-4 mr-1" />Payroll Master</TabsTrigger>
        </TabsList>
        <TabsContent value="run"><RunTab /></TabsContent>
        <TabsContent value="bulk-booking"><BulkSalaryBooking /></TabsContent>
        <TabsContent value="payslips"><PayslipsTab /></TabsContent>
        <TabsContent value="master"><MasterTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function RunTab() {
  const [month, setMonth] = useState(currentMonth());
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [skipAttendance, setSkipAttendance] = useState(false);

  const runPreview = async () => {
    setBusy(true);
    try { const { data } = await api.post("/payroll/run/preview", { month, skip_attendance_check: skipAttendance }); setPreview(data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const commit = async () => {
    if (!confirm(`Commit payroll for ${month}? This will generate payslips and auto-deduct advance EMIs.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/payroll/run/commit", { month, skip_attendance_check: skipAttendance });
      toast.success(`Committed ${data.committed_count} payslips · ${inr(data.run.total_net)}`);
      setPreview(null);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Monthly Payroll Run</CardTitle>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          <input type="checkbox" checked={skipAttendance} onChange={(e) => setSkipAttendance(e.target.checked)} data-testid="payroll-skip-attendance" />
          Skip attendance check
        </label>
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-40" />
        <Button onClick={runPreview} disabled={busy} data-testid="payroll-preview-btn"><Play className="h-4 w-4 mr-1" />{busy ? "…" : "Preview"}</Button>
        <Button onClick={commit} disabled={busy || !preview || preview?.preflight_failed} className="bg-emerald-600 hover:bg-emerald-700" data-testid="payroll-commit-btn">
          <CheckCircle2 className="h-4 w-4 mr-1" />Commit
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {preview?.preflight_failed && (
          <div className="p-3 border rounded bg-rose-50 border-rose-200">
            <div className="flex items-center gap-2 font-medium text-rose-700"><AlertCircle className="h-4 w-4" /> Attendance preflight failed</div>
            <div className="text-xs mt-1">{preview.blocker_count} employee(s) lack fully-approved attendance for {month}:</div>
            <ul className="text-xs mt-1 max-h-40 overflow-y-auto">{preview.blockers.map((b) => <li key={b.employee_id}>· {b.name} ({b.code}) — {b.department}{b.reason ? ` — ${b.reason}` : ""}</li>)}</ul>
          </div>
        )}
        {preview && !preview.preflight_failed && (
          <>
            <div className="grid grid-cols-4 gap-3">
              <Tile label="Payslips" value={preview.totals.count} />
              <Tile label="Total Earnings" value={inr(preview.totals.earnings)} />
              <Tile label="Total Deductions" value={inr(preview.totals.deductions)} />
              <Tile label="Net Pay" value={inr(preview.totals.net_pay)} tone="emerald" />
            </div>
            {preview.missing_master.length > 0 && (
              <div className="p-2 border rounded bg-amber-50 text-xs">
                <strong>{preview.missing_master.length} employees skipped</strong> — no Payroll Master configured. Add them under the "Payroll Master" tab.
              </div>
            )}
            <div className="border rounded overflow-x-auto">
              <Table>
                <TableHeader><TableRow><TableHead>Employee</TableHead><TableHead>Dept</TableHead><TableHead className="text-right">Paid Days</TableHead><TableHead className="text-right">OT Hrs</TableHead><TableHead className="text-right">Earnings</TableHead><TableHead className="text-right">Deductions</TableHead><TableHead className="text-right">Advance EMI</TableHead><TableHead className="text-right">Net Pay</TableHead><TableHead></TableHead></TableRow></TableHeader>
                <TableBody>
                  {preview.payslips.map((s) => (
                    <TableRow key={s.employee_id} data-testid={`slip-row-${s.employee_code}`}>
                      <TableCell><div className="font-medium">{s.employee_name}</div><div className="text-xs text-muted-foreground">{s.employee_code}</div></TableCell>
                      <TableCell>{s.department}</TableCell>
                      <TableCell className="text-right">{s.paid_days}/{s.total_days}</TableCell>
                      <TableCell className="text-right">{s.ot_hours > 0 ? s.ot_hours : "—"}</TableCell>
                      <TableCell className="text-right">{inr(s.total_earnings)}</TableCell>
                      <TableCell className="text-right">{inr(s.total_deductions)}</TableCell>
                      <TableCell className="text-right">{s.advance_emi > 0 ? <Badge className="bg-amber-100 text-amber-700">{inr(s.advance_emi)}</Badge> : "—"}</TableCell>
                      <TableCell className="text-right font-semibold">{inr(s.net_pay)}</TableCell>
                      <TableCell><Button size="sm" variant="ghost" onClick={() => setViewing(s)}><Eye className="h-3 w-3" /></Button></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
        {viewing && <SlipDialog slip={viewing} onClose={() => setViewing(null)} />}
      </CardContent>
    </Card>
  );
}

function Tile({ label, value, tone = "slate" }) {
  const T = { slate: "bg-slate-50 border-slate-200", emerald: "bg-emerald-50 border-emerald-200" };
  return <div className={`p-3 border rounded ${T[tone]}`}><div className="text-xs uppercase text-muted-foreground">{label}</div><div className="text-xl font-bold">{value}</div></div>;
}

function SlipDialog({ slip, onClose }) {
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader><DialogTitle>Payslip · {slip.employee_name} · {slip.month}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-4 gap-3 p-3 border rounded bg-slate-50 text-xs">
            <KV label="Code" value={slip.employee_code} />
            <KV label="Dept" value={slip.department} />
            <KV label="Designation" value={slip.designation} />
            <KV label="Paid Days" value={`${slip.paid_days}/${slip.total_days}`} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="font-semibold">Earnings</Label>
              <table className="w-full text-xs">
                <tbody>
                {Object.entries(slip.earnings).map(([k, v]) => (
                  <tr key={k} className="border-b"><td className="py-1 capitalize">{k === "da" ? "DA (Dearness Allowance)" : k === "hra" ? "HRA" : k.replace(/_/g, " ")}</td><td className="text-right">{inr(v)}</td></tr>
                ))}
                {slip.extra_earnings.map((e, i) => (
                  <tr key={i} className="border-b"><td className="py-1">{e.label}</td><td className="text-right">{inr(e.amount)}</td></tr>
                ))}
                <tr className="font-bold"><td className="py-1">Total</td><td className="text-right">{inr(slip.total_earnings)}</td></tr>
                </tbody>
              </table>
            </div>
            <div>
              <Label className="font-semibold">Deductions</Label>
              <table className="w-full text-xs">
                <tbody>
                {Object.entries(slip.statutory_deductions).map(([k, v]) => (
                  <tr key={k} className="border-b"><td className="py-1 uppercase">{k}</td><td className="text-right">{inr(v)}</td></tr>
                ))}
                {slip.advance_emi > 0 && <tr className="border-b"><td className="py-1">Advance EMI</td><td className="text-right">{inr(slip.advance_emi)}</td></tr>}
                {slip.extra_deductions.map((d, i) => (
                  <tr key={i} className="border-b"><td className="py-1">{d.label}</td><td className="text-right">{inr(d.amount)}</td></tr>
                ))}
                <tr className="font-bold"><td className="py-1">Total</td><td className="text-right">{inr(slip.total_deductions)}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="p-3 border-2 border-emerald-300 rounded bg-emerald-50 text-right">
            <div className="text-xs uppercase text-muted-foreground">Net Pay</div>
            <div className="text-2xl font-bold text-emerald-700">{inr(slip.net_pay)}</div>
          </div>
        </div>
        <DialogFooter>
          {slip.id && (
            <Button variant="outline" onClick={() => downloadPdf(`/payroll/payslips/${slip.employee_id}/${slip.month}/pdf`, `Payslip-${slip.employee_code}-${slip.month}.pdf`)} data-testid="slip-dialog-pdf-btn">
              <Download className="h-3 w-3 mr-1" /> PDF
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function KV({ label, value }) {
  return <div><div className="text-[10px] text-muted-foreground uppercase">{label}</div><div className="font-medium">{value || "—"}</div></div>;
}

function PayslipsTab() {
  const [month, setMonth] = useState(currentMonth());
  const { rows, pagination, search, setSearch, reload: load } = usePagedList("/payroll/payslips", { month }, {
    viewKey: "payroll_payslips", errorLabel: "payslips", defaultSort: { by: "month", dir: "desc" },
    searchKeys: "employee_name,employee_code,dept_doc_no,department,designation,month",
  });
  const [viewing, setViewing] = useState(null);
  const [emailing, setEmailing] = useState(false);
  const emailAll = async () => {
    if (!window.confirm(`Email each employee their ${month} payslip PDF (sent from noreply mailbox)?`)) return;
    setEmailing(true);
    try {
      const { data } = await api.post(`/payroll/payslips/email-all?month=${month}`);
      const skipped = data.skipped || [];
      toast.success(`Queued ${data.queued} of ${data.total_payslips} payslip email(s) — sending in background`, { duration: 8000 });
      if (skipped.length) {
        toast.warning(`${skipped.length} skipped: ${skipped.map((s) => s.employee).join(", ")}`, { duration: 10000 });
      }
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setEmailing(false); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Payslips</CardTitle>
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-40" />
        <Input className="h-8 w-48" placeholder="Search employee…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="payslips-search" />
        <TableViewsMenu pagination={pagination} testidPrefix="payslips" />
        <Button size="sm" onClick={load}>Reload</Button>
        {rows.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => downloadPdf(`/payroll/payslips/bulk-pdf?month=${month}`, `Payslips-${month}.pdf`)} data-testid="payslips-bulk-pdf-btn">
            <Download className="h-3 w-3 mr-1" /> All PDF
          </Button>
        )}
        {rows.length > 0 && (
          <Button size="sm" onClick={emailAll} disabled={emailing} data-testid="payslips-email-all-btn">
            <Mail className="h-3 w-3 mr-1" /> {emailing ? "Queuing…" : "Email All"}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <div className="border rounded overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Doc #</TableHead><TableHead>Employee</TableHead><TableHead>Month</TableHead><TableHead className="text-right">Net Pay</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-6">No payslips for {month}</TableCell></TableRow>}
              {rows.map((s) => (
                <TableRow key={s.id}><TableCell className="text-xs font-mono">{s.dept_doc_no}</TableCell><TableCell>{s.employee_name}<div className="text-xs text-muted-foreground">{s.employee_code}</div></TableCell><TableCell>{s.month}</TableCell><TableCell className="text-right font-semibold">{inr(s.net_pay)}</TableCell><TableCell className="whitespace-nowrap"><Button size="sm" variant="ghost" onClick={() => setViewing(s)} data-testid={`payslip-view-${s.employee_code}`}><Eye className="h-3 w-3" /></Button><Button size="sm" variant="ghost" onClick={() => downloadPdf(`/payroll/payslips/${s.employee_id}/${s.month}/pdf`, `Payslip-${s.employee_code}-${s.month}.pdf`)} data-testid={`payslip-pdf-${s.employee_code}`} title="Download Payslip PDF"><Download className="h-3 w-3" /></Button></TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="pt-2"><TablePager pagination={pagination} testidPrefix="payslips" /></div>
        {viewing && <SlipDialog slip={viewing} onClose={() => setViewing(null)} />}
      </CardContent>
    </Card>
  );
}

function MasterTab() {
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [editing, setEditing] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [pendingUpload, setPendingUpload] = useState(null); // { file, preview }
  const load = async () => {
    try {
      const [m, e] = await Promise.all([api.get("/payroll/master"), lookupGet("/employees")]);
      setRows(m.data); setEmployees(e.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  const downloadTemplate = async () => {
    try {
      const { data } = await api.get("/payroll/master/bulk/template", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([data]));
      const a = document.createElement("a");
      a.href = url; a.download = "payroll-master-template.xlsx";
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const onImportFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/payroll/master/bulk/validate", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPendingUpload({ file, preview: data });
    } catch (er) { toast.error(apiErrorMessage(er)); }
    finally { setImporting(false); }
  };
  const confirmImport = async () => {
    if (!pendingUpload?.file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", pendingUpload.file);
      const { data } = await api.post("/payroll/master/bulk/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPendingUpload(null);
      setImportResult(data);
      if (data.error_count === 0) toast.success(`Imported: ${data.created} created · ${data.updated} updated`);
      else toast.warning(`${data.error_count} row(s) had errors — see details`);
      load();
    } catch (er) { toast.error(apiErrorMessage(er)); }
    finally { setImporting(false); }
  };
  const unmapped = employees.filter((e) => e.active !== false && !rows.find((r) => r.employee_id === e.id));
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 flex-wrap">
        <CardTitle className="text-base flex-1">Payroll Master <Badge variant="outline" className="ml-2">{rows.length} mapped · {unmapped.length} unmapped</Badge></CardTitle>
        <Button size="sm" variant="outline" onClick={downloadTemplate} data-testid="master-template-btn">
          <Download className="h-3 w-3 mr-1" /> Template
        </Button>
        <label className="inline-flex">
          <input type="file" accept=".xlsx" className="hidden" onChange={onImportFile} data-testid="master-import-input" />
          <Button size="sm" variant="outline" disabled={importing} asChild data-testid="master-import-btn">
            <span className="cursor-pointer"><Upload className="h-3 w-3 mr-1" /> {importing ? "Uploading…" : "Bulk Upload"}</span>
          </Button>
        </label>
        <Button size="sm" onClick={() => setEditing({ employee_id: "", basic: 0, hra: 0, da: 0, special_allowance: 0, attendance_bonus_applicable: false, attendance_bonus_amount: 0, pf_applicable: true, esi_applicable: false, pt_state: "GJ", fixed_other_earnings: [], fixed_other_deductions: [] })} data-testid="master-add-btn">+ Add</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Employee</TableHead><TableHead>Dept</TableHead><TableHead className="text-right">Basic</TableHead><TableHead className="text-right">HRA</TableHead><TableHead className="text-right">DA</TableHead><TableHead className="text-right">Special</TableHead><TableHead className="text-right">CTC</TableHead><TableHead>PF/ESI/Bonus</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((r) => {
                const ctc = r.basic + r.hra + (r.da || 0) + r.special_allowance + r.site_allowance + r.conveyance + r.medical;
                return (
                  <TableRow key={r.id || r.employee_id} data-testid={`master-row-${r.employee_code}`}>
                    <TableCell>{r.employee_name}<div className="text-xs text-muted-foreground">{r.employee_code}</div></TableCell>
                    <TableCell>{r.department}</TableCell>
                    <TableCell className="text-right">{inr(r.basic)}</TableCell>
                    <TableCell className="text-right">{inr(r.hra)}</TableCell>
                    <TableCell className="text-right">{inr(r.da || 0)}</TableCell>
                    <TableCell className="text-right">{inr(r.special_allowance)}</TableCell>
                    <TableCell className="text-right font-semibold">{inr(ctc)}</TableCell>
                    <TableCell className="text-xs">{r.pf_applicable && <Badge variant="outline" className="mr-1">PF</Badge>}{r.esi_applicable && <Badge variant="outline" className="mr-1">ESI</Badge>}{r.attendance_bonus_applicable && <Badge variant="outline" className="bg-amber-50 border-amber-300 text-amber-700">AB {inr(r.attendance_bonus_amount || 0)}</Badge>}</TableCell>
                    <TableCell><Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        {editing && <MasterDialog initial={editing} employees={employees} existingIds={rows.map((r) => r.employee_id)} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
        {pendingUpload && <BulkPreviewDialog preview={pendingUpload.preview} importing={importing} onConfirm={confirmImport} onClose={() => setPendingUpload(null)} />}
        {importResult && <ImportResultDialog result={importResult} onClose={() => setImportResult(null)} />}
      </CardContent>
    </Card>
  );
}

function BulkPreviewDialog({ preview, importing, onConfirm, onClose }) {
  const c = preview.counts || {};
  const actionable = (c.create || 0) + (c.update || 0);
  const tone = { create: "text-emerald-700 bg-emerald-50", update: "text-blue-700 bg-blue-50", unchanged: "text-slate-500 bg-slate-50", skip: "text-slate-500 bg-slate-50", error: "text-red-700 bg-red-50" };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[88vh] overflow-y-auto" data-testid="master-bulk-preview">
        <DialogHeader><DialogTitle>Bulk Upload — Validation Preview</DialogTitle></DialogHeader>
        <div className="grid grid-cols-5 gap-2">
          <Tile label="New" value={c.create || 0} tone="emerald" />
          <Tile label="Will Update" value={c.update || 0} tone="emerald" />
          <Tile label="Unchanged" value={c.unchanged || 0} />
          <Tile label="Skipped" value={c.skip || 0} />
          <Tile label="Errors" value={c.error || 0} />
        </div>
        <div className="border rounded max-h-[46vh] overflow-y-auto">
          <Table>
            <TableHeader><TableRow>
              <TableHead className="w-12">Row</TableHead><TableHead>Employee</TableHead><TableHead>Action</TableHead>
              <TableHead className="text-right">Basic</TableHead><TableHead className="text-right">DA</TableHead>
              <TableHead className="text-right">Gross</TableHead><TableHead>Att. Bonus</TableHead><TableHead>Changes / Error</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(preview.rows || []).map((r, i) => (
                <TableRow key={i} className={r.action === "error" ? "bg-red-50/50" : ""}>
                  <TableCell className="text-xs">{r.row}</TableCell>
                  <TableCell className="text-xs">{r.employee_name || r.employee}<div className="text-[10px] text-muted-foreground font-mono">{r.employee}</div></TableCell>
                  <TableCell><span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold ${tone[r.action] || ""}`}>{r.action}</span></TableCell>
                  <TableCell className="text-right text-xs">{r.basic != null ? inr(r.basic) : "—"}</TableCell>
                  <TableCell className="text-right text-xs">{r.da != null ? inr(r.da) : "—"}</TableCell>
                  <TableCell className="text-right text-xs font-semibold">{r.gross != null ? inr(r.gross) : "—"}</TableCell>
                  <TableCell className="text-xs">{r.attendance_bonus ?? "—"}</TableCell>
                  <TableCell className="text-xs">{r.action === "error" ? <span className="text-red-600">{r.error}</span> : (r.changed_fields || []).join(", ").replaceAll("_", " ") || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {c.error > 0 && <p className="text-xs text-amber-700">Rows with errors will be reported and NOT imported. You can fix the file and re-upload, or proceed with the valid rows.</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={onConfirm} disabled={importing || actionable === 0} data-testid="master-bulk-confirm">
            {importing ? "Updating…" : `Confirm Update (${actionable} row${actionable === 1 ? "" : "s"})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ImportResultDialog({ result, onClose }) {
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="master-import-result">
        <DialogHeader><DialogTitle>Bulk Upload Result</DialogTitle></DialogHeader>
        <div className="grid grid-cols-4 gap-3">
          <Tile label="Created" value={result.created} tone="emerald" />
          <Tile label="Updated" value={result.updated} tone="emerald" />
          <Tile label="Skipped" value={result.skipped} />
          <Tile label="Errors" value={result.error_count} />
        </div>
        {result.errors?.length > 0 && (
          <div className="border rounded max-h-64 overflow-y-auto">
            <Table>
              <TableHeader><TableRow><TableHead className="w-16">Row</TableHead><TableHead>Employee</TableHead><TableHead>Error</TableHead></TableRow></TableHeader>
              <TableBody>
                {result.errors.map((e, i) => (
                  <TableRow key={i}><TableCell>{e.row}</TableCell><TableCell className="text-xs font-mono">{e.employee}</TableCell><TableCell className="text-xs text-red-600">{e.error}</TableCell></TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MasterDialog({ initial, employees, existingIds, onClose, onSaved }) {
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!form.employee_id) { toast.error("Pick employee"); return; }
    setSaving(true);
    try {
      await api.put(`/payroll/master/${form.employee_id}`, form);
      toast.success("Saved"); onSaved();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setSaving(false); }
  };
  const ctc = (form.basic || 0) + (form.hra || 0) + (form.da || 0) + (form.special_allowance || 0) + (form.site_allowance || 0) + (form.conveyance || 0) + (form.medical || 0);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Payroll Master</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {!initial.id && (
            <div>
              <Label>Employee *</Label>
              <select className="w-full p-2 border rounded" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="master-emp-select">
                <option value="">— Pick —</option>
                {employees.filter((e) => e.active !== false && !existingIds.includes(e.id)).map((e) => (
                  <option key={e.id} value={e.id}>{e.name} ({e.employee_id || e.id.slice(0, 6)})</option>
                ))}
              </select>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            {["basic", "hra", "da", "special_allowance", "site_allowance", "conveyance", "medical"].map((k) => (
              <div key={k}>
                <Label className="capitalize text-xs">{k === "da" ? "DA (Dearness Allowance)" : k.replace(/_/g, " ")}</Label>
                <Input type="number" value={form[k] || 0} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} data-testid={`master-${k}`} />
              </div>
            ))}
          </div>
          <div className="p-2 border rounded bg-amber-50/60 border-amber-200 grid grid-cols-2 gap-3 items-center">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!form.attendance_bonus_applicable}
                onChange={(e) => setForm({ ...form, attendance_bonus_applicable: e.target.checked })}
                data-testid="master-att-bonus-flag" />
              Attendance Bonus Applicable
            </label>
            <div>
              <Label className="text-xs">Bonus Amount (₹/month, paid when zero LOP)</Label>
              <Input type="number" value={form.attendance_bonus_amount || 0} disabled={!form.attendance_bonus_applicable}
                onChange={(e) => setForm({ ...form, attendance_bonus_amount: Number(e.target.value) })}
                data-testid="master-att-bonus-amount" />
            </div>
          </div>
          <div className="p-2 border rounded bg-emerald-50 text-sm"><strong>Monthly CTC:</strong> {inr(ctc)}</div>
          <div className="grid grid-cols-3 gap-3">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.pf_applicable} onChange={(e) => setForm({ ...form, pf_applicable: e.target.checked })} />PF Applicable</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.esi_applicable} onChange={(e) => setForm({ ...form, esi_applicable: e.target.checked })} />ESI Applicable</label>
            <div><Label className="text-xs">PT State</Label><Input value={form.pt_state || "GJ"} onChange={(e) => setForm({ ...form, pt_state: e.target.value })} /></div>
            <div><Label className="text-xs">TDS Override %</Label><Input type="number" value={form.tds_override_pct || 0} onChange={(e) => setForm({ ...form, tds_override_pct: Number(e.target.value) })} /></div>
            <div className="col-span-2"><Label className="text-xs">PAN</Label><Input value={form.pan || ""} onChange={(e) => setForm({ ...form, pan: e.target.value })} /></div>
            <div><Label className="text-xs">Bank Name</Label><Input value={form.bank_name || ""} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} /></div>
            <div><Label className="text-xs">Account</Label><Input value={form.bank_account || ""} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} /></div>
            <div><Label className="text-xs">IFSC</Label><Input value={form.bank_ifsc || ""} onChange={(e) => setForm({ ...form, bank_ifsc: e.target.value })} /></div>
          </div>
        </div>
        <DialogFooter><Button onClick={submit} disabled={saving} data-testid="master-save-btn">{saving ? "…" : "Save"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
