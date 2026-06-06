import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";

const CANDIDATE_STAGE_TONE = { hired: "success", rejected: "danger", offered: "primary" };

export default function Candidates() {
  const r = useResource("candidates");
  const columns = [
    { key: "name", label: "Name" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email" },
    { key: "position", label: "Position" },
    { key: "experience_yrs", label: "Exp" },
    { key: "stage", label: "Stage", badge: (row) => ({ text: row.stage || "applied", tone: toneFor(CANDIDATE_STAGE_TONE, row.stage, "warning") }) },
  ];
  const fields = [
    { key: "name", label: "Full Name" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email" },
    { key: "position", label: "Position Applied" },
    { key: "experience_yrs", label: "Experience (yrs)", type: "number" },
    { key: "current_company", label: "Current Company" },
    { key: "expected_ctc", label: "Expected CTC (INR)", type: "number" },
    { key: "source", label: "Source", type: "select", options: ["referral", "linkedin", "naukri", "indeed", "agency", "walk_in", "other"] },
    { key: "stage", label: "Stage", type: "select", options: ["applied", "shortlisted", "interview", "offered", "hired", "rejected"] },
    { key: "notes", label: "Notes", type: "textarea", full: true },
  ];
  return <DataTableShell title="Candidate Database" description="Applicants and interview pipeline." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="candidates" exportResource="candidates" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="documents" />;
}
