import { useEffect, useState } from "react";
import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { History, Sparkles, ScanLine, CheckCircle2, Loader2, Trash2 } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { toneFor } from "@/lib/statusTone";
import { useDepartments } from "@/components/DepartmentSelect";

const STATUS_TONE = { active: "success", on_leave: "warning", exited: "neutral" };

// Department master is loaded dynamically from /api/departments (see useDepartments() inside the component).

const ROLE_OPTIONS = [
  "project_manager", "site_engineer", "supervisor", "store_incharge",
  "accounts_executive", "hr_executive", "safety_officer", "purchase_officer",
  "dept_head", "technician",
];

const EMPLOYMENT_TYPE_OPTIONS = [
  { value: "permanent", label: "Permanent Worker" },
  { value: "daily_wages", label: "Daily Wages Worker" },
  { value: "contractual", label: "Contractual Worker" },
];

const GENDER_OPTIONS = ["Male", "Female", "Other", "Prefer not to say"];
const MARITAL_OPTIONS = ["Single", "Married", "Divorced", "Widowed"];
const BLOOD_GROUP_OPTIONS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-", "Unknown"];
const RELATION_OPTIONS = ["Father", "Mother", "Spouse", "Son", "Daughter", "Brother", "Sister", "Other"];

export default function Employees() {
  const r = useResource("employees");
  const DEPARTMENT_OPTIONS = useDepartments();
  const [histOpen, setHistOpen] = useState(false);
  const [histRows, setHistRows] = useState([]);
  const [histFor, setHistFor] = useState(null);

  const openHistory = async (row) => {
    setHistFor(row);
    setHistOpen(true);
    try {
      const { data } = await api.get(`/allocation/history?employee_id=${row.id}`);
      setHistRows(data || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load history");
      setHistRows([]);
    }
  };

  const renderDepts = (row) => {
    const ds = Array.isArray(row.departments) && row.departments.length
      ? row.departments
      : (row.department ? [row.department] : []);
    if (ds.length === 0) return "—";
    return (
      <div className="flex flex-wrap gap-1">
        {ds.map((d) => <StatusBadge key={d} text={d} tone="primary" />)}
      </div>
    );
  };

  const columns = [
    { key: "employee_id", label: "Emp ID", render: (row) => row.employee_id || row.emp_code || "—" },
    { key: "name", label: "Name" },
    { key: "designation", label: "Designation" },
    { key: "employment_type", label: "Type", render: (row) => {
      const v = row.employment_type || "permanent";
      const labels = { permanent: "Permanent", daily_wages: "Daily Wages", contractual: "Contractual" };
      const tone = { permanent: "primary", daily_wages: "warning", contractual: "neutral" }[v] || "neutral";
      return <StatusBadge text={labels[v] || v} tone={tone} />;
    }},
    { key: "role", label: "Role", render: (row) => (row.role || "").replaceAll("_", " ") },
    { key: "departments", label: "Departments", render: renderDepts },
    { key: "reporting_manager", label: "Reports To" },
    { key: "phone", label: "Phone" },
    { key: "joining_date", label: "Joined" },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status || "active", tone: toneFor(STATUS_TONE, row.status, "neutral") }) },
    {
      key: "_history",
      label: "History",
      render: (row) => (
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openHistory(row)} data-testid={`employees-history-${row.id}`}>
          <History className="h-3.5 w-3.5 mr-1" /> Log
        </Button>
      ),
    },
  ];

  const fields = [
    // ─── Identity & Role ───
    { key: "_sec_identity", type: "section", label: "Identity & Role", hint: "Basic employment record" },
    { key: "employee_id", label: "Employee ID (auto)" },
    { key: "emp_code", label: "Legacy Emp Code" },
    { key: "name", label: "Full Name", full: true, required: true },
    { key: "designation", label: "Designation" },
    { key: "employment_type", label: "Employment Type", type: "select", options: EMPLOYMENT_TYPE_OPTIONS, required: true, help: "Permanent / Daily Wages / Contractual" },
    { key: "role", label: "System Role", type: "select", options: ROLE_OPTIONS },
    { key: "departments", label: "Departments", type: "multiselect", options: DEPARTMENT_OPTIONS, full: true },
    { key: "allow_multi_dept", label: "Multi-Department Allowed", type: "checkbox", checkboxLabel: "May belong to >1 department" },
    { key: "reporting_manager", label: "Reporting Manager" },
    { key: "branch", label: "Branch / Office" },
    { key: "joining_date", label: "Joining Date", type: "date" },
    { key: "salary", label: "Monthly Salary (₹)", type: "number", help: "For Permanent / Contractual. Daily wagers use Daily Rate below." },

    // ─── Contact ───
    { key: "_sec_contact", type: "section", label: "Contact" },
    { key: "email", label: "Email" },
    { key: "phone", label: "Mobile Phone", required: true },
    { key: "alt_phone", label: "Alternate Phone" },
    { key: "current_address", label: "Current Address", type: "textarea", full: true },
    { key: "permanent_address", label: "Permanent Address", type: "textarea", full: true },

    // ─── Personal (Indian compliance demographics) ───
    { key: "_sec_personal", type: "section", label: "Personal Details" },
    { key: "dob", label: "Date of Birth", type: "date", help: "Used for retirement age (58y) and minor-employment compliance." },
    { key: "gender", label: "Gender", type: "select", options: GENDER_OPTIONS },
    { key: "marital_status", label: "Marital Status", type: "select", options: MARITAL_OPTIONS },
    { key: "blood_group", label: "Blood Group", type: "select", options: BLOOD_GROUP_OPTIONS },
    { key: "father_name", label: "Father's Name" },
    { key: "mother_name", label: "Mother's Name" },
    { key: "is_disabled", label: "Person with Disability (PwD)", type: "checkbox", checkboxLabel: "Yes — eligible for statutory benefits" },

    // ─── Legal Compliance (Indian Statutory IDs) ───
    { key: "_sec_legal", type: "section", label: "Legal Compliance — Indian Statutory IDs", hint: "PAN, Aadhaar, UAN, PF, ESIC" },
    { key: "pan_number", label: "PAN Number", help: "Format: ABCDE1234F (10 chars)" },
    { key: "aadhaar_number", label: "Aadhaar Number", help: "12 digits — masked in exports" },
    { key: "uan", label: "UAN (Universal Account Number)", help: "12-digit PF UAN issued by EPFO" },
    { key: "pf_account", label: "PF Account Number" },
    { key: "esic_number", label: "ESIC IP Number", help: "10-digit Insurance Person No. or 17-digit ESIC Identity No. (Employee State Insurance)" },
    { key: "is_pf_applicable", label: "PF Applicable", type: "checkbox", checkboxLabel: "Eligible for EPF (basic ≤ ₹15,000 or voluntary)" },
    { key: "is_esic_applicable", label: "ESIC Applicable", type: "checkbox", checkboxLabel: "Gross salary ≤ ₹21,000" },

    // ─── Banking (for salary credit) ───
    { key: "_sec_banking", type: "section", label: "Bank Account (for Salary)" },
    { key: "bank_name", label: "Bank Name" },
    { key: "bank_account_no", label: "Account Number" },
    { key: "bank_ifsc", label: "IFSC Code", help: "11 chars, e.g. SBIN0001234" },
    { key: "bank_branch", label: "Branch" },

    // ─── Emergency Contact + Nominee ───
    { key: "_sec_emergency", type: "section", label: "Emergency Contact & Nominee" },
    { key: "emergency_contact_name", label: "Emergency Contact Name" },
    { key: "emergency_contact_phone", label: "Emergency Contact Phone" },
    { key: "emergency_contact_relation", label: "Relation", type: "select", options: RELATION_OPTIONS },
    { key: "nominee_name", label: "Nominee Name (PF/Gratuity)" },
    { key: "nominee_relation", label: "Nominee Relation", type: "select", options: RELATION_OPTIONS },
    { key: "nominee_share_pct", label: "Nominee Share %", type: "number" },

    // ─── Daily Wages (conditional) ───
    { key: "_sec_daily", type: "section", label: "Daily Wages Details",
      showIf: (f) => f.employment_type === "daily_wages" },
    { key: "daily_rate", label: "Daily Rate (₹)", type: "number",
      showIf: (f) => f.employment_type === "daily_wages",
      help: "Per-day wage as per Minimum Wages Act notification" },
    { key: "working_days_per_month", label: "Std. Working Days / Month", type: "number",
      showIf: (f) => f.employment_type === "daily_wages",
      help: "Used to project monthly earning (e.g. 26)" },

    // ─── Contractual (conditional) ───
    { key: "_sec_contract", type: "section", label: "Contractual Engagement",
      showIf: (f) => f.employment_type === "contractual" },
    { key: "contractor_name", label: "Contractor / Agency Name",
      showIf: (f) => f.employment_type === "contractual",
      help: "Name of the manpower contractor under CLRA Act, 1970" },
    { key: "contractor_license_no", label: "CLRA License Number",
      showIf: (f) => f.employment_type === "contractual",
      help: "Contract Labour (Regulation & Abolition) Act license" },
    { key: "contract_start_date", label: "Contract Start", type: "date",
      showIf: (f) => f.employment_type === "contractual" },
    { key: "contract_end_date", label: "Contract End", type: "date",
      showIf: (f) => f.employment_type === "contractual" },

    // ─── Status ───
    { key: "_sec_status", type: "section", label: "Status" },
    { key: "status", label: "Status", type: "select", options: ["active", "on_leave", "exited"] },
  ];

  // ─── AI Auto-fill state (lifted so the formHeader and onAfterCreate can share it) ───
  const [pendingDocs, setPendingDocs] = useState([]);  // [{id, doc_type, label, file, scanResult, employee_fields}]

  const attachPendingDocs = async (createdEmployee) => {
    if (!createdEmployee?.id || pendingDocs.length === 0) return;
    let attached = 0;
    for (const pd of pendingDocs) {
      try {
        const fd = new FormData();
        fd.append("file", pd.file);
        fd.append("doc_type", pd.doc_type);
        fd.append("label", pd.label || "");
        fd.append("scan_result_json", JSON.stringify(pd.scanResult));
        await api.post(`/hr/employees/${createdEmployee.id}/documents`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        attached += 1;
      } catch (e) {
        toast.error(apiErrorMessage(e, `Attach failed for ${pd.label}`));
      }
    }
    if (attached) toast.success(`Attached ${attached} scanned document(s) to ${createdEmployee.name}`);
    setPendingDocs([]);
  };

  const formHeader = (mode, form, setForm) => {
    if (mode !== "create") return null;
    return (
      <AIPrefillPanel
        pendingDocs={pendingDocs}
        setPendingDocs={setPendingDocs}
        form={form}
        setForm={setForm}
      />
    );
  };

  return (
    <>
      <DataTableShell
        title="Employees · HR Master"
        description="Full personnel record with department mappings, reporting hierarchy and allocation history."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={r.create}
        onUpdate={r.update}
        onDelete={r.remove}
        testidPrefix="employees"
        exportResource={r.exportResource}
        canWrite={r.canWrite}
        canDelete={r.canDelete}
        attachmentsParentType="employees"
        formHeader={formHeader}
        onAfterCreate={attachPendingDocs}
      />
      <EmployeeHistoryDialog
        open={histOpen}
        onOpenChange={setHistOpen}
        rows={histRows}
        employee={histFor}
      />
    </>
  );
}

