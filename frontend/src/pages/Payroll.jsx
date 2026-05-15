import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Payroll() {
  const r = useResource("payroll");
  const columns = [
    { key: "employee_name", label: "Employee" },
    { key: "month", label: "Month" },
    { key: "gross", label: "Gross", render: (r) => "₹ " + Number(r.gross || 0).toLocaleString("en-IN") },
    { key: "deductions", label: "Deductions", render: (r) => "₹ " + Number(r.deductions || 0).toLocaleString("en-IN") },
    { key: "net", label: "Net Pay", render: (r) => "₹ " + Number(r.net || 0).toLocaleString("en-IN") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "processed" ? "success" : r.status === "paid" ? "info" : "warning" }) },
  ];
  const fields = [
    { key: "employee_name", label: "Employee", full: true },
    { key: "month", label: "Month (YYYY-MM)" },
    { key: "gross", label: "Gross (INR)", type: "number" },
    { key: "deductions", label: "Deductions (INR)", type: "number" },
    { key: "net", label: "Net Pay (INR)", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["draft", "processed", "paid", "on_hold"] },
  ];
  return <DataTableShell title="Payroll" description="Monthly payroll cycles, deductions and net pay." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="payroll" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />;
}
