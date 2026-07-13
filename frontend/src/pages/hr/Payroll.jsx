import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Wallet, Play, Eye, Download, Users, Calculator, AlertCircle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

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
          <TabsTrigger value="payslips" data-testid="tab-payslips">Payslips</TabsTrigger>
          <TabsTrigger value="master" data-testid="tab-master"><Users className="h-4 w-4 mr-1" />Payroll Master</TabsTrigger>
        </TabsList>
        <TabsContent value="run"><RunTab /></TabsContent>
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
            <div className="text-xs mt-1">{preview.blocker_count} employee(s) have no approved attendance for {month}:</div>
            <ul className="text-xs mt-1 max-h-40 overflow-y-auto">{preview.blockers.map((b) => <li key={b.employee_id}>· {b.name} ({b.code}) — {b.department}</li>)}</ul>
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
                <TableHeader><TableRow><TableHead>Employee</TableHead><TableHead>Dept</TableHead><TableHead className="text-right">Paid Days</TableHead><TableHead className="text-right">Earnings</TableHead><TableHead className="text-right">Deductions</TableHead><TableHead className="text-right">Advance EMI</TableHead><TableHead className="text-right">Net Pay</TableHead><TableHead></TableHead></TableRow></TableHeader>
                <TableBody>
                  {preview.payslips.map((s) => (
                    <TableRow key={s.employee_id} data-testid={`slip-row-${s.employee_code}`}>
                      <TableCell><div className="font-medium">{s.employee_name}</div><div className="text-xs text-muted-foreground">{s.employee_code}</div></TableCell>
                      <TableCell>{s.department}</TableCell>
                      <TableCell className="text-right">{s.paid_days}/{s.total_days}</TableCell>
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
                {Object.entries(slip.earnings).map(([k, v]) => (
                  <tr key={k} className="border-b"><td className="py-1 capitalize">{k.replace(/_/g, " ")}</td><td className="text-right">{inr(v)}</td></tr>
                ))}
                {slip.extra_earnings.map((e, i) => (
                  <tr key={i} className="border-b"><td className="py-1">{e.label}</td><td className="text-right">{inr(e.amount)}</td></tr>
                ))}
                <tr className="font-bold"><td className="py-1">Total</td><td className="text-right">{inr(slip.total_earnings)}</td></tr>
              </table>
            </div>
            <div>
              <Label className="font-semibold">Deductions</Label>
              <table className="w-full text-xs">
                {Object.entries(slip.statutory_deductions).map(([k, v]) => (
                  <tr key={k} className="border-b"><td className="py-1 uppercase">{k}</td><td className="text-right">{inr(v)}</td></tr>
                ))}
                {slip.advance_emi > 0 && <tr className="border-b"><td className="py-1">Advance EMI</td><td className="text-right">{inr(slip.advance_emi)}</td></tr>}
                {slip.extra_deductions.map((d, i) => (
                  <tr key={i} className="border-b"><td className="py-1">{d.label}</td><td className="text-right">{inr(d.amount)}</td></tr>
                ))}
                <tr className="font-bold"><td className="py-1">Total</td><td className="text-right">{inr(slip.total_deductions)}</td></tr>
              </table>
            </div>
          </div>
          <div className="p-3 border-2 border-emerald-300 rounded bg-emerald-50 text-right">
            <div className="text-xs uppercase text-muted-foreground">Net Pay</div>
            <div className="text-2xl font-bold text-emerald-700">{inr(slip.net_pay)}</div>
          </div>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function KV({ label, value }) {
  return <div><div className="text-[10px] text-muted-foreground uppercase">{label}</div><div className="font-medium">{value || "—"}</div></div>;
}

function PayslipsTab() {
  const [month, setMonth] = useState(currentMonth());
  const [rows, setRows] = useState([]);
  const [viewing, setViewing] = useState(null);
  const load = async () => {
    try { const { data } = await api.get(`/payroll/payslips?month=${month}`); setRows(data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, [month]);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Payslips</CardTitle>
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-40" />
        <Button size="sm" onClick={load}>Reload</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Doc #</TableHead><TableHead>Employee</TableHead><TableHead>Month</TableHead><TableHead className="text-right">Net Pay</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-6">No payslips for {month}</TableCell></TableRow>}
              {rows.map((s) => (
                <TableRow key={s.id}><TableCell className="text-xs font-mono">{s.dept_doc_no}</TableCell><TableCell>{s.employee_name}<div className="text-xs text-muted-foreground">{s.employee_code}</div></TableCell><TableCell>{s.month}</TableCell><TableCell className="text-right font-semibold">{inr(s.net_pay)}</TableCell><TableCell><Button size="sm" variant="ghost" onClick={() => setViewing(s)}><Eye className="h-3 w-3" /></Button></TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {viewing && <SlipDialog slip={viewing} onClose={() => setViewing(null)} />}
      </CardContent>
    </Card>
  );
}

function MasterTab() {
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [editing, setEditing] = useState(null);
  const load = async () => {
    try {
      const [m, e] = await Promise.all([api.get("/payroll/master"), api.get("/employees")]);
      setRows(m.data); setEmployees(e.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  const unmapped = employees.filter((e) => e.active !== false && !rows.find((r) => r.employee_id === e.id));
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Payroll Master <Badge variant="outline" className="ml-2">{rows.length} mapped · {unmapped.length} unmapped</Badge></CardTitle>
        <Button size="sm" onClick={() => setEditing({ employee_id: "", basic: 0, hra: 0, special_allowance: 0, pf_applicable: true, esi_applicable: false, pt_state: "GJ", fixed_other_earnings: [], fixed_other_deductions: [] })}>+ Add</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Employee</TableHead><TableHead>Dept</TableHead><TableHead className="text-right">Basic</TableHead><TableHead className="text-right">HRA</TableHead><TableHead className="text-right">Special</TableHead><TableHead className="text-right">CTC</TableHead><TableHead>PF/ESI</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((r) => {
                const ctc = r.basic + r.hra + r.special_allowance + r.site_allowance + r.conveyance + r.medical;
                return (
                  <TableRow key={r.id} data-testid={`master-row-${r.employee_code}`}>
                    <TableCell>{r.employee_name}<div className="text-xs text-muted-foreground">{r.employee_code}</div></TableCell>
                    <TableCell>{r.department}</TableCell>
                    <TableCell className="text-right">{inr(r.basic)}</TableCell>
                    <TableCell className="text-right">{inr(r.hra)}</TableCell>
                    <TableCell className="text-right">{inr(r.special_allowance)}</TableCell>
                    <TableCell className="text-right font-semibold">{inr(ctc)}</TableCell>
                    <TableCell className="text-xs">{r.pf_applicable && <Badge variant="outline" className="mr-1">PF</Badge>}{r.esi_applicable && <Badge variant="outline">ESI</Badge>}</TableCell>
                    <TableCell><Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        {editing && <MasterDialog initial={editing} employees={employees} existingIds={rows.map((r) => r.employee_id)} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      </CardContent>
    </Card>
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
  const ctc = (form.basic || 0) + (form.hra || 0) + (form.special_allowance || 0) + (form.site_allowance || 0) + (form.conveyance || 0) + (form.medical || 0);
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
            {["basic", "hra", "special_allowance", "site_allowance", "conveyance", "medical"].map((k) => (
              <div key={k}>
                <Label className="capitalize text-xs">{k.replace(/_/g, " ")}</Label>
                <Input type="number" value={form[k] || 0} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} data-testid={`master-${k}`} />
              </div>
            ))}
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
