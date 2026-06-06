import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Users, Truck, Briefcase, HardHat, ShieldAlert, Boxes,
  ShoppingCart, FileText, Wallet, ClipboardList, Wrench, Car, FolderArchive,
  CheckSquare, BarChart3, LogOut, Menu, Search, ChevronLeft, ChevronRight,
  User2, Construction, ShieldCheck, Building2, ListChecks, Workflow, FileSearch, Activity,
  ScanLine, ClipboardCheck, GraduationCap, MessageSquare, Hammer, UserPlus, MapPinned, BedDouble, Clock, Store, LayoutGrid, PackageCheck, Award, Receipt, Tag, CalendarClock, Banknote, Trash2,
  UserCircle, CalendarDays, ScrollText, LogOut as LogOutIcon, Mail, Cloud, Inbox, ShieldPlus, Plug, Package
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import MyApprovalsInbox from "@/components/MyApprovalsInbox";
import NotificationBell from "@/components/NotificationBell";

const NAV_GROUPS = [
  {
    label: "Command",
    items: [
      { to: "/app", icon: LayoutDashboard, label: "Executive Dashboard", end: true, testid: "nav-dashboard" },
      { to: "/app/approvals", icon: CheckSquare, label: "Approvals", testid: "nav-approvals", perm: "approvals" },
      { to: "/app/approvals/dashboard", icon: CheckSquare, label: "Approvals Dashboard", testid: "nav-approvals-dashboard", perm: "approvals" },
      { to: "/app/approvals/analytics", icon: CheckSquare, label: "Approvals Analytics", testid: "nav-approvals-analytics", perm: "approvals" },
      { to: "/app/approvals/my-revisions", icon: CheckSquare, label: "My Revisions", testid: "nav-my-revisions", perm: "approvals" },
      { to: "/app/reports", icon: BarChart3, label: "Reports", testid: "nav-reports" },
    ],
  },
  {
    label: "Operations",
    items: [
      { to: "/app/ops/handovers", icon: Briefcase, label: "Contract Handovers", testid: "nav-ops-handovers", perm: "project_handovers" },
      { to: "/app/ops/my-projects", icon: Activity, label: "My Assigned Projects", testid: "nav-ops-my-projects" },
      { to: "/app/ops/resource-requests", icon: Package, label: "Resource Requests", testid: "nav-ops-rr" },
      { to: "/app/ops/project-dashboard", icon: Activity, label: "Project Dashboard", testid: "nav-ops-dashboard" },
      { to: "/app/ops/reports", icon: FileText, label: "Operations Reports", testid: "nav-ops-reports" },
      { to: "/app/ops/timeline", icon: Clock, label: "Activity Timeline", testid: "nav-ops-timeline" },
      { to: "/app/projects", icon: Briefcase, label: "Projects", testid: "nav-projects", perm: "projects" },
      { to: "/app/project-dashboard", icon: Activity, label: "Project Dashboard", testid: "nav-project-dashboard", perm: "projects" },
      { to: "/app/dprs", icon: ClipboardList, label: "Daily Site Reports", testid: "nav-dprs", perm: "dprs" },
      { to: "/app/measurements", icon: ListChecks, label: "Measurements", testid: "nav-measurements", perm: "measurements" },
      { to: "/app/safety", icon: ShieldAlert, label: "Safety Reports", testid: "nav-safety", perm: "safety_reports" },
      { to: "/app/ppe", icon: Hammer, label: "PPE Issuance", testid: "nav-ppe", perm: "ppe_issuance" },
      { to: "/app/ptws", icon: ClipboardCheck, label: "Permits to Work", testid: "nav-ptws", perm: "ptws" },
      { to: "/app/safety-trainings", icon: GraduationCap, label: "Safety Trainings", testid: "nav-safety-trainings", perm: "safety_trainings" },
      { to: "/app/toolbox-talks", icon: MessageSquare, label: "Toolbox Talks", testid: "nav-toolbox", perm: "toolbox_talks" },
      { to: "/app/assets", icon: Wrench, label: "Assets", testid: "nav-assets", perm: "assets" },
      { to: "/app/logistics", icon: Car, label: "Logistics", testid: "nav-logistics", perm: "vehicles" },
    ],
  },
  {
    label: "Commerce",
    items: [
      { to: "/app/clients", icon: Users, label: "Clients", testid: "nav-clients", perm: "clients" },
      { to: "/app/client-map", icon: MapPinned, label: "Client Map", testid: "nav-client-map", perm: "clients" },
      { to: "/app/vendors", icon: Truck, label: "Vendors", testid: "nav-vendors", perm: "vendors" },
      { to: "/app/enquiries", icon: FileText, label: "Enquiries", testid: "nav-enquiries", perm: "quotations" },
      { to: "/app/quotations", icon: FileText, label: "Quotations", testid: "nav-quotations", perm: "quotations" },
      { to: "/app/orders", icon: ShoppingCart, label: "Sales Orders", testid: "nav-orders", perm: "quotations" },
      { to: "/app/sales-reports", icon: BarChart3, label: "Sales Reports", testid: "nav-sales-reports", perm: "sales_reports" },
      { to: "/app/purchase-orders", icon: ShoppingCart, label: "Purchase Orders", testid: "nav-purchase", perm: "purchase_orders" },
      { to: "/app/purchase-requisitions", icon: ClipboardList, label: "Purchase Requisitions", testid: "nav-prs", perm: "purchase_requisitions" },
      { to: "/app/rfqs", icon: FileSearch, label: "RFQs", testid: "nav-rfqs", perm: "rfqs" },
      { to: "/app/grn", icon: PackageCheck, label: "GRN (Goods Receipt)", testid: "nav-grn", perm: "grn" },
      { to: "/app/material-allocations", icon: Boxes, label: "Material Allocations", testid: "nav-allocations", perm: "material_allocations" },
      { to: "/app/asset-lifecycle", icon: Wrench, label: "Asset Lifecycle", testid: "nav-asset-lifecycle", perm: "asset_lifecycle" },
      { to: "/app/challans", icon: Truck, label: "Challans", testid: "nav-challans", perm: "challans" },
      { to: "/app/procurement-dashboard", icon: Workflow, label: "Procurement Dashboard", testid: "nav-procurement-dashboard", perm: "purchase_requisitions" },
      { to: "/app/procurement/reports", icon: Workflow, label: "Procurement Reports", testid: "nav-procurement-reports", perm: "purchase_requisitions" },
      { to: "/app/inventory", icon: Boxes, label: "Inventory & Stores", testid: "nav-inventory", perm: "inventory" },
      { to: "/app/inventory-intel", icon: BarChart3, label: "Inventory Intel", testid: "nav-inventory-intel", perm: "inventory" },
      { to: "/app/procurement-intel", icon: Award, label: "Procurement Intel", testid: "nav-procurement-intel", perm: "vendors" },
      { to: "/app/store-transactions", icon: ScanLine, label: "Stock Movements", testid: "nav-store-txns", perm: "inventory" },
    ],
  },
  {
    label: "People & Finance",
    items: [
      { to: "/app/employees", icon: HardHat, label: "Employees (HRMS)", testid: "nav-employees", perm: "employees" },
      { to: "/app/hr/onboarding", icon: UserPlus, label: "Onboarding", testid: "nav-hr-onboarding", perm: "hr_onboarding" },
      { to: "/app/hr/employee-360", icon: UserCircle, label: "Employee 360", testid: "nav-hr-emp360", perm: "hr_employee_360" },
      { to: "/app/hr/leave", icon: CalendarDays, label: "Leave Management", testid: "nav-hr-leave", perm: "hr_leave" },
      { to: "/app/hr/letters", icon: ScrollText, label: "HR Letters & Templates", testid: "nav-hr-letters", perm: "hr_letters" },
      { to: "/app/hr/advances", icon: Wallet, label: "Advance Register", testid: "nav-hr-advances", perm: "hr_advances" },
      { to: "/app/hr/advance-recovery", icon: Wallet, label: "Recovery & Reports", testid: "nav-hr-advance-recovery", perm: "hr_advances" },
      { to: "/app/hr/payroll", icon: Wallet, label: "Payroll (Monthly Run)", testid: "nav-hr-payroll", perm: "hr_payroll" },
      { to: "/app/hr/exit", icon: LogOutIcon, label: "Exit & FNF", testid: "nav-hr-exit", perm: "hr_exit" },
      { to: "/app/attendance", icon: ClipboardList, label: "Attendance", testid: "nav-attendance", perm: "attendance" },
      { to: "/app/recruitment", icon: UserPlus, label: "Recruitment", testid: "nav-recruitment", perm: "recruitment_requests" },
      { to: "/app/candidates", icon: Users, label: "Candidates", testid: "nav-candidates", perm: "candidates" },
      { to: "/app/deployments", icon: MapPinned, label: "Deployments", testid: "nav-deployments", perm: "deployments" },
      { to: "/app/accommodations", icon: BedDouble, label: "Accommodations", testid: "nav-accommodations", perm: "accommodations" },
      { to: "/app/overtime", icon: Clock, label: "Overtime", testid: "nav-overtime", perm: "overtime" },
      { to: "/app/payroll", icon: Wallet, label: "Payroll", testid: "nav-payroll", perm: "payroll" },
      { to: "/app/accounts", icon: FileText, label: "Accounts & Finance", testid: "nav-accounts", perm: "journal_entries" },
      { to: "/app/ra-bills", icon: Receipt, label: "Running Bills (RA)", testid: "nav-ra-bills", perm: "ra_bills" },
      { to: "/app/receivables", icon: Wallet, label: "Receivables", testid: "nav-receivables", perm: "receivables" },
      { to: "/app/service-rates", icon: Tag, label: "Service Rates", testid: "nav-service-rates", perm: "service_rates" },
      { to: "/app/project-ops", icon: CalendarClock, label: "Project Ops & PO Expiry", testid: "nav-project-ops", perm: "project_ops" },
      { to: "/app/documents", icon: FolderArchive, label: "Documents", testid: "nav-documents", perm: "documents" },
    ],
  },
  {
    label: "Vendor Portal",
    vendorOnly: true,
    items: [
      { to: "/app/vendor-portal", icon: Store, label: "My Portal", testid: "nav-vendor-portal" },
    ],
  },
  {
    label: "Administration",
    superAdminOnly: true,
    items: [
      { to: "/app/admin", icon: ShieldCheck, label: "Admin Console", end: true, testid: "nav-admin" },
      { to: "/app/admin/departments", icon: Building2, label: "Departments", testid: "nav-admin-departments" },
      { to: "/app/admin/dropdowns", icon: ListChecks, label: "Dropdown Master", testid: "nav-admin-dropdowns" },
      { to: "/app/admin/approval-matrix", icon: Workflow, label: "Approval Matrix", testid: "nav-admin-matrix" },
      { to: "/app/admin/approval-workflow", icon: Workflow, label: "Approval Workflow Settings", testid: "nav-admin-workflow" },
      { to: "/app/admin/sequences", icon: Workflow, label: "Sequence Reset", testid: "nav-admin-sequences" },
      { to: "/app/settings/billing-defaults", icon: Banknote, label: "Billing Defaults", testid: "nav-admin-billing-defaults" },
      { to: "/app/admin/company-profile", icon: Building2, label: "Company Profile", testid: "nav-admin-company-profile" },
      { to: "/app/admin/users", icon: Users, label: "User Management", testid: "nav-admin-users" },
      { to: "/app/admin/role-register", icon: ShieldCheck, label: "Role Register", testid: "nav-admin-role-register" },
      { to: "/app/admin/conditions", icon: ListChecks, label: "Quotation Clauses", testid: "nav-admin-conditions" },
      { to: "/app/admin/categories", icon: Tag, label: "Categories", testid: "nav-admin-categories" },
      { to: "/app/admin/cost-centers", icon: Wallet, label: "Cost Centers", testid: "nav-admin-cost-centers" },
      { to: "/app/admin/audit-logs", icon: FileSearch, label: "Audit Trail", testid: "nav-admin-audit" },
      { to: "/app/admin/sessions", icon: Activity, label: "Session Monitor", testid: "nav-admin-sessions" },
      { to: "/app/admin/data-cleanup", icon: Trash2, label: "Data Cleanup", testid: "nav-admin-data-cleanup" },
      { to: "/app/admin/email-settings", icon: Mail, label: "Email Settings (M365)", testid: "nav-admin-email-settings" },
      { to: "/app/admin/email-outbox", icon: Inbox, label: "Email Outbox", testid: "nav-admin-email-outbox" },
      { to: "/app/admin/role-catalog", icon: ShieldPlus, label: "Role Catalog", testid: "nav-admin-role-catalog" },
      { to: "/app/admin/onedrive", icon: Cloud, label: "OneDrive Cloud Storage", testid: "nav-admin-onedrive" },
      { to: "/app/admin/data-linkage", icon: Plug, label: "Data Linkage", testid: "nav-admin-data-linkage" },
      { to: "/app/admin/department-master", icon: Plug, label: "Department Master", testid: "nav-admin-dept-master" },
      { to: "/app/admin/dept-governance", icon: Plug, label: "Dept Governance", testid: "nav-admin-dept-governance" },
    ],
  },
];

