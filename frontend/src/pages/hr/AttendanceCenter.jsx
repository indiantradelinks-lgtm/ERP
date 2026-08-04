/**
 * Attendance Center — dedicated page for:
 *  • Delhi/Head-Office HR marking Head Office employees' attendance (day or month)
 *  • Project Coordinators / Site Admins marking daily attendance + OT for their projects
 *  • Project-wise register with date & designation filters
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import { CalendarDays, Save, Upload, ListChecks, Building2, Search, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { AttendanceBulkDialog } from "./HrPhase2";
import AttendanceImport from "./AttendanceImport";

const hoursBetween = (tin, tout) => {
  if (!tin || !tout) return 0;
  const [h1, m1] = tin.split(":").map(Number);
  const [h2, m2] = tout.split(":").map(Number);
  if ([h1, m1, h2, m2].some(Number.isNaN)) return 0;
  let mins = (h2 * 60 + m2) - (h1 * 60 + m1);
  if (mins <= 0) mins += 24 * 60;
  return Math.round((mins / 60) * 100) / 100;
};

const STATUSES = [
  { code: "P", value: "present", tone: "bg-green-600 text-white border-green-700" },
  { code: "A", value: "absent", tone: "bg-red-600 text-white border-red-700" },
  { code: "HD", value: "half_day", tone: "bg-amber-500 text-white border-amber-600" },
  { code: "L", value: "leave", tone: "bg-blue-600 text-white border-blue-700" },
  { code: "WO", value: "weekly_off", tone: "bg-slate-500 text-white border-slate-600" },
  { code: "OD", value: "on_duty", tone: "bg-cyan-600 text-white border-cyan-700" },
];
const todayIso = () => new Date().toISOString().slice(0, 10);

export default function AttendanceCenter() {
  const { user } = useAuth();
  const isProjectRole = ["project_coordinator", "project_manager", "supervisor", "site_engineer"].includes(user?.role);
  const [tab, setTab] = useState("daily");
  const [projects, setProjects] = useState([]);
  const [scope, setScope] = useState(isProjectRole ? "" : "HEAD-OFFICE");
  const [master, setMaster] = useState("employee");
  const [bulkOpen, setBulkOpen] = useState(false);

  useEffect(() => {
    api.get("/projects").then((r) => {
      const rows = r.data || [];
      setProjects(rows);
      if (isProjectRole && rows.length && !scope) setScope(rows[0].code);
    }).catch(() => {});
  }, []); // eslint-disable-line

  return (
    <div className="p-6 space-y-4" data-testid="attendance-center-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · HR · Attendance</div>
          <h1 className="font-display font-black text-3xl tracking-tight">Attendance Center</h1>
          <p className="text-sm text-slate-600 mt-1">Head Office & project-wise attendance — daily sheet with OT, monthly bulk upload, filtered register.</p>
        </div>
        <div className="flex gap-2 items-end flex-wrap">
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Location / Project</Label>
            <select value={scope} onChange={(e) => setScope(e.target.value)}
                     className="h-9 mt-1 w-64 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ac-scope">
              {!isProjectRole && <option value="HEAD-OFFICE">Head Office (Delhi)</option>}
              {projects.map((p) => <option key={p.id} value={p.code}>{p.code} · {p.name}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Master</Label>
            <select value={master} onChange={(e) => setMaster(e.target.value)}
                     className="h-9 mt-1 w-48 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ac-master">
              <option value="employee">Employee Master</option>
              <option value="worker">Worker / Labour Master</option>
            </select>
          </div>
          <Button variant="outline" onClick={() => setBulkOpen(true)} data-testid="ac-monthly-btn">
            <Upload className="h-4 w-4 mr-1" /> Monthly Upload
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="daily" data-testid="ac-tab-daily"><CalendarDays className="h-3.5 w-3.5 mr-1" />Daily Sheet</TabsTrigger>
          <TabsTrigger value="register" data-testid="ac-tab-register"><ListChecks className="h-3.5 w-3.5 mr-1" />Register</TabsTrigger>
          <TabsTrigger value="import" data-testid="ac-tab-import"><Bot className="h-3.5 w-3.5 mr-1" />AI Import & Bulk Update</TabsTrigger>
        </TabsList>
      </Tabs>

      {tab === "daily" ? (
        scope ? <DailySheet scope={scope} master={master} /> : (
          <div className="text-sm bg-amber-50 border border-amber-200 text-amber-700 rounded px-3 py-6 text-center" data-testid="ac-no-projects">
            No projects assigned to you yet — ask your admin to assign you via Contract Handovers.
          </div>
        )
      ) : tab === "register" ? (
        <Register scope={scope} />
      ) : (
        <AttendanceImport />
      )}

      {bulkOpen && <AttendanceBulkDialog onClose={() => setBulkOpen(false)} onDone={() => setBulkOpen(false)} />}
    </div>
  );
}

function DailySheet({ scope, master }) {
  const [date, setDate] = useState(todayIso());
  const [designation, setDesignation] = useState("");
  const [q, setQ] = useState("");
  const [sheet, setSheet] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!scope) return;
    try {
      const r = await api.get("/hr2/attendance/bulk/day-sheet", {
        params: { date, master, project_code: scope, ...(designation ? { designation } : {}), ...(q ? { q } : {}) },
      });
      setSheet(r.data);
      const d = {};
      for (const row of r.data.rows) {
        if (row.status) d[row.employee_id] = { status: row.status, ot: row.overtime_hours || 0, in_t: row.in_time || "", out_t: row.out_time || "", remarks: row.remarks || "" };
      }
      setDraft(d);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load day sheet"); }
  }, [date, master, scope, designation, q]);
  useEffect(() => { load(); }, [load]);

  const setRow = (id, patch) => setDraft((m) => {
    const cur = { status: m[id]?.status, ot: m[id]?.ot || 0, in_t: m[id]?.in_t || "", out_t: m[id]?.out_t || "", remarks: m[id]?.remarks || "", ...patch };
    if (("in_t" in patch || "out_t" in patch) && cur.in_t && cur.out_t) {
      const hrs = hoursBetween(cur.in_t, cur.out_t);
      if (hrs > 0 && !("ot" in patch)) cur.ot = Math.max(0, Math.round((hrs - 8) * 100) / 100);
    }
    return { ...m, [id]: cur };
  });
  const marked = Object.entries(draft).filter(([, v]) => v.status);

  const markAll = (value) => {
    const d = { ...draft };
    for (const row of sheet?.rows || []) if (!row.entry_locked) d[row.employee_id] = { ...d[row.employee_id], status: value, ot: d[row.employee_id]?.ot || 0 };
    setDraft(d);
  };

  const save = async () => {
    if (marked.length === 0) { toast.error("Mark at least one person"); return; }
    setSaving(true);
    try {
      const r = await api.post("/hr2/attendance/bulk/day-sheet", {
        date, project_code: scope, master,
        entries: marked.map(([id, v]) => ({ employee_id: id, status: v.status, overtime_hours: Number(v.ot) || 0,
                                            in_time: v.in_t || null, out_time: v.out_t || null, remarks: v.remarks || null })),
      });
      const d = r.data;
      toast.success(`Saved ${d.created + d.updated} entr${d.created + d.updated > 1 ? "ies" : "y"} (pending approval)`);
      if (d.errors?.length) toast.error(`${d.errors.length} error(s): ${d.errors[0].error}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-end flex-wrap bg-white border rounded-lg p-3">
        <div><Label className="text-[10px] uppercase tracking-wider">Date</Label>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="h-9 mt-1" data-testid="ac-date" /></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Designation</Label>
          <select value={designation} onChange={(e) => setDesignation(e.target.value)}
                   className="h-9 mt-1 w-48 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ac-designation">
            <option value="">All designations</option>
            {(sheet?.designations || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select></div>
        <div className="relative">
          <Label className="text-[10px] uppercase tracking-wider">Search</Label>
          <div className="relative mt-1">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name / code" className="h-9 pl-8 w-56" data-testid="ac-search" />
          </div>
        </div>
        <div className="flex gap-1 items-end ml-auto">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 mr-1 mb-2">Mark all:</span>
          {STATUSES.slice(0, 2).map((s) => (
            <Button key={s.value} size="sm" variant="outline" className="h-8" onClick={() => markAll(s.value)} data-testid={`ac-markall-${s.code}`}>{s.code}</Button>
          ))}
          <Button onClick={save} disabled={saving || sheet?.month_locked} className="h-9 ml-2" data-testid="ac-save">
            <Save className="h-4 w-4 mr-1" /> {saving ? "Saving…" : `Save ${marked.length} (pending)`}
          </Button>
        </div>
      </div>
      {sheet?.month_locked && (
        <div className="text-sm bg-red-50 border border-red-200 text-red-700 rounded px-3 py-2">This month is locked for {scope} — attendance cannot be changed.</div>
      )}
      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Code</th>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2">Designation</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-left px-3 py-2 w-24">In</th>
              <th className="text-left px-3 py-2 w-24">Out</th>
              <th className="text-right px-3 py-2 w-14">Hrs</th>
              <th className="text-left px-3 py-2 w-28">OT (hrs)</th>
              <th className="text-left px-3 py-2 w-36">Remarks</th>
              <th className="text-left px-3 py-2">Approval</th>
            </tr>
          </thead>
          <tbody>
            {(sheet?.rows || []).length === 0 && (
              <tr><td colSpan={10} className="text-center py-10 text-slate-400">No people match — check master / filters.</td></tr>
            )}
            {(sheet?.rows || []).map((row) => {
              const cur = draft[row.employee_id] || {};
              return (
                <tr key={row.employee_id} className="border-t hover:bg-slate-50" data-testid={`ac-row-${row.employee_id}`}>
                  <td className="px-3 py-1.5 font-mono-data text-xs">{row.code}</td>
                  <td className="px-3 py-1.5 font-medium">{row.name}</td>
                  <td className="px-3 py-1.5 text-xs">{row.designation || "—"}</td>
                  <td className="px-3 py-1.5">
                    <div className="flex gap-1">
                      {STATUSES.map((s) => (
                        <button key={s.value} disabled={row.entry_locked}
                                onClick={() => setRow(row.employee_id, { status: cur.status === s.value ? undefined : s.value })}
                                className={`h-7 min-w-[30px] px-1 text-[10px] font-bold border rounded-sm transition-colors
                                  ${cur.status === s.value ? s.tone : "bg-background border-border text-slate-500 hover:bg-slate-100"}
                                  ${row.entry_locked ? "opacity-40 cursor-not-allowed" : ""}`}
                                data-testid={`ac-status-${row.employee_id}-${s.code}`}>
                          {s.code}
                        </button>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-1.5">
                    <Input type="time" value={cur.in_t || ""} disabled={row.entry_locked}
                            onChange={(e) => setRow(row.employee_id, { in_t: e.target.value })}
                            className="h-7 w-24 text-xs" data-testid={`ac-in-${row.employee_id}`} />
                  </td>
                  <td className="px-3 py-1.5">
                    <Input type="time" value={cur.out_t || ""} disabled={row.entry_locked}
                            onChange={(e) => setRow(row.employee_id, { out_t: e.target.value })}
                            className="h-7 w-24 text-xs" data-testid={`ac-out-${row.employee_id}`} />
                  </td>
                  <td className="px-3 py-1.5 text-right tabular text-xs" data-testid={`ac-hrs-${row.employee_id}`}>
                    {cur.in_t && cur.out_t ? hoursBetween(cur.in_t, cur.out_t) : "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    <Input type="number" min="0" step="0.5" value={cur.ot ?? 0} disabled={row.entry_locked}
                            onChange={(e) => setRow(row.employee_id, { ot: e.target.value })}
                            className="h-7 w-20 text-right" data-testid={`ac-ot-${row.employee_id}`} />
                  </td>
                  <td className="px-3 py-1.5">
                    <Input value={cur.remarks || ""} disabled={row.entry_locked} placeholder="—"
                            onChange={(e) => setRow(row.employee_id, { remarks: e.target.value })}
                            className="h-7 w-36 text-xs" data-testid={`ac-remarks-${row.employee_id}`} />
                  </td>
                  <td className="px-3 py-1.5 text-xs">
                    {row.approval_status ? (
                      <span className={`px-1.5 py-0.5 rounded border text-[10px] ${row.approval_status === "approved" ? "bg-green-50 border-green-300 text-green-700" : "bg-amber-50 border-amber-300 text-amber-700"}`}>
                        {row.approval_status}
                      </span>
                    ) : <span className="text-slate-400">not marked</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Register({ scope }) {
  const [from, setFrom] = useState(todayIso().slice(0, 8) + "01");
  const [to, setTo] = useState(todayIso());
  const [designation, setDesignation] = useState("");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState([]);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/hr2/attendance/register", {
        params: { from_date: from, to_date: to, project_code: scope || undefined,
                   designation: designation || undefined, status: status || undefined, limit: 1000 },
      });
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load register"); }
  }, [from, to, scope, designation, status]);
  useEffect(() => { load(); }, [load]);

  const designations = useMemo(() => [...new Set(rows.map((r) => r.designation).filter(Boolean))].sort(), [rows]);

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-end flex-wrap bg-white border rounded-lg p-3">
        <div><Label className="text-[10px] uppercase tracking-wider">From</Label>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 mt-1" data-testid="ac-reg-from" /></div>
        <div><Label className="text-[10px] uppercase tracking-wider">To</Label>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 mt-1" data-testid="ac-reg-to" /></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Designation</Label>
          <select value={designation} onChange={(e) => setDesignation(e.target.value)}
                   className="h-9 mt-1 w-48 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ac-reg-designation">
            <option value="">All</option>
            {designations.map((d) => <option key={d} value={d}>{d}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Status</Label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}
                   className="h-9 mt-1 w-40 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ac-reg-status">
            <option value="">All</option>
            {["present", "absent", "half_day", "leave", "weekly_off", "holiday", "on_duty"].map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
          </select></div>
        <div className="ml-auto text-sm text-slate-600 mb-2" data-testid="ac-reg-count">{rows.length} entries · <Building2 className="h-3.5 w-3.5 inline" /> {scope || "all"}</div>
      </div>
      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Date</th>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2">Designation</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">OT</th>
              <th className="text-left px-3 py-2">Approval</th>
              <th className="text-left px-3 py-2">Marked by</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-10 text-slate-400">No entries for these filters.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50">
                <td className="px-3 py-1.5 font-mono-data text-xs">{r.date}</td>
                <td className="px-3 py-1.5">{r.employee_name}</td>
                <td className="px-3 py-1.5 text-xs">{r.designation || "—"}</td>
                <td className="px-3 py-1.5 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-1.5 text-xs">{(r.status || "").replaceAll("_", " ")}</td>
                <td className="px-3 py-1.5 text-right tabular">{r.overtime_hours || 0}</td>
                <td className="px-3 py-1.5 text-xs">{r.approval_status || "—"}</td>
                <td className="px-3 py-1.5 text-xs">{r.marked_by_name || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
