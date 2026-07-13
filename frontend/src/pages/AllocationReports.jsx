import { useEffect, useState } from "react";
import { Users, Building2, Briefcase, UserX, BarChart3, History, ArrowLeftRight } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toneFor } from "@/lib/statusTone";

const ACTION_TONE = {
  department_move: "primary",
  deployment_start: "success",
  deployment_end: "neutral",
};

const TABS = [
  { id: "by_department", label: "By Department", icon: Building2 },
  { id: "by_project", label: "By Project", icon: Briefcase },
  { id: "idle", label: "Idle Manpower", icon: UserX },
  { id: "utilization", label: "Resource Utilization", icon: BarChart3 },
  { id: "site_attendance", label: "Site Attendance", icon: Users },
  { id: "transfer", label: "Transfer History", icon: ArrowLeftRight },
  { id: "history", label: "Deployment History", icon: History },
];

export default function AllocationReports() {
  const [active, setActive] = useState("by_department");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);

  useEffect(() => {
    setLoading(true);
    setData(null);
    const endpoint = {
      by_department: "/allocation/by-department",
      by_project: "/allocation/by-project",
      idle: "/allocation/idle-employees",
      utilization: "/allocation/resource-utilization",
      site_attendance: "/allocation/site-attendance",
      transfer: "/allocation/transfer-history",
      history: "/allocation/history?limit=200",
    }[active];
    api.get(endpoint)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [active]);

  return (
    <div className="space-y-8" data-testid="allocation-reports">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <BarChart3 className="h-3 w-3" /> HR · Allocation
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Allocation Reports</h1>
        <p className="text-sm text-muted-foreground mt-1">Manpower deployment analytics across departments, projects and time.</p>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="alloc-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Button
              key={t.id}
              variant={active === t.id ? "default" : "outline"}
              className="rounded-sm h-9"
              onClick={() => setActive(t.id)}
              data-testid={`alloc-tab-${t.id}`}
            >
              <Icon className="h-3.5 w-3.5 mr-1.5" /> {t.label}
            </Button>
          );
        })}
      </div>

      <div className="bg-card border border-border rounded-sm p-5 min-h-[200px]" data-testid={`alloc-pane-${active}`}>
        {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {!loading && data && active === "by_department" && <BarList rows={data} labelKey="department" />}
        {!loading && data && active === "by_project" && <BarList rows={data} labelKey="project" />}
        {!loading && data && active === "idle" && <IdleTable rows={data} />}
        {!loading && data && active === "utilization" && <UtilTable data={data} />}
        {!loading && data && active === "site_attendance" && <SiteAttendanceTable rows={data} />}
        {!loading && data && (active === "transfer" || active === "history") && <HistoryTable rows={data} />}
      </div>
    </div>
  );
}

