import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Clients from "@/pages/Clients";
import Vendors from "@/pages/Vendors";
import Employees from "@/pages/Employees";
import Attendance from "@/pages/Attendance";
import Projects from "@/pages/Projects";
import Inventory from "@/pages/Inventory";
import PurchaseOrders from "@/pages/PurchaseOrders";
import Quotations from "@/pages/Quotations";
import Accounts from "@/pages/Accounts";
import Safety from "@/pages/Safety";
import Assets from "@/pages/Assets";
import Payroll from "@/pages/Payroll";
import Logistics from "@/pages/Logistics";
import Documents from "@/pages/Documents";
import Approvals from "@/pages/Approvals";
import ApprovalsDashboard from "@/pages/ApprovalsDashboard";
import ApprovalAnalytics from "@/pages/ApprovalAnalytics";
import MyRevisions from "@/pages/MyRevisions";
import Reports from "@/pages/Reports";
import Profile from "@/pages/Profile";
import Enquiries from "@/pages/Enquiries";
import Orders from "@/pages/Orders";
import StoreTransactions from "@/pages/StoreTransactions";
import PpeIssuance from "@/pages/PpeIssuance";
import PermitsToWork from "@/pages/PermitsToWork";
import SafetyTrainings from "@/pages/SafetyTrainings";
import ToolboxTalks from "@/pages/ToolboxTalks";
import RecruitmentRequests from "@/pages/RecruitmentRequests";
import Candidates from "@/pages/Candidates";
import Deployments from "@/pages/Deployments";
import ProjectManpower from "@/pages/ProjectManpower";
import AllocationReports from "@/pages/AllocationReports";
import AllocationBoard from "@/pages/AllocationBoard";
import DeploymentCalendar from "@/pages/DeploymentCalendar";
import ClientReports from "@/pages/ClientReports";
import ClientMap from "@/pages/ClientMap";
import SalesReports from "@/pages/SalesReports";
import PurchaseRequisitions from "@/pages/PurchaseRequisitions";
import ProcurementReports from "@/pages/ProcurementReports";
import Rfqs from "@/pages/Rfqs";
import Grn from "@/pages/Grn";
import ProcurementDashboard from "@/pages/ProcurementDashboard";
import MaterialAllocations from "@/pages/MaterialAllocations";
import AssetLifecycle from "@/pages/AssetLifecycle";
import Challans from "@/pages/Challans";
import InventoryIntel from "@/pages/InventoryIntel";
import ProcurementIntel from "@/pages/ProcurementIntel";
import Dprs from "@/pages/Dprs";
import DprMobile from "@/pages/DprMobile";
import Measurements from "@/pages/Measurements";
import RaBills from "@/pages/RaBills";
import Receivables from "@/pages/Receivables";
import ProjectOps from "@/pages/ProjectOps";
import ServiceRates from "@/pages/ServiceRates";
import BillingDefaults from "@/pages/BillingDefaults";
import CustomerCodeSettings from "@/pages/admin/CustomerCodeSettings";
import RoleDepartmentMap from "@/pages/admin/RoleDepartmentMap";
import CompanyProfile from "@/pages/admin/CompanyProfile";
import ConditionLibrary from "@/pages/admin/ConditionLibrary";
import UserManagement from "@/pages/admin/UserManagement";
import RoleRegister from "@/pages/admin/RoleRegister";
import Categories from "@/pages/admin/Categories";
import CostCenters from "@/pages/admin/CostCenters";
import DataCleanup from "@/pages/admin/DataCleanup";
import EmailSettings from "@/pages/admin/EmailSettings";
import EmailOutbox from "@/pages/admin/EmailOutbox";
import MyEmailSettings from "@/pages/MyEmailSettings";
import RoleCatalog from "@/pages/admin/RoleCatalog";
import OneDriveSettings from "@/pages/admin/OneDriveSettings";
import DataLinkage from "@/pages/admin/DataLinkage";
import DepartmentMaster from "@/pages/admin/DepartmentMaster";
import DeptGovernance from "@/pages/admin/DeptGovernance";
import Onboarding from "@/pages/hr/Onboarding";
import Employee360 from "@/pages/hr/Employee360";
import Leave from "@/pages/hr/Leave";
import HrLetters from "@/pages/hr/HrLetters";
import Advances from "@/pages/hr/Advances";
import AdvanceRecovery from "@/pages/hr/AdvanceRecovery";
import HrPayroll from "@/pages/hr/Payroll";
import Exit from "@/pages/hr/Exit";
import QuotationBuilder from "@/pages/QuotationBuilder";
import ProjectDashboard from "@/pages/ProjectDashboard";
import ContractHandovers from "@/pages/ops/ContractHandovers";
import MyAssignedProjects from "@/pages/ops/MyAssignedProjects";
import ResourceRequests from "@/pages/ops/ResourceRequests";
import ProjectOpsDashboard from "@/pages/ops/ProjectOpsDashboard";
import OpsReports from "@/pages/ops/OpsReports";
import ActivityTimeline from "@/pages/ops/ActivityTimeline";
import Accommodations from "@/pages/Accommodations";
import Overtime from "@/pages/Overtime";
import VendorPortal from "@/pages/VendorPortal";
import DepartmentLauncher from "@/pages/DepartmentLauncher";
import DepartmentWorkspace from "@/pages/DepartmentWorkspace";
import AdminConsole from "@/pages/admin/AdminConsole";
import PWAInstallPrompt from "@/components/PWAInstallPrompt";
import Departments from "@/pages/admin/Departments";
import Dropdowns from "@/pages/admin/Dropdowns";
import ApprovalMatrix from "@/pages/admin/ApprovalMatrix";
import ApprovalWorkflowSettings from "@/pages/admin/ApprovalWorkflowSettings";
import SequenceAdmin from "@/pages/admin/SequenceAdmin";
import AuditLogs from "@/pages/admin/AuditLogs";
import Sessions from "@/pages/admin/Sessions";
import "@/App.css";

