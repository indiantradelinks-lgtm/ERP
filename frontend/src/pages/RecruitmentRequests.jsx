import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";

const RECRUIT_STATUS_TONE = { filled: "success", closed: "neutral" };

export default function RecruitmentRequests() {
  const r = useResource("recruitment-requests");
  const columns = [
    { key: "position", label: "Position" },
    { key: "department", label: "Department" },
    { key: "project", label: "Project" },
    { key: "vacancies", label: "Vacancies" },
    { key: "skill_set", label: "Skills" },
    { key: "needed_by", label: "Needed By" },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status || "open", tone: toneFor(RECRUIT_STATUS_TONE, row.status, "warning") }) },
  ];
  const fields = [
    { key: "position", label: "Position Title" },
    { key: "department", label: "Department" },
    { key: "project", label: "Project / Site" },
    { key: "vacancies", label: "Vacancies", type: "number" },
    { key: "skill_set", label: "Required Skills", full: true },
    { key: "experience_yrs", label: "Min. Experience (yrs)", type: "number" },
    { key: "needed_by", label: "Needed By", type: "date" },
    { key: "raised_by", label: "Raised By" },
    { key: "justification", label: "Business Justification", type: "textarea", full: true },
    { key: "status", label: "Status", type: "select", options: ["open", "shortlisting", "interview", "offer", "filled", "closed"] },
  ];
  return <DataTableShell title="Recruitment Requests" description="Hiring requisitions raised by departments / project managers." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="recruit" exportResource="recruitment-requests" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="documents" />;
}
