import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Progress } from "@/components/ui/progress";

export default function Projects() {
  const r = useResource("projects");
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
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "active" ? "success" : r.status === "completed" ? "info" : r.status === "planned" ? "warning" : "neutral" }) },
  ];
  const fields = [
    { key: "code", label: "Project Code" },
    { key: "name", label: "Project Name", full: true },
    { key: "client", label: "Client" },
    { key: "type", label: "Type", type: "select", options: ["scaffolding", "painting", "roof_sheeting", "rope_access", "shutdown", "maintenance"] },
    { key: "site", label: "Site Location" },
    { key: "manager", label: "Project Manager" },
    { key: "start_date", label: "Start Date", type: "date" },
    { key: "end_date", label: "End Date", type: "date" },
    { key: "budget", label: "Budget (INR)", type: "number" },
    { key: "progress", label: "Progress %", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["planned", "active", "on_hold", "completed", "cancelled"] },
  ];
  return <DataTableShell title="Projects" description="Active sites, scopes, budgets and progress." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="projects" />;
}