function SidebarBody({ collapsed, onItemClick, can, role }) {
  return (
    <nav className="flex flex-col gap-6 py-6">
      {NAV_GROUPS.map((group) => {
        if (group.superAdminOnly && role !== "super_admin") return null;
        if (group.vendorOnly && role !== "vendor") return null;
        const visible = group.items.filter((it) => !it.perm || can(it.perm, "read"));
        if (visible.length === 0) return null;
        return (
        <div key={group.label}>
          {!collapsed && (
            <div className="px-5 mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-sidebar-foreground/40">
              {group.label}
            </div>
          )}
          <div className="flex flex-col gap-0.5 px-2">
            {visible.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.end}
                onClick={onItemClick}
                data-testid={it.testid}
                className={({ isActive }) =>
                  cn(
                    "group flex items-center gap-3 px-3 py-2 rounded-sm text-sm transition-colors duration-150",
                    "text-sidebar-foreground/70 hover:bg-primary/10 hover:text-primary",
                    isActive && "bg-primary/10 text-primary border-l-2 border-primary -ml-[2px] pl-[14px]"
                  )
                }
                title={collapsed ? it.label : undefined}
              >
                <it.icon className="h-4 w-4 shrink-0" strokeWidth={2} />
                {!collapsed && <span className="truncate">{it.label}</span>}
              </NavLink>
            ))}
          </div>
        </div>
      );})}
    </nav>
  );
}