function BarList({ rows, labelKey }) {
  const max = rows.reduce((m, r) => Math.max(m, r.count), 1);
  if (!rows.length) return <Empty />;
  return (
    <ul className="space-y-3" data-testid="alloc-bar-list">
      {rows.map((r) => (
        <li key={r[labelKey]} data-testid={`alloc-row-${r[labelKey]}`}>
          <div className="flex items-center justify-between text-sm mb-1">
            <span className="font-semibold">{r[labelKey]}</span>
            <span className="font-display font-bold tabular">{r.count}</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full bg-primary" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function IdleTable({ rows }) {
  if (!rows.length) return <div className="text-sm text-muted-foreground">No idle employees — everyone is deployed.</div>;
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Emp ID</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Name</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Role</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Department</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Branch</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Joined</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((e) => (
          <TableRow key={e.id} className="hover:bg-muted/30" data-testid={`alloc-idle-${e.id}`}>
            <TableCell className="font-mono-data text-xs">{e.employee_id || e.emp_code || "—"}</TableCell>
            <TableCell className="text-sm font-semibold">{e.name}</TableCell>
            <TableCell className="text-sm">{(e.role || "").replaceAll("_", " ")}</TableCell>
            <TableCell className="text-sm">{(e.departments || [e.department]).filter(Boolean).join(", ") || "—"}</TableCell>
            <TableCell className="text-sm">{e.branch || "—"}</TableCell>
            <TableCell className="text-sm">{e.joining_date || "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function UtilTable({ data }) {
  if (!data?.rows?.length) return <Empty />;
  const { summary, rows } = data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3" data-testid="alloc-util-summary">
        <KPI label="Avg Utilization" value={`${summary.avg_utilization}%`} tone="primary" />
        <KPI label="Deployed Employees" value={summary.deployed_employees} tone="success" />
        <KPI label="Total Employees" value={summary.total_employees} tone="neutral" />
      </div>
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="text-[10px] uppercase tracking-wider">Emp ID</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Name</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Department</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Deployed Days</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Available Days</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Utilization %</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={`${r.employee_id}-${r.name}`} className="hover:bg-muted/30" data-testid={`alloc-util-${r.employee_id}`}>
              <TableCell className="font-mono-data text-xs">{r.employee_id}</TableCell>
              <TableCell className="text-sm font-semibold">{r.name}</TableCell>
              <TableCell className="text-sm">{r.department}</TableCell>
              <TableCell className="text-sm tabular">{r.deployed_days}</TableCell>
              <TableCell className="text-sm tabular">{r.available_days}</TableCell>
              <TableCell>
                <UtilBar pct={r.utilization_pct} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function UtilBar({ pct }) {
  const tone = pct >= 75 ? "bg-success" : pct >= 35 ? "bg-warning" : "bg-destructive";
  return (
    <div className="flex items-center gap-2 w-32">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full", tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular w-10 text-right">{pct}%</span>
    </div>
  );
}

function SiteAttendanceTable({ rows }) {
  if (!rows.length) return <div className="text-sm text-muted-foreground">No active deployments to report attendance for today.</div>;
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Present</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Absent</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Unmarked</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Total Deployed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.project} className="hover:bg-muted/30" data-testid={`alloc-attend-${r.project}`}>
            <TableCell className="text-sm font-semibold">{r.project}</TableCell>
            <TableCell><StatusBadge text={String(r.present)} tone="success" /></TableCell>
            <TableCell><StatusBadge text={String(r.absent)} tone="danger" /></TableCell>
            <TableCell><StatusBadge text={String(r.unknown)} tone="warning" /></TableCell>
            <TableCell className="text-sm tabular font-display font-bold">{r.total}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function HistoryTable({ rows }) {
  if (!rows.length) return <Empty />;
  const labelFor = (a) => ({
    department_move: "Department change",
    deployment_start: "Deployed",
    deployment_end: "Withdrawn",
  })[a] || a;
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Employee</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Action</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Detail</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Actor</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((h, idx) => (
          <TableRow key={h.id || `${h.at}-${h.employee_id || idx}-${h.action}`} className="hover:bg-muted/30" data-testid={`alloc-history-${h.id || idx}`}>
            <TableCell className="font-mono-data text-xs">{(h.at || "").slice(0, 16).replace("T", " ")}</TableCell>
            <TableCell className="text-sm font-semibold">{h.employee_name || "—"}</TableCell>
            <TableCell><StatusBadge text={labelFor(h.action)} tone={toneFor(ACTION_TONE, h.action, "neutral")} /></TableCell>
            <TableCell className="text-sm">{h.project || "—"}</TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {h.from && <span>From: {JSON.stringify(h.from)} · </span>}
              {h.to && <span>To: {JSON.stringify(h.to)}</span>}
            </TableCell>
            <TableCell className="text-xs">{h.actor_name || "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function KPI({ label, value, tone }) {
  const t = { primary: "text-primary", success: "text-success", neutral: "text-foreground" }[tone];
  return (
    <div className="bg-muted/40 border border-border rounded-sm p-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className={cn("font-display font-black text-2xl tabular mt-1", t)}>{value}</div>
    </div>
  );
}

function Empty() {
  return <div className="text-sm text-muted-foreground py-6 text-center">No data.</div>;
}
