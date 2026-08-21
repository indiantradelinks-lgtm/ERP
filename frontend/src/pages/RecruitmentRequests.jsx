import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const RECRUIT_STATUS_TONE = { filled: "success", closed: "neutral" };

export default function RecruitmentRequests() {
  const r = useResource("recruitment-requests");
  const [projMap, setProjMap] = useState({});
  useEffect(() => {
    api.get("/projects").then((res) => {
      const m = {};
      (res.data || []).forEach((p) => {
        const info = { code: p.code || p.project_code, name: p.name, manager: p.manager || p.manager_name || p.project_manager };
        if (info.code) m[info.code] = info;
        if (p.id) m[p.id] = info;
      });
      setProjMap(m);
    }).catch(() => {});
  }, []);
  const projInfo = (row) => projMap[row.project_code] || projMap[row.project_id] || projMap[row.project] || null;
  const columns = [
    { key: "position", label: "Position" },
    {
      key: "project", label: "Project",
      render: (row) => {
        const p = projInfo(row);
        const code = p?.code || row.project_code || row.project;
        if (!code) return "—";
        return (
          <div data-testid={`recruit-project-${row.id}`}>
            <div className="font-medium">{code}</div>
            {p?.name && <div className="text-[11px] text-muted-foreground max-w-[200px] truncate" title={p.name}>{p.name}</div>}
          </div>
        );
      },
    },
    {
      key: "project_user", label: "Project User",
      render: (row) => {
        const p = projInfo(row);
        return <span data-testid={`recruit-project-user-${row.id}`}>{p?.manager || row.raised_by || "—"}</span>;
      },
    },
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
