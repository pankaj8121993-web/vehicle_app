import { createContext, useContext, useState, useCallback } from "react";
import { ROLE_LABELS } from "@/lib/format";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    const role = localStorage.getItem("fleet_role");
    return role && ROLE_LABELS[role] ? { role, name: ROLE_LABELS[role] } : null;
  });

  const selectRole = useCallback((role) => {
    localStorage.setItem("fleet_role", role);
    setUser({ role, name: ROLE_LABELS[role] });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("fleet_role");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, selectRole, logout, loading: false }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
