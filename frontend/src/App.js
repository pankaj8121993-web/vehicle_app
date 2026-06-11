import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";

import RoleSelect from "@/pages/RoleSelect";
import Dashboard from "@/pages/Dashboard";
import Vehicles from "@/pages/Vehicles";
import VehicleProfile from "@/pages/VehicleProfile";
import DriverProfile from "@/pages/DriverProfile";
import Expenses from "@/pages/Expenses";
import Reports from "@/pages/Reports";
import {
  TripsPage, FuelPage, MaintenancePage, RepairsPage, TyresPage,
  AccidentsPage, FastagPage, DowntimePage, DocumentsPage, DriversPage,
} from "@/pages/ModulePages";

const ProtectedRoute = ({ children }) => {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
};

function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<RoleSelect />} />
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
