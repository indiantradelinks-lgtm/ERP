// HR Phase 2 Hub — Attendance, Shifts, Overtime, Compliance, Safety Readiness
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
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { api, apiErrorMessage } from "@/lib/api";
import { ProjectSelect } from "@/components/MasterSelect";
import { toast } from "sonner";
import {
  ClipboardCheck, Clock, ShieldCheck, AlertTriangle, Lock,
  Unlock, Plus, Filter, Calendar, Check, X, RefreshCw, Activity,
} from "lucide-react";

const today = () => new Date().toISOString().slice(0, 10);
const monthIso = () => new Date().toISOString().slice(0, 7);

const SEVERITY_TONE = {
  high: "bg-rose-100 text-rose-900 border-rose-300",
  medium: "bg-amber-100 text-amber-900 border-amber-300",
  low: "bg-slate-100 text-slate-700 border-slate-300",
};

const ATT_STATUS_TONE = {
  present: "bg-emerald-100 text-emerald-900 border-emerald-300",
  absent: "bg-rose-100 text-rose-900 border-rose-300",
  leave: "bg-amber-100 text-amber-900 border-amber-300",
  half_day: "bg-yellow-100 text-yellow-900 border-yellow-300",
  weekly_off: "bg-slate-100 text-slate-700 border-slate-300",
  holiday: "bg-violet-100 text-violet-900 border-violet-300",
  on_duty: "bg-blue-100 text-blue-900 border-blue-300",
};

const OT_STATUS_TONE = {
  pending: "bg-amber-100 text-amber-900 border-amber-300",
  hr_pending: "bg-blue-100 text-blue-900 border-blue-300",
  approved: "bg-emerald-100 text-emerald-900 border-emerald-300",
  rejected: "bg-rose-100 text-rose-900 border-rose-300",
};

function StatusBadge({ value, map }) {
  const cls = map[value] || "bg-slate-100 text-slate-700 border-slate-300";
  return <Badge className={`text-xs border ${cls}`} data-testid={`status-badge-${value}`}>{value || "—"}</Badge>;
}

function Tile({ label, value, testid }) {
  return (
    <Card data-testid={testid}><CardContent className="p-4">
      <div className="text-[11px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </CardContent></Card>
  );
}

