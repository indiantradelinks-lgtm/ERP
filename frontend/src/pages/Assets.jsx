import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Assets() {
  const r = useResource("assets");
  const columns = [
    { key: "asset_id", label: "Asset ID" },
    { key: "name", label: "Asset" },
    { key: "category", label: "Category" },
    { key: "purchase_date", label: "Purchased" },
    { key: "cost", label: "Cost", render: (r) => "₹ " + Number(r.cost || 0).toLocaleString("en-IN") },
    { key: "location", label: "Location" },
    { key: "assigned_to", label: "Assigned To" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "in_use" ? "success" : r.status === "maintenance" ? "warning" : r.status === "disposed" ? "danger" : "neutral" }) },
  ];
  const fields = [
    { key: "asset_id", label: "Asset ID" },
    { key: "name", label: "Asset Name", full: true },
    { key: "category", label: "Category", type: "select", options: ["equipment", "vehicle", "it", "tools"] },
    { key: "purchase_date", label: "Purchase Date", type: "date" },
    { key: "cost", label: "Cost (INR)", type: "number" },
    { key: "location", label: "Location" },
    { key: "assigned_to", label: "Assigned To" },
    { key: "depreciation_rate", label: "Depreciation %", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["available", "in_use", "maintenance", "disposed"] },
  ];
  return <DataTableShell title="Asset Management" description="Equipment register, allocation, maintenance and depreciation." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="assets" />;
}
