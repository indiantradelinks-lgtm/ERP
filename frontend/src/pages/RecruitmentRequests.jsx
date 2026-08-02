import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";

const RECRUIT_STATUS_TONE = { filled: "success", closed: "neutral" };

export default function RecruitmentRequests() {
  const r = useResource("recruitment-requests");
  const columns = [
    { key: "position", label: "Position" },
    { key: "project", label: "Project", render: (row) => row.project || row.project_code || "—" },
    { key: "source", label: "Source", badge: (row) => row.source === "project_request"
        ? { text: "Project Request", tone: "info" }
        : { text: "Manual", tone: "neutral" } },
    { key: "vacancies", label: "Vacancies" },
    { key: "hired", label: "Hired", badge: (row) => ({ text: `${row.hired || 0} / ${row.vacancies || 0}`, tone: (row.hired || 0) >= (row.vacancies || 0) && row.vacancies ? "success" : "warning" }) },
    { key: "budget_monthly_per_head", label: "Budget/Head", render: (row) => row.budget_monthly_per_head ? `₹${Number(row.budget_monthly_per_head).toLocaleString("en-IN")}/mo` : "—" },
    { key: "needed_by", label: "Needed By" },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status || "open", tone: toneFor(RECRUIT_STATUS_TONE, row.status, "warning") }) },
  ];
  const fields = [
    { key: "position", label: "Position Title" },
    { key: "department", label: "Department" },
    { key: "project", label: "Project / Site" },
    { key: "vacancies", label: "Vacancies", type: "number" },
    { key: "hired", label: "Hired So Far", type: "number" },
    { key: "skill_set", label: "Required Skills", full: true },
    { key: "experience_yrs", label: "Min. Experience (yrs)", type: "number" },
    { key: "needed_by", label: "Needed By", type: "date" },
    { key: "raised_by", label: "Raised By" },
    { key: "justification", label: "Business Justification", type: "textarea", full: true },
    { key: "status", label: "Status", type: "select", options: ["open", "shortlisting", "interview", "offer", "filled", "closed"] },
  ];
  return <DataTableShell title="Recruitment Requests" description="Hiring requisitions raised by departments / project managers." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="recruit" exportResource="recruitment-requests" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="documents" />;
}
