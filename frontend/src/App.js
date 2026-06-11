import { useEffect, useRef } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useNavigate, useLocation, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import api from "@/lib/api";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { Loader2 } from "lucide-react";

import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Vehicles from "@/pages/Vehicles";
import VehicleProfile from "@/pages/VehicleProfile";
import Expenses from "@/pages/Expenses";
import Reports from "@/pages/Reports";
import UsersPage from "@/pages/Users";
import {
  TripsPage, FuelPage, MaintenancePage, RepairsPage, TyresPage,
  AccidentsPage, FastagPage, DowntimePage, DocumentsPage, DriversPage,
} from "@/pages/ModulePages";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

const FullPageLoader = () => (
  <div className="flex min-h-screen items-center justify-center bg-slate-50">
    <Loader2 className="h-7 w-7 animate-spin text-slate-400" />
  </div>
);

const AuthCallback = () => {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processSession = async () => {
      const hash = window.location.hash;
      const sessionId = new URLSearchParams(hash.substring(1)).get("session_id");
      if (!sessionId) {
        navigate("/login", { replace: true });
        return;
      }
      try {
        const res = await api.post("/auth/session", { session_id: sessionId });
        setUser(res.data);
        window.history.replaceState(null, "", window.location.pathname);
        navigate("/", { replace: true, state: { user: res.data } });
      } catch {
        navigate("/login", { replace: true });
      }
    };
    processSession();
  }, [navigate, setUser]);

  return <FullPageLoader />;
};

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
};

function AppRouter() {
  const location = useLocation();
  // Check URL fragment synchronously during render (prevents race conditions)
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/vehicles" element={<ProtectedRoute><Vehicles /></ProtectedRoute>} />
      <Route path="/vehicles/:id" element={<ProtectedRoute><VehicleProfile /></ProtectedRoute>} />
      <Route path="/drivers" element={<ProtectedRoute><DriversPage /></ProtectedRoute>} />
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
      <Route path="/users" element={<ProtectedRoute><UsersPage /></ProtectedRoute>} />
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
