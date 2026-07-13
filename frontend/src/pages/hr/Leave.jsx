import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays, Plus, Check, X as XIcon, RotateCcw, Filter, Search,
  AlertCircle, ChevronLeft, ChevronRight, Briefcase, Inbox,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { api, apiErrorMessage, stripEmpty } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STATUS_TONE = {
  pending: "bg-amber-100 text-amber-900 border-amber-300",
  approved: "bg-emerald-100 text-emerald-900 border-emerald-300",
  rejected: "bg-red-100 text-red-900 border-red-300",
  cancelled: "bg-secondary text-muted-foreground border-border",
};

const todayIso = () => new Date().toISOString().slice(0, 10);
const currentMonth = () => new Date().toISOString().slice(0, 7);

export default function Leave() {
  const { user, can } = useAuth();
  const [tab, setTab] = useState("apply");
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [mine, setMine] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [balances, setBalances] = useState([]);
  const [balanceEmp, setBalanceEmp] = useState("");
  const [calendar, setCalendar] = useState({ month: currentMonth(), rows: [] });

  const [applyForm, setApplyForm] = useState({
    employee_id: "", leave_type: "CL", from_date: todayIso(), to_date: todayIso(),
    half_day: false, reason: "",
  });
  const [actionDialog, setActionDialog] = useState(null);  // {row, mode: approve|reject}
  const [remarks, setRemarks] = useState("");

  const canApprove = can?.("hr_leave", "write");

  const load = async () => {
    try {
      const [lt, emps, m, b] = await Promise.all([
        api.get("/hr/leave-types"),
        api.get("/employees"),
        api.get("/hr/leave-applications/mine"),
        api.get("/employees"),
      ]);
      setLeaveTypes(lt.data || []);
      setEmployees(emps.data || []);
      setMine(m.data || []);
      // Default applyForm.employee_id to self
      const selfEmp = (emps.data || []).find((e) => e.email === user?.email);
      if (selfEmp) setApplyForm((f) => ({ ...f, employee_id: f.employee_id || selfEmp.id }));
      if (canApprove) {
        const inboxResp = await api.get("/hr/leave-applications?status=pending");
        setInbox(inboxResp.data || []);
      }
      // Self balances
      if (selfEmp) {
        setBalanceEmp(selfEmp.id);
        const r = await api.get(`/hr/leave-balances/${selfEmp.id}`);
        setBalances(r.data.balances || []);
      } else if ((emps.data || []).length) {
        // Admin/HR with no self-employee — fall back to first active employee
        const fallback = (emps.data || []).find((e) => e.status === "active") || emps.data[0];
        setBalanceEmp(fallback.id);
        const r = await api.get(`/hr/leave-balances/${fallback.id}`);
        setBalances(r.data.balances || []);
      }
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };

  const loadBalancesFor = async (eid) => {
    setBalanceEmp(eid);
    if (!eid) { setBalances([]); return; }
    try {
      const r = await api.get(`/hr/leave-balances/${eid}`);
      setBalances(r.data.balances || []);
    } catch (e) { toast.error(apiErrorMessage(e, "Balances load failed")); }
  };

  const loadCalendar = async (month) => {
    try {
      const r = await api.get(`/hr/leave-calendar?month=${month}`);
      setCalendar({ month: r.data.month, rows: r.data.rows || [] });
    } catch (e) { toast.error(apiErrorMessage(e, "Calendar failed")); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  useEffect(() => {
    if (tab === "calendar") loadCalendar(calendar.month);
    // eslint-disable-next-line
  }, [tab]);

  const apply = async () => {
    if (!applyForm.employee_id) { toast.error("Pick employee"); return; }
    try {
      await api.post("/hr/leave-applications", applyForm);
      toast.success("Leave applied — awaiting approval");
      setApplyForm({ ...applyForm, reason: "" });
      load();
    } catch (e) { toast.error(apiErrorMessage(e, "Apply failed")); }
  };

  const decide = async () => {
    if (!actionDialog) return;
    try {
      await api.post(`/hr/leave-applications/${actionDialog.row.id}/${actionDialog.mode}`, { remarks });
      toast.success(`Leave ${actionDialog.mode}d`);
      setActionDialog(null); setRemarks("");
      load();
    } catch (e) { toast.error(apiErrorMessage(e, "Action failed")); }
  };

  const cancel = async (id) => {
    if (!window.confirm("Cancel this leave?")) return;
    try {
      await api.post(`/hr/leave-applications/${id}/cancel`);
      toast.success("Cancelled"); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Cancel failed")); }
  };

  const shiftMonth = (delta) => {
    const [y, m] = calendar.month.split("-").map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    const next = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    setCalendar((c) => ({ ...c, month: next }));
    loadCalendar(next);
  };

  return (
    <div className="space-y-6" data-testid="hr-leave-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <CalendarDays className="h-3 w-3" /> Human Resources
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Leave Management</h1>
        <p className="text-sm text-muted-foreground mt-1">Apply, track balances, approve as a manager, and view team availability on the calendar.</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="apply" data-testid="leave-tab-apply"><Plus className="h-3.5 w-3.5 mr-1" />Apply</TabsTrigger>
          <TabsTrigger value="mine" data-testid="leave-tab-mine"><Briefcase className="h-3.5 w-3.5 mr-1" />My Leaves ({mine.length})</TabsTrigger>
          <TabsTrigger value="balances" data-testid="leave-tab-balances"><AlertCircle className="h-3.5 w-3.5 mr-1" />Balances</TabsTrigger>
          {canApprove && <TabsTrigger value="inbox" data-testid="leave-tab-inbox"><Inbox className="h-3.5 w-3.5 mr-1" />Approval Inbox ({inbox.length})</TabsTrigger>}
          <TabsTrigger value="calendar" data-testid="leave-tab-calendar"><CalendarDays className="h-3.5 w-3.5 mr-1" />Calendar</TabsTrigger>
        </TabsList>

        {/* APPLY */}
        <TabsContent value="apply" className="mt-4">
          <div className="bg-card border border-border rounded-sm p-5 max-w-2xl">
            <div className="font-display font-bold mb-3">New Leave Application</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Label className="text-[10px] uppercase tracking-wider">Employee</Label>
                <Select value={applyForm.employee_id} onValueChange={(v) => setApplyForm({ ...applyForm, employee_id: v })}>
                  <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="apply-employee"><SelectValue placeholder="Pick employee…" /></SelectTrigger>
                  <SelectContent>
                    {employees.map((e) => <SelectItem key={e.id} value={e.id}>{e.name} ({e.emp_code})</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Leave Type</Label>
                <Select value={applyForm.leave_type} onValueChange={(v) => setApplyForm({ ...applyForm, leave_type: v })}>
                  <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="apply-type"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {leaveTypes.map((lt) => <SelectItem key={lt.id} value={lt.code}>{lt.code} — {lt.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Half Day?</Label>
                <Select value={applyForm.half_day ? "yes" : "no"} onValueChange={(v) => setApplyForm({ ...applyForm, half_day: v === "yes" })}>
                  <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="apply-half"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="no">Full Day</SelectItem>
                    <SelectItem value="yes">Half Day</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Field label="From" type="date" value={applyForm.from_date} onChange={(v) => setApplyForm({ ...applyForm, from_date: v })} testid="apply-from" />
              <Field label="To" type="date" value={applyForm.to_date} onChange={(v) => setApplyForm({ ...applyForm, to_date: v })} testid="apply-to" />
              <div className="col-span-2">
                <Label className="text-[10px] uppercase tracking-wider">Reason</Label>
                <Textarea value={applyForm.reason} onChange={(e) => setApplyForm({ ...applyForm, reason: e.target.value })} className="rounded-sm mt-1 min-h-[80px]" placeholder="Brief reason…" data-testid="apply-reason" />
              </div>
            </div>
            <Button className="mt-4 rounded-sm" onClick={apply} data-testid="apply-submit">Apply for Leave</Button>
          </div>
        </TabsContent>

        {/* MY LEAVES */}
        <TabsContent value="mine" className="mt-4">
          <LeavesTable rows={mine} onCancel={cancel} showActions data-testid-prefix="mine" />
        </TabsContent>

        {/* BALANCES */}
        <TabsContent value="balances" className="mt-4 space-y-3">
          <div className="bg-card border border-border rounded-sm p-3 flex flex-wrap items-center gap-2">
            <Label className="text-[10px] uppercase tracking-wider">Employee</Label>
            <Select value={balanceEmp} onValueChange={loadBalancesFor}>
              <SelectTrigger className="h-9 w-72 rounded-sm" data-testid="balance-employee-picker">
                <SelectValue placeholder="Pick employee…" />
              </SelectTrigger>
              <SelectContent>
                {employees.map((e) => (
                  <SelectItem key={e.id} value={e.id}>{e.name} ({e.emp_code}) · {e.department || "—"}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-[11px] text-muted-foreground">
              {balances.length} type(s) for year {new Date().getFullYear()}
            </span>
          </div>
          <div className="bg-card border border-border rounded-sm overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Type</TableHead><TableHead className="text-right">Granted</TableHead>
                <TableHead className="text-right">Used</TableHead><TableHead className="text-right">Balance</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {balances.length === 0 && <TableRow><TableCell colSpan={4} className="text-center py-10 text-muted-foreground">No balances yet for this employee.</TableCell></TableRow>}
                {balances.map((b) => (
                  <TableRow key={b.id} data-testid={`balance-row-${b.leave_type}`}>
                    <TableCell>
                      <Badge variant="outline" className="rounded-sm font-mono">{b.leave_type}</Badge>
                      <span className="ml-2">{b.leave_type_label}</span>
                    </TableCell>
                    <TableCell className="text-right tabular">{b.granted}</TableCell>
                    <TableCell className="text-right tabular">{b.used}</TableCell>
                    <TableCell className="text-right tabular font-bold">{b.balance}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* INBOX */}
        {canApprove && (
          <TabsContent value="inbox" className="mt-4">
            <LeavesTable
              rows={inbox}
              showApproval
              onApprove={(row) => { setActionDialog({ row, mode: "approve" }); setRemarks(""); }}
              onReject={(row) => { setActionDialog({ row, mode: "reject" }); setRemarks(""); }}
              data-testid-prefix="inbox"
            />
          </TabsContent>
        )}

        {/* CALENDAR */}
        <TabsContent value="calendar" className="mt-4">
          <CalendarView month={calendar.month} rows={calendar.rows} onShift={shiftMonth} />
        </TabsContent>
      </Tabs>

      {/* Approve/Reject dialog */}
      <Dialog open={!!actionDialog} onOpenChange={() => setActionDialog(null)}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              {actionDialog?.mode === "approve" ? <Check className="h-5 w-5 text-emerald-700" /> : <XIcon className="h-5 w-5 text-red-700" />}
              {actionDialog?.mode === "approve" ? "Approve Leave" : "Reject Leave"}
            </DialogTitle>
            <DialogDescription>
              {actionDialog?.row?.employee_name} · {actionDialog?.row?.leave_type} ({actionDialog?.row?.days} days, {actionDialog?.row?.from_date} → {actionDialog?.row?.to_date})
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Remarks (optional)</Label>
            <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} className="rounded-sm mt-1 min-h-[80px]" data-testid="leave-action-remarks" />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setActionDialog(null)}>Cancel</Button>
            <Button
              className={`rounded-sm ${actionDialog?.mode === "approve" ? "bg-emerald-700 hover:bg-emerald-800" : "bg-red-700 hover:bg-red-800"}`}
              onClick={decide}
              data-testid="leave-action-confirm"
            >
              {actionDialog?.mode === "approve" ? "Approve" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LeavesTable({ rows, onCancel, onApprove, onReject, showActions, showApproval, "data-testid-prefix": tprefix = "leave" }) {
  return (
    <div className="bg-card border border-border rounded-sm overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>From</TableHead>
            <TableHead>To</TableHead>
            <TableHead className="text-right">Days</TableHead>
            <TableHead>Reason</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 && <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">No applications.</TableCell></TableRow>}
          {rows.map((r) => (
            <TableRow key={r.id} data-testid={`${tprefix}-row-${r.id}`}>
              <TableCell>
                <div className="font-semibold">{r.employee_name}</div>
                <div className="text-[11px] text-muted-foreground">{r.department || "—"}</div>
              </TableCell>
              <TableCell><Badge variant="outline" className="rounded-sm font-mono">{r.leave_type}</Badge></TableCell>
              <TableCell className="text-[12px]">{r.from_date}</TableCell>
              <TableCell className="text-[12px]">{r.to_date}{r.half_day && <span className="ml-1 text-[10px] text-muted-foreground">(½)</span>}</TableCell>
              <TableCell className="text-right tabular">{r.days}</TableCell>
              <TableCell className="text-[11px] max-w-xs truncate">{r.reason || "—"}</TableCell>
              <TableCell><Badge className={`rounded-sm border ${STATUS_TONE[r.status] || ""}`}>{r.status}</Badge></TableCell>
              <TableCell className="text-right">
                {showApproval && r.status === "pending" && (
                  <div className="inline-flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm border-emerald-300 text-emerald-700" onClick={() => onApprove(r)} data-testid={`${tprefix}-approve-${r.id}`}>
                      <Check className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm border-red-300 text-red-700" onClick={() => onReject(r)} data-testid={`${tprefix}-reject-${r.id}`}>
                      <XIcon className="h-3 w-3" />
                    </Button>
                  </div>
                )}
                {showActions && (r.status === "pending" || r.status === "approved") && (
                  <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => onCancel(r.id)} data-testid={`${tprefix}-cancel-${r.id}`}>
                    <RotateCcw className="h-3 w-3 mr-1" /> Cancel
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function CalendarView({ month, rows, onShift }) {
  const [y, m] = month.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(y, m, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const byDay = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      const start = new Date(r.from_date), end = new Date(r.to_date);
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        if (d.getMonth() + 1 !== m || d.getFullYear() !== y) continue;
        const key = d.getDate();
        (map[key] ||= []).push(r);
      }
    });
    return map;
  }, [rows, m, y]);

  const monthName = first.toLocaleString("default", { month: "long", year: "numeric" });

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="p-3 border-b border-border flex items-center gap-2">
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => onShift(-1)} data-testid="cal-prev"><ChevronLeft className="h-3 w-3" /></Button>
        <div className="font-display font-bold text-sm flex-1 text-center">{monthName}</div>
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => onShift(1)} data-testid="cal-next"><ChevronRight className="h-3 w-3" /></Button>
      </div>
      <div className="grid grid-cols-7 text-[10px] uppercase tracking-wider text-muted-foreground bg-secondary/40">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => <div key={d} className="p-2 text-center font-bold">{d}</div>)}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((c, i) => (
          <div key={i} className="border-t border-l border-border last:border-r-0 min-h-[90px] p-1.5">
            {c && (
              <>
                <div className="text-xs font-bold mb-1">{c}</div>
                <div className="space-y-0.5">
                  {(byDay[c] || []).slice(0, 3).map((r) => (
                    <div key={r.id} className="text-[10px] bg-primary/10 text-primary border-l-2 border-primary px-1.5 py-0.5 truncate" title={`${r.employee_name} (${r.leave_type})`}>
                      {r.employee_name} · {r.leave_type}
                    </div>
                  ))}
                  {(byDay[c] || []).length > 3 && (
                    <div className="text-[10px] text-muted-foreground">+{byDay[c].length - 3} more</div>
                  )}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
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