function EmployeeHistoryDialog({ open, onOpenChange, rows, employee }) {
  const labelFor = (act) => {
    if (act === "department_move") return "Department change";
    if (act === "deployment_start") return "Deployed";
    if (act === "deployment_end") return "Withdrawn";
    return act || "—";
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            Allocation History — {employee?.name || "—"}
          </DialogTitle>
          <DialogDescription className="sr-only">Every department or project move recorded for this employee.</DialogDescription>
        </DialogHeader>
        <ul className="divide-y divide-border max-h-96 overflow-y-auto">
          {rows.length === 0 && <li className="text-center text-xs text-muted-foreground py-8">No history yet.</li>}
          {rows.map((h) => (
            <li key={h.id} className="py-2.5 text-sm" data-testid={`emp-history-${h.id}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold">{labelFor(h.action)}</div>
                <div className="text-[10px] text-muted-foreground">{(h.at || "").slice(0, 16).replace("T", " ")}</div>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {h.from && <span>From: <span className="font-mono-data text-foreground">{JSON.stringify(h.from)}</span> · </span>}
                <span>To: <span className="font-mono-data text-foreground">{JSON.stringify(h.to)}</span></span>
              </div>
              {h.actor_name && <div className="text-[10px] text-muted-foreground mt-0.5">by {h.actor_name}</div>}
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

const PREFILL_DOC_OPTIONS = [
  { value: "aadhaar", label: "Aadhaar Card" },
  { value: "pan", label: "PAN Card" },
  { value: "bank_passbook", label: "Bank Passbook / Statement" },
  { value: "uan_passbook", label: "UAN / EPF Passbook" },
  { value: "esic_card", label: "ESIC Card" },
  { value: "driving_license", label: "Driving License" },
  { value: "passport", label: "Passport" },
  { value: "voter_id", label: "Voter ID" },
];

function AIPrefillPanel({ pendingDocs, setPendingDocs, form, setForm }) {
  const [docType, setDocType] = useState("aadhaar");
  const [file, setFile] = useState(null);
  const [scanning, setScanning] = useState(false);

  const onScan = async () => {
    if (!file) { toast.error("Pick a document to scan"); return; }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", docType);
    setScanning(true);
    try {
      const r = await api.post("/hr/documents/scan-prefill", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const ef = r.data.employee_fields || {};
      // Merge into form — only fill empties, never overwrite existing values
      const merged = { ...form };
      let filled = 0;
      Object.entries(ef).forEach(([k, v]) => {
        if (merged[k] === undefined || merged[k] === "" || merged[k] === null) {
          merged[k] = v;
          filled += 1;
        }
      });
      setForm(merged);
      // Record pending doc so we can attach it to the employee after Save
      setPendingDocs((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          doc_type: docType,
          label: PREFILL_DOC_OPTIONS.find((o) => o.value === docType)?.label || docType,
          file,
          scanResult: r.data,
        },
      ]);
      setFile(null);
      // reset file input
      const inp = document.querySelector('[data-testid="emp-prefill-file"]');
      if (inp) inp.value = "";
      const skipped = Object.keys(ef).length - filled;
      toast.success(
        `Scanned ${PREFILL_DOC_OPTIONS.find((o) => o.value === docType)?.label || docType}: filled ${filled} field(s)`
        + (skipped > 0 ? ` · ${skipped} skipped (already set)` : "")
      );
    } catch (e) {
      toast.error(apiErrorMessage(e, "AI scan failed"));
    } finally {
      setScanning(false);
    }
  };

  const removeChip = (id) => setPendingDocs((p) => p.filter((d) => d.id !== id));

  return (
    <div className="bg-gradient-to-r from-violet-50 to-blue-50 border border-violet-200 rounded-sm p-3" data-testid="emp-prefill-panel">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="h-4 w-4 text-violet-700" />
        <div className="text-[11px] font-bold uppercase tracking-[0.15em] text-violet-900">
          AI Auto-fill from Documents
        </div>
        <span className="text-[10px] text-muted-foreground">Powered by Gemini · only empty fields are filled</span>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-[10px] uppercase tracking-wider">Doc Type</Label>
          <Select value={docType} onValueChange={setDocType}>
            <SelectTrigger className="h-9 w-56 rounded-sm" data-testid="emp-prefill-doctype">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PREFILL_DOC_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
          <Label className="text-[10px] uppercase tracking-wider">File (JPG / PNG / PDF)</Label>
          <Input
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="h-9 rounded-sm"
            data-testid="emp-prefill-file"
          />
        </div>
        <Button
          className="h-9 rounded-sm bg-violet-700 hover:bg-violet-800"
          onClick={onScan}
          disabled={!file || scanning}
          data-testid="emp-prefill-scan"
        >
          {scanning ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Scanning…</>
                    : <><ScanLine className="h-4 w-4 mr-1.5" /> Scan & Fill</>}
        </Button>
      </div>

      {pendingDocs.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-violet-200">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-1 self-center">Will be attached on save:</span>
          {pendingDocs.map((d) => (
            <Badge key={d.id} variant="outline" className="rounded-sm bg-white border-violet-300 text-violet-900 gap-1 pr-1" data-testid={`emp-prefill-chip-${d.doc_type}`}>
              <CheckCircle2 className="h-3 w-3" /> {d.label}
              <button onClick={() => removeChip(d.id)} className="ml-1 hover:text-red-600">
                <Trash2 className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
