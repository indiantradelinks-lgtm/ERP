import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Attendance() {
  const r = useResource("attendance");
  const columns = [
    { key: "date", label: "Date" },
    { key: "employee_name", label: "Employee" },
    { key: "check_in", label: "In" },
    { key: "check_out", label: "Out" },
    { key: "hours", label: "Hours" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "present" ? "success" : r.status === "absent" ? "danger" : "warning" }) },
  ];
  const fields = [
    { key: "employee_name", label: "Employee Name", full: true },
    { key: "date", label: "Date", type: "date" },
    { key: "check_in", label: "Check In (HH:MM)" },
    { key: "check_out", label: "Check Out (HH:MM)" },
    { key: "hours", label: "Hours", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["present", "absent", "leave", "half_day"] },
  ];
  return <DataTableShell title="Attendance" description="Daily check-in/out records by employee." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="attendance" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />;
}
