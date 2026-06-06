import { useNavigate } from "react-router-dom";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import useSiteOptions from "@/hooks/useSiteOptions";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Users } from "lucide-react";
import { toneFor } from "@/lib/statusTone";

const PROJECT_STATUS_TONE = { active: "success", completed: "info", planned: "warning" };

export default function Projects() {
  const navigate = useNavigate();
  const r = useResource("projects");
  const siteOptions = useSiteOptions();
  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Project" },
    { key: "client", label: "Client" },
    { key: "type", label: "Type", render: (r) => (r.type || "").replaceAll("_", " ") },
    { key: "site", label: "Site" },
    { key: "manager", label: "Manager" },
    { key: "budget", label: "Budget", render: (r) => "₹ " + Number(r.budget || 0).toLocaleString("en-IN") },
    {
      key: "progress",
      label: "Progress",
      render: (r) => (
        <div className="w-32">
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-muted-foreground">{r.progress || 0}%</span>
          </div>
          <Progress value={r.progress || 0} className="h-1.5" />
        </div>
      ),
    },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: toneFor(PROJECT_STATUS_TONE, r.status, "neutral") }) },
    {
      key: "_mp",
      label: "Manpower",
      render: (row) => (
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => navigate(`/app/projects/${encodeURIComponent(row.code)}/manpower`)} data-testid={`projects-manpower-${row.id}`}>
          <Users className="h-3.5 w-3.5 mr-1" /> View
        </Button>
      ),
    },
  ];
  const fields = [
    { key: "code", label: "Project Code" },
    { key: "name", label: "Project Name", full: true },
    { key: "client", label: "Client" },
    { key: "site_id", label: "Customer Site", type: "select", options: siteOptions },
    { key: "type", label: "Type", type: "select", options: ["scaffolding", "painting", "roof_sheeting", "rope_access", "shutdown", "maintenance"] },
    { key: "site", label: "Site Location" },
    { key: "manager", label: "Project Manager" },
    { key: "start_date", label: "Start Date", type: "date" },
    { key: "end_date", label: "End Date", type: "date" },
    { key: "budget", label: "Budget (INR)", type: "number" },
    { key: "progress", label: "Progress %", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["planned", "active", "on_hold", "completed", "cancelled"] },
  ];
  return <DataTableShell title="Projects" description="Active sites, scopes, budgets and progress." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="projects" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="projects" />;
}
