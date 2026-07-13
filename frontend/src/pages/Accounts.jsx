/**
 * Accounts Module · Phase 1 Shell  (Iter 72)
 * ==========================================
 * Left sidebar with 17 submenus → right content area renders the selected view.
 * All views imported from /pages/accounts/AccountsViews.jsx.
 */
import { useState } from "react";
import {
  BookOpen, LayoutDashboard, FileText, Receipt, ArrowRightLeft, FileMinus,
  FilePlus, Scale, FileBarChart2, ListChecks, Inbox, ShieldCheck, Settings,
  Wallet, Calculator, BadgeIndianRupee, ClipboardList,
  FileInput, IndianRupee, Percent, TrendingUp, AlertTriangle, FileCheck2,
  Building2, CreditCard, PackageSearch, Clock, Lock,
  Landmark, FileSpreadsheet, FileCheck, Building,
} from "lucide-react";

import {
  AccountsDashboardView, CoAView, VoucherView, OpeningBalanceView, TrialBalanceView,
  GeneralLedgerView, DayBookView, ApprovalInboxView, AuditTrailView, AgingView, SettingsView,
} from "./accounts/AccountsViews";

import {
  ClientInvoicesView, ReceiptsView, ClientOutstandingView, GSTSalesRegisterView,
  TDSReceivableView, RetentionReceivableView, CollectionReportView, OverdueInvoicesView,
} from "./accounts/BillingViews";

import {
  VendorBillsView, VendorPaymentsView, VendorOutstandingView, GSTPurchaseRegisterView,
  TDSPayableView, RetentionPayableView, PaymentDueView, GRNPendingInvoiceView,
} from "./accounts/VendorBillingViews";

import {
  SiteExpensesView, PayrollPostingView, MaterialMovementView, ProjectCostSummaryView,
  SiteExpenseReportView, SalaryPayableView,
} from "./accounts/CostingViews";

import {
  ProjectProfitabilityView, BalanceSheetView, CashFlowView,
  MonthEndClosingView, AlertsCentreView,
} from "./accounts/ClosingViews";

import {
  BankRecView, GSTR1View, GSTR3BView, TDS26ASView, FixedAssetsView,
} from "./accounts/StatutoryViews";

