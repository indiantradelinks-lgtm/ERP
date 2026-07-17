/**
 * Central Menu Configuration — Single source of truth for both the left
 * sidebar AND every module landing page menu.
 *
 * Structure: 11 departments. Each item maps to an existing route where one
 * exists. Items flagged `comingSoon: true` point to the department landing
 * page; renderers display a small "Soon" badge and do not navigate.
 *
 * Field reference (per item):
 *   department:      Owner department key (sales, ops, hr, store, ...)
 *   parentLabel:     Optional sub-group label (Phase 2, Payroll & Advances)
 *   label:           Display name
 *   to:              Route path
 *   icon:            lucide-react component
 *   perm:            Permission key (matches backend rbac.PERMISSIONS_BASE)
 *   testid:          data-testid for QA
 *   roles:           Optional whitelist of roles that always see this item
 *   superAdminOnly:  Only super_admin sees
 *   vendorOnly:      Only role=vendor sees
 *   comingSoon:      Show with "Soon" badge, do not navigate
 *   inSidebar:       Default true. Set false to hide from sidebar
 *   inModuleMenu:    Default true. Set false to hide from module menu
 *   order:           Tie-breaker for sort within department
 *
 * No item should exist in only one surface — sidebar and module menu both
 * read from this same file.
 */
import {
  LayoutDashboard, Users, Truck, Briefcase, HardHat, ShieldAlert, Boxes,
  ShoppingCart, FileText, Wallet, ClipboardList, Wrench, Car, FolderArchive, MapPin,
  CheckSquare, BarChart3, User2, Construction, ShieldCheck, Building2, ListChecks,
  Workflow, FileSearch, Activity, ScanLine, ClipboardCheck, GraduationCap,
  MessageSquare, Hammer, UserPlus, MapPinned, BedDouble, Clock, Store, LayoutGrid,
  PackageCheck, Award, Receipt, Tag, CalendarClock, Banknote, Trash2, UserCircle,
  CalendarDays, ScrollText, Mail, Cloud, Inbox, ShieldPlus, Plug, Package,
  Warehouse, DollarSign, FileSignature, History, Settings as SettingsIcon, Network,
  CalendarRange, Ruler, AlertTriangle, PlusSquare, Layers, Lock, Landmark, LineChart,
  Bell, TrendingUp, Calculator, FileBarChart, Stethoscope, Fuel, Route, FilePlus2,
  Database, Siren, FileSpreadsheet, Hotel, LogOut, KeyRound,
} from "lucide-react";

// ─── Department registry ─────────────────────────────────────────────────
export const DEPARTMENTS = [
  { key: "dashboard",      label: "Dashboard",             icon: LayoutDashboard, route: "/app",                       },
  { key: "sales",          label: "Sales",                 icon: ShoppingCart,    route: "/app/quotations",            },
  { key: "ops",            label: "Projects & Operations", icon: Briefcase,       route: "/app/ops/dashboard",         },
  { key: "hr",             label: "Human Resources",       icon: HardHat,         route: "/app/employees",             },
  { key: "store",          label: "Store & Inventory",     icon: Warehouse,       route: "/app/store-inventory",       },
  { key: "procurement",    label: "Procurement & Vendors", icon: Truck,           route: "/app/procurement-dashboard", },
  { key: "accounts",       label: "Accounts",              icon: FileText,        route: "/app/accounts",              },
  { key: "finance",        label: "Finance",               icon: LineChart,       route: "/app/accounts/dashboard",    },
  { key: "safety",         label: "Safety",                icon: ShieldAlert,     route: "/app/safety",                },
  { key: "logistics",      label: "Logistics",             icon: Car,             route: "/app/logistics",             },
  { key: "admin",          label: "Management & Admin",    icon: ShieldCheck,     route: "/app/admin",                 superAdminOnly: true },
];

// Convenience map
export const DEPARTMENT_MAP = Object.fromEntries(DEPARTMENTS.map((d) => [d.key, d]));

