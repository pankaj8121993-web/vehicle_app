import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";

import Login from "@/pages/Login";
import ChangePassword from "@/pages/ChangePassword";
import Dashboard from "@/pages/Dashboard";
import Vehicles from "@/pages/Vehicles";
import VehicleProfile from "@/pages/VehicleProfile";
import DriverProfile from "@/pages/DriverProfile";
import Expenses from "@/pages/Expenses";
import Reports from "@/pages/Reports";
import Compliance from "@/pages/Compliance";
import ComplianceContacts from "@/pages/ComplianceContacts";
import CalendarPage from "@/pages/CalendarPage";
import FleetStatus from "@/pages/FleetStatus";
import UserManagement from "@/pages/UserManagement";
import TestDataAdmin from "@/pages/TestDataAdmin";
import {
  TripsPage, FuelPage, MaintenancePage, RepairsPage, TyresPage,
  AccidentsPage, FastagPage, DowntimePage, DocumentsPage, DriversPage,
} from "@/pages/ModulePages";

const SplashLoader = () => (
  <div className="flex h-screen items-center justify-center bg-slate-50">
    <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
  </div>
);

const ProtectedRoute = ({ children, roles }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <SplashLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <Layout>{children}</Layout>;
};

function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePassword forced /></ProtectedRoute>} />
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/vehicles" element={<ProtectedRoute><Vehicles /></ProtectedRoute>} />
      <Route path="/vehicles/:id" element={<ProtectedRoute><VehicleProfile /></ProtectedRoute>} />
      <Route path="/drivers" element={<ProtectedRoute><DriversPage /></ProtectedRoute>} />
      <Route path="/drivers/:id" element={<ProtectedRoute><DriverProfile /></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute><DocumentsPage /></ProtectedRoute>} />
      <Route path="/trips" element={<ProtectedRoute><TripsPage /></ProtectedRoute>} />
      <Route path="/fuel" element={<ProtectedRoute><FuelPage /></ProtectedRoute>} />
      <Route path="/maintenance" element={<ProtectedRoute><MaintenancePage /></ProtectedRoute>} />
      <Route path="/repairs" element={<ProtectedRoute><RepairsPage /></ProtectedRoute>} />
      <Route path="/tyres" element={<ProtectedRoute><TyresPage /></ProtectedRoute>} />
      <Route path="/accidents" element={<ProtectedRoute><AccidentsPage /></ProtectedRoute>} />
      <Route path="/fastag" element={<ProtectedRoute><FastagPage /></ProtectedRoute>} />
      <Route path="/downtime" element={<ProtectedRoute><DowntimePage /></ProtectedRoute>} />
      <Route path="/expenses" element={<ProtectedRoute><Expenses /></ProtectedRoute>} />
      <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
      <Route path="/compliance" element={<ProtectedRoute><Compliance /></ProtectedRoute>} />
      <Route path="/compliance/contacts" element={<ProtectedRoute roles={["management", "admin"]}><ComplianceContacts /></ProtectedRoute>} />
      <Route path="/calendar" element={<ProtectedRoute><CalendarPage /></ProtectedRoute>} />
      <Route path="/fleet-status" element={<ProtectedRoute><FleetStatus /></ProtectedRoute>} />
      <Route path="/users" element={<ProtectedRoute roles={["admin"]}><UserManagement /></ProtectedRoute>} />
      <Route path="/admin/test-data" element={<ProtectedRoute roles={["admin"]}><TestDataAdmin /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRouter />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
