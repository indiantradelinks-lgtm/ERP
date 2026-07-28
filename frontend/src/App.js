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
import StoreInventory from "@/pages/StoreInventory";
import PurchaseOrders from "@/pages/PurchaseOrders";
import Quotations from "@/pages/Quotations";
import Accounts from "@/pages/Accounts";
import Safety from "@/pages/Safety";
// Iter 127 — Safety Foundation phase 1
import SafetyDashboard from "@/pages/safety/SafetyDashboard";
import SafetyMasters from "@/pages/safety/SafetyMasters";
import Hira from "@/pages/safety/Hira";
import Jsa from "@/pages/safety/Jsa";
import SafetyPlanRegister from "@/pages/safety/SafetyPlanRegister";
import SafetyDocumentRegister from "@/pages/safety/SafetyDocumentRegister";
// Iter 128 — Safety Phase 2
import WorkPermitRegister from "@/pages/safety/WorkPermitRegister";
import PpeRequirements from "@/pages/safety/PpeRequirements";
import PpeCompliance from "@/pages/safety/PpeCompliance";
import SafetyReadiness from "@/pages/safety/SafetyReadiness";
import TrainingExpiryRegister from "@/pages/safety/TrainingExpiryRegister";
// Iter 129 — Safety Phase 3
import SafetyInspections from "@/pages/safety/SafetyInspections";
import SafetyObservationsRegister from "@/pages/safety/SafetyObservationsRegister";
import Incidents from "@/pages/safety/Incidents";
import Capa from "@/pages/safety/Capa";
import SafetyEscalationDashboard from "@/pages/safety/SafetyEscalationDashboard";
// Iter 130 — Safety Phase 4 (Audits · Client Compliance · Reviews · Vendor · Cost)
import SafetyAudits from "@/pages/safety/SafetyAudits";
import ClientCompliance from "@/pages/safety/ClientCompliance";
import MonthlySafetyReview from "@/pages/safety/MonthlySafetyReview";
import VendorSafetyCompliance from "@/pages/safety/VendorSafetyCompliance";
import SafetyCostRegister from "@/pages/safety/SafetyCostRegister";
import SafetyManagementReview from "@/pages/safety/SafetyManagementReview";
// Iter 131 — Safety Phase 5 (Closure · Reports · Audit Trail)
import ProjectSafetyClosure from "@/pages/safety/ProjectSafetyClosure";
import SafetyReportsCenter from "@/pages/safety/SafetyReportsCenter";
import SafetyAuditTrail from "@/pages/safety/SafetyAuditTrail";
import Assets from "@/pages/Assets";
import Payroll from "@/pages/Payroll";
import Logistics from "@/pages/Logistics";
// Iter 132 — Logistics Phase 1
import LogisticsDashboard from "@/pages/logistics/LogisticsDashboard";
import VehicleMaster from "@/pages/logistics/VehicleMaster";
import DriverMaster from "@/pages/logistics/DriverMaster";
import DispatchRequests from "@/pages/logistics/DispatchRequests";
import { RouteMaster, LoadingUnloadingPoints, DispatchTypes, TransportVendorProfiles } from "@/pages/logistics/LogisticsMasters";
import { VehicleAvailability, DriverAvailability, LogisticsAuditTrail } from "@/pages/logistics/LogisticsAvailAudit";
// Iter 133 — Logistics Phase 2 (Dispatch lifecycle)
import DispatchRequestDetail from "@/pages/logistics/DispatchRequestDetail";
import { InTransitTracking, DeliveryConfirmations, TransitExceptions } from "@/pages/logistics/LogisticsPhase2Lists";
// Iter 134/135 — Logistics Phase 3 & 4
import {
  ManpowerMobilization, TravelArrangement, AccommodationArrangement, SiteReporting, Demobilization,
  FuelEntries, VehicleExpenses, VehicleMaintenance, VendorBills, LogisticsCostSummary,
} from "@/pages/logistics/LogisticsPhase34Pages";
// Iter 136 — Logistics Phase 4 Completion
import {
  FinanceApprovalInbox, VendorPayable, AccountsPostingStatus, ProjectWiseCost, VehicleWiseCost,
} from "@/pages/logistics/LogisticsPhase4Views";
// Iter 137 — Logistics Phase 5 (Reports, Closure, Advanced Dashboard)
import {
  LogisticsReportsCenter, TripClosurePanel, LogisticsAdvancedDashboard,
} from "@/pages/logistics/LogisticsPhase5Views";
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
import CodeOverride from "@/pages/admin/CodeOverride";
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
import HrMasters from "@/pages/hr/HrMasters";
import Employee360 from "@/pages/hr/Employee360";
import Leave from "@/pages/hr/Leave";
import HrLetters from "@/pages/hr/HrLetters";
import Advances from "@/pages/hr/Advances";
import AdvanceRecovery from "@/pages/hr/AdvanceRecovery";
import HrPayroll from "@/pages/hr/Payroll";
import Exit from "@/pages/hr/Exit";
import HrPhase2 from "@/pages/hr/HrPhase2";
import HrPhase3 from "@/pages/hr/HrPhase3";
import HrPhase4 from "@/pages/hr/HrPhase4";
import HrPhase5 from "@/pages/hr/HrPhase5";
import AttendanceCenter from "@/pages/hr/AttendanceCenter";
import GroupMedical from "@/pages/hr/GroupMedical";
import ReportsCenter from "@/pages/ReportsCenter";
import BillRequests from "@/pages/ops/BillRequests";
import QuotationBuilder from "@/pages/QuotationBuilder";
import ProjectDashboard from "@/pages/ProjectDashboard";
import ContractHandovers from "@/pages/ops/ContractHandovers";
import ServiceTypeMaster from "@/pages/ops/ServiceTypeMaster";
import SiteMaster from "@/pages/ops/SiteMaster";
import WorkOrders from "@/pages/ops/WorkOrders";
import ProjectTeam from "@/pages/ops/ProjectTeam";
import ProjectDocuments from "@/pages/ops/ProjectDocuments";
import ProjectStatus from "@/pages/ops/ProjectStatus";
import ProjectAuditTrail from "@/pages/ops/ProjectAuditTrail";
import ProjectSettings from "@/pages/ops/ProjectSettings";
import ProjectDashboardPhase1 from "@/pages/ops/ProjectDashboard";
import MyAssignedProjects from "@/pages/ops/MyAssignedProjects";
import ResourceRequests from "@/pages/ops/ResourceRequests";
import ProjectOpsDashboard from "@/pages/ops/ProjectOpsDashboard";
import OpsReports from "@/pages/ops/OpsReports";
import ActivityTimeline from "@/pages/ops/ActivityTimeline";
import ProjectPlanning from "@/pages/ops/ProjectPlanning";
import ProjectBOQ from "@/pages/ops/ProjectBOQ";
import ProjectWBS from "@/pages/ops/ProjectWBS";
import ProjectActivities from "@/pages/ops/ProjectActivities";
import ProjectResources from "@/pages/ops/ProjectResources";
import DailyProgressReports from "@/pages/ops/DailyProgressReports";
import WorkProgressTracker from "@/pages/ops/WorkProgressTracker";
import MeasurementSheets from "@/pages/ops/MeasurementSheets";
import SiteIssues from "@/pages/ops/SiteIssues";
import ClientInstructions from "@/pages/ops/ClientInstructions";
import ExtraWorks from "@/pages/ops/ExtraWorks";
import WorkPermits from "@/pages/ops/WorkPermits";
import ExecutionDashboard from "@/pages/ops/ExecutionDashboard";
import ProjectControlCenter from "@/pages/ops/ProjectControlCenter";
import ProjectClosureCenter from "@/pages/ops/ProjectClosureCenter";
import RateContracts from "@/pages/procurement/RateContracts";
import ServiceOrders from "@/pages/procurement/ServiceOrders";
import VendorComplianceCenter from "@/pages/procurement/VendorComplianceCenter";
import DebitCreditNotes from "@/pages/accounts/DebitCreditNotes";
import BudgetCommitmentCenter from "@/pages/accounts/BudgetCommitmentCenter";
import ComplianceCenter from "@/pages/accounts/ComplianceCenter";
import FinanceDashboard from "@/pages/accounts/FinanceDashboard";
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
import SecurityCenter from "@/pages/admin/SecurityCenter";
import GoLiveCenter from "@/pages/admin/GoLiveCenter";
import FinanceAlerts from "@/pages/accounts/FinanceAlerts";
import EnquiryFollowUpTracker from "@/pages/sales/EnquiryFollowUpTracker";
import InternalProjectReview from "@/pages/ops/InternalProjectReview";
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
            <Route path="/app/workers" element={<ProtectedShell><Employees master="worker" /></ProtectedShell>} />
            <Route path="/app/attendance" element={<ProtectedShell><Attendance /></ProtectedShell>} />
            <Route path="/app/attendance-center" element={<ProtectedShell><AttendanceCenter /></ProtectedShell>} />
            <Route path="/app/hr/group-medical" element={<ProtectedShell><GroupMedical /></ProtectedShell>} />
            <Route path="/app/projects" element={<ProtectedShell><Projects /></ProtectedShell>} />
            <Route path="/app/ops/handovers" element={<ProtectedShell><ContractHandovers /></ProtectedShell>} />
            <Route path="/app/ops/service-types" element={<ProtectedShell><ServiceTypeMaster /></ProtectedShell>} />
            <Route path="/app/ops/site-master" element={<ProtectedShell><SiteMaster /></ProtectedShell>} />
            <Route path="/app/ops/work-orders" element={<ProtectedShell><WorkOrders /></ProtectedShell>} />
            <Route path="/app/ops/team" element={<ProtectedShell><ProjectTeam /></ProtectedShell>} />
            <Route path="/app/ops/documents" element={<ProtectedShell><ProjectDocuments /></ProtectedShell>} />
            <Route path="/app/ops/project-status" element={<ProtectedShell><ProjectStatus /></ProtectedShell>} />
            <Route path="/app/ops/audit-trail" element={<ProtectedShell><ProjectAuditTrail /></ProtectedShell>} />
            <Route path="/app/ops/settings" element={<ProtectedShell><ProjectSettings /></ProtectedShell>} />
            <Route path="/app/ops/dashboard" element={<ProtectedShell><ProjectDashboardPhase1 /></ProtectedShell>} />
            <Route path="/app/ops/my-projects" element={<ProtectedShell><MyAssignedProjects /></ProtectedShell>} />
            <Route path="/app/ops/resource-requests" element={<ProtectedShell><ResourceRequests /></ProtectedShell>} />
            <Route path="/app/ops/project-dashboard" element={<ProtectedShell><ProjectOpsDashboard /></ProtectedShell>} />
            <Route path="/app/ops/reports" element={<ProtectedShell><OpsReports /></ProtectedShell>} />
            <Route path="/app/ops/timeline" element={<ProtectedShell><ActivityTimeline /></ProtectedShell>} />
            <Route path="/app/ops/planning" element={<ProtectedShell><ProjectPlanning /></ProtectedShell>} />
            <Route path="/app/ops/boq" element={<ProtectedShell><ProjectBOQ /></ProtectedShell>} />
            <Route path="/app/ops/wbs" element={<ProtectedShell><ProjectWBS /></ProtectedShell>} />
            <Route path="/app/ops/activities" element={<ProtectedShell><ProjectActivities /></ProtectedShell>} />
            <Route path="/app/ops/resources" element={<ProtectedShell><ProjectResources /></ProtectedShell>} />
            <Route path="/app/ops/dpr" element={<ProtectedShell><DailyProgressReports /></ProtectedShell>} />
            <Route path="/app/ops/work-progress" element={<ProtectedShell><WorkProgressTracker /></ProtectedShell>} />
            <Route path="/app/ops/measurements" element={<ProtectedShell><MeasurementSheets /></ProtectedShell>} />
            <Route path="/app/ops/site-issues" element={<ProtectedShell><SiteIssues /></ProtectedShell>} />
            <Route path="/app/ops/client-instructions" element={<ProtectedShell><ClientInstructions /></ProtectedShell>} />
            <Route path="/app/ops/extra-works" element={<ProtectedShell><ExtraWorks /></ProtectedShell>} />
            <Route path="/app/ops/work-permits" element={<ProtectedShell><WorkPermits /></ProtectedShell>} />
            <Route path="/app/ops/execution-dashboard" element={<ProtectedShell><ExecutionDashboard /></ProtectedShell>} />
            <Route path="/app/ops/control-center" element={<ProtectedShell><ProjectControlCenter /></ProtectedShell>} />
            <Route path="/app/ops/closure-center" element={<ProtectedShell><ProjectClosureCenter /></ProtectedShell>} />
            <Route path="/app/procurement/rate-contracts" element={<ProtectedShell><RateContracts /></ProtectedShell>} />
            <Route path="/app/procurement/service-orders" element={<ProtectedShell><ServiceOrders /></ProtectedShell>} />
            <Route path="/app/procurement/compliance" element={<ProtectedShell><VendorComplianceCenter /></ProtectedShell>} />
            <Route path="/app/accounts/notes" element={<ProtectedShell><DebitCreditNotes /></ProtectedShell>} />
            <Route path="/app/accounts/budget" element={<ProtectedShell><BudgetCommitmentCenter /></ProtectedShell>} />
            <Route path="/app/accounts/compliance" element={<ProtectedShell><ComplianceCenter /></ProtectedShell>} />
            <Route path="/app/accounts/dashboard" element={<ProtectedShell><FinanceDashboard /></ProtectedShell>} />
            <Route path="/app/accounts/alerts" element={<ProtectedShell><FinanceAlerts /></ProtectedShell>} />
            <Route path="/app/sales/enquiry-followup" element={<ProtectedShell><EnquiryFollowUpTracker /></ProtectedShell>} />
            <Route path="/app/ops/internal-review" element={<ProtectedShell><InternalProjectReview /></ProtectedShell>} />
            <Route path="/app/admin/security-center" element={<ProtectedShell><SecurityCenter /></ProtectedShell>} />
            <Route path="/app/admin/go-live" element={<ProtectedShell><GoLiveCenter /></ProtectedShell>} />
            <Route path="/app/project-dashboard" element={<ProtectedShell><ProjectDashboard /></ProtectedShell>} />
            <Route path="/app/project-dashboard/:id" element={<ProtectedShell><ProjectDashboard /></ProtectedShell>} />
            <Route path="/app/inventory" element={<ProtectedShell><Inventory /></ProtectedShell>} />
            <Route path="/app/store-inventory" element={<ProtectedShell><StoreInventory /></ProtectedShell>} />
            <Route path="/app/purchase-orders" element={<ProtectedShell><PurchaseOrders /></ProtectedShell>} />
            <Route path="/app/quotations" element={<ProtectedShell><Quotations /></ProtectedShell>} />
            <Route path="/app/quotations/:id/builder" element={<ProtectedShell><QuotationBuilder /></ProtectedShell>} />
            <Route path="/app/admin/company-profile" element={<ProtectedShell><CompanyProfile /></ProtectedShell>} />
            <Route path="/app/admin/conditions" element={<ProtectedShell><ConditionLibrary /></ProtectedShell>} />
            <Route path="/app/admin/users" element={<ProtectedShell><UserManagement /></ProtectedShell>} />
            <Route path="/app/admin/role-register" element={<ProtectedShell><RoleRegister /></ProtectedShell>} />
            <Route path="/app/admin/categories" element={<ProtectedShell><Categories /></ProtectedShell>} />
            <Route path="/app/admin/code-override" element={<ProtectedShell><CodeOverride /></ProtectedShell>} />
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
            <Route path="/app/hr/masters" element={<ProtectedShell><HrMasters /></ProtectedShell>} />
            <Route path="/app/hr/employee-360" element={<ProtectedShell><Employee360 /></ProtectedShell>} />
            <Route path="/app/hr/leave" element={<ProtectedShell><Leave /></ProtectedShell>}/>
            <Route path="/app/hr/letters" element={<ProtectedShell><HrLetters /></ProtectedShell>}/>
            <Route path="/app/hr/advances" element={<ProtectedShell><Advances /></ProtectedShell>}/>
            <Route path="/app/hr/advance-recovery" element={<ProtectedShell><AdvanceRecovery /></ProtectedShell>}/>
            <Route path="/app/hr/payroll" element={<ProtectedShell><HrPayroll /></ProtectedShell>}/>
            <Route path="/app/hr/exit" element={<ProtectedShell><Exit /></ProtectedShell>}/>
            <Route path="/app/hr/operations" element={<ProtectedShell><HrPhase2 /></ProtectedShell>}/>
            <Route path="/app/hr/manpower-planning" element={<ProtectedShell><HrPhase3 /></ProtectedShell>}/>
            <Route path="/app/hr/payroll-statutory" element={<ProtectedShell><HrPhase4 /></ProtectedShell>}/>
            <Route path="/app/hr/command-center" element={<ProtectedShell><HrPhase5 /></ProtectedShell>}/>
            <Route path="/app/accounts" element={<ProtectedShell><Accounts /></ProtectedShell>} />
            <Route path="/app/safety" element={<ProtectedShell><Safety /></ProtectedShell>} />
            <Route path="/app/safety/dashboard" element={<ProtectedShell><SafetyDashboard /></ProtectedShell>} />
            <Route path="/app/safety/masters" element={<ProtectedShell><SafetyMasters /></ProtectedShell>} />
            <Route path="/app/safety/hira" element={<ProtectedShell><Hira /></ProtectedShell>} />
            <Route path="/app/safety/jsa" element={<ProtectedShell><Jsa /></ProtectedShell>} />
            <Route path="/app/safety/plans" element={<ProtectedShell><SafetyPlanRegister /></ProtectedShell>} />
            <Route path="/app/safety/documents" element={<ProtectedShell><SafetyDocumentRegister /></ProtectedShell>} />
            <Route path="/app/safety/work-permits" element={<ProtectedShell><WorkPermitRegister /></ProtectedShell>} />
            <Route path="/app/safety/ppe-requirements" element={<ProtectedShell><PpeRequirements /></ProtectedShell>} />
            <Route path="/app/safety/ppe-compliance" element={<ProtectedShell><PpeCompliance /></ProtectedShell>} />
            <Route path="/app/safety/readiness" element={<ProtectedShell><SafetyReadiness /></ProtectedShell>} />
            <Route path="/app/safety/training-expiry" element={<ProtectedShell><TrainingExpiryRegister /></ProtectedShell>} />
            <Route path="/app/safety/inspections" element={<ProtectedShell><SafetyInspections /></ProtectedShell>} />
            <Route path="/app/safety/observations" element={<ProtectedShell><SafetyObservationsRegister /></ProtectedShell>} />
            <Route path="/app/safety/incidents" element={<ProtectedShell><Incidents /></ProtectedShell>} />
            <Route path="/app/safety/capa" element={<ProtectedShell><Capa /></ProtectedShell>} />
            <Route path="/app/safety/escalations" element={<ProtectedShell><SafetyEscalationDashboard /></ProtectedShell>} />
            {/* Iter 130 — Safety Phase 4 */}
            <Route path="/app/safety/audits" element={<ProtectedShell><SafetyAudits /></ProtectedShell>} />
            <Route path="/app/safety/client-compliance" element={<ProtectedShell><ClientCompliance /></ProtectedShell>} />
            <Route path="/app/safety/reviews" element={<ProtectedShell><MonthlySafetyReview /></ProtectedShell>} />
            <Route path="/app/safety/vendor-compliance" element={<ProtectedShell><VendorSafetyCompliance /></ProtectedShell>} />
            <Route path="/app/safety/costs" element={<ProtectedShell><SafetyCostRegister /></ProtectedShell>} />
            <Route path="/app/safety/management-review" element={<ProtectedShell><SafetyManagementReview /></ProtectedShell>} />
            {/* Iter 131 — Safety Phase 5 */}
            <Route path="/app/safety/project-closure" element={<ProtectedShell><ProjectSafetyClosure /></ProtectedShell>} />
            <Route path="/app/safety/reports" element={<ProtectedShell><SafetyReportsCenter /></ProtectedShell>} />
            <Route path="/app/safety/audit-trail" element={<ProtectedShell><SafetyAuditTrail /></ProtectedShell>} />
            <Route path="/app/assets" element={<ProtectedShell><Assets /></ProtectedShell>} />
            <Route path="/app/payroll" element={<ProtectedShell><Payroll /></ProtectedShell>} />
            <Route path="/app/logistics" element={<ProtectedShell><LogisticsDashboard /></ProtectedShell>} />
            <Route path="/app/logistics/vehicles" element={<ProtectedShell><VehicleMaster /></ProtectedShell>} />
            <Route path="/app/logistics/vehicles-legacy" element={<ProtectedShell><Logistics /></ProtectedShell>} />
            <Route path="/app/logistics/drivers" element={<ProtectedShell><DriverMaster /></ProtectedShell>} />
            <Route path="/app/logistics/routes" element={<ProtectedShell><RouteMaster /></ProtectedShell>} />
            <Route path="/app/logistics/loading-points" element={<ProtectedShell><LoadingUnloadingPoints /></ProtectedShell>} />
            <Route path="/app/logistics/dispatch-types" element={<ProtectedShell><DispatchTypes /></ProtectedShell>} />
            <Route path="/app/logistics/dispatch-requests" element={<ProtectedShell><DispatchRequests /></ProtectedShell>} />
            <Route path="/app/logistics/dispatch-requests/:id" element={<ProtectedShell><DispatchRequestDetail /></ProtectedShell>} />
            <Route path="/app/logistics/in-transit" element={<ProtectedShell><InTransitTracking /></ProtectedShell>} />
            <Route path="/app/logistics/deliveries" element={<ProtectedShell><DeliveryConfirmations /></ProtectedShell>} />
            <Route path="/app/logistics/exceptions" element={<ProtectedShell><TransitExceptions /></ProtectedShell>} />
            {/* Iter 134/135 — Logistics Phase 3 & 4 */}
            <Route path="/app/logistics/mobilizations" element={<ProtectedShell><ManpowerMobilization /></ProtectedShell>} />
            <Route path="/app/logistics/travel" element={<ProtectedShell><TravelArrangement /></ProtectedShell>} />
            <Route path="/app/logistics/accommodations" element={<ProtectedShell><AccommodationArrangement /></ProtectedShell>} />
            <Route path="/app/logistics/site-reporting" element={<ProtectedShell><SiteReporting /></ProtectedShell>} />
            <Route path="/app/logistics/demobilizations" element={<ProtectedShell><Demobilization /></ProtectedShell>} />
            <Route path="/app/logistics/fuel" element={<ProtectedShell><FuelEntries /></ProtectedShell>} />
            <Route path="/app/logistics/vehicle-expenses" element={<ProtectedShell><VehicleExpenses /></ProtectedShell>} />
            <Route path="/app/logistics/maintenance" element={<ProtectedShell><VehicleMaintenance /></ProtectedShell>} />
            <Route path="/app/logistics/vendor-bills" element={<ProtectedShell><VendorBills /></ProtectedShell>} />
            <Route path="/app/logistics/cost-summary" element={<ProtectedShell><LogisticsCostSummary /></ProtectedShell>} />
            <Route path="/app/logistics/vendor-profiles" element={<ProtectedShell><TransportVendorProfiles /></ProtectedShell>} />
            <Route path="/app/logistics/vehicle-availability" element={<ProtectedShell><VehicleAvailability /></ProtectedShell>} />
            <Route path="/app/logistics/driver-availability" element={<ProtectedShell><DriverAvailability /></ProtectedShell>} />
            <Route path="/app/logistics/audit-trail" element={<ProtectedShell><LogisticsAuditTrail /></ProtectedShell>} />
            {/* Iter 136 — Logistics Phase 4 Completion */}
            <Route path="/app/logistics/finance-approvals" element={<ProtectedShell><FinanceApprovalInbox /></ProtectedShell>} />
            <Route path="/app/logistics/vendor-payable" element={<ProtectedShell><VendorPayable /></ProtectedShell>} />
            <Route path="/app/logistics/accounts-posting" element={<ProtectedShell><AccountsPostingStatus /></ProtectedShell>} />
            <Route path="/app/logistics/cost-by-project" element={<ProtectedShell><ProjectWiseCost /></ProtectedShell>} />
            <Route path="/app/logistics/cost-by-vehicle" element={<ProtectedShell><VehicleWiseCost /></ProtectedShell>} />
            {/* Iter 137 — Logistics Phase 5 */}
            <Route path="/app/logistics/reports-center" element={<ProtectedShell><LogisticsReportsCenter /></ProtectedShell>} />
            <Route path="/app/logistics/dashboard-advanced" element={<ProtectedShell><LogisticsAdvancedDashboard /></ProtectedShell>} />
            <Route path="/app/logistics/dispatch-requests/:id/closure" element={<ProtectedShell><TripClosurePanel /></ProtectedShell>} />
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
            <Route path="/app/reports-center" element={<ProtectedShell><ReportsCenter /></ProtectedShell>} />
            <Route path="/app/ops/bill-requests" element={<ProtectedShell><BillRequests /></ProtectedShell>} />
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
