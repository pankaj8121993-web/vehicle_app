import { createContext, useContext, useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

const stored = () => {
  try { return JSON.parse(localStorage.getItem("fleet_user") || "null"); } catch { return null; }
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => stored());
  const [loading, setLoading] = useState(!!localStorage.getItem("fleet_token"));

  // Validate token on mount — single source of truth is /auth/me
  useEffect(() => {
    const token = localStorage.getItem("fleet_token");
    if (!token) { setLoading(false); return; }
    api.get("/auth/me")
      .then((r) => {
        setUser(r.data);
        localStorage.setItem("fleet_user", JSON.stringify(r.data));
      })
      .catch(() => {
        localStorage.removeItem("fleet_token");
        localStorage.removeItem("fleet_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username, password) => {
    const r = await api.post("/auth/login", { username, password });
    localStorage.setItem("fleet_token", r.data.token);
    localStorage.setItem("fleet_user", JSON.stringify(r.data.user));
    setUser(r.data.user);
    return r.data.user;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    localStorage.removeItem("fleet_token");
    localStorage.removeItem("fleet_user");
    setUser(null);
  }, []);

  const setSession = useCallback((token, u) => {
    localStorage.setItem("fleet_token", token);
    localStorage.setItem("fleet_user", JSON.stringify(u));
    setUser(u);
  }, []);

  const enterDemo = useCallback(async (role) => {
    const r = await api.post("/demo/enter", { role });
    localStorage.setItem("fleet_token", r.data.token);
    localStorage.setItem("fleet_user", JSON.stringify(r.data.user));
    setUser(r.data.user);
    return r.data.user;
  }, []);

  const refresh = useCallback(async () => {
    const r = await api.get("/auth/me");
    setUser(r.data);
    localStorage.setItem("fleet_user", JSON.stringify(r.data));
    return r.data;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh, setSession, enterDemo }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