const NAV = [
  { key: "dashboard",  label: "Dashboard",         icon: LayoutDashboard, group: "Overview" },
  { key: "coa",        label: "Chart of Accounts", icon: BookOpen,        group: "Masters" },
  { key: "ledger",     label: "Ledger Master",     icon: ClipboardList,   group: "Masters" },
  { key: "vch_sv",     label: "Sales Voucher",     icon: BadgeIndianRupee, group: "Vouchers", vType: "SV" },
  { key: "vch_puv",    label: "Purchase Voucher",  icon: Receipt,         group: "Vouchers", vType: "PUV" },
  { key: "vch_pv",     label: "Payment Voucher",   icon: Wallet,          group: "Vouchers", vType: "PV" },
  { key: "vch_rv",     label: "Receipt Voucher",   icon: Wallet,          group: "Vouchers", vType: "RV" },
  { key: "vch_jv",     label: "Journal Entry",     icon: FileText,        group: "Vouchers", vType: "JV" },
  { key: "vch_cv",     label: "Contra Voucher",    icon: ArrowRightLeft,  group: "Vouchers", vType: "CV" },
  { key: "vch_dn",     label: "Debit Note",        icon: FileMinus,       group: "Vouchers", vType: "DN" },
  { key: "vch_cn",     label: "Credit Note",       icon: FilePlus,        group: "Vouchers", vType: "CN" },
  // ── Phase 2: Client Billing & Receivables ───────────────────────
  { key: "client_inv", label: "Client Invoices",   icon: FileInput,       group: "Billing" },
  { key: "receipts",   label: "Receipts",          icon: IndianRupee,     group: "Billing" },
  { key: "outstanding",label: "Client Outstanding",icon: AlertTriangle,   group: "Receivables" },
  { key: "overdue",    label: "Overdue Invoices",  icon: AlertTriangle,   group: "Receivables" },
  { key: "collection", label: "Collection Report", icon: TrendingUp,      group: "Receivables" },
  { key: "tds_rcvbl",  label: "TDS Receivable",    icon: Percent,         group: "Receivables" },
  { key: "retn_rcvbl", label: "Retention Receivable", icon: FileCheck2,   group: "Receivables" },
  { key: "gst_sales",  label: "GST Sales Register",icon: FileBarChart2,   group: "Receivables" },
  // ── Phase 3: Vendor Bills & Payables ───────────────────────────────
  { key: "vendor_bills",  label: "Vendor Bills",        icon: Building2,    group: "Payables" },
  { key: "vendor_pays",   label: "Vendor Payments",     icon: CreditCard,   group: "Payables" },
  { key: "vendor_outs",   label: "Vendor Outstanding",  icon: AlertTriangle, group: "Payables" },
  { key: "payment_due",   label: "Payment Due",         icon: Clock,        group: "Payables" },
  { key: "tds_payable",   label: "TDS Payable",         icon: Percent,      group: "Payables" },
  { key: "retn_payable",  label: "Retention Payable",   icon: FileCheck2,   group: "Payables" },
  { key: "gst_purchase",  label: "GST Purchase Register", icon: FileBarChart2, group: "Payables" },
  { key: "grn_pending",   label: "GRN → Invoice Pending", icon: PackageSearch, group: "Payables" },
  // ── Phase 4: Project Costing & Site Expenses ───────────────────────
  { key: "site_expenses",  label: "Site Expenses",        icon: BadgeIndianRupee, group: "Costing" },
  { key: "payroll_post",   label: "Payroll Posting",      icon: Wallet,        group: "Costing" },
  { key: "material_move",  label: "Material Movement",    icon: PackageSearch, group: "Costing" },
  { key: "proj_cost",      label: "Project Cost Summary", icon: TrendingUp,    group: "Costing" },
  { key: "site_exp_rpt",   label: "Site Expense Report",  icon: FileBarChart2, group: "Costing" },
  { key: "salary_payable", label: "Salary & Advances",    icon: IndianRupee,   group: "Costing" },
  // ── Phase 5: Profitability, Closing, Controls ─────────────────────
  { key: "proj_profit",    label: "Project Profitability", icon: TrendingUp,    group: "Closing" },
  { key: "balance_sheet",  label: "Balance Sheet",         icon: Scale,         group: "Closing" },
  { key: "cash_flow",      label: "Cash Flow Statement",   icon: IndianRupee,   group: "Closing" },
  { key: "month_close",    label: "Month-End Closing",     icon: Lock,          group: "Closing" },
  { key: "alerts_centre",  label: "Alerts Centre",         icon: AlertTriangle, group: "Closing" },
  // ── Phase 6: Statutory & Compliance ───────────────────────────────
  { key: "bank_rec",       label: "Bank Reconciliation",   icon: Landmark,        group: "Statutory" },
  { key: "gstr1",          label: "GSTR-1 (Outward)",      icon: FileSpreadsheet, group: "Statutory" },
  { key: "gstr3b",         label: "GSTR-3B (Summary)",     icon: FileSpreadsheet, group: "Statutory" },
  { key: "tds_26as",       label: "TDS 26AS Matching",     icon: FileCheck,       group: "Statutory" },
  { key: "fixed_assets",   label: "Fixed Assets Register", icon: Building,        group: "Statutory" },
  // ── Period / Reports ────────────────────────────────────────────
  { key: "opening",    label: "Opening Balance",   icon: Calculator,      group: "Period" },
  { key: "trial",      label: "Trial Balance",     icon: Scale,           group: "Reports" },
  { key: "gl",         label: "General Ledger",    icon: FileBarChart2,   group: "Reports" },
  { key: "daybook",    label: "Day Book",          icon: ListChecks,      group: "Reports" },
  { key: "ar",         label: "AR Aging",          icon: FileBarChart2,   group: "Reports" },
  { key: "ap",         label: "AP Aging",          icon: FileBarChart2,   group: "Reports" },
  { key: "inbox",      label: "Approval Inbox",    icon: Inbox,           group: "Governance" },
  { key: "audit",      label: "Audit Trail",       icon: ShieldCheck,     group: "Governance" },
  { key: "settings",   label: "Accounts Settings", icon: Settings,        group: "Configure" },
];

