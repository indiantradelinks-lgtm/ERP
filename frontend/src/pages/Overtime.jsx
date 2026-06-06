import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";

const OVERTIME_STATUS_TONE = { approved: "success", rejected: "danger" };

export default function Overtime() {
  const r = useResource("overtime");
  const columns = [
    { key: "employee", label: "Employee" },
    { key: "date", label: "Date" },
    { key: "hours", label: "Hours" },
    { key: "rate", label: "Rate" },
    { key: "project", label: "Project" },
    { key: "approver", label: "Approver" },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status || "pending", tone: toneFor(OVERTIME_STATUS_TONE, row.status, "warning") }) },
  ];
  const fields = [
    { key: "employee", label: "Employee" },
    { key: "date", label: "Date", type: "date" },
    { key: "hours", label: "Overtime Hours", type: "number" },
    { key: "rate", label: "Rate / Hr (INR)", type: "number" },
    { key: "project", label: "Project Code" },
    { key: "reason", label: "Reason", type: "textarea", full: true },
    { key: "approver", label: "Approver" },
    { key: "status", label: "Status", type: "select", options: ["pending", "approved", "rejected"] },
  ];
  return <DataTableShell title="Overtime Entries" description="Recorded extra hours awaiting approval before going into payroll." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="overtime" exportResource="overtime" canWrite={r.canWrite} canDelete={r.canDelete} />;
}
