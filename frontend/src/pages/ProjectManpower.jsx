import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Users, UserCheck, UserX, Building2, Briefcase } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toneFor } from "@/lib/statusTone";

const STATUS_TONE = { active: "success", planned: "info", completed: "neutral", withdrawn: "danger" };

function KPI({ label, value, icon: Icon, tone = "neutral", testid }) {
  const toneClass = {
    primary: "text-primary",
    success: "text-success",
    danger: "text-destructive",
    warning: "text-warning",
    info: "text-chart-3",
    neutral: "text-foreground",
  }[tone];
  return (
    <div className="bg-card border border-border rounded-sm p-4 flex items-center gap-3" data-testid={testid}>
      <div className={cn("h-10 w-10 grid place-items-center rounded-sm bg-muted/60", toneClass)}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className={cn("font-display font-black text-3xl tabular leading-none mt-0.5", toneClass)}>{value}</div>
      </div>
    </div>
  );
}

export default function ProjectManpower() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null); setError(null);
    api.get(`/projects/${encodeURIComponent(code)}/manpower`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Failed to load manpower"));
  }, [code]);

  if (error) {
    return (
      <div className="text-center py-16" data-testid="project-manpower-error">
        <div className="font-display font-bold text-lg">{error}</div>
        <Button className="mt-4 rounded-sm" onClick={() => navigate("/app/projects")}>← Back to Projects</Button>
      </div>
    );
  }
  if (!data) return <div className="text-sm text-muted-foreground" data-testid="project-manpower-loading">Loading manpower…</div>;

  const attMap = Object.fromEntries((data.attendance_today || []).map((a) => [a.employee_id, a.status]));

  return (
    <div className="space-y-8" data-testid={`project-manpower-${code}`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Briefcase className="h-3 w-3" /> Project Manpower
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">{data.project.name || data.project.code}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data.project.code} · {data.project.site || "—"} · Manager: <span className="text-foreground">{data.project.manager || "—"}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge text={data.project.status || "—"} tone={toneFor(STATUS_TONE, data.project.status, "neutral")} />
          <Button variant="outline" className="rounded-sm" onClick={() => navigate("/app/deployments")} data-testid="mp-back-deployments">
            <ArrowLeft className="h-4 w-4 mr-1.5" /> Deployments
          </Button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 stagger" data-testid="mp-kpis">
        <KPI label="Total Deployed" value={data.kpis.total_deployed} icon={Users} tone="primary" testid="mp-kpi-total" />
        <KPI label="Present Today" value={data.kpis.present_today} icon={UserCheck} tone="success" testid="mp-kpi-present" />
        <KPI label="Absent Today" value={data.kpis.absent_today} icon={UserX} tone="danger" testid="mp-kpi-absent" />
        <KPI label="Departments" value={data.kpis.distinct_depts} icon={Building2} tone="info" testid="mp-kpi-depts" />
      </div>

      {/* Breakdown cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Breakdown title="By Role at Site" rows={data.by_role.map((r) => ({ label: r.role.replaceAll("_", " "), count: r.count }))} testid="mp-by-role" />
        <Breakdown title="By Department" rows={data.by_department.map((d) => ({ label: d.department, count: d.count }))} testid="mp-by-department" />
      </div>

      {/* Deployment roster */}
      <div className="bg-card border border-border rounded-sm" data-testid="mp-roster">
        <div className="p-4 border-b border-border">
          <h2 className="font-display font-bold text-lg">Active Roster ({data.deployments.length})</h2>
          <p className="text-xs text-muted-foreground">Everyone currently deployed on this project.</p>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Dep #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Employee</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Role on Site</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Shift</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Start</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">End</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Today</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.deployments.length === 0 && (
              <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-10">No active deployments on this project.</TableCell></TableRow>
            )}
            {data.deployments.map((d) => {
              const att = attMap[d.employee_id];
              return (
                <TableRow key={d.id} className="hover:bg-muted/30" data-testid={`mp-roster-row-${d.id}`}>
                  <TableCell className="font-mono-data text-xs">{d.deployment_no || d.id?.slice(0, 8)}</TableCell>
                  <TableCell className="text-sm font-semibold">{d.employee}</TableCell>
                  <TableCell className="text-sm">{(d.site_role || d.role || "—").replaceAll("_", " ")}</TableCell>
                  <TableCell className="text-sm">{d.shift || "—"}</TableCell>
                  <TableCell className="text-sm">{d.start_date || "—"}</TableCell>
                  <TableCell className="text-sm">{d.end_date || "—"}</TableCell>
                  <TableCell><StatusBadge text={d.status || "active"} tone={toneFor(STATUS_TONE, d.status, "neutral")} /></TableCell>
                  <TableCell>
                    {att === "present" && <StatusBadge text="Present" tone="success" />}
                    {att === "absent" && <StatusBadge text="Absent" tone="danger" />}
                    {!att && <span className="text-[10px] text-muted-foreground">—</span>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function Breakdown({ title, rows, testid }) {
  const max = rows.reduce((m, r) => Math.max(m, r.count), 1);
  return (
    <div className="bg-card border border-border rounded-sm p-5" data-testid={testid}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">{title}</div>
      {rows.length === 0 && <div className="text-xs text-muted-foreground py-4">No data yet.</div>}
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.label} className="text-sm">
            <div className="flex items-center justify-between">
              <span className="capitalize">{r.label}</span>
              <span className="font-display font-bold tabular">{r.count}</span>
            </div>
            <div className="h-1.5 mt-1 rounded-full bg-muted overflow-hidden">
              <div className="h-full bg-primary" style={{ width: `${(r.count / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