// ─── Menu items ──────────────────────────────────────────────────────────
export const MENU_ITEMS = [
  // ═══════════════ 1. DASHBOARD ═══════════════
  { department: "dashboard", label: "Main Dashboard",        to: "/app",                            icon: LayoutDashboard, testid: "nav-dashboard", end: true },
  { department: "dashboard", label: "Management Dashboard",  to: "/app",                            icon: TrendingUp,      testid: "nav-mgmt-dashboard" },
  { department: "dashboard", label: "Department Dashboard",  to: "/app/modules",                    icon: LayoutGrid,      testid: "nav-dept-dashboard" },
  { department: "dashboard", label: "Alerts & Notifications", to: "/app/accounts/alerts",            icon: Bell,            testid: "nav-alerts", perm: "accounting" },
  { department: "dashboard", label: "Pending Approvals",     to: "/app/approvals",                  icon: CheckSquare,     testid: "nav-approvals", perm: "approvals" },
  { department: "dashboard", label: "Approvals Dashboard",   to: "/app/approvals/dashboard",        icon: CheckSquare,     testid: "nav-approvals-dashboard", perm: "approvals" },
  { department: "dashboard", label: "Approvals Analytics",   to: "/app/approvals/analytics",        icon: BarChart3,       testid: "nav-approvals-analytics", perm: "approvals" },
  { department: "dashboard", label: "My Revisions",          to: "/app/approvals/my-revisions",     icon: CheckSquare,     testid: "nav-my-revisions", perm: "approvals" },
  { department: "dashboard", label: "Reports Summary",       to: "/app/reports",                    icon: BarChart3,       testid: "nav-reports" },

  // ═══════════════ 2. SALES ═══════════════
  { department: "sales", label: "Sales Dashboard",          to: "/app/sales-reports",              icon: BarChart3,    testid: "nav-sales-dashboard", perm: "sales_reports" },
  { department: "sales", label: "Lead / Enquiry Management", to: "/app/enquiries",                  icon: FileText,     testid: "nav-enquiries", perm: "quotations" },
  { department: "sales", label: "Client Master",            to: "/app/clients",                    icon: Users,        testid: "nav-clients", perm: "clients" },
  { department: "sales", label: "Client Map",               to: "/app/client-map",                 icon: MapPinned,    testid: "nav-client-map", perm: "clients" },
  { department: "sales", label: "RFQ / Tender",             to: "/app/rfqs",                       icon: FileSearch,   testid: "nav-rfqs", perm: "rfqs" },
  { department: "sales", label: "Site Visit / Tech Discussion", to: "/app/enquiries",              icon: MapPin,       testid: "nav-site-visit", perm: "quotations" },
  { department: "sales", label: "Quotation",                to: "/app/quotations",                 icon: FileText,     testid: "nav-quotations", perm: "quotations" },
  { department: "sales", label: "BOQ / Scope",              to: "/app/quotations",                 icon: ClipboardList, testid: "nav-sales-boq", perm: "quotations" },
  { department: "sales", label: "Commercial Offer",         to: "/app/quotations",                 icon: Calculator,   testid: "nav-commercial-offer", perm: "quotations" },
  { department: "sales", label: "Quotation Approval",       to: "/app/approvals",                  icon: CheckSquare,  testid: "nav-quotation-approval", perm: "approvals" },
  { department: "sales", label: "Work Order Received",      to: "/app/orders",                     icon: ShoppingCart, testid: "nav-orders", perm: "quotations" },
  { department: "sales", label: "Sales Handover to Project", to: "/app/ops/handovers",             icon: Briefcase,    testid: "nav-sales-handover", perm: "project_handovers" },
  { department: "sales", label: "Client Follow-up",         to: "/app/accounts/alerts",            icon: Bell,         testid: "nav-client-followup", perm: "accounting" },
  { department: "sales", label: "Enquiry Follow-Up Tracker", to: "/app/sales/enquiry-followup",    icon: CalendarClock, testid: "nav-enquiry-followup", perm: "quotations" },
  { department: "sales", label: "Sales Reports",            to: "/app/sales-reports",              icon: BarChart3,    testid: "nav-sales-reports", perm: "sales_reports" },
  { department: "sales", label: "Service Rates",            to: "/app/service-rates",              icon: Tag,          testid: "nav-service-rates", perm: "service_rates" },

  // ═══════════════ 3. PROJECTS & OPERATIONS ═══════════════
  { department: "ops", label: "Projects Dashboard",         to: "/app/ops/dashboard",              icon: Activity,        testid: "nav-ops-dashboard", perm: "projects" },
  { department: "ops", label: "Project Master",             to: "/app/projects",                   icon: Briefcase,       testid: "nav-ops-master", perm: "projects" },
  { department: "ops", label: "Site Master",                to: "/app/ops/site-master",            icon: MapPin,          testid: "nav-ops-sites", perm: "projects" },
  { department: "ops", label: "Service Type Master",        to: "/app/ops/service-types",          icon: Wrench,          testid: "nav-ops-service-types", perm: "projects" },
  { department: "ops", label: "Contract Handovers",         to: "/app/ops/handovers",              icon: Briefcase,       testid: "nav-ops-handovers", perm: "project_handovers" },
  { department: "ops", label: "Work Order Mapping",         to: "/app/ops/work-orders",            icon: FileSignature,   testid: "nav-ops-wo", perm: "projects" },
  { department: "ops", label: "Project Planning",           to: "/app/ops/planning",               icon: ClipboardList,   testid: "nav-ops-planning", perm: "projects" },
  { department: "ops", label: "BOQ / Scope Breakdown",      to: "/app/ops/boq",                    icon: FileText,        testid: "nav-ops-boq", perm: "projects" },
  { department: "ops", label: "Work Breakdown (WBS)",       to: "/app/ops/wbs",                    icon: Network,         testid: "nav-ops-wbs", perm: "projects" },
  { department: "ops", label: "Activity Schedule",          to: "/app/ops/activities",             icon: CalendarRange,   testid: "nav-ops-act", perm: "projects" },
  { department: "ops", label: "Resource Planning",          to: "/app/ops/resources",              icon: Users,           testid: "nav-ops-res", perm: "projects" },
  { department: "ops", label: "Project Budget",             to: "/app/accounts/budget",            icon: Wallet,          testid: "nav-ops-budget", perm: "accounting" },
  { department: "ops", label: "Pre-Mobilization Checklist", to: "/app/ops/planning",               icon: ClipboardCheck,  testid: "nav-ops-premob", perm: "projects" },
  { department: "ops", label: "Manpower Requirement",       to: "/app/ops/resource-requests",      icon: Users,           testid: "nav-ops-manpower-req", perm: "projects" },
  { department: "ops", label: "Material Requirement",       to: "/app/material-allocations",       icon: Boxes,           testid: "nav-ops-material-req", perm: "material_allocations" },
  { department: "ops", label: "Daily Progress Report",      to: "/app/ops/dpr",                    icon: ClipboardCheck,  testid: "nav-ops-dpr", perm: "projects" },
  { department: "ops", label: "Measurement Sheet",          to: "/app/ops/measurements",           icon: Ruler,           testid: "nav-ops-ms", perm: "projects" },
  { department: "ops", label: "Work Progress Tracker",      to: "/app/ops/work-progress",          icon: Activity,        testid: "nav-ops-wp", perm: "projects" },
  { department: "ops", label: "Site Issue Register",        to: "/app/ops/site-issues",            icon: AlertTriangle,   testid: "nav-ops-iss", perm: "projects" },
  { department: "ops", label: "Delay Register",             to: "/app/ops/site-issues",            icon: Clock,           testid: "nav-ops-delay", perm: "projects" },
  { department: "ops", label: "Client Instruction",         to: "/app/ops/client-instructions",    icon: MessageSquare,   testid: "nav-ops-ci", perm: "projects" },
  { department: "ops", label: "Extra Work Register",        to: "/app/ops/extra-works",            icon: PlusSquare,      testid: "nav-ops-ew", perm: "projects" },
  { department: "ops", label: "Work Permit Register",       to: "/app/ops/work-permits",           icon: ShieldAlert,     testid: "nav-ops-wp2", perm: "projects" },
  { department: "ops", label: "Project Control Center",     to: "/app/ops/control-center",         icon: Layers,          testid: "nav-ops-cc", perm: "projects" },
  { department: "ops", label: "Internal Project Review",    to: "/app/ops/internal-review",        icon: ClipboardCheck,  testid: "nav-ops-internal-review", perm: "projects" },
  { department: "ops", label: "Execution Dashboard",        to: "/app/ops/execution-dashboard",    icon: Activity,        testid: "nav-ops-ed", perm: "projects" },
  { department: "ops", label: "RA Billing Support",         to: "/app/ra-bills",                   icon: Receipt,         testid: "nav-ops-ra", perm: "ra_bills" },
  { department: "ops", label: "Final Billing Support",      to: "/app/ra-bills",                   icon: Receipt,         testid: "nav-ops-final-bill", perm: "ra_bills" },
  { department: "ops", label: "Project Cost Summary",       to: "/app/accounts/budget",            icon: Calculator,      testid: "nav-ops-cost", perm: "accounting" },
  { department: "ops", label: "Project Profitability",      to: "/app/accounts/dashboard",         icon: TrendingUp,      testid: "nav-ops-prof", perm: "accounting" },
  { department: "ops", label: "Project Closure",            to: "/app/ops/closure-center",         icon: Lock,            testid: "nav-ops-clo", perm: "projects" },
  { department: "ops", label: "Project Team",               to: "/app/ops/team",                   icon: Users,           testid: "nav-ops-team", perm: "projects" },
  { department: "ops", label: "Project Documents",          to: "/app/ops/documents",              icon: FileText,        testid: "nav-ops-docs", perm: "projects" },
  { department: "ops", label: "My Assigned Projects",       to: "/app/ops/my-projects",            icon: Activity,        testid: "nav-ops-my-projects" },
  { department: "ops", label: "Activity Timeline",          to: "/app/ops/timeline",               icon: Clock,           testid: "nav-ops-timeline" },
  { department: "ops", label: "Resource Requests",          to: "/app/ops/resource-requests",      icon: Package,         testid: "nav-ops-rr" },
  { department: "ops", label: "Project Audit Trail",        to: "/app/ops/audit-trail",            icon: History,         testid: "nav-ops-audit", perm: "projects" },
  { department: "ops", label: "Project Reports",            to: "/app/ops/reports",                icon: FileBarChart,    testid: "nav-ops-reports", perm: "projects" },
  { department: "ops", label: "Project Settings",           to: "/app/ops/settings",               icon: SettingsIcon,    testid: "nav-ops-settings", perm: "projects" },

  // ═══════════════ 4. HUMAN RESOURCES ═══════════════
  { department: "hr", parentLabel: "Core",      label: "HR Dashboard",            to: "/app/hr/command-center",     icon: LayoutDashboard, testid: "nav-hr-dashboard", perm: "hr_onboarding" },
  { department: "hr", parentLabel: "Core",      label: "Employee Master",         to: "/app/employees",             icon: HardHat,         testid: "nav-employees", perm: "employees" },
  { department: "hr", parentLabel: "Core",      label: "Worker / Labour Master",  to: "/app/employees",             icon: Users,           testid: "nav-workers", perm: "employees" },
  { department: "hr", parentLabel: "Core",      label: "Onboarding",              to: "/app/hr/onboarding",         icon: UserPlus,        testid: "nav-hr-onboarding", perm: "hr_onboarding" },
  { department: "hr", parentLabel: "Core",      label: "Employee 360",            to: "/app/hr/employee-360",       icon: UserCircle,      testid: "nav-hr-emp360", perm: "hr_employee_360" },
  { department: "hr", parentLabel: "Core",      label: "Department Master",       to: "/app/admin/department-master", icon: Building2,     testid: "nav-hr-dept", superAdminOnly: true },
  { department: "hr", parentLabel: "Masters",   label: "Designation Master",      to: "/app/admin/dropdowns",       icon: Tag,             testid: "nav-designations", superAdminOnly: true },
  { department: "hr", parentLabel: "Masters",   label: "Skill / Trade Master",    to: "/app/admin/dropdowns",       icon: Tag,             testid: "nav-skills", superAdminOnly: true },
  { department: "hr", parentLabel: "Documents", label: "Employee Documents",      to: "/app/hr/letters",            icon: ScrollText,      testid: "nav-emp-docs", perm: "hr_letters" },
  { department: "hr", parentLabel: "Documents", label: "Document Verification",   to: "/app/hr/onboarding",         icon: ClipboardCheck,  testid: "nav-doc-verify", perm: "hr_onboarding" },
  { department: "hr", parentLabel: "Compliance", label: "Medical Fitness Register", to: "/app/hr/letters",          icon: Stethoscope,     testid: "nav-medical", perm: "hr_letters" },
  { department: "hr", parentLabel: "Compliance", label: "Police Verification",    to: "/app/hr/letters",            icon: ShieldCheck,     testid: "nav-police-verify", perm: "hr_letters" },
  { department: "hr", parentLabel: "Compliance", label: "Training & Certification", to: "/app/safety-trainings",    icon: GraduationCap,   testid: "nav-training", perm: "safety_trainings" },
  { department: "hr", parentLabel: "Attendance", label: "Attendance Register",    to: "/app/hr/operations",         icon: ClipboardList,   testid: "nav-attendance", perm: "attendance" },
  { department: "hr", parentLabel: "Attendance", label: "Attendance Approval",    to: "/app/approvals",             icon: CheckSquare,     testid: "nav-att-approval", perm: "approvals" },
  { department: "hr", parentLabel: "Attendance", label: "Shift Management",      to: "/app/hr/operations",         icon: Clock,           testid: "nav-shifts", perm: "attendance" },
  { department: "hr", parentLabel: "Attendance", label: "Overtime Register",     to: "/app/overtime",              icon: Clock,           testid: "nav-overtime", perm: "overtime" },
  { department: "hr", parentLabel: "Attendance", label: "Leave Management",      to: "/app/hr/leave",              icon: CalendarDays,    testid: "nav-leave", perm: "hr_leave" },
  { department: "hr", parentLabel: "Manpower",   label: "Manpower Requirement",  to: "/app/recruitment",           icon: UserPlus,        testid: "nav-mr-req", perm: "recruitment_requests" },
  { department: "hr", parentLabel: "Manpower",   label: "Manpower Planning",     to: "/app/hr/manpower-planning",  icon: Users,           testid: "nav-mr-plan", perm: "hr_onboarding" },
  { department: "hr", parentLabel: "Manpower",   label: "Project / Site Deployment", to: "/app/deployments",       icon: MapPinned,       testid: "nav-deployments", perm: "deployments" },
  { department: "hr", parentLabel: "Manpower",   label: "Mobilization",          to: "/app/deployments",           icon: Truck,           testid: "nav-mobilization", perm: "deployments" },
  { department: "hr", parentLabel: "Manpower",   label: "Demobilization",        to: "/app/deployments",           icon: Truck,           testid: "nav-demob", perm: "deployments" },
  { department: "hr", parentLabel: "Manpower",   label: "Candidates",            to: "/app/candidates",            icon: Users,           testid: "nav-candidates", perm: "candidates" },
  { department: "hr", parentLabel: "Manpower",   label: "Accommodations",        to: "/app/accommodations",        icon: BedDouble,       testid: "nav-accom", perm: "accommodations" },
  { department: "hr", parentLabel: "Payroll",    label: "Salary Structure",      to: "/app/hr/payroll-statutory",  icon: DollarSign,      testid: "nav-salary-struct", perm: "hr_onboarding" },
  { department: "hr", parentLabel: "Payroll",    label: "Wage Structure",        to: "/app/hr/payroll-statutory",  icon: DollarSign,      testid: "nav-wage-struct", perm: "hr_onboarding" },
  { department: "hr", parentLabel: "Payroll",    label: "Payroll Processing",    to: "/app/hr/payroll",            icon: Wallet,          testid: "nav-payroll", perm: "hr_payroll" },
  { department: "hr", parentLabel: "Payroll",    label: "Payroll Approval",      to: "/app/approvals",             icon: CheckSquare,     testid: "nav-payroll-approval", perm: "approvals" },
  { department: "hr", parentLabel: "Payroll",    label: "PF / ESIC Dashboard",   to: "/app/accounts/compliance",   icon: Landmark,        testid: "nav-pf-esic", perm: "accounting" },
  { department: "hr", parentLabel: "Payroll",    label: "TDS Dashboard",         to: "/app/accounts/compliance",   icon: Landmark,        testid: "nav-tds", perm: "accounting" },
  { department: "hr", parentLabel: "Payroll",    label: "Salary Advance",        to: "/app/hr/advances",           icon: Wallet,          testid: "nav-advances", perm: "hr_advances" },
  { department: "hr", parentLabel: "Payroll",    label: "Employee Loan",         to: "/app/hr/advances",           icon: Wallet,          testid: "nav-loan", perm: "hr_advances" },
  { department: "hr", parentLabel: "Payroll",    label: "Reimbursement",         to: "/app/hr/advances",           icon: Wallet,          testid: "nav-reimburse", perm: "hr_advances" },
  { department: "hr", parentLabel: "Payroll",    label: "Advance Recovery",      to: "/app/hr/advance-recovery",   icon: Wallet,          testid: "nav-recovery", perm: "hr_advances" },
  { department: "hr", parentLabel: "Exit",       label: "Employee Exit",         to: "/app/hr/exit",               icon: User2,           testid: "nav-exit", perm: "hr_exit" },
  { department: "hr", parentLabel: "Exit",       label: "Full & Final Settlement", to: "/app/hr/exit",             icon: Calculator,      testid: "nav-fnf", perm: "hr_exit" },
  { department: "hr", parentLabel: "Exit",       label: "Employee Clearance",    to: "/app/hr/exit",               icon: ClipboardCheck,  testid: "nav-clearance", perm: "hr_exit" },
  { department: "hr", parentLabel: "Reports",    label: "HR Letters & Templates", to: "/app/hr/letters",           icon: ScrollText,      testid: "nav-hr-letters", perm: "hr_letters" },
  { department: "hr", parentLabel: "Reports",    label: "HR Reports",            to: "/app/reports",               icon: FileBarChart,    testid: "nav-hr-reports" },

  // ═══════════════ 5. STORE & INVENTORY ═══════════════
  { department: "store", label: "Inventory Dashboard",      to: "/app/inventory-intel",            icon: BarChart3,    testid: "nav-inv-dashboard", perm: "inventory" },
  { department: "store", label: "Store & Inventory",        to: "/app/store-inventory",            icon: Warehouse,    testid: "nav-store", perm: "inventory" },
  { department: "store", label: "Item Master",              to: "/app/store-inventory",            icon: Package,      testid: "nav-item-master", perm: "inventory" },
  { department: "store", label: "Item Category Master",     to: "/app/admin/categories",           icon: Tag,          testid: "nav-item-cat", superAdminOnly: true },
  { department: "store", label: "Unit Master",              to: "/app/admin/dropdowns",            icon: Ruler,        testid: "nav-unit-master", superAdminOnly: true },
  { department: "store", label: "Store / Warehouse Master", to: "/app/store-inventory",            icon: Warehouse,    testid: "nav-warehouse", perm: "inventory" },
  { department: "store", label: "Site Store Master",        to: "/app/ops/site-master",            icon: MapPin,       testid: "nav-site-store", perm: "projects" },
  { department: "store", label: "Bin / Shelf Location",     to: "/app/store-inventory",            icon: Layers,       testid: "nav-bin", perm: "inventory" },
  { department: "store", label: "Opening Stock",            to: "/app/store-inventory",            icon: PlusSquare,   testid: "nav-opening", perm: "inventory" },
  { department: "store", label: "Stock Balance",            to: "/app/store-inventory",            icon: Boxes,        testid: "nav-stock-bal", perm: "inventory" },
  { department: "store", label: "Stock Ledger",             to: "/app/store-transactions",         icon: ScanLine,     testid: "nav-stock-ledger", perm: "inventory" },
  { department: "store", label: "Stock Movements",          to: "/app/store-transactions",         icon: ScanLine,     testid: "nav-store-txns", perm: "inventory" },
  { department: "store", label: "Material Request",         to: "/app/material-allocations",       icon: ClipboardList, testid: "nav-mat-req", perm: "material_allocations" },
  { department: "store", label: "Purchase Requisition Link", to: "/app/purchase-requisitions",     icon: ClipboardList, testid: "nav-pr-link", perm: "purchase_requisitions" },
  { department: "store", label: "Goods Receipt Note",       to: "/app/grn",                        icon: PackageCheck, testid: "nav-grn", perm: "grn" },
  { department: "store", label: "Material Inspection",      to: "/app/grn",                        icon: ClipboardCheck, testid: "nav-mat-inspect", perm: "grn" },
  { department: "store", label: "Material Issue",           to: "/app/material-allocations",       icon: Boxes,        testid: "nav-mat-issue", perm: "material_allocations" },
  { department: "store", label: "Material Return",          to: "/app/store-transactions",         icon: ScanLine,     testid: "nav-mat-return", perm: "inventory" },
  { department: "store", label: "Material Transfer",        to: "/app/challans",                   icon: Truck,        testid: "nav-mat-transfer", perm: "challans" },
  { department: "store", label: "In-Transit Stock",         to: "/app/challans",                   icon: Truck,        testid: "nav-in-transit", perm: "challans" },
  { department: "store", label: "Stock Adjustment",         to: "/app/store-transactions",         icon: ScanLine,     testid: "nav-stock-adj", perm: "inventory" },
  { department: "store", label: "Damage / Loss Entry",      to: "/app/store-transactions",         icon: AlertTriangle, testid: "nav-damage", perm: "inventory" },
  { department: "store", label: "Scrap Management",         to: "/app/store-transactions",         icon: Trash2,       testid: "nav-scrap", perm: "inventory" },
  { department: "store", label: "Tool Issue Register",      to: "/app/assets",                     icon: Wrench,       testid: "nav-tool-issue", perm: "assets" },
  { department: "store", label: "Tool Return Register",     to: "/app/assets",                     icon: Wrench,       testid: "nav-tool-return", perm: "assets" },
  { department: "store", label: "PPE Issue Register",       to: "/app/ppe",                        icon: Hammer,       testid: "nav-ppe", perm: "ppe_issuance" },
  { department: "store", label: "Asset Issue Register",     to: "/app/asset-lifecycle",            icon: Wrench,       testid: "nav-asset-issue", perm: "asset_lifecycle" },
  { department: "store", label: "Asset Lifecycle",          to: "/app/asset-lifecycle",            icon: Wrench,       testid: "nav-asset-life", perm: "asset_lifecycle" },
  { department: "store", label: "Assets",                   to: "/app/assets",                     icon: Wrench,       testid: "nav-assets", perm: "assets" },
  { department: "store", label: "Physical Stock Count",     to: "/app/store-inventory",            icon: ClipboardCheck, testid: "nav-stock-count", perm: "inventory" },
  { department: "store", label: "Stock Reconciliation",     to: "/app/store-inventory",            icon: ClipboardCheck, testid: "nav-stock-recon", perm: "inventory" },
  { department: "store", label: "Low Stock / Reorder Alert", to: "/app/inventory-intel",           icon: AlertTriangle, testid: "nav-low-stock", perm: "inventory" },
  { department: "store", label: "Project-wise Consumption", to: "/app/inventory-intel",            icon: BarChart3,    testid: "nav-proj-consume", perm: "inventory" },
  { department: "store", label: "Site-wise Stock",          to: "/app/inventory-intel",            icon: BarChart3,    testid: "nav-site-stock", perm: "inventory" },
  { department: "store", label: "Employee-wise PPE Pending", to: "/app/ppe",                       icon: Hammer,       testid: "nav-emp-ppe", perm: "ppe_issuance" },
  { department: "store", label: "Inventory Intel",          to: "/app/inventory-intel",            icon: BarChart3,    testid: "nav-inv-intel", perm: "inventory" },
  { department: "store", label: "Inventory Reports",        to: "/app/inventory-intel",            icon: FileBarChart, testid: "nav-inv-reports", perm: "inventory" },

  // ═══════════════ 6. PROCUREMENT & VENDORS ═══════════════
  { department: "procurement", label: "Procurement Dashboard", to: "/app/procurement-dashboard",   icon: Workflow,      testid: "nav-procurement-dashboard", perm: "purchase_requisitions" },
  { department: "procurement", label: "Vendor Master",         to: "/app/vendors",                  icon: Truck,         testid: "nav-vendors", perm: "vendors" },
  { department: "procurement", label: "Vendor Onboarding",     to: "/app/vendors",                  icon: UserPlus,      testid: "nav-vendor-onboard", perm: "vendors" },
  { department: "procurement", label: "Vendor Documents",      to: "/app/procurement/compliance",   icon: FolderArchive, testid: "nav-vendor-docs", perm: "vendors" },
  { department: "procurement", label: "Vendor Compliance",     to: "/app/procurement/compliance",   icon: ShieldCheck,   testid: "nav-vendor-compliance", perm: "vendors" },
  { department: "procurement", label: "Vendor Category Master", to: "/app/admin/categories",         icon: Tag,           testid: "nav-vendor-cat", superAdminOnly: true },
  { department: "procurement", label: "Purchase Requisition",  to: "/app/purchase-requisitions",    icon: ClipboardList, testid: "nav-pr", perm: "purchase_requisitions" },
  { department: "procurement", label: "PR Approval",           to: "/app/approvals",                icon: CheckSquare,   testid: "nav-pr-approval", perm: "approvals" },
  { department: "procurement", label: "Stock Availability Check", to: "/app/inventory-intel",       icon: BarChart3,     testid: "nav-stock-check", perm: "inventory" },
  { department: "procurement", label: "RFQ Management",        to: "/app/rfqs",                     icon: FileSearch,    testid: "nav-rfq", perm: "rfqs" },
  { department: "procurement", label: "Vendor Quotation Entry", to: "/app/rfqs",                    icon: FileText,      testid: "nav-vendor-quote", perm: "rfqs" },
  { department: "procurement", label: "Quotation Comparison",  to: "/app/rfqs",                     icon: BarChart3,     testid: "nav-quote-compare", perm: "rfqs" },
  { department: "procurement", label: "Negotiation Record",    to: "/app/rfqs",                     icon: MessageSquare, testid: "nav-negotiate", perm: "rfqs" },
  { department: "procurement", label: "Purchase Order",        to: "/app/purchase-orders",          icon: ShoppingCart,  testid: "nav-po", perm: "purchase_orders" },
  { department: "procurement", label: "PO Approval",           to: "/app/approvals",                icon: CheckSquare,   testid: "nav-po-approval", perm: "approvals" },
  { department: "procurement", label: "Service Orders & SRN",  to: "/app/procurement/service-orders", icon: Briefcase,   testid: "nav-service-orders", perm: "purchase_orders" },
  { department: "procurement", label: "Rate Contracts",        to: "/app/procurement/rate-contracts", icon: FileSignature, testid: "nav-rate-contracts", perm: "vendors" },
  { department: "procurement", label: "Material Receipt / GRN", to: "/app/grn",                     icon: PackageCheck,  testid: "nav-grn-link", perm: "grn" },
  { department: "procurement", label: "Service Receipt Link",  to: "/app/procurement/service-orders", icon: ClipboardCheck, testid: "nav-srn", perm: "purchase_orders" },
  { department: "procurement", label: "Quality Inspection",    to: "/app/grn",                      icon: ClipboardCheck, testid: "nav-qi", perm: "grn" },
  { department: "procurement", label: "Vendor Bill Verification", to: "/app/accounts",              icon: Receipt,       testid: "nav-bill-verify", perm: "accounting" },
  { department: "procurement", label: "Vendor Bill Mismatch",  to: "/app/accounts/notes",           icon: AlertTriangle, testid: "nav-bill-mismatch", perm: "accounting" },
  { department: "procurement", label: "Vendor Advance",        to: "/app/accounts",                 icon: Wallet,        testid: "nav-vendor-adv", perm: "accounting" },
  { department: "procurement", label: "Vendor Payment Status", to: "/app/accounts/dashboard",       icon: Wallet,        testid: "nav-vendor-payment", perm: "accounting" },
  { department: "procurement", label: "Vendor Performance",    to: "/app/procurement-intel",        icon: Award,         testid: "nav-vendor-perf", perm: "vendors" },
  { department: "procurement", label: "Procurement Intel",     to: "/app/procurement-intel",        icon: BarChart3,     testid: "nav-procurement-intel", perm: "vendors" },
  { department: "procurement", label: "Procurement Reports",   to: "/app/procurement/reports",      icon: FileBarChart,  testid: "nav-procurement-reports", perm: "purchase_requisitions" },

  // ═══════════════ 7. ACCOUNTS ═══════════════
  { department: "accounts", label: "Accounts Dashboard",       to: "/app/accounts",                  icon: FileText,    testid: "nav-accounts", perm: "accounting" },
  { department: "accounts", label: "Chart of Accounts",        to: "/app/accounts",                  icon: ListChecks,  testid: "nav-coa", perm: "accounting" },
  { department: "accounts", label: "Ledger Master",            to: "/app/accounts",                  icon: ListChecks,  testid: "nav-ledger", perm: "accounting" },
  { department: "accounts", label: "Client Invoice",           to: "/app/ra-bills",                  icon: Receipt,     testid: "nav-client-inv", perm: "ra_bills" },
  { department: "accounts", label: "RA Bill / Running Bill",   to: "/app/ra-bills",                  icon: Receipt,     testid: "nav-ra-bills", perm: "ra_bills" },
  { department: "accounts", label: "Vendor Invoice",           to: "/app/accounts",                  icon: Receipt,     testid: "nav-vendor-inv", perm: "accounting" },
  { department: "accounts", label: "Receipt Entry",            to: "/app/receivables",               icon: Wallet,      testid: "nav-receipts", perm: "receivables" },
  { department: "accounts", label: "Payment Entry",            to: "/app/accounts",                  icon: Wallet,      testid: "nav-payments", perm: "accounting" },
  { department: "accounts", label: "Journal Voucher",          to: "/app/accounts",                  icon: FileSignature, testid: "nav-jv", perm: "accounting" },
  { department: "accounts", label: "Contra Voucher",           to: "/app/accounts",                  icon: FileSignature, testid: "nav-contra", perm: "accounting" },
  { department: "accounts", label: "Debit Note",               to: "/app/accounts/notes",            icon: Receipt,     testid: "nav-dn", perm: "accounting" },
  { department: "accounts", label: "Credit Note",              to: "/app/accounts/notes",            icon: Receipt,     testid: "nav-cn", perm: "accounting" },
  { department: "accounts", label: "Expense Voucher",          to: "/app/accounts",                  icon: Receipt,     testid: "nav-expense", perm: "accounting" },
  { department: "accounts", label: "Site Expense Verification", to: "/app/accounts",                 icon: ClipboardCheck, testid: "nav-site-expense", perm: "accounting" },
  { department: "accounts", label: "Payroll Posting",          to: "/app/accounts",                  icon: DollarSign,  testid: "nav-payroll-post", perm: "accounting" },
  { department: "accounts", label: "Bank Management",          to: "/app/accounts",                  icon: Banknote,    testid: "nav-bank", perm: "accounting" },
  { department: "accounts", label: "Cash Management",          to: "/app/accounts",                  icon: Banknote,    testid: "nav-cash", perm: "accounting" },
  { department: "accounts", label: "Bank Reconciliation",      to: "/app/accounts",                  icon: ClipboardCheck, testid: "nav-bank-recon", perm: "accounting" },
  { department: "accounts", label: "GST Dashboard",            to: "/app/accounts/compliance",       icon: Landmark,    testid: "nav-gst", perm: "accounting" },
  { department: "accounts", label: "TDS Dashboard",            to: "/app/accounts/compliance",       icon: Landmark,    testid: "nav-tds-acc", perm: "accounting" },
  { department: "accounts", label: "PF / ESIC Dashboard",      to: "/app/accounts/compliance",       icon: Landmark,    testid: "nav-pf-acc", perm: "accounting" },
  { department: "accounts", label: "Receivable Dashboard",     to: "/app/receivables",               icon: Wallet,      testid: "nav-receivables", perm: "receivables" },
  { department: "accounts", label: "Payable Dashboard",        to: "/app/accounts/dashboard",        icon: Wallet,      testid: "nav-payables", perm: "accounting" },
  { department: "accounts", label: "Project Profitability",    to: "/app/accounts/dashboard",        icon: TrendingUp,  testid: "nav-proj-prof", perm: "accounting" },
  { department: "accounts", label: "Project Cost Sheet",       to: "/app/accounts/budget",           icon: Calculator,  testid: "nav-proj-cost", perm: "accounting" },
  { department: "accounts", label: "Compliance Center",        to: "/app/accounts/compliance",       icon: Landmark,    testid: "nav-finance-compliance", perm: "accounting" },
  { department: "accounts", label: "Approval Inbox",           to: "/app/approvals",                 icon: CheckSquare, testid: "nav-acc-approvals", perm: "approvals" },
  { department: "accounts", label: "Audit Trail",              to: "/app/admin/audit-logs",          icon: FileSearch,  testid: "nav-acc-audit", superAdminOnly: true },
  { department: "accounts", label: "Reports Center",           to: "/app/reports",                   icon: FileBarChart, testid: "nav-acc-reports" },
  { department: "accounts", label: "Month-End Closing",        to: "/app/accounts",                  icon: Lock,        testid: "nav-mec", perm: "accounting" },
  { department: "accounts", label: "Year-End Closing",         to: "/app/accounts",                  icon: Lock,        testid: "nav-yec", perm: "accounting" },

  // ═══════════════ 8. FINANCE ═══════════════
  { department: "finance", label: "Finance Dashboard",         to: "/app/accounts/dashboard",        icon: LineChart,   testid: "nav-finance-dashboard", perm: "accounting" },
  { department: "finance", label: "Alerts & Follow-ups",       to: "/app/accounts/alerts",           icon: Bell,        testid: "nav-finance-alerts", perm: "accounting" },
  { department: "finance", label: "Cash Flow Planning",        to: "/app/accounts/dashboard",        icon: TrendingUp,  testid: "nav-cashflow", perm: "accounting" },
  { department: "finance", label: "Fund Planning",             to: "/app/accounts/dashboard",        icon: Calculator,  testid: "nav-fund-plan", perm: "accounting" },
  { department: "finance", label: "Bank Balance Planning",     to: "/app/accounts/dashboard",        icon: Banknote,    testid: "nav-bank-plan", perm: "accounting" },
  { department: "finance", label: "Payment Priority",          to: "/app/accounts/dashboard",        icon: ListChecks,  testid: "nav-pay-priority", perm: "accounting" },
  { department: "finance", label: "Payment Approval",          to: "/app/approvals",                 icon: CheckSquare, testid: "nav-pay-approval", perm: "approvals" },
  { department: "finance", label: "Budget Management",         to: "/app/accounts/budget",           icon: Wallet,      testid: "nav-budget", perm: "accounting" },
  { department: "finance", label: "Project Budget Approval",   to: "/app/approvals",                 icon: CheckSquare, testid: "nav-budget-approval", perm: "approvals" },
  { department: "finance", label: "Expense Approval",          to: "/app/approvals",                 icon: CheckSquare, testid: "nav-expense-approval", perm: "approvals" },
  { department: "finance", label: "Vendor Payment Planning",   to: "/app/accounts/dashboard",        icon: Wallet,      testid: "nav-vendor-pay-plan", perm: "accounting" },
  { department: "finance", label: "Salary Release Approval",   to: "/app/approvals",                 icon: CheckSquare, testid: "nav-salary-rel", perm: "approvals" },
  { department: "finance", label: "Advance Approval",          to: "/app/approvals",                 icon: CheckSquare, testid: "nav-adv-approval", perm: "approvals" },
  { department: "finance", label: "Loan Approval",             to: "/app/approvals",                 icon: CheckSquare, testid: "nav-loan-approval", perm: "approvals" },
  { department: "finance", label: "Financial Risk Dashboard",  to: "/app/accounts/dashboard",        icon: AlertTriangle, testid: "nav-risk", perm: "accounting" },
  { department: "finance", label: "Project Financial Health",  to: "/app/accounts/dashboard",        icon: Activity,    testid: "nav-proj-health", perm: "accounting" },
  { department: "finance", label: "Finance Reports",           to: "/app/reports",                   icon: FileBarChart, testid: "nav-finance-reports" },
  { department: "finance", label: "Go-Live Center",            to: "/app/admin/go-live",             icon: ListChecks,  testid: "nav-finance-golive", superAdminOnly: true },

  // ═══════════════ 9. SAFETY ═══════════════
  // Iter 127 — Safety Foundation phase 1. Real routes replace the old
  // "everything points to /app/safety" stubs. Section is grouped by phase-1
  // spec: Dashboard → Plan/HIRA/JSA → Permits/PPE/Training → Docs → Approvals/Audit.
  { department: "safety", label: "Safety Dashboard",          to: "/app/safety/dashboard",           icon: ShieldAlert,    testid: "nav-safety-dashboard", perm: "safety_reports" },
  { department: "safety", label: "Safety Plan",               to: "/app/safety/plans",               icon: ShieldCheck,    testid: "nav-safety-plan", perm: "safety_plans" },
  { department: "safety", label: "HIRA / Risk Assessment",    to: "/app/safety/hira",                icon: AlertTriangle,  testid: "nav-hira", perm: "hira" },
  { department: "safety", label: "JSA / Job Safety Analysis", to: "/app/safety/jsa",                 icon: ClipboardList,  testid: "nav-jsa", perm: "jsa" },
  { department: "safety", label: "Work Permits",              to: "/app/safety/work-permits",        icon: ClipboardCheck, testid: "nav-safety-wp", perm: "ptws" },
  { department: "safety", label: "PPE Requirements",          to: "/app/safety/ppe-requirements",    icon: Hammer,         testid: "nav-safety-ppe-req", perm: "safety_ppe_reqs" },
  { department: "safety", label: "PPE Compliance",            to: "/app/safety/ppe-compliance",      icon: ShieldCheck,    testid: "nav-safety-ppe-comp", perm: "ppe_issuance" },
  { department: "safety", label: "Safety Readiness",          to: "/app/safety/readiness",           icon: ShieldPlus,     testid: "nav-safety-readiness", perm: "safety_readiness" },
  { department: "safety", label: "Safety Training",           to: "/app/safety-trainings",           icon: GraduationCap,  testid: "nav-safety-training", perm: "safety_trainings" },
  { department: "safety", label: "Training Expiry",           to: "/app/safety/training-expiry",     icon: CalendarClock,  testid: "nav-safety-training-exp", perm: "safety_trainings" },
  { department: "safety", label: "Toolbox Talks",             to: "/app/toolbox-talks",              icon: MessageSquare,  testid: "nav-toolbox", perm: "toolbox_talks" },
  { department: "safety", label: "Safety Inspections",        to: "/app/safety/inspections",         icon: ClipboardList,  testid: "nav-safety-inspections", perm: "safety_inspections" },
  { department: "safety", label: "Safety Observations",       to: "/app/safety/observations",        icon: FileText,       testid: "nav-safety-obs", perm: "safety_reports" },
  { department: "safety", label: "Incidents / Near Miss",     to: "/app/safety/incidents",           icon: AlertTriangle,  testid: "nav-incident", perm: "safety_incidents" },
  { department: "safety", label: "CAPA Register",             to: "/app/safety/capa",                icon: Wrench,         testid: "nav-capa", perm: "safety_capa" },
  { department: "safety", label: "Safety Escalations",        to: "/app/safety/escalations",         icon: Siren,          testid: "nav-safety-esc", perm: "safety_escalations" },
  { department: "safety", label: "Safety Document Register",  to: "/app/safety/documents",           icon: FileText,       testid: "nav-safety-docs", perm: "safety_documents" },
  { department: "safety", label: "Safety Master Data",        to: "/app/safety/masters",             icon: Database,       testid: "nav-safety-masters", perm: "safety_masters" },
  // Phase 4 · Audits · Client Compliance · Reviews · Vendor · Cost · Management Review
  { department: "safety", label: "Safety Audits",             to: "/app/safety/audits",              icon: ClipboardCheck, testid: "nav-safety-audits", perm: "safety_audits" },
  { department: "safety", label: "Client Compliance",         to: "/app/safety/client-compliance",   icon: CheckSquare,    testid: "nav-safety-client-compliance", perm: "safety_client_compliance" },
  { department: "safety", label: "Monthly Safety Review",     to: "/app/safety/reviews",             icon: CalendarDays,   testid: "nav-safety-reviews", perm: "safety_reviews" },
  { department: "safety", label: "Vendor Safety Compliance",  to: "/app/safety/vendor-compliance",   icon: Truck,          testid: "nav-safety-vendor-compliance", perm: "safety_vendor_compliance" },
  { department: "safety", label: "Safety Cost Register",      to: "/app/safety/costs",               icon: Wallet,         testid: "nav-safety-costs", perm: "safety_costs" },
  { department: "safety", label: "Management Review Dashboard", to: "/app/safety/management-review", icon: Activity,       testid: "nav-safety-mgmt-review", perm: "safety_reports" },
  // Phase 5 · Closure · Reports · Audit Trail
  { department: "safety", label: "Project Safety Closure",     to: "/app/safety/project-closure",     icon: ClipboardList,  testid: "nav-safety-closure", perm: "safety_closure" },
  { department: "safety", label: "Safety Reports Center",      to: "/app/safety/reports",             icon: FileSpreadsheet, testid: "nav-safety-reports", perm: "safety_reports" },
  { department: "safety", label: "Safety Audit Trail",         to: "/app/safety/audit-trail",         icon: History,        testid: "nav-safety-audit-trail", perm: "safety_reports" },
  { department: "safety", label: "Safety Approval Inbox",     to: "/app/approvals",                  icon: ClipboardCheck, testid: "nav-safety-approvals", perm: "approvals" },
  { department: "safety", label: "Safety Reports",            to: "/app/safety",                     icon: FileBarChart,   testid: "nav-safety-reports", perm: "safety_reports" },
  { department: "safety", label: "Medical Fitness Link",      to: "/app/hr/letters",                 icon: Stethoscope,    testid: "nav-med-link", perm: "hr_letters" },

  // ═══════════════ 10. LOGISTICS ═══════════════
  { department: "logistics", label: "Logistics Dashboard",    to: "/app/logistics",                       icon: Car,           testid: "nav-logistics", perm: "vehicles" },
  { department: "logistics", label: "Vehicle Master",         to: "/app/logistics/vehicles",              icon: Car,           testid: "nav-vehicles", perm: "vehicles" },
  { department: "logistics", label: "Driver Master",          to: "/app/logistics/drivers",               icon: User2,         testid: "nav-drivers", perm: "drivers" },
  { department: "logistics", label: "Transport Vendor",       to: "/app/logistics/vendor-profiles",       icon: Truck,         testid: "nav-transport-vendor", perm: "logistics_masters" },
  { department: "logistics", label: "Route Master",           to: "/app/logistics/routes",                icon: Route,         testid: "nav-routes", perm: "logistics_masters" },
  { department: "logistics", label: "Loading / Unloading Points", to: "/app/logistics/loading-points",    icon: PackageCheck,  testid: "nav-loading", perm: "logistics_masters" },
  { department: "logistics", label: "Dispatch Types",         to: "/app/logistics/dispatch-types",        icon: Package,       testid: "nav-dispatch-types", perm: "logistics_masters" },
  { department: "logistics", label: "Dispatch Request",       to: "/app/logistics/dispatch-requests",     icon: Truck,         testid: "nav-dispatch-req", perm: "dispatch_requests" },
  { department: "logistics", label: "In-Transit Tracking",    to: "/app/logistics/in-transit",            icon: MapPinned,     testid: "nav-in-transit", perm: "dispatch_requests" },
  { department: "logistics", label: "Delivery Confirmations", to: "/app/logistics/deliveries",            icon: PackageCheck,  testid: "nav-deliveries", perm: "dispatch_requests" },
  { department: "logistics", label: "Transit Exceptions",     to: "/app/logistics/exceptions",            icon: FilePlus2,     testid: "nav-exceptions", perm: "dispatch_requests" },
  { department: "logistics", label: "Vehicle Availability",   to: "/app/logistics/vehicle-availability",  icon: Car,           testid: "nav-veh-avail", perm: "vehicles" },
  { department: "logistics", label: "Driver Availability",    to: "/app/logistics/driver-availability",   icon: User2,         testid: "nav-drv-avail", perm: "drivers" },
  { department: "logistics", label: "Material Dispatch",      to: "/app/challans",                        icon: Truck,         testid: "nav-mat-dispatch", perm: "challans" },
  { department: "logistics", label: "Manpower Mobilization",  to: "/app/logistics/mobilizations",         icon: Users,         testid: "nav-log-mobilization", perm: "dispatch_requests" },
  { department: "logistics", label: "Manpower Mobilization Travel", to: "/app/logistics/travel",         icon: Route,         testid: "nav-mob-travel", perm: "dispatch_requests" },
  { department: "logistics", label: "Accommodation",           to: "/app/logistics/accommodations",       icon: Hotel,         testid: "nav-accommodation", perm: "dispatch_requests" },
  { department: "logistics", label: "Site Reporting",          to: "/app/logistics/site-reporting",       icon: MapPinned,     testid: "nav-site-reporting", perm: "dispatch_requests" },
  { department: "logistics", label: "Demobilization",          to: "/app/logistics/demobilizations",      icon: LogOut,        testid: "nav-demobilization", perm: "dispatch_requests" },
  { department: "logistics", label: "Fuel / Diesel Entry",    to: "/app/logistics/fuel",                  icon: Fuel,          testid: "nav-fuel", perm: "dispatch_requests" },
  { department: "logistics", label: "Vehicle Expense",        to: "/app/logistics/vehicle-expenses",      icon: Wallet,        testid: "nav-vehicle-exp", perm: "dispatch_requests" },
  { department: "logistics", label: "Vehicle Maintenance",    to: "/app/logistics/maintenance",           icon: Wrench,        testid: "nav-maintenance", perm: "vehicles" },
  { department: "logistics", label: "Transport Vendor Bills", to: "/app/logistics/vendor-bills",          icon: FileText,      testid: "nav-vendor-bills", perm: "dispatch_requests" },
  { department: "logistics", label: "Logistics Cost Summary", to: "/app/logistics/cost-summary",          icon: DollarSign,    testid: "nav-logistics-cost", perm: "dispatch_requests" },
  { department: "logistics", label: "Project-wise Cost",     to: "/app/logistics/cost-by-project",       icon: DollarSign,    testid: "nav-cost-by-project", perm: "dispatch_requests" },
  { department: "logistics", label: "Vehicle-wise Cost",     to: "/app/logistics/cost-by-vehicle",       icon: Car,           testid: "nav-cost-by-vehicle", perm: "vehicles" },
  { department: "logistics", label: "Finance Approvals",     to: "/app/logistics/finance-approvals",     icon: FileBarChart,  testid: "nav-finance-approvals", perm: "dispatch_requests" },
  { department: "logistics", label: "Vendor Payable",        to: "/app/logistics/vendor-payable",        icon: FileText,      testid: "nav-vendor-payable", perm: "dispatch_requests" },
  { department: "logistics", label: "Accounts Posting",      to: "/app/logistics/accounts-posting",      icon: FileBarChart,  testid: "nav-accounts-posting", perm: "dispatch_requests" },
  { department: "logistics", label: "Logistics Audit Trail",  to: "/app/logistics/audit-trail",           icon: History,       testid: "nav-logistics-audit", perm: "logistics_audit" },
  { department: "logistics", label: "Reports Center",         to: "/app/logistics/reports-center",        icon: FileBarChart,  testid: "nav-logistics-reports-center", perm: "logistics_reports" },
  { department: "logistics", label: "Advanced Dashboard",     to: "/app/logistics/dashboard-advanced",    icon: TrendingUp,    testid: "nav-logistics-adv-dashboard", perm: "vehicles" },
  { department: "logistics", label: "Logistics Reports",      to: "/app/reports",                         icon: FileBarChart,  testid: "nav-logistics-reports" },

  // ═══════════════ 11. MANAGEMENT & ADMIN ═══════════════
  { department: "admin", label: "Admin Console",              to: "/app/admin",                      icon: ShieldCheck,   testid: "nav-admin", end: true, superAdminOnly: true },
  { department: "admin", label: "User Management",            to: "/app/admin/users",                icon: Users,         testid: "nav-admin-users", superAdminOnly: true },
  { department: "admin", label: "Role Management",            to: "/app/admin/role-register",        icon: ShieldCheck,   testid: "nav-admin-role-register", superAdminOnly: true },
  { department: "admin", label: "Auto Code Override",         to: "/app/admin/code-override",        icon: KeyRound,      testid: "nav-admin-code-override", superAdminOnly: true },
  { department: "admin", label: "Role Catalog",               to: "/app/admin/role-catalog",         icon: ShieldPlus,    testid: "nav-admin-role-catalog", superAdminOnly: true },
  { department: "admin", label: "Permission Management",      to: "/app/admin/security-center",      icon: Lock,          testid: "nav-admin-security-center", superAdminOnly: true },
  { department: "admin", label: "Security Center",            to: "/app/admin/security-center",      icon: ShieldCheck,   testid: "nav-admin-security", superAdminOnly: true },
  { department: "admin", label: "Department Settings",        to: "/app/admin/departments",          icon: Building2,     testid: "nav-admin-departments", superAdminOnly: true },
  { department: "admin", label: "Department Master",          to: "/app/admin/department-master",    icon: Building2,     testid: "nav-admin-dept-master", superAdminOnly: true },
  { department: "admin", label: "Dept Governance",            to: "/app/admin/dept-governance",      icon: Workflow,      testid: "nav-admin-dept-governance", superAdminOnly: true },
  { department: "admin", label: "Approval Workflow Settings", to: "/app/admin/approval-workflow",    icon: Workflow,      testid: "nav-admin-workflow", superAdminOnly: true },
  { department: "admin", label: "Approval Matrix",            to: "/app/admin/approval-matrix",      icon: Workflow,      testid: "nav-admin-matrix", superAdminOnly: true },
  { department: "admin", label: "Notification Settings",      to: "/app/admin/email-settings",       icon: Bell,          testid: "nav-admin-notif", superAdminOnly: true },
  { department: "admin", label: "Numbering Series",           to: "/app/admin/sequences",            icon: ListChecks,    testid: "nav-admin-sequences", superAdminOnly: true },
  { department: "admin", label: "Company Settings",           to: "/app/admin/company-profile",      icon: Building2,     testid: "nav-admin-company", superAdminOnly: true },
  { department: "admin", label: "Branch / Site Settings",     to: "/app/ops/site-master",            icon: MapPin,        testid: "nav-admin-branch", perm: "projects" },
  { department: "admin", label: "Audit Logs",                 to: "/app/admin/audit-logs",           icon: FileSearch,    testid: "nav-admin-audit", superAdminOnly: true },
  { department: "admin", label: "Session Monitor",            to: "/app/admin/sessions",             icon: Activity,      testid: "nav-admin-sessions", superAdminOnly: true },
  { department: "admin", label: "Email Settings (M365)",      to: "/app/admin/email-settings",       icon: Mail,          testid: "nav-admin-email-settings", superAdminOnly: true },
  { department: "admin", label: "Email Outbox",               to: "/app/admin/email-outbox",         icon: Inbox,         testid: "nav-admin-email-outbox", superAdminOnly: true },
  { department: "admin", label: "OneDrive Cloud Storage",     to: "/app/admin/onedrive",             icon: Cloud,         testid: "nav-admin-onedrive", superAdminOnly: true },
  { department: "admin", label: "Data Linkage",               to: "/app/admin/data-linkage",         icon: Plug,          testid: "nav-admin-data-linkage", superAdminOnly: true },
  { department: "admin", label: "Master Data Settings",       to: "/app/admin/dropdowns",            icon: ListChecks,    testid: "nav-admin-dropdowns", superAdminOnly: true },
  { department: "admin", label: "Quotation Clauses",          to: "/app/admin/conditions",           icon: FileText,      testid: "nav-admin-conditions", superAdminOnly: true },
  { department: "admin", label: "Categories",                 to: "/app/admin/categories",           icon: Tag,           testid: "nav-admin-categories", superAdminOnly: true },
  { department: "admin", label: "Cost Centers",               to: "/app/admin/cost-centers",         icon: Wallet,        testid: "nav-admin-cost-centers", superAdminOnly: true },
  { department: "admin", label: "Billing Defaults",           to: "/app/settings/billing-defaults",  icon: Banknote,      testid: "nav-admin-billing-defaults", superAdminOnly: true },
  { department: "admin", label: "Data Cleanup",               to: "/app/admin/data-cleanup",         icon: Trash2,        testid: "nav-admin-data-cleanup", superAdminOnly: true },
  { department: "admin", label: "Go-Live Center",             to: "/app/admin/go-live",              icon: ListChecks,    testid: "nav-admin-go-live", superAdminOnly: true },
  { department: "admin", label: "System Health",              to: "/app/admin",                      icon: Activity,      testid: "nav-admin-health", superAdminOnly: true },
  { department: "admin", label: "Backup / Export",            to: "/app/admin/onedrive",             icon: Cloud,         testid: "nav-admin-backup", superAdminOnly: true },

  // ═══════════════ VENDOR PORTAL (vendor role only) ═══════════════
  { department: "admin", label: "My Vendor Portal", to: "/app/vendor-portal", icon: Store, testid: "nav-vendor-portal", vendorOnly: true, inSidebar: true },
];

