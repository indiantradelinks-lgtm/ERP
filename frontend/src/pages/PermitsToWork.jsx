import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";

const PTW_STATUS_TONE = { open: "warning", closed: "success", revoked: "danger" };

export default function PermitsToWork() {
  const r = useResource("ptws");
  const columns = [
    { key: "ptw_no", label: "PTW #" },
    { key: "work_type", label: "Work Type" },
    { key: "location", label: "Location" },
    { key: "project", label: "Project" },
    { key: "valid_from", label: "Valid From" },
    { key: "valid_to", label: "Valid To" },
    { key: "issued_to", label: "Issued To" },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status, tone: toneFor(PTW_STATUS_TONE, row.status, "info") }) },
  ];
  const fields = [
    { key: "ptw_no", label: "PTW Number" },
    { key: "work_type", label: "Work Type", type: "select", options: ["hot_work", "confined_space", "working_at_height", "electrical", "excavation", "lifting", "general"] },
    { key: "location", label: "Location" },
    { key: "project", label: "Project Code" },
    { key: "valid_from", label: "Valid From", type: "date" },
    { key: "valid_to", label: "Valid To", type: "date" },
    { key: "issued_to", label: "Issued To" },
    { key: "issued_by", label: "Issued By" },
    { key: "precautions", label: "Precautions", type: "textarea", full: true },
    { key: "status", label: "Status", type: "select", options: ["draft", "open", "closed", "revoked"] },
  ];
  return <DataTableShell title="Permits to Work (PTW)" description="Hot work, confined-space, working-at-height, and other safety-critical authorisations." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="ptw" exportResource="ptws" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="safety" />;
}
