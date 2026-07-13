import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { roleTier } from "@/lib/format";

import Landing from "@/pages/Landing";
import Onboarding from "@/pages/Onboarding";
import DemoEntry from "@/pages/DemoEntry";
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
import Vendors from "@/pages/Vendors";
import DriverHome from "@/pages/DriverHome";
import OrgSettings from "@/pages/OrgSettings";
import { InstallPrompt } from "@/components/InstallPrompt";
import {
  TripsPage, FuelPage, MaintenancePage, RepairsPage, TyresPage,
  AccidentsPage, FastagPage, DowntimePage, DocumentsPage, DriversPage,
} from "@/pages/ModulePages";

const SplashLoader = () => (
  <div className="flex h-screen items-center justify-center bg-slate-50">
    <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
  </div>
);

const ProtectedRoute = ({ children, roles, module }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <SplashLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  if (roles && !roles.includes(roleTier(user.role))) return <Navigate to="/dashboard" replace />;
  if (module && user.modules && !user.modules.includes(module)) return <Navigate to="/dashboard" replace />;
  return <Layout>{children}</Layout>;
};

const HomeRoute = () => {
  const { user } = useAuth();
  return roleTier(user?.role) === "driver" ? <DriverHome /> : <Dashboard />;
};

function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/get-started" element={<Onboarding />} />
      <Route path="/demo" element={<DemoEntry />} />
      <Route path="/login" element={<Login />} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePassword forced /></ProtectedRoute>} />
      <Route path="/dashboard" element={<ProtectedRoute><HomeRoute /></ProtectedRoute>} />
      <Route path="/vehicles" element={<ProtectedRoute module="vehicles"><Vehicles /></ProtectedRoute>} />
      <Route path="/vehicles/:id" element={<ProtectedRoute module="vehicles"><VehicleProfile /></ProtectedRoute>} />
      <Route path="/drivers" element={<ProtectedRoute module="drivers"><DriversPage /></ProtectedRoute>} />
      <Route path="/drivers/:id" element={<ProtectedRoute module="drivers"><DriverProfile /></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute module="documents"><DocumentsPage /></ProtectedRoute>} />
      <Route path="/trips" element={<ProtectedRoute module="trips"><TripsPage /></ProtectedRoute>} />
      <Route path="/fuel" element={<ProtectedRoute module="fuel"><FuelPage /></ProtectedRoute>} />
      <Route path="/maintenance" element={<ProtectedRoute module="maintenance"><MaintenancePage /></ProtectedRoute>} />
      <Route path="/repairs" element={<ProtectedRoute module="repairs"><RepairsPage /></ProtectedRoute>} />
      <Route path="/tyres" element={<ProtectedRoute module="tyres"><TyresPage /></ProtectedRoute>} />
      <Route path="/accidents" element={<ProtectedRoute module="accidents"><AccidentsPage /></ProtectedRoute>} />
      <Route path="/fastag" element={<ProtectedRoute module="fastag"><FastagPage /></ProtectedRoute>} />
      <Route path="/downtime" element={<ProtectedRoute module="downtime"><DowntimePage /></ProtectedRoute>} />
      <Route path="/expenses" element={<ProtectedRoute module="expenses"><Expenses /></ProtectedRoute>} />
      <Route path="/reports" element={<ProtectedRoute module="reports"><Reports /></ProtectedRoute>} />
      <Route path="/compliance" element={<ProtectedRoute module="compliance"><Compliance /></ProtectedRoute>} />
      <Route path="/compliance/contacts" element={<ProtectedRoute roles={["management", "admin"]} module="compliance"><ComplianceContacts /></ProtectedRoute>} />
      <Route path="/calendar" element={<ProtectedRoute module="calendar"><CalendarPage /></ProtectedRoute>} />
      <Route path="/fleet-status" element={<ProtectedRoute module="fleet-status"><FleetStatus /></ProtectedRoute>} />
      <Route path="/vendors" element={<ProtectedRoute module="vendors"><Vendors /></ProtectedRoute>} />
      <Route path="/settings/organisation" element={<ProtectedRoute roles={["management", "admin"]} module="org-settings"><OrgSettings /></ProtectedRoute>} />
      <Route path="/users" element={<ProtectedRoute roles={["admin"]} module="users"><UserManagement /></ProtectedRoute>} />
      <Route path="/admin/test-data" element={<ProtectedRoute roles={["admin"]} module="test-data"><TestDataAdmin /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRouter />
        <InstallPrompt />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
