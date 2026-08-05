/**
 * Attendance Summary — interactive dashboard with month-wise P/A/HD/L/WO/OD counts,
 * late/early, OT, leave balance; group-by views; employee drill-down; print & downloads.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, Download, Printer, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { api } from "@/lib/api";

const monthIso = () => new Date().toISOString().slice(0, 7);
const CODES = ["P", "A", "HD", "L", "WO", "H", "OD"];
const CODE_TONE = {
  P: "text-emerald-700", A: "text-red-600", HD: "text-amber-600", L: "text-blue-600",
  WO: "text-slate-500", H: "text-violet-600", OD: "text-cyan-700",
};

function Kpi({ label, value, testid }) {
  return (
    <div className="bg-card border border-border rounded-sm px-4 py-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-2xl font-black font-display mt-0.5">{value}</div>
    </div>
  );
}

function GroupTable({ rows, keyName, keyLabel }) {
  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 text-xs uppercase text-slate-600">
        <tr>
          <th className="text-left px-3 py-2">{keyLabel}</th>
          {CODES.map((c) => <th key={c} className="text-right px-2 py-2">{c}</th>)}
          <th className="text-right px-2 py-2">Late</th>
          <th className="text-right px-2 py-2">Early</th>
          <th className="text-right px-2 py-2">OT hrs</th>
          <th className="text-right px-3 py-2">Entries</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && <tr><td colSpan={12} className="text-center py-8 text-slate-400">No data for these filters.</td></tr>}
        {rows.map((r) => (
          <tr key={r[keyName]} className="border-t hover:bg-slate-50">
            <td className="px-3 py-1.5 font-mono-data text-xs">{r[keyName]}</td>
            {CODES.map((c) => <td key={c} className={`text-right px-2 py-1.5 tabular ${CODE_TONE[c]}`}>{r[c] || 0}</td>)}
            <td className="text-right px-2 py-1.5 tabular">{r.late_count || 0}</td>
            <td className="text-right px-2 py-1.5 tabular">{r.early_count || 0}</td>
            <td className="text-right px-2 py-1.5 tabular">{r.ot_hours || 0}</td>
            <td className="text-right px-3 py-1.5 tabular">{r.days || 0}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DrillDown({ emp, month, onClose }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    const [y, m] = month.split("-").map(Number);
    const last = new Date(y, m, 0).getDate();
    api.get("/hr2/attendance/register", {
      params: { employee_id: emp.employee_id, from_date: `${month}-01`, to_date: `${month}-${String(last).padStart(2, "0")}`, limit: 100 },
    }).then((r) => setRows((r.data || []).sort((a, b) => (a.date < b.date ? -1 : 1)))).catch(() => {});
  }, [emp, month]);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl bg-white dark:bg-slate-900 max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{emp.employee_name} — {month}</DialogTitle>
          <DialogDescription>{emp.employee_code} · {emp.department || "—"} · Leave balance: {emp.leave_balance}</DialogDescription>
        </DialogHeader>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr><th className="text-left px-2 py-1.5">Date</th><th className="text-left px-2 py-1.5">Status</th>
              <th className="text-left px-2 py-1.5">In</th><th className="text-left px-2 py-1.5">Out</th>
              <th className="text-right px-2 py-1.5">Hours</th><th className="text-right px-2 py-1.5">OT</th>
              <th className="text-left px-2 py-1.5">Project</th><th className="text-left px-2 py-1.5">Remarks</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t">
                <td className="px-2 py-1 font-mono-data text-xs">{r.date}</td>
                <td className="px-2 py-1 text-xs">{(r.status || "").replaceAll("_", " ")}</td>
                <td className="px-2 py-1 text-xs">{r.in_time || "—"}</td>
                <td className="px-2 py-1 text-xs">{r.out_time || "—"}</td>
                <td className="px-2 py-1 text-right tabular">{r.total_hours ?? r.hours ?? 0}</td>
                <td className="px-2 py-1 text-right tabular">{r.overtime_hours || 0}</td>
                <td className="px-2 py-1 text-xs">{r.project_code || "—"}</td>
                <td className="px-2 py-1 text-xs">{r.remarks || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DialogContent>
    </Dialog>
  );
}

export default function AttendanceSummary() {
  const [month, setMonth] = useState(monthIso());
  const [project, setProject] = useState("");
  const [dept, setDept] = useState("");
  const [shift, setShift] = useState("");
  const [q, setQ] = useState("");
  const [view, setView] = useState("employee");
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [drill, setDrill] = useState(null);
  const [downloading, setDownloading] = useState("");

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/hr2/attendance-plus/summary", {
        params: { month, project_code: project || undefined, department: dept || undefined,
                  shift_code: shift || undefined, q: q || undefined },
      });
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load summary"); }
  }, [month, project, dept, shift, q]);
  useEffect(() => { load(); }, [load]);

  const download = async (fmt) => {
    setDownloading(fmt);
    try {
      const r = await api.get("/hr2/attendance-plus/summary/export", {
        params: { fmt, month, project_code: project || undefined, department: dept || undefined,
                  shift_code: shift || undefined, q: q || undefined },
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `attendance_summary_${month}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error("Download failed"); }
    finally { setDownloading(""); }
  };

  const breakdown = async (fmt, print) => {
    setDownloading("breakdown");
    try {
      const r = await api.get("/hr2/attendance-plus/summary/breakdown/export", {
        params: { fmt, month, project_code: project || undefined, department: dept || undefined,
                  shift_code: shift || undefined, q: q || undefined },
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      if (print) {
        const w = window.open(url, "_blank");
        if (w) w.focus();
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = `attendance_breakdown_${month}.${fmt}`;
        a.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { toast.error("Breakdown export failed"); }
    finally { setDownloading(""); }
  };

  const departments = useMemo(() => (data?.by_department || []).map((d) => d.department).filter((d) => d !== "—"), [data]);
  const shiftCodes = useMemo(() => (data?.by_shift || []).map((s) => s.shift_code).filter((s) => s !== "—"), [data]);
  const t = data?.totals || {};

  return (
    <div className="p-6 space-y-4 print:p-2" data-testid="attendance-summary-page">
      <div className="flex items-end justify-between gap-3 flex-wrap print:hidden">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · HR · Attendance</div>
          <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2"><BarChart3 className="h-7 w-7 text-primary" /> Attendance Summary</h1>
          <p className="text-sm text-slate-600 mt-1">Month-wise P/A/HD/L/WO/OD analytics with late entry, early exit, overtime and leave balance.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" onClick={() => window.print()} data-testid="summary-print-btn"><Printer className="h-4 w-4 mr-1.5" /> Print</Button>
          <Button variant="outline" disabled={!!downloading} onClick={() => download("csv")} data-testid="summary-dl-csv">CSV</Button>
          <Button variant="outline" disabled={!!downloading} onClick={() => download("pdf")} data-testid="summary-dl-pdf">PDF</Button>
          <Button className="bg-emerald-600 hover:bg-emerald-700" disabled={!!downloading} onClick={() => download("xlsx")} data-testid="summary-download-btn">
            <Download className="h-4 w-4 mr-1.5" /> {downloading ? "Preparing…" : "Download Attendance Summary"}
          </Button>
          <div className="w-full flex gap-2 items-center justify-end">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Employee × Date Breakdown:</span>
            <Button variant="outline" size="sm" disabled={!!downloading} onClick={() => breakdown("xlsx", false)} data-testid="breakdown-dl-xlsx">Excel</Button>
            <Button variant="outline" size="sm" disabled={!!downloading} onClick={() => breakdown("pdf", false)} data-testid="breakdown-dl-pdf">PDF</Button>
            <Button variant="outline" size="sm" disabled={!!downloading} onClick={() => breakdown("pdf", true)} data-testid="breakdown-print-btn"><Printer className="h-3.5 w-3.5 mr-1" /> Print</Button>
          </div>
        </div>
      </div>

      <div className="flex gap-2 items-end flex-wrap bg-card border border-border rounded-sm p-3 print:hidden">
        <div><Label className="text-[10px] uppercase tracking-wider">Month</Label>
          <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="h-9 mt-1 w-40" data-testid="summary-month" /></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Location / Project</Label>
          <select value={project} onChange={(e) => setProject(e.target.value)}
                  className="h-9 mt-1 w-56 rounded-sm border border-input bg-background px-2 text-sm" data-testid="summary-project">
            <option value="">All locations & projects</option>
            <option value="HEAD-OFFICE">Head Office (Delhi)</option>
            {projects.map((p) => <option key={p.id} value={p.code}>{p.code} · {p.name}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Department</Label>
          <select value={dept} onChange={(e) => setDept(e.target.value)} className="h-9 mt-1 w-44 rounded-sm border border-input bg-background px-2 text-sm" data-testid="summary-dept">
            <option value="">All departments</option>
            {departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Shift</Label>
          <select value={shift} onChange={(e) => setShift(e.target.value)} className="h-9 mt-1 w-32 rounded-sm border border-input bg-background px-2 text-sm" data-testid="summary-shift">
            <option value="">All shifts</option>
            {shiftCodes.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></div>
        <div className="relative">
          <Label className="text-[10px] uppercase tracking-wider">Employee</Label>
          <div className="relative mt-1">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name / code" className="h-9 pl-8 w-52" data-testid="summary-search" />
          </div>
        </div>
        {(project || dept || shift || q) && (
          <Button variant="ghost" size="sm" className="h-9" onClick={() => { setProject(""); setDept(""); setShift(""); setQ(""); }} data-testid="summary-clear">
            <X className="h-4 w-4 mr-1" /> Clear
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-9 gap-2">
        <Kpi label="Employees" value={t.employees ?? 0} testid="kpi-employees" />
        <Kpi label="Present (P)" value={t.P ?? 0} testid="kpi-present" />
        <Kpi label="Absent (A)" value={t.A ?? 0} testid="kpi-absent" />
        <Kpi label="Leave (L)" value={t.L ?? 0} testid="kpi-leave" />
        <Kpi label="Paid Days" value={t.paid_days ?? 0} testid="kpi-paid-days" />
        <Kpi label="Present Days" value={t.present_days ?? 0} testid="kpi-present-days" />
        <Kpi label="Late Entries" value={t.late_count ?? 0} testid="kpi-late" />
        <Kpi label="Early Exits" value={t.early_count ?? 0} testid="kpi-early" />
        <Kpi label="OT Hours" value={t.ot_hours ?? 0} testid="kpi-ot" />
      </div>

      <Tabs value={view} onValueChange={setView} className="print:hidden">
        <TabsList>
          <TabsTrigger value="employee" data-testid="view-employee">Employee-wise</TabsTrigger>
          <TabsTrigger value="date" data-testid="view-date">Date-wise</TabsTrigger>
          <TabsTrigger value="department" data-testid="view-department">Department-wise</TabsTrigger>
          <TabsTrigger value="project" data-testid="view-project">Project-wise</TabsTrigger>
          <TabsTrigger value="shift" data-testid="view-shift">Shift-wise</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="border border-border rounded-sm overflow-x-auto bg-card">
        {view === "employee" && (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Code</th>
                <th className="text-left px-3 py-2">Employee</th>
                <th className="text-left px-3 py-2">Dept</th>
                {CODES.map((c) => <th key={c} className="text-right px-2 py-2">{c}</th>)}
                <th className="text-right px-2 py-2">Late</th>
                <th className="text-right px-2 py-2">Early</th>
                <th className="text-right px-2 py-2">Paid Days</th>
                <th className="text-right px-2 py-2">Present Days</th>
                <th className="text-right px-2 py-2">OT hrs</th>
                <th className="text-right px-3 py-2">Leave Bal</th>
              </tr>
            </thead>
            <tbody>
              {(data?.employees || []).length === 0 && <tr><td colSpan={16} className="text-center py-8 text-slate-400">No attendance for these filters.</td></tr>}
              {(data?.employees || []).map((e) => (
                <tr key={e.employee_id} className="border-t hover:bg-blue-50/40 cursor-pointer" onClick={() => setDrill(e)} data-testid={`summary-emp-${e.employee_id}`}>
                  <td className="px-3 py-1.5 font-mono-data text-xs">{e.employee_code || "—"}</td>
                  <td className="px-3 py-1.5 font-medium text-primary underline-offset-2 hover:underline">{e.employee_name}</td>
                  <td className="px-3 py-1.5 text-xs">{e.department || "—"}</td>
                  {CODES.map((c) => <td key={c} className={`text-right px-2 py-1.5 tabular ${CODE_TONE[c]}`}>{e[c] || 0}</td>)}
                  <td className="text-right px-2 py-1.5 tabular">{e.late_count}</td>
                  <td className="text-right px-2 py-1.5 tabular">{e.early_count}</td>
                  <td className="text-right px-2 py-1.5 tabular font-semibold" data-testid={`paid-days-${e.employee_id}`}>{e.paid_days ?? 0}</td>
                  <td className="text-right px-2 py-1.5 tabular font-semibold">{e.present_days}</td>
                  <td className="text-right px-2 py-1.5 tabular">{e.ot_hours}</td>
                  <td className="text-right px-3 py-1.5 tabular">{e.leave_balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {view === "date" && <GroupTable rows={data?.by_date || []} keyName="date" keyLabel="Date" />}
        {view === "department" && <GroupTable rows={data?.by_department || []} keyName="department" keyLabel="Department" />}
        {view === "project" && <GroupTable rows={data?.by_project || []} keyName="project_code" keyLabel="Project" />}
        {view === "shift" && <GroupTable rows={data?.by_shift || []} keyName="shift_code" keyLabel="Shift" />}
      </div>

      {drill && <DrillDown emp={drill} month={month} onClose={() => setDrill(null)} />}
    </div>
  );
}