export default function Layout({ children }) {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const initials = (user?.name || user?.email || "U")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const breadcrumb = location.pathname.split("/").filter(Boolean).slice(1).join(" / ") || "executive";

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden lg:flex sticky top-0 h-screen flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-[width] duration-200",
          collapsed ? "w-16" : "w-64"
        )}
        data-testid="desktop-sidebar"
      >
        <div className="flex items-center justify-between px-4 h-16 border-b border-sidebar-border">
          <Brand compact={collapsed} />
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="text-sidebar-foreground/60 hover:text-primary"
            data-testid="sidebar-collapse-btn"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <SidebarBody collapsed={collapsed} can={can} role={user?.role} />
        </div>
        {!collapsed && (
          <div className="px-4 py-3 border-t border-sidebar-border flex items-center gap-2 text-xs text-sidebar-foreground/50">
            <Construction className="h-3.5 w-3.5" />
            <span>INDIAN TRADE LINKS · ERP v1.1</span>
          </div>
        )}
      </aside>

      {/* Mobile sheet */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 p-0 bg-sidebar text-sidebar-foreground border-sidebar-border">
          <div className="flex items-center px-4 h-16 border-b border-sidebar-border">
            <Brand />
          </div>
          <div className="overflow-y-auto h-[calc(100vh-64px)]">
            <SidebarBody collapsed={false} onItemClick={() => setMobileOpen(false)} can={can} role={user?.role} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="sticky top-0 z-30 h-16 flex items-center gap-3 px-4 lg:px-6 bg-background/80 backdrop-blur-md border-b border-border">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-btn">
            <Menu className="h-5 w-5" />
          </Button>
          <BackButton />
          <div className="hidden md:flex items-center gap-2 text-xs uppercase tracking-[0.15em] text-muted-foreground">
            <span>Module</span>
            <span className="text-primary">/</span>
            <span className="text-foreground font-semibold">{breadcrumb}</span>
          </div>
          <div className="hidden md:flex items-center gap-2 ml-4 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search projects, clients, POs…"
                className="pl-9 h-9 rounded-sm border-border bg-muted/40"
                data-testid="global-search"
              />
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <NotificationBell />
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-9 rounded-sm hidden md:inline-flex"
              data-testid="header-modules-btn"
            >
              <NavLink to="/app/modules">
                <LayoutGrid className="h-4 w-4 mr-1.5" /> Modules
              </NavLink>
            </Button>
            <MyApprovalsInbox />
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 pl-1 pr-3 h-9 border border-border rounded-sm hover:border-primary/60 transition-colors" data-testid="user-menu-btn">
                  <Avatar className="h-7 w-7 rounded-sm">
                    <AvatarFallback className="rounded-sm bg-primary text-primary-foreground text-xs font-bold">{initials}</AvatarFallback>
                  </Avatar>
                  <div className="hidden md:block text-left leading-tight">
                    <div className="text-xs font-semibold">{user?.name}</div>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{user?.role?.replaceAll("_", " ")}</div>
                  </div>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 rounded-sm">
                <DropdownMenuLabel className="text-xs">
                  <div className="font-semibold">{user?.name}</div>
                  <div className="text-muted-foreground">{user?.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/app/profile")} data-testid="menu-profile">
                  <User2 className="h-4 w-4 mr-2" /> Profile & Roles
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/app/me/email")} data-testid="menu-my-email">
                  <Mail className="h-4 w-4 mr-2" /> Email Settings (M365)
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onLogout} data-testid="menu-logout" className="text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4 mr-2" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

/**
 * BackButton — sits in the global top bar.
 *
 *  - Hidden on `/app` (the modules home) and on the very first navigation when
 *    there is nothing useful to go back to.
 *  - Uses `navigate(-1)` for true browser-history back. If the user landed
 *    directly on a deep link (`window.history.length <= 1`), falls back to
 *    `/app` so the button never becomes a dead-end.
 *  - Long-press / right-click is preserved for power users (default browser
 *    history dropdown).
 */
function BackButton() {
  const navigate = useNavigate();
  const location = useLocation();
  // Hide on the modules home and on login
  const hide = ["/app", "/app/", "/login"].includes(location.pathname);
  if (hide) return null;
  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/app");
    }
  };
  return (
    <Button
      variant="outline"
      size="sm"
      className="h-9 rounded-sm shrink-0"
      onClick={goBack}
      data-testid="global-back-btn"
      aria-label="Back"
    >
      <ChevronLeft className="h-4 w-4 md:mr-1" />
      <span className="hidden md:inline">Back</span>
    </Button>
  );
}


