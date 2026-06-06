import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { LayoutGrid, XCircle, Upload, Download } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { toneFor } from "@/lib/statusTone";

const DEPLOYMENT_STATUS_TONE = { active: "success", completed: "neutral", planned: "info", withdrawn: "danger" };

const SITE_ROLE_OPTIONS = [
  "site_engineer", "supervisor", "safety_officer", "store_incharge",
  "logistics_coordinator", "rigger", "scaffolder", "painter", "rope_access_tech",
  "helper", "electrician", "welder", "foreman",
];

const SHIFT_OPTIONS = ["day", "night", "general", "rotational"];

export default function Deployments() {
  const navigate = useNavigate();
  const r = useResource("deployments");
  const [employees, setEmployees] = useState([]);
  const [projects, setProjects] = useState([]);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    api.get("/employees").then((res) => setEmployees(res.data || [])).catch(() => {});
    api.get("/projects").then((res) => setProjects(res.data || [])).catch(() => {});
  }, []);

  const endDeployment = async (row) => {
    if (!window.confirm(`End deployment ${row.deployment_no || row.id} for ${row.employee}?`)) return;
    try {
      await api.post(`/deployments/${row.id}/end`, {});
      toast.success("Deployment ended");
      r.reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to end deployment");
    }
  };

  const openProjectMP = (row) => {
    const code = row.project;
    if (!code) return;
    navigate(`/app/projects/${encodeURIComponent(code)}/manpower`);
  };

  const columns = [
    { key: "deployment_no", label: "Dep #" },
    { key: "employee", label: "Employee" },
    { key: "site_role", label: "Role on Site", render: (row) => (row.site_role || row.role || "").replaceAll("_", " ") },
    { key: "project", label: "Project" },
    { key: "site", label: "Site" },
    { key: "shift", label: "Shift" },
    { key: "start_date", label: "Start" },
    { key: "end_date", label: "End" },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status || "active", tone: toneFor(DEPLOYMENT_STATUS_TONE, row.status, "warning") }) },
    {
      key: "_act",
      label: "Action",
      render: (row) => (
        <div className="inline-flex gap-1">
          <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openProjectMP(row)} data-testid={`deployments-mp-${row.id}`}>
            <LayoutGrid className="h-3.5 w-3.5 mr-1" /> Manpower
          </Button>
          {r.canWrite && row.status !== "completed" && row.status !== "withdrawn" && (
            <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => endDeployment(row)} data-testid={`deployments-end-${row.id}`}>
              <XCircle className="h-3.5 w-3.5 mr-1" /> End
            </Button>
          )}
        </div>
      ),
    },
  ];

  const fields = [
    { key: "employee", label: "Employee", type: "select", options: employees.map((e) => ({ value: e.name, label: `${e.name}${e.employee_id ? " · " + e.employee_id : ""}` })) },
    { key: "employee_id", label: "Linked Employee ID (auto-fill via Employee)", type: "select", options: employees.map((e) => ({ value: e.id, label: e.name })) },
    { key: "site_role", label: "Role on Site", type: "select", options: SITE_ROLE_OPTIONS },
    { key: "project", label: "Project", type: "select", options: projects.map((p) => ({ value: p.code, label: `${p.code} · ${p.name}` })) },
    { key: "site", label: "Site / Location" },
    { key: "shift", label: "Shift", type: "select", options: SHIFT_OPTIONS },
    { key: "start_date", label: "Start Date", type: "date" },
    { key: "end_date", label: "End Date", type: "date" },
    { key: "reporting_to", label: "Reporting To" },
    { key: "status", label: "Status", type: "select", options: ["planned", "active", "completed", "withdrawn"] },
  ];

  return (
    <>
      <DataTableShell
        title="Site Deployments"
        description="Allocate manpower to specific projects with role, shift and validity window. Visibility is auto-scoped per role."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={r.create}
        onUpdate={r.update}
        onDelete={r.remove}
        testidPrefix="deployments"
        exportResource="deployments"
        canWrite={r.canWrite}
        canDelete={r.canDelete}
        extraActions={r.canWrite ? (
          <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={() => setImportOpen(true)} data-testid="deployments-import-open">
            <Upload className="h-3.5 w-3.5 mr-1.5" /> Bulk Import
          </Button>
        ) : null}
      />
      {importOpen && <ImportDialog onClose={() => { setImportOpen(false); r.reload(); }} />}
    </>
  );
}

function ImportDialog({ onClose }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const download = async () => {
    try {
      const res = await api.get("/deployments/import-template", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = "site_teams_template.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(e.response?.data?.detail || "Template download failed"); }
  };

  const upload = async () => {
    if (!file) { toast.error("Pick a CSV file first"); return; }
    setBusy(true);
    try {
      const form = new FormData(); form.append("file", file);
      const { data } = await api.post("/deployments/import.csv", form, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`Created ${data.summary.created} · Pending ${data.summary.pending_approval} · Errors ${data.summary.errors}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm" data-testid="deployments-import-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Bulk Import — Site Teams</DialogTitle>
          <DialogDescription className="sr-only">Upload a CSV file to create deployments in bulk. Employees are resolved by code, email, or name; projects by code or name.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="bg-muted/30 border border-border rounded-sm p-3 text-xs space-y-1.5">
            <div className="text-[10px] uppercase tracking-wider text-primary font-bold">CSV format</div>
            <p className="text-muted-foreground">Columns: <code className="font-mono-data">employee_code, employee_email, employee_name, project, site_role, shift, site, start_date, end_date, reporting_to, status</code>. At least one of <em>employee_code/email/name</em> is required per row. <code>project</code> matches by code or name. Rows for non-HR users are queued for the 2-step deployment approval chain.</p>
            <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={download} data-testid="deployments-import-template">
              <Download className="h-3.5 w-3.5 mr-1.5" /> Download template
            </Button>
          </div>
          <div className="flex gap-2 items-center">
            <input type="file" accept=".csv,.tsv,.txt" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} className="text-sm" data-testid="deployments-import-file" />
            <Button className="rounded-sm h-9" onClick={upload} disabled={busy || !file} data-testid="deployments-import-go">
              <Upload className="h-4 w-4 mr-1.5" /> {busy ? "Uploading…" : "Import"}
            </Button>
          </div>
          {result && (
            <div className="border border-border rounded-sm p-3 space-y-2" data-testid="deployments-import-result">
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Created" value={result.summary.created} tone="success" />
                <Stat label="Pending Approval" value={result.summary.pending_approval} tone="info" />
                <Stat label="Errors" value={result.summary.errors} tone="danger" />
              </div>
              {result.errors?.length > 0 && (
                <div className="text-xs text-destructive max-h-32 overflow-y-auto">
                  <div className="font-bold mb-1">Errors</div>
                  <ul className="space-y-0.5">{result.errors.map((e, i) => <li key={`${e.row}-${i}`}>Row {e.row}: {e.error}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Stat({ label, value, tone = "neutral" }) {
  const c = { success: "text-success", danger: "text-destructive", info: "text-chart-3", neutral: "text-foreground" }[tone] || "text-foreground";
  return (
    <div className="bg-card border border-border rounded-sm p-2 text-center">
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-display font-black text-xl tabular ${c}`}>{value}</div>
    </div>
  );
}
