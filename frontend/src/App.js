import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import PWAInstallPrompt from "@/components/PWAInstallPrompt";
import "@/App.css";
// Route-level code splitting: each page is its own chunk, loaded on first visit.
const PoAck = lazy(() => import("@/pages/PoAck"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Clients = lazy(() => import("@/pages/Clients"));
const Vendors = lazy(() => import("@/pages/Vendors"));
const Employees = lazy(() => import("@/pages/Employees"));
const Attendance = lazy(() => import("@/pages/Attendance"));
const Projects = lazy(() => import("@/pages/Projects"));
const Inventory = lazy(() => import("@/pages/Inventory"));
const StoreInventory = lazy(() => import("@/pages/StoreInventory"));
const PurchaseOrders = lazy(() => import("@/pages/PurchaseOrders"));
const POTermsMaster = lazy(() => import("@/pages/procurement/POTermsMaster"));
const Quotations = lazy(() => import("@/pages/Quotations"));
const Accounts = lazy(() => import("@/pages/Accounts"));
const Safety = lazy(() => import("@/pages/Safety"));
const SafetyDashboard = lazy(() => import("@/pages/safety/SafetyDashboard"));
const SafetyMasters = lazy(() => import("@/pages/safety/SafetyMasters"));
const Hira = lazy(() => import("@/pages/safety/Hira"));
const Jsa = lazy(() => import("@/pages/safety/Jsa"));
const SafetyPlanRegister = lazy(() => import("@/pages/safety/SafetyPlanRegister"));
const SafetyDocumentRegister = lazy(() => import("@/pages/safety/SafetyDocumentRegister"));
const WorkPermitRegister = lazy(() => import("@/pages/safety/WorkPermitRegister"));
const PpeRequirements = lazy(() => import("@/pages/safety/PpeRequirements"));
const PpeCompliance = lazy(() => import("@/pages/safety/PpeCompliance"));
const SafetyReadiness = lazy(() => import("@/pages/safety/SafetyReadiness"));
const TrainingExpiryRegister = lazy(() => import("@/pages/safety/TrainingExpiryRegister"));
const SafetyInspections = lazy(() => import("@/pages/safety/SafetyInspections"));
const SafetyObservationsRegister = lazy(() => import("@/pages/safety/SafetyObservationsRegister"));
const Incidents = lazy(() => import("@/pages/safety/Incidents"));
const Capa = lazy(() => import("@/pages/safety/Capa"));
const SafetyEscalationDashboard = lazy(() => import("@/pages/safety/SafetyEscalationDashboard"));
const SafetyAudits = lazy(() => import("@/pages/safety/SafetyAudits"));
const ClientCompliance = lazy(() => import("@/pages/safety/ClientCompliance"));
const MonthlySafetyReview = lazy(() => import("@/pages/safety/MonthlySafetyReview"));
const VendorSafetyCompliance = lazy(() => import("@/pages/safety/VendorSafetyCompliance"));
const SafetyCostRegister = lazy(() => import("@/pages/safety/SafetyCostRegister"));
const SafetyManagementReview = lazy(() => import("@/pages/safety/SafetyManagementReview"));
const ProjectSafetyClosure = lazy(() => import("@/pages/safety/ProjectSafetyClosure"));
const SafetyReportsCenter = lazy(() => import("@/pages/safety/SafetyReportsCenter"));
const SafetyAuditTrail = lazy(() => import("@/pages/safety/SafetyAuditTrail"));
const Assets = lazy(() => import("@/pages/Assets"));
const Payroll = lazy(() => import("@/pages/Payroll"));
const Logistics = lazy(() => import("@/pages/Logistics"));
const LogisticsDashboard = lazy(() => import("@/pages/logistics/LogisticsDashboard"));
const VehicleMaster = lazy(() => import("@/pages/logistics/VehicleMaster"));
const DriverMaster = lazy(() => import("@/pages/logistics/DriverMaster"));
const DispatchRequests = lazy(() => import("@/pages/logistics/DispatchRequests"));
const DispatchRequestDetail = lazy(() => import("@/pages/logistics/DispatchRequestDetail"));
const Documents = lazy(() => import("@/pages/Documents"));
const Approvals = lazy(() => import("@/pages/Approvals"));
const ApprovalsDashboard = lazy(() => import("@/pages/ApprovalsDashboard"));
const ApprovalAnalytics = lazy(() => import("@/pages/ApprovalAnalytics"));
const MyRevisions = lazy(() => import("@/pages/MyRevisions"));
const Reports = lazy(() => import("@/pages/Reports"));
const Profile = lazy(() => import("@/pages/Profile"));
const Enquiries = lazy(() => import("@/pages/Enquiries"));
const Orders = lazy(() => import("@/pages/Orders"));
const StoreTransactions = lazy(() => import("@/pages/StoreTransactions"));
const PpeIssuance = lazy(() => import("@/pages/PpeIssuance"));
const PermitsToWork = lazy(() => import("@/pages/PermitsToWork"));
const SafetyTrainings = lazy(() => import("@/pages/SafetyTrainings"));
const ToolboxTalks = lazy(() => import("@/pages/ToolboxTalks"));
const RecruitmentRequests = lazy(() => import("@/pages/RecruitmentRequests"));
const Candidates = lazy(() => import("@/pages/Candidates"));
const Deployments = lazy(() => import("@/pages/Deployments"));
const ProjectManpower = lazy(() => import("@/pages/ProjectManpower"));
const AllocationReports = lazy(() => import("@/pages/AllocationReports"));
const AllocationBoard = lazy(() => import("@/pages/AllocationBoard"));
const DeploymentCalendar = lazy(() => import("@/pages/DeploymentCalendar"));
const ClientReports = lazy(() => import("@/pages/ClientReports"));
const ClientMap = lazy(() => import("@/pages/ClientMap"));
const SalesReports = lazy(() => import("@/pages/SalesReports"));
const PurchaseRequisitions = lazy(() => import("@/pages/PurchaseRequisitions"));
const ProcurementReports = lazy(() => import("@/pages/ProcurementReports"));
const Rfqs = lazy(() => import("@/pages/Rfqs"));
const Grn = lazy(() => import("@/pages/Grn"));
const ProcurementDashboard = lazy(() => import("@/pages/ProcurementDashboard"));
const MaterialAllocations = lazy(() => import("@/pages/MaterialAllocations"));
const AssetLifecycle = lazy(() => import("@/pages/AssetLifecycle"));
const Challans = lazy(() => import("@/pages/Challans"));
const InventoryIntel = lazy(() => import("@/pages/InventoryIntel"));
const ProcurementIntel = lazy(() => import("@/pages/ProcurementIntel"));
const Dprs = lazy(() => import("@/pages/Dprs"));
const DprMobile = lazy(() => import("@/pages/DprMobile"));
const Measurements = lazy(() => import("@/pages/Measurements"));
const RaBills = lazy(() => import("@/pages/RaBills"));
const Receivables = lazy(() => import("@/pages/Receivables"));
const ProjectOps = lazy(() => import("@/pages/ProjectOps"));
const ServiceRates = lazy(() => import("@/pages/ServiceRates"));
const BillingDefaults = lazy(() => import("@/pages/BillingDefaults"));
const CustomerCodeSettings = lazy(() => import("@/pages/admin/CustomerCodeSettings"));
const RoleDepartmentMap = lazy(() => import("@/pages/admin/RoleDepartmentMap"));
const CompanyProfile = lazy(() => import("@/pages/admin/CompanyProfile"));
const ConditionLibrary = lazy(() => import("@/pages/admin/ConditionLibrary"));
const UserManagement = lazy(() => import("@/pages/admin/UserManagement"));
const AssignmentManager = lazy(() => import("@/pages/admin/AssignmentManager"));
const RoleRegister = lazy(() => import("@/pages/admin/RoleRegister"));
const Categories = lazy(() => import("@/pages/admin/Categories"));
const CodeOverride = lazy(() => import("@/pages/admin/CodeOverride"));
const CostCenters = lazy(() => import("@/pages/admin/CostCenters"));
const DataCleanup = lazy(() => import("@/pages/admin/DataCleanup"));
const EmailSettings = lazy(() => import("@/pages/admin/EmailSettings"));
const EmailOutbox = lazy(() => import("@/pages/admin/EmailOutbox"));
const MyEmailSettings = lazy(() => import("@/pages/MyEmailSettings"));
const RoleCatalog = lazy(() => import("@/pages/admin/RoleCatalog"));
const OneDriveSettings = lazy(() => import("@/pages/admin/OneDriveSettings"));
const DataLinkage = lazy(() => import("@/pages/admin/DataLinkage"));
const DepartmentMaster = lazy(() => import("@/pages/admin/DepartmentMaster"));
const DeptGovernance = lazy(() => import("@/pages/admin/DeptGovernance"));
const Onboarding = lazy(() => import("@/pages/hr/Onboarding"));
const HrMasters = lazy(() => import("@/pages/hr/HrMasters"));
const Employee360 = lazy(() => import("@/pages/hr/Employee360"));
const Leave = lazy(() => import("@/pages/hr/Leave"));
const HrLetters = lazy(() => import("@/pages/hr/HrLetters"));
const Advances = lazy(() => import("@/pages/hr/Advances"));
const AdvanceRecovery = lazy(() => import("@/pages/hr/AdvanceRecovery"));
const HrPayroll = lazy(() => import("@/pages/hr/Payroll"));
const Exit = lazy(() => import("@/pages/hr/Exit"));
const HrPhase2 = lazy(() => import("@/pages/hr/HrPhase2"));
const HrPhase3 = lazy(() => import("@/pages/hr/HrPhase3"));
const HrPhase4 = lazy(() => import("@/pages/hr/HrPhase4"));
const LabourLicenses = lazy(() => import("@/pages/hr/LabourLicenses"));
const ServiceWorkflowDashboard = lazy(() => import("@/pages/services/ServiceWorkflowDashboard"));
const ServiceRequests = lazy(() => import("@/pages/services/ServiceRequests"));
const ServiceRequestDetail = lazy(() => import("@/pages/services/ServiceRequestDetail"));
const ServiceRfqs = lazy(() => import("@/pages/services/ServiceRfqs"));
const ServicePos = lazy(() => import("@/pages/services/ServicePos"));
const ServiceRecurring = lazy(() => import("@/pages/services/ServiceRecurring"));
const ServiceSrns = lazy(() => import("@/pages/services/ServiceSrns"));
const ServiceInvoices = lazy(() => import("@/pages/services/ServiceInvoices"));
const HrPhase5 = lazy(() => import("@/pages/hr/HrPhase5"));
const AttendanceCenter = lazy(() => import("@/pages/hr/AttendanceCenter"));
const AttendanceSummary = lazy(() => import("@/pages/hr/AttendanceSummary"));
const MinimumWages = lazy(() => import("@/pages/hr/MinimumWages"));
const GroupMedical = lazy(() => import("@/pages/hr/GroupMedical"));
const ProjectExpenses = lazy(() => import("@/pages/ops/ProjectExpenses"));
const ProjectRequests = lazy(() => import("@/pages/ops/ProjectRequests"));
const PmHandover = lazy(() => import("@/pages/ops/PmHandover"));
const Scaffolding = lazy(() => import("@/pages/store/Scaffolding"));
const MyApprovalsCenter = lazy(() => import("@/pages/MyApprovalsCenter"));
const ApprovalReport = lazy(() => import("@/pages/admin/ApprovalReport"));
const BillingPendingReport = lazy(() => import("@/pages/accounts/BillingPendingReport"));
const RequestOptions = lazy(() => import("@/pages/admin/RequestOptions"));
const ProjectPnl = lazy(() => import("@/pages/ops/ProjectPnl"));
const ReportsCenter = lazy(() => import("@/pages/ReportsCenter"));
const BillRequests = lazy(() => import("@/pages/ops/BillRequests"));
const QuotationBuilder = lazy(() => import("@/pages/QuotationBuilder"));
const ProjectDashboard = lazy(() => import("@/pages/ProjectDashboard"));
const ContractHandovers = lazy(() => import("@/pages/ops/ContractHandovers"));
const ServiceTypeMaster = lazy(() => import("@/pages/ops/ServiceTypeMaster"));
const SiteMaster = lazy(() => import("@/pages/ops/SiteMaster"));
const WorkOrders = lazy(() => import("@/pages/ops/WorkOrders"));
const ProjectTeam = lazy(() => import("@/pages/ops/ProjectTeam"));
const ProjectDocuments = lazy(() => import("@/pages/ops/ProjectDocuments"));
const DocumentCenter = lazy(() => import("@/pages/DocumentCenter"));
const ProjectStatus = lazy(() => import("@/pages/ops/ProjectStatus"));
const ProjectAuditTrail = lazy(() => import("@/pages/ops/ProjectAuditTrail"));
const ProjectSettings = lazy(() => import("@/pages/ops/ProjectSettings"));
const ProjectDashboardPhase1 = lazy(() => import("@/pages/ops/ProjectDashboard"));
const MyAssignedProjects = lazy(() => import("@/pages/ops/MyAssignedProjects"));
const PlanningHub = lazy(() => import("@/pages/ops/PlanningHub"));
const ProjectOpsDashboard = lazy(() => import("@/pages/ops/ProjectOpsDashboard"));
const OpsReports = lazy(() => import("@/pages/ops/OpsReports"));
const ActivityTimeline = lazy(() => import("@/pages/ops/ActivityTimeline"));
const DailyProgressReports = lazy(() => import("@/pages/ops/DailyProgressReports"));
const WorkProgressTracker = lazy(() => import("@/pages/ops/WorkProgressTracker"));
const MeasurementSheets = lazy(() => import("@/pages/ops/MeasurementSheets"));
const SiteIssues = lazy(() => import("@/pages/ops/SiteIssues"));
const ClientInstructions = lazy(() => import("@/pages/ops/ClientInstructions"));
const ExtraWorks = lazy(() => import("@/pages/ops/ExtraWorks"));
const WorkPermits = lazy(() => import("@/pages/ops/WorkPermits"));
const ExecutionDashboard = lazy(() => import("@/pages/ops/ExecutionDashboard"));
const ProjectControlCenter = lazy(() => import("@/pages/ops/ProjectControlCenter"));
const ProjectClosureCenter = lazy(() => import("@/pages/ops/ProjectClosureCenter"));
const RateContracts = lazy(() => import("@/pages/procurement/RateContracts"));
const ServiceOrders = lazy(() => import("@/pages/procurement/ServiceOrders"));
const VendorComplianceCenter = lazy(() => import("@/pages/procurement/VendorComplianceCenter"));
const DebitCreditNotes = lazy(() => import("@/pages/accounts/DebitCreditNotes"));
const BudgetCommitmentCenter = lazy(() => import("@/pages/accounts/BudgetCommitmentCenter"));
const ComplianceCenter = lazy(() => import("@/pages/accounts/ComplianceCenter"));
const FinanceDashboard = lazy(() => import("@/pages/accounts/FinanceDashboard"));
const Accommodations = lazy(() => import("@/pages/Accommodations"));
const Overtime = lazy(() => import("@/pages/Overtime"));
const VendorPortal = lazy(() => import("@/pages/VendorPortal"));
const DepartmentLauncher = lazy(() => import("@/pages/DepartmentLauncher"));
const DepartmentWorkspace = lazy(() => import("@/pages/DepartmentWorkspace"));
const AdminConsole = lazy(() => import("@/pages/admin/AdminConsole"));
const Departments = lazy(() => import("@/pages/admin/Departments"));
const Dropdowns = lazy(() => import("@/pages/admin/Dropdowns"));
const ApprovalMatrix = lazy(() => import("@/pages/admin/ApprovalMatrix"));
const ApprovalWorkflowSettings = lazy(() => import("@/pages/admin/ApprovalWorkflowSettings"));
const SequenceAdmin = lazy(() => import("@/pages/admin/SequenceAdmin"));
const AuditLogs = lazy(() => import("@/pages/admin/AuditLogs"));
const DuplicateBlocks = lazy(() => import("@/pages/admin/DuplicateBlocks"));
const Sessions = lazy(() => import("@/pages/admin/Sessions"));
const SecurityCenter = lazy(() => import("@/pages/admin/SecurityCenter"));
const GoLiveCenter = lazy(() => import("@/pages/admin/GoLiveCenter"));
const SystemHealth = lazy(() => import("@/pages/admin/SystemHealth"));
const FinanceAlerts = lazy(() => import("@/pages/accounts/FinanceAlerts"));
const PaymentProcessingCenter = lazy(() => import("@/pages/accounts/PaymentProcessingCenter"));
const EnquiryFollowUpTracker = lazy(() => import("@/pages/sales/EnquiryFollowUpTracker"));
const InternalProjectReview = lazy(() => import("@/pages/ops/InternalProjectReview"));
const RouteMaster = lazy(() => import("@/pages/logistics/LogisticsMasters").then((m) => ({ default: m.RouteMaster })));
const LoadingUnloadingPoints = lazy(() => import("@/pages/logistics/LogisticsMasters").then((m) => ({ default: m.LoadingUnloadingPoints })));
const DispatchTypes = lazy(() => import("@/pages/logistics/LogisticsMasters").then((m) => ({ default: m.DispatchTypes })));
const TransportVendorProfiles = lazy(() => import("@/pages/logistics/LogisticsMasters").then((m) => ({ default: m.TransportVendorProfiles })));
const VehicleAvailability = lazy(() => import("@/pages/logistics/LogisticsAvailAudit").then((m) => ({ default: m.VehicleAvailability })));
const DriverAvailability = lazy(() => import("@/pages/logistics/LogisticsAvailAudit").then((m) => ({ default: m.DriverAvailability })));
const LogisticsAuditTrail = lazy(() => import("@/pages/logistics/LogisticsAvailAudit").then((m) => ({ default: m.LogisticsAuditTrail })));
const InTransitTracking = lazy(() => import("@/pages/logistics/LogisticsPhase2Lists").then((m) => ({ default: m.InTransitTracking })));
const DeliveryConfirmations = lazy(() => import("@/pages/logistics/LogisticsPhase2Lists").then((m) => ({ default: m.DeliveryConfirmations })));
const TransitExceptions = lazy(() => import("@/pages/logistics/LogisticsPhase2Lists").then((m) => ({ default: m.TransitExceptions })));
const ManpowerMobilization = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.ManpowerMobilization })));
const TravelArrangement = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.TravelArrangement })));
const AccommodationArrangement = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.AccommodationArrangement })));
const SiteReporting = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.SiteReporting })));
const Demobilization = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.Demobilization })));
const FuelEntries = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.FuelEntries })));
const VehicleExpenses = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.VehicleExpenses })));
const VehicleMaintenance = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.VehicleMaintenance })));
const VendorBills = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.VendorBills })));
const LogisticsCostSummary = lazy(() => import("@/pages/logistics/LogisticsPhase34Pages").then((m) => ({ default: m.LogisticsCostSummary })));
const FinanceApprovalInbox = lazy(() => import("@/pages/logistics/LogisticsPhase4Views").then((m) => ({ default: m.FinanceApprovalInbox })));
const VendorPayable = lazy(() => import("@/pages/logistics/LogisticsPhase4Views").then((m) => ({ default: m.VendorPayable })));
const AccountsPostingStatus = lazy(() => import("@/pages/logistics/LogisticsPhase4Views").then((m) => ({ default: m.AccountsPostingStatus })));
const ProjectWiseCost = lazy(() => import("@/pages/logistics/LogisticsPhase4Views").then((m) => ({ default: m.ProjectWiseCost })));
const VehicleWiseCost = lazy(() => import("@/pages/logistics/LogisticsPhase4Views").then((m) => ({ default: m.VehicleWiseCost })));
const LogisticsReportsCenter = lazy(() => import("@/pages/logistics/LogisticsPhase5Views").then((m) => ({ default: m.LogisticsReportsCenter })));
const TripClosurePanel = lazy(() => import("@/pages/logistics/LogisticsPhase5Views").then((m) => ({ default: m.TripClosurePanel })));
const LogisticsAdvancedDashboard = lazy(() => import("@/pages/logistics/LogisticsPhase5Views").then((m) => ({ default: m.LogisticsAdvancedDashboard })));


