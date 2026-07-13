import { useEffect, useMemo, useState } from "react";
import { Users, Briefcase, AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const SITE_ROLE_OPTIONS = ["site_engineer", "supervisor", "safety_officer", "store_incharge", "logistics_coordinator", "helper"];
const SHIFT_OPTIONS = ["day", "night", "general", "rotational"];

/**
 * Drag-drop allocation board.
 *  - Left column lists idle employees (employees with no active deployment)
 *  - Each subsequent column = one project + its current active roster
 *
 * Drag an idle employee onto a project column → opens a quick-deploy dialog
 * (POST /api/deployments). Drag an active deployment back onto "Idle" → ends
 * that deployment (POST /api/deployments/{id}/end).
 */
export default function AllocationBoard() {
  const [idle, setIdle] = useState([]);
  const [projects, setProjects] = useState([]);
  const [byProject, setByProject] = useState({});           // {projectCode: [deployment]}
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(null);               // {employee, projectCode}
  const [form, setForm] = useState({ site_role: "site_engineer", shift: "day", start_date: new Date().toISOString().slice(0, 10) });
  const [shortages, setShortages] = useState({ total_shortfall: 0, rows: [] });

  const reload = async () => {
    setLoading(true);
    try {
      const [idleR, projR, sh] = await Promise.all([
        api.get("/allocation/idle-employees"),
        api.get("/projects"),
        api.get("/allocation/shortages"),
      ]);
      setIdle(idleR.data || []);
      setProjects((projR.data || []).filter((p) => p.status !== "completed" && p.status !== "cancelled"));
      setShortages(sh.data || { total_shortfall: 0, rows: [] });
      // Load deployments per project in parallel
      const projCodes = (projR.data || []).filter((p) => p.status !== "completed" && p.status !== "cancelled").map((p) => p.code);
      const mpResults = await Promise.all(
        projCodes.map((code) =>
          api.get(`/projects/${encodeURIComponent(code)}/manpower`).then((r) => [code, r.data.deployments || []]).catch(() => [code, []]),
        ),
      );
      setByProject(Object.fromEntries(mpResults));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); }, []);

  const onDragStart = (e, payload) => {
    e.dataTransfer.setData("application/json", JSON.stringify(payload));
    e.dataTransfer.effectAllowed = "move";
  };
  const onDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; };

  const onDropToProject = (e, projectCode) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/json");
    if (!raw) return;
    const payload = JSON.parse(raw);
    if (payload.kind !== "idle-employee") {
      toast.error("Drag an idle employee here.");
      return;
    }
    setDialog({ employee: payload.employee, projectCode });
    setForm({ site_role: "site_engineer", shift: "day", start_date: new Date().toISOString().slice(0, 10) });
  };

  const onDropToIdle = async (e) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/json");
    if (!raw) return;
    const payload = JSON.parse(raw);
    if (payload.kind !== "active-deployment") return;
    if (!window.confirm(`End deployment of ${payload.employee} from ${payload.projectCode}?`)) return;
    try {
      await api.post(`/deployments/${payload.deploymentId}/end`, {});
      toast.success("Deployment ended");
      reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const confirmDeploy = async () => {
    if (!dialog) return;
    const body = {
      employee: dialog.employee.name,
      employee_id: dialog.employee.id,
      project: dialog.projectCode,
      site: dialog.projectCode,
      site_role: form.site_role,
      shift: form.shift,
      start_date: form.start_date,
      status: "active",
    };
    try {
      const { data } = await api.post("/deployments", body);
      if (data.status === "pending_approval") {
        toast.success(`Deployment submitted for approval (${data.deployment_no})`);
      } else {
        toast.success(`Deployed ${dialog.employee.name} (${data.deployment_no})`);
      }
      setDialog(null);
      reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Deploy failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="allocation-board">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Users className="h-3 w-3" /> HR · Allocation
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Manpower Allocation Board</h1>
          <p className="text-sm text-muted-foreground mt-1">Drag idle employees onto a project to deploy. Drag back to "Idle" to end a deployment.</p>
        </div>
        <Button variant="outline" className="rounded-sm" onClick={reload} data-testid="board-refresh">
          <RefreshCw className={cn("h-4 w-4 mr-1.5", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {shortages.total_shortfall > 0 && <ShortageStrip rows={shortages.rows} total={shortages.total_shortfall} />}

      <div className="grid gap-3 [grid-template-columns:280px_1fr]" data-testid="board-grid">
        {/* Idle column */}
        <div
          onDragOver={onDragOver}
          onDrop={onDropToIdle}
          className="bg-card border border-border rounded-sm p-3 min-h-[400px]"
          data-testid="board-idle-column"
        >
          <div className="flex items-center justify-between mb-3">
            <div className="font-display font-bold text-sm uppercase tracking-wider">Idle Bench</div>
            <StatusBadge text={String(idle.length)} tone="warning" />
          </div>
          <ul className="space-y-2">
            {idle.length === 0 && <li className="text-xs text-muted-foreground text-center py-6">Everyone is deployed.</li>}
            {idle.map((e) => (
              <li
                key={e.id}
                draggable
                onDragStart={(ev) => onDragStart(ev, { kind: "idle-employee", employee: { id: e.id, name: e.name } })}
                className="p-2.5 bg-muted/40 border border-border rounded-sm cursor-grab active:cursor-grabbing hover:border-primary/60 transition-colors"
                data-testid={`board-idle-${e.id}`}
              >
                <div className="font-semibold text-sm">{e.name}</div>
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{e.employee_id || e.emp_code || "—"} · {(e.departments || [e.department]).filter(Boolean).join(", ") || "—"}</div>
              </li>
            ))}
          </ul>
        </div>

        {/* Projects strip */}
        <div className="overflow-x-auto">
          <div className="flex gap-3 pb-2 min-w-max">
            {projects.map((p) => (
              <ProjectColumn
                key={p.code}
                project={p}
                deployments={byProject[p.code] || []}
                onDragOver={onDragOver}
                onDrop={(e) => onDropToProject(e, p.code)}
                onDragStart={onDragStart}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Deploy dialog */}
      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Deploy {dialog?.employee?.name}</DialogTitle>
            <DialogDescription className="sr-only">Configure deployment to {dialog?.projectCode}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-xs uppercase tracking-wider">Project</Label>
              <div className="font-mono-data text-sm mt-1">{dialog?.projectCode}</div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Role on Site</Label>
              <select
                value={form.site_role}
                onChange={(e) => setForm({ ...form, site_role: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1"
                data-testid="board-deploy-site_role"
              >
                {SITE_ROLE_OPTIONS.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Shift</Label>
              <select
                value={form.shift}
                onChange={(e) => setForm({ ...form, shift: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1"
                data-testid="board-deploy-shift"
              >
                {SHIFT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Start Date</Label>
              <Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="board-deploy-start_date" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setDialog(null)}>Cancel</Button>
            <Button className="rounded-sm" onClick={confirmDeploy} data-testid="board-deploy-confirm">Deploy</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ProjectColumn({ project, deployments, onDragOver, onDrop, onDragStart }) {
  return (
    <div
      onDragOver={onDragOver}
      onDrop={onDrop}
      className="bg-card border border-border rounded-sm p-3 w-[280px] flex-shrink-0 min-h-[400px]"
      data-testid={`board-project-${project.code}`}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{project.code}</div>
          <div className="font-display font-bold text-sm leading-tight truncate" title={project.name}>{project.name}</div>
        </div>
        <StatusBadge text={String(deployments.length)} tone="primary" />
      </div>
      <ul className="space-y-2">
        {deployments.length === 0 && (
          <li className="text-xs text-muted-foreground text-center py-6 border-2 border-dashed border-border rounded-sm">
            Drop employees here
          </li>
        )}
        {deployments.map((d) => (
          <li
            key={d.id}
            draggable
            onDragStart={(ev) => onDragStart(ev, { kind: "active-deployment", deploymentId: d.id, employee: d.employee, projectCode: project.code })}
            className="p-2.5 bg-primary/5 border border-primary/30 rounded-sm cursor-grab active:cursor-grabbing hover:border-primary transition-colors"
            data-testid={`board-deployment-${d.id}`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="font-semibold text-sm truncate">{d.employee}</div>
              {d.status === "pending_approval" && <StatusBadge text="Pending" tone="warning" />}
            </div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {(d.site_role || d.role || "").replaceAll("_", " ") || "—"} · {d.shift || "—"}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ShortageStrip({ rows, total }) {
  return (
    <div className="bg-warning/10 border border-warning/40 rounded-sm p-4 flex items-start gap-3" data-testid="board-shortages">
      <AlertTriangle className="h-5 w-5 text-warning shrink-0 mt-0.5" />
      <div className="flex-1">
        <div className="font-display font-bold text-sm">Manpower shortage detected — {total} headcount short</div>
        <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 text-xs">
          {rows.slice(0, 6).map((r) => (
            <li key={r.req_no} className="flex items-center justify-between bg-card border border-border rounded-sm px-2.5 py-1.5">
              <span><span className="font-semibold">{r.position}</span> · {r.department}</span>
              <StatusBadge text={`-${r.shortfall}`} tone="danger" />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
