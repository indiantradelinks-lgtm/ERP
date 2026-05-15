import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Employees() {
  const r = useResource("employees");
  const columns = [
    { key: "emp_code", label: "Code" },
    { key: "name", label: "Name" },
    { key: "role", label: "Role", render: (r) => (r.role || "").replaceAll("_", " ") },
    { key: "department", label: "Department" },
    { key: "phone", label: "Phone" },
    { key: "joining_date", label: "Joined" },
    { key: "salary", label: "Salary", render: (r) => "₹ " + Number(r.salary || 0).toLocaleString("en-IN") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status || "active", tone: r.status === "active" ? "success" : "neutral" }) },
  ];
  const fields = [
    { key: "emp_code", label: "Employee Code" },
    { key: "name", label: "Full Name", full: true },
    { key: "role", label: "Role", type: "select", options: ["project_manager", "site_engineer", "supervisor", "store_incharge", "accounts_executive", "hr_executive", "safety_officer", "purchase_officer", "technician"] },
    { key: "department", label: "Department" },
    { key: "email", label: "Email" },
    { key: "phone", label: "Phone" },
    { key: "joining_date", label: "Joining Date", type: "date" },
    { key: "salary", label: "Monthly Salary", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["active", "on_leave", "exited"] },
  ];
  return <DataTableShell title="Employees · HRMS" description="Master record for all on-roll personnel." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="employees" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />;
}
