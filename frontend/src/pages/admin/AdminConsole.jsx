import { Link } from "react-router-dom";
import { Building2, ListChecks, Workflow, FileSearch, Activity, ShieldCheck, Hash, Grid3x3, Trash2, Mail, Inbox, ShieldPlus, Cloud, Plug } from "lucide-react";

const TILES = [
  {
    to: "/app/admin/departments",
    icon: Building2,
    label: "Departments",
    desc: "Master list of org departments. Used in employee, project & approval routing.",
    testid: "admin-card-departments",
  },
  {
    to: "/app/admin/role-department-map",
    icon: Grid3x3,
    label: "Role × Department Matrix",
    desc: "Pick which roles see which department workspaces on the Module Launcher.",
    testid: "admin-card-role-dept-map",
  },
  {
    to: "/app/admin/customer-code",
    icon: Hash,
    label: "Customer Code Format",
    desc: "System-wide prefix, padding and FY format for auto-generated customer codes.",
    testid: "admin-card-customer-code",
  },
  {
    to: "/app/admin/dropdowns",
    icon: ListChecks,
    label: "Dropdown Master",
    desc: "Manage select-list options across modules (status, category, severity, etc.).",
    testid: "admin-card-dropdowns",
  },
  {
    to: "/app/admin/approval-matrix",
    icon: Workflow,
    label: "Approval Matrix",
    desc: "Edit the multi-level approval chain for each request type.",
    testid: "admin-card-matrix",
  },
  {
    to: "/app/admin/audit-logs",
    icon: FileSearch,
    label: "Audit Trail",
    desc: "Tamper-evident log of every create / update / delete in the system.",
    testid: "admin-card-audit",
  },
  {
    to: "/app/admin/sessions",
    icon: Activity,
    label: "Session Monitor",
    desc: "Recent logins, IP addresses and user-agent fingerprints.",
    testid: "admin-card-sessions",
  },
  {
    to: "/app/admin/data-cleanup",
    icon: Trash2,
    label: "Data Cleanup",
    desc: "Inspect, archive and purge garbage / test / mistaken records with a 30-day recovery window.",
    testid: "admin-card-data-cleanup",
  },
  {
    to: "/app/admin/email-settings",
    icon: Mail,
    label: "Email Settings (M365)",
    desc: "Configure & test the shared Microsoft 365 mailbox used for quotations, POs, invoices and HR letters.",
    testid: "admin-card-email-settings",
  },
  {
    to: "/app/admin/email-outbox",
    icon: Inbox,
    label: "Email Outbox",
    desc: "Audit every email sent from the ERP — status, retries, attachments and SMTP responses.",
    testid: "admin-card-email-outbox",
  },
  {
    to: "/app/admin/role-catalog",
    icon: ShieldPlus,
    label: "Role Catalog",
    desc: "Add or retire roles (e.g. Site Safety Supervisor). Custom roles flow into every dropdown and the Role Register.",
    testid: "admin-card-role-catalog",
  },
  {
    to: "/app/admin/onedrive",
    icon: Cloud,
    label: "OneDrive Cloud Storage",
    desc: "One-way push of all ERP files + nightly database backups to a shared OneDrive (Microsoft Graph).",
    testid: "admin-card-onedrive",
  },
  {
    to: "/app/admin/data-linkage",
    icon: Plug,
    label: "Data Linkage",
    desc: "Live Google Sheets feeds, Tally master sync, and cross-module record linking.",
    testid: "admin-card-data-linkage",
  },
];

export default function AdminConsole() {
  return (
    <div className="space-y-8" data-testid="admin-console">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ShieldCheck className="h-3 w-3" /> Super Admin
        </div>
        <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Admin Console</h1>
        <p className="text-sm text-muted-foreground mt-1">Master controls for departments, dropdowns, approval routing and system auditing.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 stagger">
        {TILES.map((t) => (
          <Link
            key={t.to}
            to={t.to}
            data-testid={t.testid}
            className="kpi-tile bg-card border border-border rounded-sm p-5 hover:border-primary/60"
          >
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 grid place-items-center rounded-sm bg-primary/10 text-primary">
                <t.icon className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="font-display font-bold">{t.label}</div>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{t.desc}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