// ─────────── DASHBOARD ───────────
function DashboardView() {
  const [d, setD] = useState(null);
  const [a, setA] = useState(null);
  const load = async () => {
    try {
      const [r1, r2] = await Promise.all([
        api.get("/hr2/dashboard"),
        api.get("/hr2/compliance-alerts?days=30"),
      ]);
      setD(r1.data); setA(r2.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  if (!d) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <Tile label="Active Shifts" value={d.active_shifts} testid="hr2-tile-active-shifts" />
        <Tile label="Attendance Today" value={d.attendance_today} testid="hr2-tile-att-today" />
        <Tile label="Pending Approval" value={d.attendance_pending_approval} testid="hr2-tile-att-pending" />
        <Tile label="Locked Periods" value={d.attendance_locked_periods} testid="hr2-tile-locked" />
        <Tile label="OT Pending" value={d.overtime_pending} testid="hr2-tile-ot-pending" />
        <Tile label="OT Approved (Mo)" value={d.overtime_approved_month} testid="hr2-tile-ot-approved" />
        <Tile label="Leave Pending" value={d.leave_pending} testid="hr2-tile-leave-pending" />
      </div>
      {a && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Compliance Open ({a.total_open})</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
              {a.cards.map((c) => (
                <div key={c.key}
                     className={`border rounded p-2 text-xs ${SEVERITY_TONE[c.severity]}`}
                     data-testid={`hr2-alert-${c.key}`}>
                  <div className="font-medium truncate">{c.label}</div>
                  <div className="text-lg font-semibold mt-0.5">{c.count}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─────────── SHIFTS ───────────
function ShiftsView() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({});
  const [open, setOpen] = useState(false);
  const load = async () => {
    try { setRows((await api.get("/hr2/shifts")).data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      await api.post("/hr2/shifts", {
        code: form.code, name: form.name,
        start_time: form.start_time, end_time: form.end_time,
        break_minutes: parseFloat(form.break_minutes || 0),
        standard_hours: parseFloat(form.standard_hours || 8),
        overtime_after: parseFloat(form.overtime_after || form.standard_hours || 8),
        night_shift: !!form.night_shift,
        active: true,
        project_code: form.project_code || null,
        employee_type: form.employee_type || "all",
      });
      toast.success("Shift created");
      setOpen(false); setForm({}); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const seed = async () => {
    try {
      const r = await api.post("/hr2/shifts/seed-defaults");
      toast.success(`Seeded ${r.data.added} default shifts`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm flex items-center gap-2"><Clock className="h-4 w-4" /> Shift Master ({rows.length})</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={seed} data-testid="hr2-shift-seed">Seed Defaults</Button>
          <Button size="sm" onClick={() => setOpen(true)} data-testid="hr2-shift-new">
            <Plus className="h-4 w-4 mr-1" /> New Shift
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead><TableHead>Name</TableHead>
              <TableHead>Start</TableHead><TableHead>End</TableHead>
              <TableHead>Break (m)</TableHead><TableHead>Std Hrs</TableHead>
              <TableHead>OT After</TableHead><TableHead>Night</TableHead>
              <TableHead>Active</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`shift-row-${r.code}`}>
                <TableCell className="font-mono">{r.code}</TableCell>
                <TableCell>{r.name}</TableCell>
                <TableCell>{r.start_time}</TableCell>
                <TableCell>{r.end_time}</TableCell>
                <TableCell>{r.break_minutes}</TableCell>
                <TableCell>{r.standard_hours}</TableCell>
                <TableCell>{r.overtime_after}</TableCell>
                <TableCell>{r.night_shift ? "Yes" : "No"}</TableCell>
                <TableCell>{r.active ? "Yes" : "No"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Shift</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Code"><Input value={form.code || ""} onChange={e => setForm({ ...form, code: e.target.value })} data-testid="shift-code-input" /></Field>
            <Field label="Name"><Input value={form.name || ""} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="shift-name-input" /></Field>
            <Field label="Start Time (HH:MM)"><Input value={form.start_time || ""} onChange={e => setForm({ ...form, start_time: e.target.value })} data-testid="shift-start-input" /></Field>
            <Field label="End Time (HH:MM)"><Input value={form.end_time || ""} onChange={e => setForm({ ...form, end_time: e.target.value })} data-testid="shift-end-input" /></Field>
            <Field label="Break (minutes)"><Input type="number" value={form.break_minutes || ""} onChange={e => setForm({ ...form, break_minutes: e.target.value })} /></Field>
            <Field label="Standard Hours"><Input type="number" value={form.standard_hours || ""} onChange={e => setForm({ ...form, standard_hours: e.target.value })} /></Field>
            <Field label="OT Starts After (h)"><Input type="number" value={form.overtime_after || ""} onChange={e => setForm({ ...form, overtime_after: e.target.value })} /></Field>
            <Field label="Night Shift?">
              <Select value={String(form.night_shift || false)} onValueChange={v => setForm({ ...form, night_shift: v === "true" })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="false">No</SelectItem>
                  <SelectItem value="true">Yes</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Project Code (optional)"><ProjectSelect label={undefined} value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} /></Field>
            <Field label="Employee Type">
              <Select value={form.employee_type || "all"} onValueChange={v => setForm({ ...form, employee_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="office_staff">Office Staff</SelectItem>
                  <SelectItem value="site_staff">Site Staff</SelectItem>
                  <SelectItem value="worker">Worker</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="shift-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

const Field = ({ label, children }) => (
  <div className="space-y-1">
    <Label className="text-xs">{label}</Label>
    {children}
  </div>
);

// ─────────── ATTENDANCE REGISTER + APPROVAL + LOCK ───────────
function AttendanceView() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ from_date: today(), to_date: today(), project_code: "", approval_status: "" });
  const [shifts, setShifts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ status: "present", source: "manual", date: today(), shift_code: "GEN" });
  const [selected, setSelected] = useState(new Set());
  const [lockOpen, setLockOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [lockForm, setLockForm] = useState({ month: monthIso(), project_code: "", reason: "" });
  const [locks, setLocks] = useState([]);

  const load = async () => {
    const params = Object.fromEntries(Object.entries(filter).filter(([_, v]) => v));
    try {
      const r = await api.get("/hr2/attendance/register", { params });
      setRows(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  useEffect(() => { (async () => {
    try {
      const r = await api.get("/hr2/shifts");
      setShifts(r.data || []);
      const lr = await api.get("/hr2/attendance/locks");
      setLocks(lr.data || []);
    } catch { /* silent */ }
  })(); }, []);

  const mark = async () => {
    try {
      await api.post("/hr2/attendance", form);
      toast.success("Attendance marked");
      setOpen(false); setForm({ status: "present", source: "manual", date: today(), shift_code: "GEN" });
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decide = async (decision) => {
    const ids = [...selected];
    if (!ids.length) { toast.warning("Select rows first"); return; }
    try {
      await api.post("/hr2/attendance/approve", { ids, decision, remarks: "" });
      toast.success(`${decision}d ${ids.length} record(s)`);
      setSelected(new Set()); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const lock = async () => {
    try {
      await api.post("/hr2/attendance/lock", lockForm);
      toast.success(`Locked ${lockForm.month}`);
      setLockOpen(false);
      const lr = await api.get("/hr2/attendance/locks");
      setLocks(lr.data || []);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const unlock = async (l) => {
    try {
      await api.post("/hr2/attendance/unlock", { project_code: l.project_code, month: l.month });
      toast.success(`Unlocked ${l.month}`);
      const lr = await api.get("/hr2/attendance/locks");
      setLocks(lr.data || []);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const toggleSel = (id) => {
    const ns = new Set(selected); if (ns.has(id)) ns.delete(id); else ns.add(id); setSelected(ns);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm flex items-center gap-2"><ClipboardCheck className="h-4 w-4" /> Attendance Register</CardTitle>
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="outline" onClick={() => setBulkOpen(true)} data-testid="att-bulk-btn">
              Monthly Bulk Upload
            </Button>
            <Button size="sm" variant="outline" onClick={() => setLockOpen(true)} data-testid="att-lock-btn">
              <Lock className="h-4 w-4 mr-1" /> Lock Month
            </Button>
            <Button size="sm" onClick={() => setOpen(true)} data-testid="att-mark-btn">
              <Plus className="h-4 w-4 mr-1" /> Mark Attendance
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 flex-wrap items-end mb-3">
            <Field label="From"><Input type="date" value={filter.from_date} onChange={e => setFilter({ ...filter, from_date: e.target.value })} className="w-36" /></Field>
            <Field label="To"><Input type="date" value={filter.to_date} onChange={e => setFilter({ ...filter, to_date: e.target.value })} className="w-36" /></Field>
            <Field label="Project"><ProjectSelect label={undefined} includeBlank value={filter.project_code} onChange={v => setFilter({ ...filter, project_code: v })} className="w-32" /></Field>
            <Field label="Approval">
              <Select value={filter.approval_status || "all"} onValueChange={v => setFilter({ ...filter, approval_status: v === "all" ? "" : v })}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Button size="sm" variant="outline" onClick={load} data-testid="att-filter-apply"><Filter className="h-4 w-4 mr-1" /> Apply</Button>
            <div className="flex gap-2 ml-auto">
              <Button size="sm" variant="outline" onClick={() => decide("approve")} disabled={!selected.size} data-testid="att-approve-btn">
                <Check className="h-4 w-4 mr-1" /> Approve ({selected.size})
              </Button>
              <Button size="sm" variant="outline" onClick={() => decide("reject")} disabled={!selected.size} data-testid="att-reject-btn">
                <X className="h-4 w-4 mr-1" /> Reject
              </Button>
            </div>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input type="checkbox" title="Select all pending"
                    checked={rows.some(r => r.approval_status === "pending") && rows.filter(r => r.approval_status === "pending").every(r => selected.has(r.id))}
                    onChange={(e) => {
                      const pend = rows.filter(r => r.approval_status === "pending").map(r => r.id);
                      setSelected(e.target.checked ? new Set([...selected, ...pend]) : new Set([...selected].filter(id => !pend.includes(id))));
                    }}
                    data-testid="att-select-all" />
                </TableHead>
                <TableHead>Date</TableHead><TableHead>Employee</TableHead>
                <TableHead>Project</TableHead><TableHead>Shift</TableHead>
                <TableHead>In</TableHead><TableHead>Out</TableHead>
                <TableHead>Hours</TableHead><TableHead>OT</TableHead>
                <TableHead>Status</TableHead><TableHead>Approval</TableHead>
                <TableHead>Lock</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow><TableCell colSpan={12} className="text-center text-sm text-muted-foreground py-6">No records</TableCell></TableRow>
              )}
              {rows.map(r => (
                <TableRow key={r.id} data-testid={`att-row-${r.id}`}>
                  <TableCell>
                    {r.approval_status === "pending" && (
                      <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSel(r.id)} data-testid={`att-sel-${r.id}`} />
                    )}
                  </TableCell>
                  <TableCell>{r.date}</TableCell>
                  <TableCell>{r.employee_name}</TableCell>
                  <TableCell className="font-mono text-xs">{r.project_code || "—"}</TableCell>
                  <TableCell>{r.shift_code || "—"}</TableCell>
                  <TableCell>{r.in_time || "—"}</TableCell>
                  <TableCell>{r.out_time || "—"}</TableCell>
                  <TableCell>{r.total_hours ?? r.hours ?? 0}</TableCell>
                  <TableCell>{r.overtime_hours || 0}</TableCell>
                  <TableCell><StatusBadge value={r.status} map={ATT_STATUS_TONE} /></TableCell>
                  <TableCell><StatusBadge value={r.approval_status} map={OT_STATUS_TONE} /></TableCell>
                  <TableCell>{r.locked ? <Lock className="h-3.5 w-3.5 text-rose-600" /> : <Unlock className="h-3.5 w-3.5 text-emerald-600" />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {locks.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Lock className="h-4 w-4" /> Attendance Locks</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Month</TableHead><TableHead>Project</TableHead>
                <TableHead>Locked By</TableHead><TableHead>At</TableHead>
                <TableHead>Reason</TableHead><TableHead></TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {locks.map(l => (
                  <TableRow key={l.id} data-testid={`lock-row-${l.id}`}>
                    <TableCell className="font-mono">{l.month}</TableCell>
                    <TableCell>{l.project_code || "ALL"}</TableCell>
                    <TableCell>{l.locked_by_name}</TableCell>
                    <TableCell className="text-xs">{l.locked_at?.slice(0, 16)}</TableCell>
                    <TableCell>{l.reason || "—"}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => unlock(l)} data-testid={`unlock-${l.id}`}>
                        <Unlock className="h-3.5 w-3.5 mr-1" /> Unlock
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Mark Attendance</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date"><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} data-testid="mark-date" /></Field>
            <Field label="Employee Name"><Input value={form.employee_name || ""} onChange={e => setForm({ ...form, employee_name: e.target.value })} data-testid="mark-emp-name" /></Field>
            <Field label="Employee Code"><Input value={form.employee_code || ""} onChange={e => setForm({ ...form, employee_code: e.target.value })} /></Field>
            <Field label="Project Code"><ProjectSelect label={undefined} value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} testid="mark-project" /></Field>
            <Field label="Department"><Input value={form.department || ""} onChange={e => setForm({ ...form, department: e.target.value })} /></Field>
            <Field label="Designation / Skill"><Input value={form.designation || ""} onChange={e => setForm({ ...form, designation: e.target.value })} /></Field>
            <Field label="Shift">
              <Select value={form.shift_code || "GEN"} onValueChange={v => setForm({ ...form, shift_code: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {shifts.map(s => <SelectItem key={s.id} value={s.code}>{s.code} — {s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Status">
              <Select value={form.status} onValueChange={v => setForm({ ...form, status: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["present", "absent", "half_day", "leave", "weekly_off", "holiday", "on_duty"].map(s =>
                    <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="In Time (HH:MM)"><Input value={form.in_time || ""} onChange={e => setForm({ ...form, in_time: e.target.value })} data-testid="mark-in" /></Field>
            <Field label="Out Time (HH:MM)"><Input value={form.out_time || ""} onChange={e => setForm({ ...form, out_time: e.target.value })} data-testid="mark-out" /></Field>
            <Field label="Source">
              <Select value={form.source} onValueChange={v => setForm({ ...form, source: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["manual", "mobile", "biometric", "upload", "site_entry"].map(s =>
                    <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <div className="col-span-2">
              <Label className="text-xs">Remarks</Label>
              <Textarea rows={2} value={form.remarks || ""} onChange={e => setForm({ ...form, remarks: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={mark} data-testid="mark-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={lockOpen} onOpenChange={setLockOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Lock Attendance Month</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 gap-3">
            <Field label="Month (YYYY-MM)"><Input value={lockForm.month} onChange={e => setLockForm({ ...lockForm, month: e.target.value })} data-testid="lock-month" /></Field>
            <Field label="Project Code (blank = ALL)"><ProjectSelect label={undefined} includeBlank value={lockForm.project_code} onChange={v => setLockForm({ ...lockForm, project_code: v })} /></Field>
            <Field label="Reason"><Textarea rows={2} value={lockForm.reason} onChange={e => setLockForm({ ...lockForm, reason: e.target.value })} /></Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLockOpen(false)}>Cancel</Button>
            <Button onClick={lock} data-testid="lock-save-btn">Lock</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {bulkOpen && <AttendanceBulkDialog onClose={() => setBulkOpen(false)} onDone={() => { setBulkOpen(false); load(); }} />}
    </div>
  );
}

export function AttendanceBulkDialog({ onClose, onDone }) {
  const [month, setMonth] = useState(monthIso());
  const [master, setMaster] = useState("employee");
  const [projectCode, setProjectCode] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const r = await api.get("/hr2/attendance/bulk/template", { params: { month, master }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `attendance_${master}_${month}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Template download failed"); }
  };

  const upload = async () => {
    if (!file) { toast.error("Choose the filled .xlsx first"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const qs = new URLSearchParams({ month, master, ...(projectCode ? { project_code: projectCode } : {}) });
      const r = await api.post(`/hr2/attendance/bulk/upload?${qs}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(r.data);
      const d = r.data;
      if (d.created + d.updated > 0) toast.success(`Marked ${d.created + d.updated} entr${d.created + d.updated > 1 ? "ies" : "y"} (pending approval)`);
      else toast.error("Nothing marked — check errors below");
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>Monthly Attendance — Bulk Upload</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <Field label="Month">
              <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} data-testid="att-bulk-month" />
            </Field>
            <Field label="Master">
              <select value={master} onChange={(e) => setMaster(e.target.value)}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="att-bulk-master">
                <option value="employee">Employee Master</option>
                <option value="worker">Worker / Labour Master</option>
              </select>
            </Field>
            <Field label="Project Code (optional)">
              <Input value={projectCode} onChange={(e) => setProjectCode(e.target.value)} placeholder="PRJ-…" data-testid="att-bulk-project" />
            </Field>
          </div>
          <Button variant="outline" onClick={downloadTemplate} data-testid="att-bulk-template">
            Download {master === "worker" ? "Worker" : "Employee"} template for {month}
          </Button>
          <div className="text-[11px] text-muted-foreground">
            Codes: P present · A absent · HD half-day · L leave · WO weekly off · H holiday · OD on-duty · OT like "P+2". Blank = skipped. Entries land as <b>pending approval</b>.
          </div>
          <Field label="Filled template">
            <Input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="att-bulk-file" />
          </Field>
          {result && (
            <div className="border rounded-sm p-3 text-sm bg-slate-50 space-y-1" data-testid="att-bulk-result">
              <div>✓ Created: <b>{result.created}</b> · Updated: <b>{result.updated}</b> · Blank skipped: {result.skipped_blank} · Errors: {result.error_count}</div>
              {(result.errors || []).slice(0, 8).map((e, i) => <div key={i} className="text-xs text-red-600">Row {e.row}: {e.error}</div>)}
              {result.error_count > 8 && <div className="text-xs text-slate-500">…and {result.error_count - 8} more</div>}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => ((result?.created || 0) + (result?.updated || 0) > 0 ? onDone() : onClose())}>
            {(result?.created || 0) + (result?.updated || 0) > 0 ? "Done" : "Close"}
          </Button>
          <Button onClick={upload} disabled={busy || !file} data-testid="att-bulk-upload">
            {busy ? "Uploading…" : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────── MONTHLY SUMMARY ───────────
function MonthlySummaryView() {
  const [month, setMonth] = useState(monthIso());
  const [project, setProject] = useState("");
  const [data, setData] = useState(null);

  const load = async () => {
    try {
      const params = { month };
      if (project) params.project_code = project;
      const r = await api.get("/hr2/attendance/monthly-summary", { params });
      setData(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 flex-wrap">
        <CardTitle className="text-sm flex items-center gap-2"><Calendar className="h-4 w-4" /> Monthly Summary</CardTitle>
        <div className="flex gap-2">
          <Input value={month} onChange={e => setMonth(e.target.value)} className="w-32" placeholder="YYYY-MM" data-testid="month-input" />
          <ProjectSelect label={undefined} includeBlank value={project} onChange={v => setProject(v)} className="w-32" />
          <Button size="sm" onClick={load} data-testid="month-apply"><RefreshCw className="h-4 w-4 mr-1" /> Load</Button>
        </div>
      </CardHeader>
      <CardContent>
        {!data?.rows?.length && <div className="text-sm text-muted-foreground py-4 text-center">No data for {month}</div>}
        {!!data?.rows?.length && (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Employee</TableHead><TableHead>P</TableHead><TableHead>A</TableHead>
              <TableHead>L</TableHead><TableHead>HD</TableHead><TableHead>WO</TableHead>
              <TableHead>HOL</TableHead><TableHead>OD</TableHead>
              <TableHead>Hours</TableHead><TableHead>OT</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.rows.map((r, i) => (
                <TableRow key={r.employee_id || `${r.employee_name}-${i}`} data-testid={`summary-row-${i}`}>
                  <TableCell>{r.employee_name || "—"}</TableCell>
                  <TableCell>{r.present}</TableCell>
                  <TableCell>{r.absent}</TableCell>
                  <TableCell>{r.leave}</TableCell>
                  <TableCell>{r.half_day}</TableCell>
                  <TableCell>{r.weekly_off}</TableCell>
                  <TableCell>{r.holiday}</TableCell>
                  <TableCell>{r.on_duty}</TableCell>
                  <TableCell>{r.total_hours?.toFixed?.(1) || 0}</TableCell>
                  <TableCell>{r.overtime_hours?.toFixed?.(1) || 0}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────── OVERTIME ───────────
function OvertimeView() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ overtime_date: today(), normal_hours: 8, overtime_hours: 0, overtime_rate: 0 });
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const load = async () => {
    try {
      const params = filter && filter !== "all" ? { status: filter } : {};
      const r = await api.get("/hr2/overtime/register", { params });
      setRows(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filter]);

  const save = async () => {
    try {
      await api.post("/hr2/overtime", {
        employee_name: form.employee_name,
        employee_code: form.employee_code,
        project_code: form.project_code,
        site_location: form.site_location,
        overtime_date: form.overtime_date,
        normal_hours: parseFloat(form.normal_hours || 8),
        overtime_hours: parseFloat(form.overtime_hours || 0),
        overtime_rate: parseFloat(form.overtime_rate || 0),
        reason: form.reason || "",
      });
      toast.success("OT request created");
      setOpen(false); setForm({ overtime_date: today(), normal_hours: 8, overtime_hours: 0, overtime_rate: 0 });
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decide = async (id, action) => {
    try {
      await api.post(`/hr2/overtime/${id}/${action}`, { remarks: "" });
      toast.success(`OT ${action}`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Clock className="h-4 w-4" /> Overtime Register</CardTitle>
        <div className="flex gap-2">
          <Select value={filter || "all"} onValueChange={v => setFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-36"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="hr_pending">HR Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" onClick={() => setOpen(true)} data-testid="ot-new-btn">
            <Plus className="h-4 w-4 mr-1" /> New OT
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>OT No</TableHead><TableHead>Date</TableHead>
            <TableHead>Employee</TableHead><TableHead>Project</TableHead>
            <TableHead>Hours</TableHead><TableHead>Rate</TableHead>
            <TableHead>Amount</TableHead><TableHead>PM</TableHead>
            <TableHead>HR</TableHead><TableHead>Status</TableHead>
            <TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={11} className="text-center text-sm text-muted-foreground py-6">No records</TableCell></TableRow>
            )}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`ot-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.request_no || "—"}</TableCell>
                <TableCell>{r.overtime_date || r.date}</TableCell>
                <TableCell>{r.employee_name || r.employee}</TableCell>
                <TableCell className="font-mono text-xs">{r.project_code || r.project || "—"}</TableCell>
                <TableCell>{r.overtime_hours || r.hours}</TableCell>
                <TableCell>{r.overtime_rate || r.rate || 0}</TableCell>
                <TableCell>₹{(r.overtime_amount || 0).toLocaleString("en-IN")}</TableCell>
                <TableCell>{r.pm_status === "approved" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : "—"}</TableCell>
                <TableCell>{r.hr_status === "approved" ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : "—"}</TableCell>
                <TableCell><StatusBadge value={r.status} map={OT_STATUS_TONE} /></TableCell>
                <TableCell className="flex gap-1">
                  {r.pm_status !== "approved" && r.status !== "rejected" && (
                    <Button size="sm" variant="outline" onClick={() => decide(r.id, "approve-pm")} data-testid={`ot-approve-pm-${r.id}`}>PM ✓</Button>
                  )}
                  {r.pm_status === "approved" && r.hr_status !== "approved" && r.status !== "rejected" && (
                    <Button size="sm" variant="outline" onClick={() => decide(r.id, "approve-hr")} data-testid={`ot-approve-hr-${r.id}`}>HR ✓</Button>
                  )}
                  {r.status !== "approved" && r.status !== "rejected" && (
                    <Button size="sm" variant="outline" onClick={() => decide(r.id, "reject")} data-testid={`ot-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>New Overtime Request</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Employee Name"><Input value={form.employee_name || ""} onChange={e => setForm({ ...form, employee_name: e.target.value })} data-testid="ot-emp-name" /></Field>
            <Field label="Employee Code"><Input value={form.employee_code || ""} onChange={e => setForm({ ...form, employee_code: e.target.value })} /></Field>
            <Field label="Project Code"><ProjectSelect label={undefined} value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} testid="ot-project" /></Field>
            <Field label="Site Location"><Input value={form.site_location || ""} onChange={e => setForm({ ...form, site_location: e.target.value })} /></Field>
            <Field label="Date"><Input type="date" value={form.overtime_date} onChange={e => setForm({ ...form, overtime_date: e.target.value })} /></Field>
            <Field label="Normal Hours"><Input type="number" value={form.normal_hours} onChange={e => setForm({ ...form, normal_hours: e.target.value })} /></Field>
            <Field label="Overtime Hours"><Input type="number" value={form.overtime_hours} onChange={e => setForm({ ...form, overtime_hours: e.target.value })} data-testid="ot-hours" /></Field>
            <Field label="OT Rate / Hour (INR)"><Input type="number" value={form.overtime_rate} onChange={e => setForm({ ...form, overtime_rate: e.target.value })} data-testid="ot-rate" /></Field>
            <div className="col-span-2">
              <Label className="text-xs">Reason</Label>
              <Textarea rows={2} value={form.reason || ""} onChange={e => setForm({ ...form, reason: e.target.value })} data-testid="ot-reason" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="ot-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── COMPLIANCE ALERTS (detailed view) ───────────
function ComplianceView() {
  const [data, setData] = useState(null);
  const [med, setMed] = useState(null);
  const [train, setTrain] = useState(null);
  const [days, setDays] = useState(30);

  const load = async () => {
    try {
      const [r1, r2, r3] = await Promise.all([
        api.get(`/hr2/compliance-alerts?days=${days}`),
        api.get(`/hr2/medical-fitness-expiry?days=${days}`),
        api.get(`/hr2/training-expiry?days=${days}`),
      ]);
      setData(r1.data); setMed(r2.data); setTrain(r3.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Compliance Alerts ({data.total_open} open)</CardTitle>
          <div className="flex gap-2">
            <Input type="number" className="w-24" value={days} onChange={e => setDays(parseInt(e.target.value) || 30)} data-testid="compliance-days" />
            <Button size="sm" onClick={load} data-testid="compliance-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {data.cards.map(c => (
              <div key={c.key} className={`border rounded p-3 ${SEVERITY_TONE[c.severity]}`} data-testid={`compliance-card-${c.key}`}>
                <div className="text-xs font-medium">{c.label}</div>
                <div className="text-2xl font-semibold mt-1">{c.count}</div>
                <div className="text-[10px] uppercase tracking-wide opacity-75">{c.severity}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Medical Fitness — Expired ({med?.expired?.length || 0}) / Expiring ({med?.expiring?.length || 0})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Person</TableHead><TableHead>Test Date</TableHead>
              <TableHead>Status</TableHead><TableHead>Valid Till</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(med?.expired || []).slice(0, 30).map((r, i) => (
                <TableRow key={r.id || i} data-testid={`med-expired-${i}`}>
                  <TableCell>{r.person_name}</TableCell>
                  <TableCell>{r.test_date}</TableCell>
                  <TableCell><Badge className="bg-rose-100 text-rose-900 border-rose-300">expired</Badge></TableCell>
                  <TableCell>{r.valid_till}</TableCell>
                </TableRow>
              ))}
              {(med?.expiring || []).slice(0, 30).map((r, i) => (
                <TableRow key={`exp-${r.id || i}`} data-testid={`med-expiring-${i}`}>
                  <TableCell>{r.person_name}</TableCell>
                  <TableCell>{r.test_date}</TableCell>
                  <TableCell><Badge className="bg-amber-100 text-amber-900 border-amber-300">expiring</Badge></TableCell>
                  <TableCell>{r.valid_till}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Training / Certification — Expired ({train?.expired?.length || 0}) / Expiring ({train?.expiring?.length || 0})</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Employee</TableHead><TableHead>Cert</TableHead>
              <TableHead>Project</TableHead><TableHead>Expiry</TableHead><TableHead>Days Left</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(train?.expired || []).slice(0, 30).map((r, i) => (
                <TableRow key={`te-${i}`} data-testid={`train-expired-${i}`}>
                  <TableCell>{r.employee_name}</TableCell>
                  <TableCell>{r.certification}</TableCell>
                  <TableCell className="text-xs font-mono">{r.project_code || "—"}</TableCell>
                  <TableCell>{r.expiry_date}</TableCell>
                  <TableCell><Badge className="bg-rose-100 text-rose-900 border-rose-300">expired</Badge></TableCell>
                </TableRow>
              ))}
              {(train?.expiring || []).slice(0, 30).map((r, i) => (
                <TableRow key={`tx-${i}`} data-testid={`train-expiring-${i}`}>
                  <TableCell>{r.employee_name}</TableCell>
                  <TableCell>{r.certification}</TableCell>
                  <TableCell className="text-xs font-mono">{r.project_code || "—"}</TableCell>
                  <TableCell>{r.expiry_date}</TableCell>
                  <TableCell>{r.days_left}d</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ─────────── SAFETY READINESS ───────────
function SafetyReadinessView() {
  const [data, setData] = useState(null);
  const [project, setProject] = useState("");
  const load = async () => {
    try {
      const params = project ? { project_code: project } : {};
      const r = await api.get("/hr2/safety-readiness", { params });
      setData(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Safety Readiness</CardTitle>
          <div className="flex gap-2">
            <ProjectSelect label={undefined} includeBlank value={project} onChange={v => setProject(v)} className="w-40" testid="sr-project" />
            <Button size="sm" onClick={load} data-testid="sr-apply"><Filter className="h-4 w-4 mr-1" /> Apply</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <Card className="border-emerald-300" data-testid="sr-ready-tile">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">Deployment-Ready</div>
                <div className="text-3xl font-semibold text-emerald-700 mt-1">{data.ready_count}</div>
              </CardContent>
            </Card>
            <Card className="border-rose-300" data-testid="sr-blocked-tile">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">Blocked / Pending</div>
                <div className="text-3xl font-semibold text-rose-700 mt-1">{data.blocked_count}</div>
              </CardContent>
            </Card>
          </div>

          <h4 className="text-sm font-semibold mt-4 mb-2">Blocked Employees</h4>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Name</TableHead><TableHead>Role</TableHead>
              <TableHead>Project</TableHead><TableHead>Safety</TableHead>
              <TableHead>Medical</TableHead><TableHead>Certs</TableHead>
              <TableHead>PPE</TableHead><TableHead>Reasons</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.blocked.slice(0, 50).map((p, i) => (
                <TableRow key={`b-${p.person_id || i}`} data-testid={`sr-blocked-${i}`}>
                  <TableCell>{p.person_name}</TableCell>
                  <TableCell>{p.designation || p.kind}</TableCell>
                  <TableCell className="text-xs font-mono">{p.project_code || "—"}</TableCell>
                  <TableCell>{p.safety_induction ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <X className="h-3.5 w-3.5 text-rose-600" />}</TableCell>
                  <TableCell>{p.medical_fitness ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <X className="h-3.5 w-3.5 text-rose-600" />}</TableCell>
                  <TableCell>{p.certification_ok ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <X className="h-3.5 w-3.5 text-rose-600" />}</TableCell>
                  <TableCell>{p.ppe_issued ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <X className="h-3.5 w-3.5 text-amber-600" />}</TableCell>
                  <TableCell className="text-xs">{(p.blocking_reasons || []).join("; ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ─────────── PARENT HUB ───────────
export default function HrPhase2() {
  const [tab, setTab] = useState("dashboard");
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Activity className="h-5 w-5" /> HR Operations — Attendance, Shifts, Overtime, Compliance
          </h1>
          <p className="text-sm text-muted-foreground">Phase 2 — daily attendance workflow, multi-step OT approval and compliance/safety readiness</p>
        </div>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="dashboard" data-testid="hr2-tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="attendance" data-testid="hr2-tab-attendance">Attendance</TabsTrigger>
          <TabsTrigger value="summary" data-testid="hr2-tab-summary">Monthly Summary</TabsTrigger>
          <TabsTrigger value="shifts" data-testid="hr2-tab-shifts">Shifts</TabsTrigger>
          <TabsTrigger value="overtime" data-testid="hr2-tab-overtime">Overtime</TabsTrigger>
          <TabsTrigger value="compliance" data-testid="hr2-tab-compliance">Compliance</TabsTrigger>
          <TabsTrigger value="readiness" data-testid="hr2-tab-readiness">Safety Readiness</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><DashboardView /></TabsContent>
        <TabsContent value="attendance"><AttendanceView /></TabsContent>
        <TabsContent value="summary"><MonthlySummaryView /></TabsContent>
        <TabsContent value="shifts"><ShiftsView /></TabsContent>
        <TabsContent value="overtime"><OvertimeView /></TabsContent>
        <TabsContent value="compliance"><ComplianceView /></TabsContent>
        <TabsContent value="readiness"><SafetyReadinessView /></TabsContent>
      </Tabs>
    </div>
  );
}
