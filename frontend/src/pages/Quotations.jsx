import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Quotations() {
  const r = useResource("quotations");
  const columns = [
    { key: "quote_number", label: "Quote #" },
    { key: "client", label: "Client" },
    { key: "project", label: "Project" },
    { key: "date", label: "Date" },
    { key: "valid_until", label: "Valid Till" },
    { key: "total", label: "Total", render: (r) => "₹ " + Number(r.total || 0).toLocaleString("en-IN") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "invoiced" ? "success" : r.status === "sent" ? "info" : r.status === "lost" ? "danger" : "warning" }) },
  ];
  const fields = [
    { key: "quote_number", label: "Quote Number" },
    { key: "client", label: "Client" },
    { key: "project", label: "Project / Scope", full: true },
    { key: "date", label: "Date", type: "date" },
    { key: "valid_until", label: "Valid Until", type: "date" },
    { key: "total", label: "Total (INR)", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["draft", "sent", "won", "invoiced", "lost"] },
  ];
  return <DataTableShell title="Sales & Quotations" description="Lead → Quote → Win → Invoice pipeline." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="quotations" />;
}
