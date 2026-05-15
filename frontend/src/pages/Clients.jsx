import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Clients() {
  const r = useResource("clients");
  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Client" },
    { key: "contact", label: "Contact" },
    { key: "phone", label: "Phone" },
    { key: "gst", label: "GSTIN" },
    { key: "credit_limit", label: "Credit Limit", render: (r) => "₹ " + Number(r.credit_limit || 0).toLocaleString("en-IN") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status || "active", tone: r.status === "active" ? "success" : "neutral" }) },
  ];
  const fields = [
    { key: "code", label: "Client Code" },
    { key: "name", label: "Client Name", full: true },
    { key: "contact", label: "Contact Person" },
    { key: "email", label: "Email" },
    { key: "phone", label: "Phone" },
    { key: "gst", label: "GSTIN" },
    { key: "address", label: "Address", full: true, type: "textarea" },
    { key: "credit_limit", label: "Credit Limit", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["active", "inactive", "on_hold"] },
  ];
  return (
    <DataTableShell
      title="Client Management"
      description="Industrial accounts, GST, credit limits and contract anchors."
      data={r.data}
      columns={columns}
      fields={fields}
      onCreate={r.create}
      onUpdate={r.update}
      onDelete={r.remove}
      testidPrefix="clients" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete}
    />
  );
}