function ProtectedShell({ children }) {
  return (
    <ProtectedRoute>
      <Layout>
        <ErrorBoundary>{children}</ErrorBoundary>
      </Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Toaster richColors position="top-right" />
          <PWAInstallPrompt />
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/app" element={<ProtectedShell><Dashboard /></ProtectedShell>} />
            <Route path="/app/clients" element={<ProtectedShell><Clients /></ProtectedShell>} />
            <Route path="/app/vendors" element={<ProtectedShell><Vendors /></ProtectedShell>} />
            <Route path="/app/employees" element={<ProtectedShell><Employees /></ProtectedShell>} />
            <Route path="/app/attendance" element={<ProtectedShell><Attendance /></ProtectedShell>} />
            <Route path="/app/projects" element={<ProtectedShell><Projects /></ProtectedShell>} />
            <Route path="/app/ops/handovers" element={<ProtectedShell><ContractHandovers /></ProtectedShell>} />
            <Route path="/app/ops/my-projects" element={<ProtectedShell><MyAssignedProjects /></ProtectedShell>} />
            <Route path="/app/ops/resource-requests" element={<ProtectedShell><ResourceRequests /></ProtectedShell>} />
            <Route path="/app/ops/project-dashboard" element={<ProtectedShell><ProjectOpsDashboard /></ProtectedShell>} />
            <Route path="/app/ops/reports" element={<ProtectedShell><OpsReports /></ProtectedShell>} />
            <Route path="/app/ops/timeline" element={<ProtectedShell><ActivityTimeline /></ProtectedShell>} />
            <Route path="/app/project-dashboard" element={<ProtectedShell><ProjectDashboard /></ProtectedShell>} />
            <Route path="/app/project-dashboard/:id" element={<ProtectedShell><ProjectDashboard /></ProtectedShell>} />
            <Route path="/app/inventory" element={<ProtectedShell><Inventory /></ProtectedShell>} />
            <Route path="/app/purchase-orders" element={<ProtectedShell><PurchaseOrders /></ProtectedShell>} />
            <Route path="/app/quotations" element={<ProtectedShell><Quotations /></ProtectedShell>} />
            <Route path="/app/quotations/:id/builder" element={<ProtectedShell><QuotationBuilder /></ProtectedShell>} />
            <Route path="/app/admin/company-profile" element={<ProtectedShell><CompanyProfile /></ProtectedShell>} />
            <Route path="/app/admin/conditions" element={<ProtectedShell><ConditionLibrary /></ProtectedShell>} />
            <Route path="/app/admin/users" element={<ProtectedShell><UserManagement /></ProtectedShell>} />
            <Route path="/app/admin/role-register" element={<ProtectedShell><RoleRegister /></ProtectedShell>} />
            <Route path="/app/admin/categories" element={<ProtectedShell><Categories /></ProtectedShell>} />
            <Route path="/app/admin/cost-centers" element={<ProtectedShell><CostCenters /></ProtectedShell>} />
            <Route path="/app/admin/data-cleanup" element={<ProtectedShell><DataCleanup /></ProtectedShell>} />
            <Route path="/app/admin/email-settings" element={<ProtectedShell><EmailSettings /></ProtectedShell>} />
            <Route path="/app/admin/email-outbox" element={<ProtectedShell><EmailOutbox /></ProtectedShell>} />
            <Route path="/app/me/email" element={<ProtectedShell><MyEmailSettings /></ProtectedShell>} />
            <Route path="/app/admin/role-catalog" element={<ProtectedShell><RoleCatalog /></ProtectedShell>} />
            <Route path="/app/admin/onedrive" element={<ProtectedShell><OneDriveSettings /></ProtectedShell>} />
            <Route path="/app/admin/data-linkage" element={<ProtectedShell><DataLinkage /></ProtectedShell>} />
            <Route path="/app/admin/department-master" element={<ProtectedShell><DepartmentMaster /></ProtectedShell>} />
            <Route path="/app/admin/dept-governance" element={<ProtectedShell><DeptGovernance /></ProtectedShell>} />
            <Route path="/app/hr/onboarding" element={<ProtectedShell><Onboarding /></ProtectedShell>} />
            <Route path="/app/hr/employee-360" element={<ProtectedShell><Employee360 /></ProtectedShell>} />
            <Route path="/app/hr/leave" element={<ProtectedShell><Leave /></ProtectedShell>}/>
            <Route path="/app/hr/letters" element={<ProtectedShell><HrLetters /></ProtectedShell>}/>
            <Route path="/app/hr/advances" element={<ProtectedShell><Advances /></ProtectedShell>}/>
            <Route path="/app/hr/advance-recovery" element={<ProtectedShell><AdvanceRecovery /></ProtectedShell>}/>
            <Route path="/app/hr/payroll" element={<ProtectedShell><HrPayroll /></ProtectedShell>}/>
            <Route path="/app/hr/exit" element={<ProtectedShell><Exit /></ProtectedShell>}/>
            <Route path="/app/accounts" element={<ProtectedShell><Accounts /></ProtectedShell>} />
            <Route path="/app/safety" element={<ProtectedShell><Safety /></ProtectedShell>} />
            <Route path="/app/assets" element={<ProtectedShell><Assets /></ProtectedShell>} />
            <Route path="/app/payroll" element={<ProtectedShell><Payroll /></ProtectedShell>} />
            <Route path="/app/logistics" element={<ProtectedShell><Logistics /></ProtectedShell>} />
            <Route path="/app/documents" element={<ProtectedShell><Documents /></ProtectedShell>} />
            <Route path="/app/approvals" element={<ProtectedShell><Approvals /></ProtectedShell>} />
            <Route path="/app/approvals/my-revisions" element={<ProtectedShell><MyRevisions /></ProtectedShell>} />
            <Route path="/app/approvals/dashboard" element={<ProtectedShell><ApprovalsDashboard /></ProtectedShell>} />
            <Route path="/app/approvals/analytics" element={<ProtectedShell><ApprovalAnalytics /></ProtectedShell>} />
            <Route path="/app/reports" element={<ProtectedShell><Reports /></ProtectedShell>} />
            <Route path="/app/profile" element={<ProtectedShell><Profile /></ProtectedShell>} />
            <Route path="/app/enquiries" element={<ProtectedShell><Enquiries /></ProtectedShell>} />
            <Route path="/app/orders" element={<ProtectedShell><Orders /></ProtectedShell>} />
            <Route path="/app/store-transactions" element={<ProtectedShell><StoreTransactions /></ProtectedShell>} />
            <Route path="/app/ppe" element={<ProtectedShell><PpeIssuance /></ProtectedShell>} />
            <Route path="/app/ptws" element={<ProtectedShell><PermitsToWork /></ProtectedShell>} />
            <Route path="/app/safety-trainings" element={<ProtectedShell><SafetyTrainings /></ProtectedShell>} />
            <Route path="/app/toolbox-talks" element={<ProtectedShell><ToolboxTalks /></ProtectedShell>} />
            <Route path="/app/recruitment" element={<ProtectedShell><RecruitmentRequests /></ProtectedShell>} />
            <Route path="/app/candidates" element={<ProtectedShell><Candidates /></ProtectedShell>} />
            <Route path="/app/deployments" element={<ProtectedShell><Deployments /></ProtectedShell>} />
            <Route path="/app/projects/:code/manpower" element={<ProtectedShell><ProjectManpower /></ProtectedShell>} />
            <Route path="/app/allocation-reports" element={<ProtectedShell><AllocationReports /></ProtectedShell>} />
            <Route path="/app/allocation-board" element={<ProtectedShell><AllocationBoard /></ProtectedShell>} />
            <Route path="/app/deployment-calendar" element={<ProtectedShell><DeploymentCalendar /></ProtectedShell>} />
            <Route path="/app/client-reports" element={<ProtectedShell><ClientReports /></ProtectedShell>} />
            <Route path="/app/client-map" element={<ProtectedShell><ClientMap /></ProtectedShell>} />
            <Route path="/app/sales-reports" element={<ProtectedShell><SalesReports /></ProtectedShell>} />
            <Route path="/app/purchase-requisitions" element={<ProtectedShell><PurchaseRequisitions /></ProtectedShell>} />
            <Route path="/app/procurement/reports" element={<ProtectedShell><ProcurementReports /></ProtectedShell>} />
            <Route path="/app/rfqs" element={<ProtectedShell><Rfqs /></ProtectedShell>} />
            <Route path="/app/grn" element={<ProtectedShell><Grn /></ProtectedShell>} />
            <Route path="/app/procurement-dashboard" element={<ProtectedShell><ProcurementDashboard /></ProtectedShell>} />
            <Route path="/app/material-allocations" element={<ProtectedShell><MaterialAllocations /></ProtectedShell>} />
            <Route path="/app/asset-lifecycle" element={<ProtectedShell><AssetLifecycle /></ProtectedShell>} />
            <Route path="/app/asset-lifecycle/:id" element={<ProtectedShell><AssetLifecycle /></ProtectedShell>} />
            <Route path="/app/challans" element={<ProtectedShell><Challans /></ProtectedShell>} />
            <Route path="/app/inventory-intel" element={<ProtectedShell><InventoryIntel /></ProtectedShell>} />
            <Route path="/app/procurement-intel" element={<ProtectedShell><ProcurementIntel /></ProtectedShell>} />
            <Route path="/app/dprs" element={<ProtectedShell><Dprs /></ProtectedShell>} />
            <Route path="/app/dprs/mobile" element={<ProtectedShell><DprMobile /></ProtectedShell>} />
            <Route path="/app/measurements" element={<ProtectedShell><Measurements /></ProtectedShell>} />
            <Route path="/app/ra-bills" element={<ProtectedShell><RaBills /></ProtectedShell>} />
            <Route path="/app/receivables" element={<ProtectedShell><Receivables /></ProtectedShell>} />
            <Route path="/app/project-ops" element={<ProtectedShell><ProjectOps /></ProtectedShell>} />
            <Route path="/app/service-rates" element={<ProtectedShell><ServiceRates /></ProtectedShell>} />
            <Route path="/app/settings/billing-defaults" element={<ProtectedShell><BillingDefaults /></ProtectedShell>} />
            <Route path="/app/admin/customer-code" element={<ProtectedShell><CustomerCodeSettings /></ProtectedShell>} />
            <Route path="/app/admin/role-department-map" element={<ProtectedShell><RoleDepartmentMap /></ProtectedShell>} />
            <Route path="/app/accommodations" element={<ProtectedShell><Accommodations /></ProtectedShell>} />
            <Route path="/app/overtime" element={<ProtectedShell><Overtime /></ProtectedShell>} />
            <Route path="/app/vendor-portal" element={<ProtectedShell><VendorPortal /></ProtectedShell>} />
            <Route path="/app/modules" element={<ProtectedShell><DepartmentLauncher /></ProtectedShell>} />
            <Route path="/app/modules/:dept" element={<ProtectedShell><DepartmentWorkspace /></ProtectedShell>} />
            <Route path="/app/admin" element={<ProtectedShell><AdminConsole /></ProtectedShell>} />
            <Route path="/app/admin/departments" element={<ProtectedShell><Departments /></ProtectedShell>} />
            <Route path="/app/admin/dropdowns" element={<ProtectedShell><Dropdowns /></ProtectedShell>} />
            <Route path="/app/admin/approval-matrix" element={<ProtectedShell><ApprovalMatrix /></ProtectedShell>} />
            <Route path="/app/admin/approval-workflow" element={<ProtectedShell><ApprovalWorkflowSettings /></ProtectedShell>} />
            <Route path="/app/admin/sequences" element={<ProtectedShell><SequenceAdmin /></ProtectedShell>} />
            <Route path="/app/admin/audit-logs" element={<ProtectedShell><AuditLogs /></ProtectedShell>} />
            <Route path="/app/admin/sessions" element={<ProtectedShell><Sessions /></ProtectedShell>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
