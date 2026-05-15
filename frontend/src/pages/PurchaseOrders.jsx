import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function PurchaseOrders() {
  const r = useResource("purchase-orders");
  const columns = [
    { key: "po_number", label: "PO #" },
    { key: "vendor", label: "Vendor" },
    { key: "project", label: "Project" },
    { key: "date", label: "Date" },
    { key: "total", label: "Total", render: (r) => "₹ " + Number(r.total || 0).toLocaleString("en-IN") },
    { key: "paid", label: "Paid", render: (r) => (r.paid ? "Yes" : "No") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "approved" ? "success" : r.status === "rejected" ? "danger" : r.status === "received" ? "info" : "warning" }) },
  ];
  const fields = [
    { key: "po_number", label: "PO Number" },
    { key: "vendor", label: "Vendor Name", full: true },
    { key: "project", label: "Project" },
    { key: "date", label: "Date", type: "date" },
    { key: "total", label: "Total (INR)", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["draft", "pending", "approved", "rejected", "received"] },
    { key: "paid", label: "Paid (true/false)", type: "select", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] },
  ];
  return <DataTableShell title="Purchase Orders" description="Requisition → RFQ → PO → GRN. Multi-level approvals." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="purchase" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />;
}
