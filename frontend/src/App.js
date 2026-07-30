import "@/App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { roleTier } from "@/lib/format";
import { lazyWithRetry } from "@/lib/lazyWithRetry";

import Login from "@/pages/Login";
import PermissionDenied from "@/pages/PermissionDenied";
import NotFound from "@/pages/NotFound";
import { InstallPrompt } from "@/components/InstallPrompt";

// Guest/marketing pages are code-split so authenticated pages do not pay for
// their weight in the initial bundle. Login stays eager for instant render.
const Landing = lazy(lazyWithRetry(() => import("@/pages/Landing")));
const Onboarding = lazy(lazyWithRetry(() => import("@/pages/Onboarding")));
const DemoEntry = lazy(lazyWithRetry(() => import("@/pages/DemoEntry")));
const ChangePassword = lazy(lazyWithRetry(() => import("@/pages/ChangePassword")));
const Dashboard = lazy(lazyWithRetry(() => import("@/pages/Dashboard")));
const Vehicles = lazy(lazyWithRetry(() => import("@/pages/Vehicles")));
const VehicleProfile = lazy(lazyWithRetry(() => import("@/pages/VehicleProfile")));
const DriverProfile = lazy(lazyWithRetry(() => import("@/pages/DriverProfile")));
const Expenses = lazy(lazyWithRetry(() => import("@/pages/Expenses")));
const Reports = lazy(lazyWithRetry(() => import("@/pages/Reports")));
const Compliance = lazy(lazyWithRetry(() => import("@/pages/Compliance")));
const ComplianceContacts = lazy(lazyWithRetry(() => import("@/pages/ComplianceContacts")));
const CalendarPage = lazy(lazyWithRetry(() => import("@/pages/CalendarPage")));
const FleetStatus = lazy(lazyWithRetry(() => import("@/pages/FleetStatus")));
const UserManagement = lazy(lazyWithRetry(() => import("@/pages/UserManagement")));
const TestDataAdmin = lazy(lazyWithRetry(() => import("@/pages/TestDataAdmin")));
const Vendors = lazy(lazyWithRetry(() => import("@/pages/Vendors")));
const DriverHome = lazy(lazyWithRetry(() => import("@/pages/DriverHome")));
const OrgSettings = lazy(lazyWithRetry(() => import("@/pages/OrgSettings")));
const lazyModulePage = (name) => lazy(lazyWithRetry(() => import("@/pages/ModulePages").then((module) => ({ default: module[name] }))));
const TripsPage = lazyModulePage("TripsPage");
const FuelPage = lazyModulePage("FuelPage");
const MaintenancePage = lazyModulePage("MaintenancePage");
const RepairsPage = lazyModulePage("RepairsPage");
const TyresPage = lazyModulePage("TyresPage");
const AccidentsPage = lazyModulePage("AccidentsPage");
const FastagPage = lazyModulePage("FastagPage");
const DowntimePage = lazyModulePage("DowntimePage");
const DocumentsPage = lazyModulePage("DocumentsPage");
const DriversPage = lazyModulePage("DriversPage");

const SplashLoader = () => (
  <div className="flex h-screen items-center justify-center bg-slate-50" role="status" aria-live="polite" aria-label="Checking your session">
    <Loader2 className="h-8 w-8 animate-spin text-slate-400" aria-hidden="true" />
  </div>
);

const ProtectedRoute = ({ children, roles, module }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <SplashLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (user.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  if (roles && !roles.includes(roleTier(user.role))) {
    return <Navigate to="/permission-denied" replace state={{ message: "Your role cannot open this page." }} />;
  }
  if (module && user.modules && !user.modules.includes(module)) {
    return <Navigate to="/permission-denied" replace state={{ message: "This module is not available for your account." }} />;
  }
  return <Layout>{children}</Layout>;
};

const GuestOnlyRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <SplashLoader />;
  return user ? <Navigate to="/dashboard" replace /> : children;
};

const HomeRoute = () => {
  const { user } = useAuth();
  return roleTier(user?.role) === "driver" ? <DriverHome /> : <Dashboard />;
};

export function AppRouter() {
  return (
    <Suspense fallback={<SplashLoader />}>
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/get-started" element={<GuestOnlyRoute><Onboarding /></GuestOnlyRoute>} />
      <Route path="/demo" element={<GuestOnlyRoute><DemoEntry /></GuestOnlyRoute>} />
      <Route path="/login" element={<GuestOnlyRoute><Login /></GuestOnlyRoute>} />
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
      <Route path="/permission-denied" element={<ProtectedRoute><PermissionDenied /></ProtectedRoute>} />
      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
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