function RouteLoader() {
  return (
    <div className="flex h-screen w-full items-center justify-center" data-testid="route-loading">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
    </div>
  );
}

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
          <Suspense fallback={<RouteLoader />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/po-ack/:token" element={<PoAck />} />
            <Route path="/app" element={<ProtectedShell><Dashboard /></ProtectedShell>} />
            <Route path="/app/clients" element={<ProtectedShell><Clients /></ProtectedShell>} />
            <Route path="/app/vendors" element={<ProtectedShell><Vendors /></ProtectedShell>} />
            <Route path="/app/employees" element={<ProtectedShell><Employees /></ProtectedShell>} />
            <Route path="/app/workers" element={<ProtectedShell><Employees master="worker" /></ProtectedShell>} />
            <Route path="/app/attendance" element={<ProtectedShell><Attendance /></ProtectedShell>} />
            <Route path="/app/attendance-center" element={<ProtectedShell><AttendanceCenter /></ProtectedShell>} />
            <Route path="/app/hr/attendance-summary" element={<ProtectedShell><AttendanceSummary /></ProtectedShell>} />
            <Route path="/app/hr/minimum-wages" element={<ProtectedShell><MinimumWages /></ProtectedShell>} />
            <Route path="/app/hr/group-medical" element={<ProtectedShell><GroupMedical /></ProtectedShell>} />
            <Route path="/app/ops/expenses" element={<Navigate to="/app/ops/requests?tab=expenses" replace />} />
            <Route path="/app/ops/requests" element={<ProtectedShell><ProjectRequests /></ProtectedShell>} />
            <Route path="/app/ops/handover-pack" element={<ProtectedShell><PmHandover /></ProtectedShell>} />
            <Route path="/app/scaffolding" element={<ProtectedShell><Scaffolding /></ProtectedShell>} />
            <Route path="/app/my-approvals" element={<ProtectedShell><MyApprovalsCenter /></ProtectedShell>} />
            <Route path="/app/admin/approval-report" element={<ProtectedShell><ApprovalReport /></ProtectedShell>} />
            <Route path="/app/accounts/billing-pending" element={<ProtectedShell><BillingPendingReport /></ProtectedShell>} />
            <Route path="/app/admin/request-options" element={<ProtectedShell><RequestOptions /></ProtectedShell>} />
            <Route path="/app/ops/pnl" element={<ProtectedShell><ProjectPnl /></ProtectedShell>} />
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
            <Route path="/app/ops/resource-requests" element={<Navigate to="/app/ops/requests" replace />} />
            <Route path="/app/ops/project-dashboard" element={<ProtectedShell><ProjectOpsDashboard /></ProtectedShell>} />
            <Route path="/app/ops/reports" element={<ProtectedShell><OpsReports /></ProtectedShell>} />
            <Route path="/app/ops/timeline" element={<ProtectedShell><ActivityTimeline /></ProtectedShell>} />
            <Route path="/app/ops/planning-hub" element={<ProtectedShell><PlanningHub /></ProtectedShell>} />
            <Route path="/app/ops/planning" element={<Navigate to="/app/ops/planning-hub?tab=premob" replace />} />
            <Route path="/app/ops/boq" element={<Navigate to="/app/ops/planning-hub?tab=boq" replace />} />
            <Route path="/app/ops/wbs" element={<Navigate to="/app/ops/planning-hub?tab=wbs" replace />} />
            <Route path="/app/ops/activities" element={<Navigate to="/app/ops/planning-hub?tab=schedule" replace />} />
            <Route path="/app/ops/resources" element={<Navigate to="/app/ops/planning-hub?tab=resources" replace />} />
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
            <Route path="/app/accounts/payment-processing" element={<ProtectedShell><PaymentProcessingCenter /></ProtectedShell>} />
            <Route path="/app/sales/enquiry-followup" element={<ProtectedShell><EnquiryFollowUpTracker /></ProtectedShell>} />
            <Route path="/app/ops/internal-review" element={<ProtectedShell><InternalProjectReview /></ProtectedShell>} />
            <Route path="/app/admin/security-center" element={<ProtectedShell><SecurityCenter /></ProtectedShell>} />
            <Route path="/app/admin/go-live" element={<ProtectedShell><GoLiveCenter /></ProtectedShell>} />
            <Route path="/app/admin/system-health" element={<ProtectedShell><SystemHealth /></ProtectedShell>} />
            <Route path="/app/project-dashboard" element={<ProtectedShell><ProjectDashboard /></ProtectedShell>} />
            <Route path="/app/project-dashboard/:id" element={<ProtectedShell><ProjectDashboard /></ProtectedShell>} />
            <Route path="/app/inventory" element={<ProtectedShell><Inventory /></ProtectedShell>} />
            <Route path="/app/store-inventory" element={<ProtectedShell><StoreInventory /></ProtectedShell>} />
            <Route path="/app/purchase-orders" element={<ProtectedShell><PurchaseOrders /></ProtectedShell>} />
            <Route path="/app/procurement/po-terms" element={<ProtectedShell><POTermsMaster /></ProtectedShell>} />
            <Route path="/app/quotations" element={<ProtectedShell><Quotations /></ProtectedShell>} />
            <Route path="/app/quotations/:id/builder" element={<ProtectedShell><QuotationBuilder /></ProtectedShell>} />
            <Route path="/app/admin/company-profile" element={<ProtectedShell><CompanyProfile /></ProtectedShell>} />
            <Route path="/app/admin/conditions" element={<ProtectedShell><ConditionLibrary /></ProtectedShell>} />
            <Route path="/app/admin/users" element={<ProtectedShell><UserManagement /></ProtectedShell>} />
            <Route path="/app/admin/project-assignments" element={<ProtectedShell><AssignmentManager /></ProtectedShell>} />
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
            <Route path="/app/hr/labour-licenses" element={<ProtectedShell><LabourLicenses /></ProtectedShell>}/>
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
            <Route path="/app/dms" element={<ProtectedShell><DocumentCenter /></ProtectedShell>} />
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
            <Route path="/app/admin/duplicate-blocks" element={<ProtectedShell><DuplicateBlocks /></ProtectedShell>} />
            <Route path="/app/admin/sessions" element={<ProtectedShell><Sessions /></ProtectedShell>} />
            <Route path="/app/services/dashboard" element={<ProtectedShell><ServiceWorkflowDashboard /></ProtectedShell>} />
            <Route path="/app/services/requests" element={<ProtectedShell><ServiceRequests /></ProtectedShell>} />
            <Route path="/app/services/requests/:id" element={<ProtectedShell><ServiceRequestDetail /></ProtectedShell>} />
            <Route path="/app/services/rfqs" element={<ProtectedShell><ServiceRfqs /></ProtectedShell>} />
            <Route path="/app/services/pos" element={<ProtectedShell><ServicePos /></ProtectedShell>} />
            <Route path="/app/services/recurring" element={<ProtectedShell><ServiceRecurring /></ProtectedShell>} />
            <Route path="/app/services/srns" element={<ProtectedShell><ServiceSrns /></ProtectedShell>} />
            <Route path="/app/services/invoices" element={<ProtectedShell><ServiceInvoices /></ProtectedShell>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
