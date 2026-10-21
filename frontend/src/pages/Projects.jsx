import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import useSiteOptions from "@/hooks/useSiteOptions";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Users } from "lucide-react";
import { toneFor } from "@/lib/statusTone";
import { api } from "@/lib/api";

const PROJECT_STATUS_TONE = {
  draft: "neutral", planned: "warning", approved: "info", mobilization_pending: "warning",
  active: "success", on_hold: "warning", completed: "info",
  closure_pending: "warning", closed: "neutral", cancelled: "neutral",
};

export default function Projects() {
  const navigate = useNavigate();
  const r = useResource("projects");
  const siteOptions = useSiteOptions();
  const [serviceTypes, setServiceTypes] = useState([]);
  useEffect(() => {
    api.get("/proj-masters/service-types?active_only=true")
      .then((res) => setServiceTypes(res.data))
      .catch(() => {});
  }, []);
  const serviceTypeOptions = serviceTypes.map((s) => ({ value: s.id, label: `${s.code} · ${s.name}` }));

  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Project" },
    { key: "client", label: "Client" },
    { key: "service_type_name", label: "Service",
      render: (r) => {
        const st = serviceTypes.find((s) => s.id === r.service_type_id);
        return st ? `${st.code} · ${st.name}` : (r.type || "").replaceAll("_", " ");
      } },
    { key: "site", label: "Site" },
    { key: "manager", label: "Manager",
      render: (r) => r.project_manager_name || r.manager || <span className="text-muted-foreground">—</span> },
    { key: "contract_value", label: "Contract Value",
      render: (r) => "₹ " + Number(r.contract_value || r.budget || 0).toLocaleString("en-IN") },
    {
      key: "progress",
      label: "Progress",
      render: (r) => (
        <div className="w-32">
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-muted-foreground">{r.progress || 0}%</span>
          </div>
          <Progress value={r.progress || 0} className="h-1.5" />
        </div>
      ),
    },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: toneFor(PROJECT_STATUS_TONE, r.status, "neutral") }) },
    {
      key: "_mp",
      label: "Manpower",
      render: (row) => (
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => navigate(`/app/projects/${encodeURIComponent(row.code)}/manpower`)} data-testid={`projects-manpower-${row.id}`}>
          <Users className="h-3.5 w-3.5 mr-1" /> View
        </Button>
      ),
    },
  ];
  const fields = [
    { key: "_section_basic", type: "section", label: "1 · Project Basics" },
    { key: "code", label: "Project Code" },
    { key: "name", label: "Project Name", full: true },
    { key: "_section_client", type: "section", label: "2 · Client Details" },
    { key: "client_code", label: "Client Code" },
    { key: "client", label: "Client Name" },
    { key: "client_contact_person", label: "Client Contact Person" },
    { key: "client_contact_number", label: "Client Contact Number" },
    { key: "client_email", label: "Client Email" },
    { key: "billing_address", label: "Billing Address", type: "textarea", full: true },
    { key: "_section_site", type: "section", label: "3 · Site Details" },
    { key: "site_id", label: "Customer Site (Master)", type: "select", options: siteOptions },
    { key: "site_address", label: "Site Address", type: "textarea", full: true },
    { key: "site", label: "Site Location" },
    { key: "state", label: "State" },
    { key: "city", label: "City" },
    { key: "_section_service", type: "section", label: "4 · Service / Scope" },
    { key: "service_type_id", label: "Service Type (Master)", type: "select", options: serviceTypeOptions,
      help: "Select from the Service Type Master — drives default rate, UOM and SLA." },
    { key: "type", label: "Service Category", type: "select",
      options: ["scaffolding", "painting", "roof_sheeting", "rope_access", "manpower_supply", "material_supply", "composite_work", "other"] },
    { key: "_section_sales", type: "section", label: "5 · Sales & Work Order Linkage" },
    { key: "sales_quotation_ref", label: "Sales Quotation Reference" },
    { key: "work_order_number", label: "Work Order Number" },
    { key: "work_order_date", label: "Work Order Date", type: "date" },
    { key: "work_order_value", label: "Work Order Value (INR)", type: "number" },
    { key: "contract_value", label: "Contract Value (INR)", type: "number" },
    { key: "_section_commercial", type: "section", label: "6 · Commercial Terms" },
    { key: "gst_applicability", label: "GST Applicability", type: "select", options: ["applicable", "not_applicable", "exempt"] },
    { key: "tds_applicability", label: "TDS Applicability", type: "select", options: ["applicable", "not_applicable"] },
    { key: "retention_percentage", label: "Retention %", type: "number" },
    { key: "mobilization_advance", label: "Mobilization Advance (INR)", type: "number" },
    { key: "payment_terms", label: "Payment Terms", type: "textarea", full: true },
    { key: "billing_frequency", label: "Billing Frequency", type: "select",
      options: ["weekly", "fortnightly", "monthly", "milestone", "completion"] },
    { key: "monthly_billing_amount", label: "Monthly Billing Amount (AMC/ARC)", type: "number",
      help: "Fixed amount billed every month for AMC / ARC projects. Left blank, the ERP spreads the Contract Value over the project months." },
    { key: "billing_milestone_count", label: "Total Billing Milestones", type: "number" },
    { key: "_section_schedule", type: "section", label: "7 · Schedule" },
    { key: "start_date", label: "Project Start Date", type: "date" },
    { key: "end_date", label: "Target Completion Date", type: "date" },
    { key: "actual_completion_date", label: "Actual Completion Date", type: "date" },
    { key: "_section_team", type: "section", label: "8 · Team" },
    { key: "manager", label: "Project Manager" },
    { key: "site_supervisor", label: "Site Incharge" },
    { key: "safety_officer", label: "Safety Officer" },
    { key: "store_incharge", label: "Store / Site-Store Incharge" },
    { key: "material_coordinator", label: "Material Coordinator" },
    { key: "client_engineer", label: "Client Engineer-in-Charge" },
    { key: "_section_status", type: "section", label: "9 · Status & Classification" },
    { key: "status", label: "Project Status", type: "select",
      options: ["draft", "planned", "approved", "mobilization_pending", "active", "on_hold", "completed", "closure_pending", "closed", "cancelled"] },
    { key: "priority", label: "Project Priority", type: "select",
      options: ["normal", "urgent", "shutdown", "emergency"] },
    { key: "category", label: "Project Category", type: "select",
      options: ["short_term", "long_term", "shutdown", "amc_arc", "one_time"],
      help: "Drives billing: AMC/ARC bills month-wise for the whole project validity; every other category bills against the project scope / timeline." },
    { key: "labour_licence_required", label: "Labour Licence Required", type: "select",
      options: [{ value: "yes", label: "Yes" }, { value: "no", label: "No" }],
      help: "Does this project need a Labour Licence (CLRA) before mobilisation?" },
    { key: "progress", label: "Progress %", type: "number" },
    { key: "_section_scope", type: "section", label: "10 · Scope & Notes" },
    { key: "scope_summary", label: "Scope Summary", type: "textarea", full: true },
    { key: "remarks", label: "Remarks", type: "textarea", full: true },
  ];
  return <DataTableShell title="Projects" description="Active sites, scopes, budgets and progress." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="projects" exportResource={r.exportResource} canWrite={r.canWrite} pagination={r.pagination} canDelete={r.canDelete} attachmentsParentType="projects" />;
}
