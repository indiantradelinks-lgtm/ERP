import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
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
import Reports from "@/pages/Reports";
import Profile from "@/pages/Profile";
import "@/App.css";

function ProtectedShell({ children }) {
  return (
    <ProtectedRoute>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Toaster richColors position="top-right" />
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/app" element={<ProtectedShell><Dashboard /></ProtectedShell>} />
            <Route path="/app/clients" element={<ProtectedShell><Clients /></ProtectedShell>} />
            <Route path="/app/vendors" element={<ProtectedShell><Vendors /></ProtectedShell>} />
            <Route path="/app/employees" element={<ProtectedShell><Employees /></ProtectedShell>} />
            <Route path="/app/attendance" element={<ProtectedShell><Attendance /></ProtectedShell>} />
            <Route path="/app/projects" element={<ProtectedShell><Projects /></ProtectedShell>} />
            <Route path="/app/inventory" element={<ProtectedShell><Inventory /></ProtectedShell>} />
            <Route path="/app/purchase-orders" element={<ProtectedShell><PurchaseOrders /></ProtectedShell>} />
            <Route path="/app/quotations" element={<ProtectedShell><Quotations /></ProtectedShell>} />
            <Route path="/app/accounts" element={<ProtectedShell><Accounts /></ProtectedShell>} />
            <Route path="/app/safety" element={<ProtectedShell><Safety /></ProtectedShell>} />
            <Route path="/app/assets" element={<ProtectedShell><Assets /></ProtectedShell>} />
            <Route path="/app/payroll" element={<ProtectedShell><Payroll /></ProtectedShell>} />
            <Route path="/app/logistics" element={<ProtectedShell><Logistics /></ProtectedShell>} />
            <Route path="/app/documents" element={<ProtectedShell><Documents /></ProtectedShell>} />
            <Route path="/app/approvals" element={<ProtectedShell><Approvals /></ProtectedShell>} />
            <Route path="/app/reports" element={<ProtectedShell><Reports /></ProtectedShell>} />
            <Route path="/app/profile" element={<ProtectedShell><Profile /></ProtectedShell>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
