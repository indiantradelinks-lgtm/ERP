import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Vendors() {
  const r = useResource("vendors");
  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Vendor" },
    { key: "category", label: "Category" },
    { key: "contact", label: "Contact" },
    { key: "phone", label: "Phone" },
    { key: "rating", label: "Rating", render: (r) => "★ " + (r.rating ?? "—") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status || "pending", tone: r.status === "approved" ? "success" : r.status === "rejected" ? "danger" : "warning" }) },
  ];
  const fields = [
    { key: "code", label: "Vendor Code" },
    { key: "name", label: "Vendor Name", full: true },
    { key: "category", label: "Category", type: "select", options: ["material", "service", "ppe", "paint", "rope_access", "transport"] },
    { key: "contact", label: "Contact" },
    { key: "email", label: "Email" },
    { key: "phone", label: "Phone" },
    { key: "gst", label: "GSTIN" },
    { key: "rating", label: "Rating (1-5)", type: "number" },
    { key: "status", label: "Approval Status", type: "select", options: ["pending", "approved", "rejected"] },
  ];
  return (
    <DataTableShell title="Vendor Management" description="Approved supplier base, compliance and performance ratings." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="vendors" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />
  );
}
