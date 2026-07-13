/**
 * Store & Inventory · Phase 1 — consolidated hub
 *
 * Sidebar pattern mirrors the Accounts module. Each entry renders an EXISTING
 * top-level page as an embedded component when possible (no duplication).
 *
 * The legacy top-level routes (/app/inventory, /app/store-transactions,
 * /app/material-allocations, /app/inventory-intel, /app/grn) remain available
 * for backward compatibility; this hub at /app/store-inventory is the new
 * canonical entry point per the Phase 1 spec.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  LayoutDashboard, Boxes, Tag, Ruler, Warehouse, MapPin, Layers,
  PackagePlus, BookOpenCheck, ArrowRightLeft, Inbox, ScrollText,
  BarChart3, Settings as SettingsIcon, ExternalLink, PackageCheck,
  Truck, ClipboardList, ShoppingCart, FileText, AlertOctagon, IndianRupee,
  FolderOpen, RotateCcw, ArrowLeftRight, Send, FolderCheck,
  HardHat, ShieldAlert, Drill, Recycle, UserCheck, AlertTriangle,
} from "lucide-react";

import {
  InventoryDashboardView, CategoryMasterView, UnitMasterView,
  StoreMasterView, SiteStoreMasterView, BinMasterView, OpeningStockView,
  StockBalanceView, InventorySettingsView,
} from "./store-inventory/MasterViews";

import {
  PRFromStockView, PendingPOsView, StockInwardReportView,
  GRNPendingInvoiceView, AccountsGRNVisibilityView, InspectionHoldView,
  ProcurementPipelineView,
} from "./store-inventory/Phase2Views";

import {
  MaterialRequestView, MaterialTransferView, InTransitStockView,
  SiteStockView, ProjectStockView, ProjectConsumptionView,
  PendingReturnableView, ProjectClosureCheckView,
} from "./store-inventory/Phase3Views";

import {
  PPEIssueView, PPEExpiryRegisterView, DamageLossView, ScrapView,
  EmployeeClearanceView, RecoveryRegisterView, TransitExceptionView, ToolRegisterView,
} from "./store-inventory/Phase4Views";

import {
  StockValuationView, PhysicalStockCountView, FinalDashboardView, ReconcileCheckView,
} from "./store-inventory/Phase5Views";

// Re-use the existing pages so we don't duplicate any logic
import Inventory from "./Inventory";
import StoreTransactions from "./StoreTransactions";
import InventoryIntel from "./InventoryIntel";
import Grn from "./Grn";
import MaterialAllocations from "./MaterialAllocations";

const NAV = [
  { key: "dashboard",     label: "Inventory Dashboard",  icon: LayoutDashboard, group: "Overview" },
  { key: "items",         label: "Item Master",          icon: Boxes,           group: "Masters" },
  { key: "categories",    label: "Item Categories",      icon: Tag,             group: "Masters" },
  { key: "units",         label: "Unit / UOM",           icon: Ruler,           group: "Masters" },
  { key: "stores",        label: "Store / Warehouse",    icon: Warehouse,       group: "Masters" },
  { key: "site_stores",   label: "Site Stores",          icon: MapPin,          group: "Masters" },
  { key: "bins",          label: "Bin / Shelf",          icon: Layers,          group: "Masters" },
  { key: "opening_stock", label: "Opening Stock",        icon: PackagePlus,     group: "Stock" },
  { key: "balance",       label: "Stock Balance",        icon: BookOpenCheck,   group: "Stock" },
  { key: "ledger",        label: "Stock Ledger",         icon: ScrollText,      group: "Stock" },
  { key: "transactions",  label: "Inventory Txns",       icon: ArrowRightLeft,  group: "Operations" },
  { key: "grn",           label: "GRN",                  icon: PackageCheck,    group: "Operations" },
  { key: "allocations",   label: "Material Allocations", icon: Truck,           group: "Operations" },
  // ── Phase 2: Procurement / Accounts / Finance integration ──────────
  { key: "pr_from_stock", label: "PR from Stock",        icon: ClipboardList,   group: "Procurement Integration" },
  { key: "pending_pos",   label: "Pending POs for GRN",  icon: ShoppingCart,    group: "Procurement Integration" },
  { key: "inward_report", label: "Stock Inward Report",  icon: PackageCheck,    group: "Procurement Integration" },
  { key: "inspection_hold", label: "Inspection Hold",    icon: AlertOctagon,    group: "Procurement Integration" },
  { key: "grn_pending_inv", label: "GRN Pending Invoice", icon: FileText,       group: "Accounts Integration" },
  { key: "accounts_grn",  label: "3-Way Match",          icon: FileText,        group: "Accounts Integration" },
  { key: "pipeline",      label: "Procurement Pipeline", icon: IndianRupee,     group: "Finance Integration" },
  // ── Phase 3: Material Requests + Transfers + Project/Site Stock ───
  { key: "material_req",  label: "Material Request",     icon: Send,            group: "Material Movement" },
  { key: "material_trf",  label: "Material Transfer",    icon: ArrowLeftRight,  group: "Material Movement" },
  { key: "in_transit",    label: "In-Transit Stock",     icon: Truck,           group: "Material Movement" },
  { key: "returnable",    label: "Pending Returnable",   icon: RotateCcw,       group: "Material Movement" },
  { key: "site_stock",    label: "Site-wise Stock",      icon: MapPin,          group: "Project & Site" },
  { key: "project_stock", label: "Project-wise Stock",   icon: FolderOpen,      group: "Project & Site" },
  { key: "project_consumption", label: "Project Consumption", icon: BarChart3,  group: "Project & Site" },
  { key: "closure_check", label: "Project Closure Check", icon: FolderCheck,    group: "Project & Site" },
  // ── Phase 4: Safety / Tools / Damage / Scrap / HR clearance ────────
  { key: "tool_register", label: "Tool Register",         icon: Drill,           group: "Safety & Tools" },
  { key: "ppe_issue",     label: "PPE Issue",             icon: HardHat,         group: "Safety & Tools" },
  { key: "ppe_expiry",    label: "PPE Expiry Register",   icon: ShieldAlert,     group: "Safety & Tools" },
  { key: "damage_loss",   label: "Damage / Loss",         icon: AlertTriangle,   group: "Damage & Scrap" },
  { key: "scrap",         label: "Scrap Entries",         icon: Recycle,         group: "Damage & Scrap" },
  { key: "recovery",      label: "Recovery Register",     icon: IndianRupee,     group: "Damage & Scrap" },
  { key: "transit_exc",   label: "Transit Exceptions",    icon: AlertOctagon,    group: "Damage & Scrap" },
  { key: "emp_clearance", label: "Employee Clearance",    icon: UserCheck,       group: "HR Integration" },
  // ── Phase 5: Valuation / Stock Count / Final Dashboard / Reconciliation ─
  { key: "final_dash",    label: "Final Dashboard",       icon: LayoutDashboard, group: "Valuation & Audit" },
  { key: "valuation",     label: "Stock Valuation",       icon: IndianRupee,     group: "Valuation & Audit" },
  { key: "stock_count",   label: "Physical Stock Count",  icon: ClipboardList,   group: "Valuation & Audit" },
  { key: "reconcile",     label: "Reconciliation Check",  icon: FolderCheck,     group: "Valuation & Audit" },
  { key: "approvals",     label: "Approval Inbox",       icon: Inbox,           group: "Governance" },
  { key: "audit",         label: "Audit Trail",          icon: ScrollText,      group: "Governance" },
  { key: "reports",       label: "Reports",              icon: BarChart3,       group: "Reports" },
  { key: "settings",      label: "Settings",             icon: SettingsIcon,    group: "Reports" },
];

function ExternalLinkCard({ to, title, description, testid }) {
  return (
    <div className="p-6 border rounded-md bg-slate-50">
      <h3 className="font-semibold text-base mb-1">{title}</h3>
      <p className="text-sm text-slate-600 mb-4">{description}</p>
      <Link to={to} data-testid={testid}
            className="inline-flex items-center gap-1 text-sm text-blue-700 hover:underline">
        Open <ExternalLink className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}

export default function StoreInventory() {
  const [view, setView] = useState("dashboard");
  const groups = [...new Set(NAV.map(n => n.group))];

  const renderView = () => {
    switch (view) {
      case "dashboard":     return <InventoryDashboardView />;
      case "items":         return <Inventory />;
      case "categories":    return <CategoryMasterView />;
      case "units":         return <UnitMasterView />;
      case "stores":        return <StoreMasterView />;
      case "site_stores":   return <SiteStoreMasterView />;
      case "bins":          return <BinMasterView />;
      case "opening_stock": return <OpeningStockView />;
      case "balance":       return <StockBalanceView />;
      case "ledger":        return (
        <ExternalLinkCard
          to="/app/inventory"
          title="Stock Ledger"
          description="Open Item Master and click the ledger icon on any item to see its detailed stock ledger (opening · receipt · issue · transfer · scrap · closing) with date filters."
          testid="link-ledger"
        />);
      case "transactions":  return <StoreTransactions />;
      case "grn":           return <Grn />;
      case "allocations":   return <MaterialAllocations />;
      // Phase 2 integration views
      case "pr_from_stock": return <PRFromStockView />;
      case "pending_pos":   return <PendingPOsView />;
      case "inward_report": return <StockInwardReportView />;
      case "inspection_hold": return <InspectionHoldView />;
      case "grn_pending_inv": return <GRNPendingInvoiceView />;
      case "accounts_grn":  return <AccountsGRNVisibilityView />;
      case "pipeline":      return <ProcurementPipelineView />;
      // Phase 3
      case "material_req":  return <MaterialRequestView />;
      case "material_trf":  return <MaterialTransferView />;
      case "in_transit":    return <InTransitStockView />;
      case "returnable":    return <PendingReturnableView />;
      case "site_stock":    return <SiteStockView />;
      case "project_stock": return <ProjectStockView />;
      case "project_consumption": return <ProjectConsumptionView />;
      case "closure_check": return <ProjectClosureCheckView />;
      // Phase 4
      case "tool_register": return <ToolRegisterView />;
      case "ppe_issue":     return <PPEIssueView />;
      case "ppe_expiry":    return <PPEExpiryRegisterView />;
      case "damage_loss":   return <DamageLossView />;
      case "scrap":         return <ScrapView />;
      case "recovery":      return <RecoveryRegisterView />;
      case "transit_exc":   return <TransitExceptionView />;
      case "emp_clearance": return <EmployeeClearanceView />;
      // Phase 5
      case "final_dash":    return <FinalDashboardView />;
      case "valuation":     return <StockValuationView />;
      case "stock_count":   return <PhysicalStockCountView />;
      case "reconcile":     return <ReconcileCheckView />;
      case "approvals":     return (
        <ExternalLinkCard
          to="/app/approvals"
          title="Approval Inbox"
          description="Inventory-related approvals (material issues above threshold, opening stock above value threshold) show up alongside other module approvals in the central Approvals inbox."
          testid="link-approvals"
        />);
      case "audit":         return (
        <ExternalLinkCard
          to="/app/audit-trail"
          title="Inventory Audit Trail"
          description="Every create / update / delete / approve action across Item Master, Stores, Bins, Categories, UOMs, Opening Stock and Inventory Transactions is captured in the global audit_logs collection. Filter by resource starting with `inv_` or `inventory_`."
          testid="link-audit"
        />);
      case "reports":       return <InventoryIntel />;
      case "settings":      return <InventorySettingsView />;
      default:              return <InventoryDashboardView />;
    }
  };

  return (
    <div className="flex gap-4 p-4">
      <aside className="w-60 shrink-0 border-r pr-3">
        <h2 className="font-semibold text-base mb-3 px-2">Store &amp; Inventory</h2>
        <nav className="space-y-3">
          {groups.map(g => (
            <div key={g}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-2 mb-1">{g}</div>
              <div className="space-y-0.5">
                {NAV.filter(n => n.group === g).map(n => {
                  const Icon = n.icon;
                  return (
                    <button key={n.key}
                      onClick={() => setView(n.key)}
                      data-testid={`si-nav-${n.key}`}
                      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-sm hover:bg-slate-100 ${
                        view === n.key ? "bg-slate-100 font-medium text-slate-900" : "text-slate-700"}`}>
                      <Icon className="h-3.5 w-3.5" /><span>{n.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>
      <main className="flex-1 min-w-0">{renderView()}</main>
    </div>
  );
}
