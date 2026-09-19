import { useEffect, useState } from "react";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";
import { api } from "@/lib/api";

const ASSET_STATUS_TONE = { in_use: "success", maintenance: "warning", disposed: "danger" };

export default function Assets() {
  const r = useResource("assets");
  const [catOptions, setCatOptions] = useState(["Machinery and Equipment", "Vehicle/Logistics Items", "IT Items", "Tools and Tackles", "Office Furniture"]);

  useEffect(() => {
    api.get("/inv/categories")
      .then((res) => {
        const names = (res.data || []).filter((c) => c.active !== false).map((c) => c.name).filter(Boolean);
        if (names.length) setCatOptions(names);
      })
      .catch(() => {});
  }, []);

  const columns = [
    { key: "asset_id", label: "Asset ID" },
    { key: "name", label: "Asset" },
    { key: "category", label: "Category" },
    { key: "purchase_date", label: "Purchased" },
    { key: "cost", label: "Cost", render: (r) => "₹ " + Number(r.cost || 0).toLocaleString("en-IN") },
    { key: "location", label: "Location" },
    { key: "assigned_to", label: "Assigned To" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: toneFor(ASSET_STATUS_TONE, r.status, "neutral") }) },
  ];
  const fields = [
    { key: "asset_id", label: "Asset ID" },
    { key: "name", label: "Asset Name", full: true },
    { key: "category", label: "Category", type: "select", options: catOptions },
    { key: "purchase_date", label: "Purchase Date", type: "date" },
    { key: "cost", label: "Cost (INR)", type: "number" },
    { key: "location", label: "Location" },
    { key: "assigned_to", label: "Assigned To" },
    { key: "depreciation_rate", label: "Depreciation %", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["available", "in_use", "maintenance", "disposed"] },
  ];
  return <DataTableShell title="Asset Management" description="Equipment register, allocation, maintenance and depreciation. Categories come from the unified Item Category Master." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="assets" exportResource={r.exportResource} canWrite={r.canWrite} pagination={r.pagination} canDelete={r.canDelete} attachmentsParentType="assets" />;
}
