import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Safety() {
  const r = useResource("safety-reports");
  const columns = [
    { key: "report_id", label: "Report" },
    { key: "date", label: "Date" },
    { key: "project", label: "Project" },
    { key: "type", label: "Type", render: (r) => (r.type || "").replaceAll("_", " ") },
    { key: "severity", label: "Severity", badge: (r) => ({ text: r.severity, tone: r.severity === "high" ? "danger" : r.severity === "medium" ? "warning" : "success" }) },
    { key: "reporter", label: "Reporter" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "closed" ? "success" : r.status === "open" ? "warning" : "info" }) },
  ];
  const fields = [
    { key: "report_id", label: "Report ID" },
    { key: "date", label: "Date", type: "date" },
    { key: "project", label: "Project", full: true },
    { key: "type", label: "Type", type: "select", options: ["observation", "near_miss", "incident", "ptw", "toolbox_talk"] },
    { key: "severity", label: "Severity", type: "select", options: ["low", "medium", "high"] },
    { key: "reporter", label: "Reporter" },
    { key: "description", label: "Description", full: true, type: "textarea" },
    { key: "status", label: "Status", type: "select", options: ["open", "under_review", "closed"] },
  ];
  return <DataTableShell title="Safety Management" description="Observations, near-miss, incidents and PTWs." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="safety" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />;
}
