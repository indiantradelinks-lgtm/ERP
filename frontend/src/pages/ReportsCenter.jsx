import { useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FileText, CalendarRange, FolderDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const REPORTS = [
  // Sales
  { module: "Sales", key: "enquiries", label: "Enquiries", desc: "All sales enquiries", generic: true,
    statuses: ["open", "under_review", "submitted", "negotiation", "hold", "won", "lost"] },
  { module: "Sales", key: "quotations", label: "Quotations", desc: "Quotation register", generic: true },
  { module: "Sales", key: "followups", label: "Enquiry Follow-Ups", desc: "Follow-up tracker views", custom: "followups" },
  // Projects & Operations
  { module: "Projects & Operations", key: "projects", label: "Projects Master", desc: "All projects with PM & client", generic: true },
  { module: "Projects & Operations", key: "handovers", label: "Contract Handovers", desc: "Sales → Ops handovers", custom: "handovers",
    statuses: ["draft", "submitted", "allocated", "active", "on_hold"] },
  { module: "Projects & Operations", key: "resource-plan", label: "Resource Plan (per project)", desc: "Manpower / material / tools / sub-contract", custom: "resource-plan" },
  { module: "Projects & Operations", key: "documents", label: "Project Documents", desc: "Document register", generic: true },
  // HR
  { module: "Human Resources", key: "employees", label: "Employees Master", desc: "Employee records", generic: true },
  { module: "Human Resources", key: "attendance", label: "Attendance", desc: "Attendance entries", generic: true,
    statuses: ["present", "absent", "half_day", "leave", "week_off", "on_duty"] },
  { module: "Human Resources", key: "payroll", label: "Payroll", desc: "Payroll runs", generic: true },
  { module: "Human Resources", key: "candidates", label: "Candidates", desc: "Recruitment pipeline", generic: true },
  // Store & Inventory
  { module: "Store & Inventory", key: "inventory", label: "Inventory / Item Master", desc: "Stock items", generic: true },
  { module: "Store & Inventory", key: "assets", label: "Assets", desc: "Asset register", generic: true },
  // Procurement
  { module: "Procurement & Vendors", key: "purchase-orders", label: "Purchase Orders", desc: "PO register", generic: true },
  { module: "Procurement & Vendors", key: "vendors", label: "Vendors", desc: "Vendor master", generic: true },
  // Accounts
  { module: "Accounts & Finance", key: "journal-entries", label: "Journal Entries", desc: "Accounting entries", generic: true },
  { module: "Accounts & Finance", key: "approvals", label: "Approvals", desc: "Approval requests", generic: true,
    statuses: ["pending", "approved", "rejected"] },
  // Safety
  { module: "Safety", key: "safety-reports", label: "Safety Reports", desc: "Incidents & observations", generic: true },
  { module: "Safety", key: "ptws", label: "Permits to Work", desc: "PTW register", generic: true,
    statuses: ["open", "closed"] },
  // Logistics & Masters
  { module: "Logistics & Masters", key: "vehicles", label: "Vehicles", desc: "Fleet register", generic: true },
  { module: "Logistics & Masters", key: "clients", label: "Clients", desc: "Client master", generic: true },
];

const MODULES = [...new Set(REPORTS.map((r) => r.module))];

export default function ReportsCenter() {
  const { user } = useAuth();
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [statusMap, setStatusMap] = useState({});
  const [busy, setBusy] = useState("");
  const [projects, setProjects] = useState([]);
  const [rpProject, setRpProject] = useState("");
  const [rpType, setRpType] = useState("");
  const [fuView, setFuView] = useState("all");

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  const saveBlob = (data, filename) => {
    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  const download = async (report, fmt) => {
    const id = `${report.key}-${fmt}`;
    setBusy(id);
    try {
      let path, params = {};
      if (report.custom === "handovers") {
        path = `/ops/handovers/export/${fmt}`;
        if (statusMap[report.key]) params.status = statusMap[report.key];
      } else if (report.custom === "resource-plan") {
        if (!rpProject) { toast.error("Select a project first"); setBusy(""); return; }
        path = `/proj-phase2/resources/${rpProject}/export/${fmt}`;
        if (rpType) params.type = rpType;
      } else if (report.custom === "followups") {
        path = `/enquiry-followups/export.${fmt === "pdf" ? "xlsx" : fmt}`;
        params.view = fuView;
      } else {
        path = `/export/${report.key}.${fmt}`;
        if (statusMap[report.key]) params.status = statusMap[report.key];
        if (fromDate) params.from_date = fromDate;
        if (toDate) params.to_date = toDate;
      }
      const { data } = await api.get(path, { responseType: "blob", params });
      saveBlob(data, `${report.key}.${fmt === "pdf" && report.custom === "followups" ? "xlsx" : fmt}`);
      toast.success(`${report.label} downloaded`);
    } catch (e) {
      toast.error(e?.response?.status === 403 ? "You don't have permission for this report" : "Export failed");
    } finally { setBusy(""); }
  };

  return (
    <div className="space-y-6" data-testid="reports-center-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <FolderDown className="h-3 w-3" /> Reports
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Reports Center</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Every downloadable report in one place — branded Excel & PDF with logo, watermark and corporate footer.
            Date range applies to record creation date.
          </p>
        </div>
        <div className="flex items-end gap-2 bg-card border border-border rounded-sm p-3">
          <CalendarRange className="h-4 w-4 text-muted-foreground mb-2" />
          <div>
            <Label className="text-[10px] uppercase tracking-wider">From</Label>
            <Input type="date" className="h-8 rounded-sm mt-0.5 w-36" value={fromDate} onChange={(e) => setFromDate(e.target.value)} data-testid="rc-from-date" />
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">To</Label>
            <Input type="date" className="h-8 rounded-sm mt-0.5 w-36" value={toDate} onChange={(e) => setToDate(e.target.value)} data-testid="rc-to-date" />
          </div>
          {(fromDate || toDate) && (
            <Button variant="ghost" size="sm" className="h-8" onClick={() => { setFromDate(""); setToDate(""); }} data-testid="rc-clear-dates">Clear</Button>
          )}
        </div>
      </div>

      {MODULES.map((mod) => (
        <div key={mod} className="space-y-2">
          <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted-foreground border-b border-border pb-1.5">{mod}</div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {REPORTS.filter((r) => r.module === mod).map((r) => (
              <div key={r.key} className="bg-card border border-border rounded-sm p-4 flex flex-col gap-3 hover:border-primary/40 transition-colors" data-testid={`rc-card-${r.key}`}>
                <div>
                  <div className="font-semibold text-sm">{r.label}</div>
                  <div className="text-[11px] text-muted-foreground">{r.desc}</div>
                </div>

                {r.custom === "resource-plan" && (
                  <div className="flex gap-2">
                    <Select value={rpProject || "__none"} onValueChange={(v) => setRpProject(v === "__none" ? "" : v)}>
                      <SelectTrigger className="h-8 rounded-sm text-xs flex-1" data-testid="rc-rp-project"><SelectValue placeholder="Select project" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none">Select project…</SelectItem>
                        {projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <Select value={rpType || "__all"} onValueChange={(v) => setRpType(v === "__all" ? "" : v)}>
                      <SelectTrigger className="h-8 rounded-sm text-xs w-32" data-testid="rc-rp-type"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__all">All types</SelectItem>
                        <SelectItem value="manpower">Manpower</SelectItem>
                        <SelectItem value="material">Material</SelectItem>
                        <SelectItem value="tool">Tools</SelectItem>
                        <SelectItem value="subcontract">Sub-Contract</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {r.custom === "followups" && (
                  <Select value={fuView} onValueChange={setFuView}>
                    <SelectTrigger className="h-8 rounded-sm text-xs" data-testid="rc-fu-view"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Open</SelectItem>
                      <SelectItem value="today">Due Today</SelectItem>
                      <SelectItem value="upcoming">Upcoming</SelectItem>
                      <SelectItem value="overdue">Overdue</SelectItem>
                    </SelectContent>
                  </Select>
                )}

                {r.statuses && (
                  <Select value={statusMap[r.key] || "__all"} onValueChange={(v) => setStatusMap({ ...statusMap, [r.key]: v === "__all" ? "" : v })}>
                    <SelectTrigger className="h-8 rounded-sm text-xs" data-testid={`rc-status-${r.key}`}><SelectValue placeholder="All statuses" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all">All statuses</SelectItem>
                      {r.statuses.map((s) => <SelectItem key={s} value={s}>{s.replace(/_/g, " ")}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}

                <div className="flex gap-2 mt-auto">
                  <Button size="sm" variant="outline" className="h-8 rounded-sm flex-1"
                    disabled={busy === `${r.key}-xlsx`} onClick={() => download(r, "xlsx")} data-testid={`rc-dl-${r.key}-xlsx`}>
                    <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5 text-emerald-700" /> {busy === `${r.key}-xlsx` ? "…" : "Excel"}
                  </Button>
                  {r.custom !== "followups" && (
                    <Button size="sm" variant="outline" className="h-8 rounded-sm flex-1"
                      disabled={busy === `${r.key}-pdf`} onClick={() => download(r, "pdf")} data-testid={`rc-dl-${r.key}-pdf`}>
                      <FileText className="h-3.5 w-3.5 mr-1.5 text-rose-700" /> {busy === `${r.key}-pdf` ? "…" : "PDF"}
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
