import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function PpeIssuance() {
  const r = useResource("ppe-issuance");
  const columns = [
    { key: "employee", label: "Employee" },
    { key: "item_type", label: "PPE Type" },
    { key: "size", label: "Size" },
    { key: "issue_date", label: "Issued" },
    { key: "expiry_date", label: "Expiry" },
    { key: "issued_by", label: "Issued By" },
    { key: "qty", label: "Qty" },
  ];
  const fields = [
    { key: "employee", label: "Employee" },
    { key: "item_type", label: "PPE Type", type: "select", options: ["helmet", "safety_shoes", "gloves", "harness", "goggles", "respirator", "ear_plugs", "high_vis_jacket", "fr_coverall"] },
    { key: "size", label: "Size" },
    { key: "qty", label: "Quantity", type: "number" },
    { key: "issue_date", label: "Issue Date", type: "date" },
    { key: "expiry_date", label: "Expiry Date", type: "date" },
    { key: "issued_by", label: "Issued By" },
    { key: "remarks", label: "Remarks", type: "textarea", full: true },
  ];
  return <DataTableShell title="PPE Issuance Register" description="Track personal protective equipment issued to each employee with expiry alerts." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="ppe" exportResource="ppe-issuance" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="safety" />;
}