export default function Accounts() {
  const [active, setActive] = useState("dashboard");
  const groups = [...new Set(NAV.map(n => n.group))];

  const View = (() => {
    const item = NAV.find(n => n.key === active);
    if (!item) return null;
    switch (item.key) {
      case "dashboard": return <AccountsDashboardView onJump={(card) => {
        // smart-jump: card → relevant view
        const map = {
          total_receivables: "ar", total_payables: "ap",
          retention_receivable: "ar", retention_payable: "ap",
          vendor_payable: "ap", client_advances: "trial",
          bank_balance: "gl", cash_balance: "gl", petty_cash: "gl",
          gst_payable: "trial", tds_payable: "trial", salary_payable: "trial",
          labour_payable: "trial", employee_advances: "trial", vendor_advances: "trial",
          monthly_income: "trial", monthly_expenses: "trial", net_cash_flow: "trial",
          pending_vouchers: "inbox", unposted_vouchers: "inbox",
          missing_attachment_alerts: "daybook",
        };
        setActive(map[card] || "trial");
      }} />;
      case "coa":     return <CoAView />;
      case "ledger":  return <CoAView />; /* Ledger Master = CoA grouped view */
      case "opening": return <OpeningBalanceView />;
      case "trial":   return <TrialBalanceView />;
      case "gl":      return <GeneralLedgerView />;
      case "daybook": return <DayBookView />;
      case "ar":      return <AgingView kind="ar" />;
      case "ap":      return <AgingView kind="ap" />;
      case "inbox":   return <ApprovalInboxView />;
      case "audit":   return <AuditTrailView />;
      case "settings":return <SettingsView />;
      // Billing & Receivables
      case "client_inv":  return <ClientInvoicesView />;
      case "receipts":    return <ReceiptsView />;
      case "outstanding": return <ClientOutstandingView />;
      case "overdue":     return <OverdueInvoicesView />;
      case "collection":  return <CollectionReportView />;
      case "tds_rcvbl":   return <TDSReceivableView />;
      case "retn_rcvbl":  return <RetentionReceivableView />;
      case "gst_sales":   return <GSTSalesRegisterView />;
      // Vendor Bills & Payables
      case "vendor_bills":  return <VendorBillsView />;
      case "vendor_pays":   return <VendorPaymentsView />;
      case "vendor_outs":   return <VendorOutstandingView />;
      case "payment_due":   return <PaymentDueView />;
      case "tds_payable":   return <TDSPayableView />;
      case "retn_payable":  return <RetentionPayableView />;
      case "gst_purchase":  return <GSTPurchaseRegisterView />;
      case "grn_pending":   return <GRNPendingInvoiceView />;
      // Phase 4: Project Costing
      case "site_expenses":  return <SiteExpensesView />;
      case "payroll_post":   return <PayrollPostingView />;
      case "material_move":  return <MaterialMovementView />;
      case "proj_cost":      return <ProjectCostSummaryView />;
      case "site_exp_rpt":   return <SiteExpenseReportView />;
      case "salary_payable": return <SalaryPayableView />;
      // Phase 5: Profitability & Closing
      case "proj_profit":    return <ProjectProfitabilityView />;
      case "balance_sheet":  return <BalanceSheetView />;
      case "cash_flow":      return <CashFlowView />;
      case "month_close":    return <MonthEndClosingView />;
      case "alerts_centre":  return <AlertsCentreView />;
      // Phase 6: Statutory & Compliance
      case "bank_rec":      return <BankRecView />;
      case "gstr1":         return <GSTR1View />;
      case "gstr3b":        return <GSTR3BView />;
      case "tds_26as":      return <TDS26ASView />;
      case "fixed_assets":  return <FixedAssetsView />;
      default:
        if (item.vType) return <VoucherView voucherType={item.vType} title={item.label} />;
        return null;
    }
  })();

  return (
    <div className="flex h-[calc(100vh-3.5rem)]" data-testid="accounts-page">
      {/* ─── Left Sub-Nav ─── */}
      <aside className="w-60 border-r bg-slate-50 overflow-y-auto shrink-0" data-testid="acc-subnav">
        <div className="px-3 py-3 border-b bg-white">
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-primary" />
            <div>
              <div className="text-sm font-display font-bold">Accounts</div>
              <div className="text-[10px] text-slate-500">Financial Control Centre</div>
            </div>
          </div>
        </div>
        {groups.map(g => (
          <div key={g} className="py-1">
            <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{g}</div>
            {NAV.filter(n => n.group === g).map(n => {
              const Icon = n.icon;
              return (
                <button
                  key={n.key}
                  onClick={() => setActive(n.key)}
                  data-testid={`acc-nav-${n.key}`}
                  className={`w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 transition ${
                    active === n.key
                      ? "bg-primary/10 text-primary font-semibold border-l-2 border-primary"
                      : "hover:bg-white text-slate-700"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span>{n.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </aside>

      {/* ─── Right Content ─── */}
      <main className="flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center gap-3">
          <div>
            <h1 className="text-xl font-display font-bold">
              {NAV.find(n => n.key === active)?.label || "Accounts"}
            </h1>
            <p className="text-xs text-slate-500">{NAV.find(n => n.key === active)?.group}</p>
          </div>
        </div>
        {View}
      </main>
    </div>
  );
}