// ─── Helpers ─────────────────────────────────────────────────────────────
/** Items for a department, grouped by parentLabel (or "_root" when none). */
export function itemsByDepartment(dept) {
  const items = MENU_ITEMS.filter((it) => it.department === dept);
  const groups = {};
  for (const it of items) {
    const key = it.parentLabel || "_root";
    if (!groups[key]) groups[key] = [];
    groups[key].push(it);
  }
  return groups;
}

/** Check whether a single item is visible to the current user. */
export function isItemVisible(item, { role, can }) {
  if (item.vendorOnly && role !== "vendor") return false;
  if (!item.vendorOnly && role === "vendor") return false; // vendors never see non-vendor items
  if (item.superAdminOnly && role !== "super_admin") return false;
  if (item.perm && can && !can(item.perm, "read")) return false;
  return true;
}

/** URL-pattern → department priority map. Patterns are evaluated in order;
 * first matching prefix wins. This avoids ambiguity when multiple menu items
 * share the same `to` (e.g. /app/accounts links exist in both accounts and
 * procurement departments). */
const ROUTE_DEPT_PRIORITY = [
  // most-specific first
  ["/app/accounts/dashboard", "finance"],
  ["/app/accounts/alerts", "finance"],
  ["/app/accounts/budget", "finance"],
  ["/app/admin/go-live", "finance"],
  ["/app/accounts", "accounts"],
  ["/app/ra-bills", "accounts"],
  ["/app/receivables", "accounts"],
  ["/app/ops", "ops"],
  ["/app/projects", "ops"],
  ["/app/dprs", "ops"],
  ["/app/measurements", "ops"],
  ["/app/employees", "hr"],
  ["/app/hr", "hr"],
  ["/app/payroll", "hr"],
  ["/app/recruitment", "hr"],
  ["/app/candidates", "hr"],
  ["/app/overtime", "hr"],
  ["/app/attendance", "hr"],
  ["/app/deployments", "hr"],
  ["/app/accommodations", "hr"],
  ["/app/safety", "safety"],
  ["/app/ppe", "safety"],
  ["/app/ptws", "safety"],
  ["/app/safety-trainings", "safety"],
  ["/app/toolbox-talks", "safety"],
  ["/app/store-inventory", "store"],
  ["/app/store-transactions", "store"],
  ["/app/inventory-intel", "store"],
  ["/app/assets", "store"],
  ["/app/asset-lifecycle", "store"],
  ["/app/grn", "store"],
  ["/app/material-allocations", "store"],
  ["/app/procurement-dashboard", "procurement"],
  ["/app/procurement-intel", "procurement"],
  ["/app/procurement", "procurement"],
  ["/app/purchase-orders", "procurement"],
  ["/app/purchase-requisitions", "procurement"],
  ["/app/rfqs", "procurement"],
  ["/app/vendors", "procurement"],
  ["/app/challans", "logistics"],
  ["/app/logistics", "logistics"],
  ["/app/quotations", "sales"],
  ["/app/sales", "sales"],
  ["/app/enquiries", "sales"],
  ["/app/orders", "sales"],
  ["/app/clients", "sales"],
  ["/app/client-map", "sales"],
  ["/app/sales-reports", "sales"],
  ["/app/service-rates", "sales"],
  ["/app/admin", "admin"],
  ["/app/settings", "admin"],
  ["/app/approvals", "dashboard"],
  ["/app/reports", "dashboard"],
];

/** Find the department key best matching a route path. */
export function findDepartmentForRoute(pathname) {
  if (!pathname) return null;
  for (const [prefix, dept] of ROUTE_DEPT_PRIORITY) {
    if (pathname === prefix || pathname.startsWith(prefix + "/")) return dept;
  }
  return null;
}

/** Returns departments visible to the user (i.e. at least one visible item). */
export function visibleDepartments({ role, can }) {
  const out = [];
  for (const d of DEPARTMENTS) {
    if (d.superAdminOnly && role !== "super_admin") continue;
    const items = MENU_ITEMS.filter((it) => it.department === d.key && isItemVisible(it, { role, can }));
    if (items.length === 0 && d.key !== "dashboard") continue;
    out.push({ ...d, items });
  }
  return out;
}

/** Routes where the per-page ModuleMenu rail should NOT be shown. */
export const MODULE_MENU_HIDDEN_ROUTES = new Set([
  "/app",
  "/app/",
  "/app/profile",
  "/app/me/email",
  "/app/modules",
]);

