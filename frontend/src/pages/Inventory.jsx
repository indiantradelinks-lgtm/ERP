import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Inventory() {
  const r = useResource("inventory");
  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Item" },
    { key: "category", label: "Category", render: (r) => (r.category || "").replaceAll("_", " ") },
    { key: "uom", label: "UOM" },
    { key: "quantity", label: "Qty" },
    { key: "min_stock", label: "Min" },
    { key: "rate", label: "Rate", render: (r) => "₹ " + Number(r.rate || 0).toLocaleString("en-IN") },
    { key: "location", label: "Location" },
    {
      key: "_alert",
      label: "Stock",
      render: (r) => Number(r.quantity || 0) < Number(r.min_stock || 0)
        ? <StatusBadge text="Low" tone="danger" />
        : <StatusBadge text="OK" tone="success" />,
    },
  ];
  const fields = [
    { key: "code", label: "Item Code" },
    { key: "name", label: "Item Name", full: true },
    { key: "category", label: "Category", type: "select", options: ["scaffolding", "painting", "rope_access", "roof_sheeting", "ppe", "consumables"] },
    { key: "uom", label: "UOM (nos/meter/kg)" },
    { key: "quantity", label: "Quantity", type: "number" },
    { key: "min_stock", label: "Min Stock", type: "number" },
    { key: "rate", label: "Rate (INR)", type: "number" },
    { key: "location", label: "Location" },
  ];
  return <DataTableShell title="Inventory & Stores" description="Material master with reorder points and location." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="inventory" />;
}
