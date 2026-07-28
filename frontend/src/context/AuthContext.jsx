import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

// AUTH-01: the session lives in an HttpOnly cookie, so the frontend never holds
// a token. `fleet_user` caches the *display* profile only (name, role, modules)
// to avoid a flash of empty chrome on load — it is not a credential, confers no
// access, and /auth/me remains the single source of truth.
const stored = () => {
  try { return JSON.parse(localStorage.getItem("fleet_user") || "null"); } catch { return null; }
};

const cacheUser = (u) => {
  if (u) localStorage.setItem("fleet_user", JSON.stringify(u));
  else localStorage.removeItem("fleet_user");
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => stored());
  // We cannot see the HttpOnly cookie, so we always ask the server on mount.
  const [loading, setLoading] = useState(true);
  const revalidating = useRef(false);

  const revalidate = useCallback(async () => {
    if (revalidating.current) return null;
    revalidating.current = true;
    try {
      const r = await api.get("/auth/me");
      setUser(r.data);
      cacheUser(r.data);
      return r.data;
    } catch {
      // Session gone (expired, revoked, or revoked elsewhere). Drop the cached
      // profile so the UI cannot keep rendering an authenticated shell.
      setUser(null);
      cacheUser(null);
      return null;
    } finally {
      revalidating.current = false;
    }
  }, []);

  useEffect(() => {
    revalidate().finally(() => setLoading(false));
  }, [revalidate]);

  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      cacheUser(null);
    };
    window.addEventListener("fleetflow:unauthorized", onUnauthorized);
    return () => window.removeEventListener("fleetflow:unauthorized", onUnauthorized);
  }, []);

  // AUTH-01 revalidation. A session can be revoked server-side at any time —
  // password change, role change, deactivation, or "revoke all" from another
  // device — and the tab would otherwise keep showing a stale authenticated UI.
  //
  // `pageshow` with persisted=true is a back/forward-cache restore: the browser
  // replays a snapshot taken *before* logout, so without this a logged-out user
  // can press Back and see the app again. Re-checking on focus covers the case
  // where the session was revoked while the tab sat in the background.
  useEffect(() => {
    const onFocus = () => { if (!document.hidden) revalidate(); };
    const onPageShow = (e) => { if (e.persisted) revalidate(); };
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onPageShow);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pageshow", onPageShow);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [revalidate]);

  const login = useCallback(async (username, password) => {
    // The response carries the session as a Set-Cookie; the body's token field
    // is legacy and deliberately ignored here.
    const r = await api.post("/auth/login", { username, password });
    setUser(r.data.user);
    cacheUser(r.data.user);
    return r.data.user;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    setUser(null);
    cacheUser(null);
  }, []);

  const setSession = useCallback((_token, u) => {
    // Kept for callers that still pass a token (onboarding/demo). The cookie is
    // already set by the response; the token argument is unused.
    setUser(u);
    cacheUser(u);
  }, []);

  const enterDemo = useCallback(async (role) => {
    const r = await api.post("/demo/enter", { role });
    // Prove the browser stored and sends the newly-issued HttpOnly cookie
    // before navigating into protected routes.
    const me = await api.get("/auth/me");
    setUser(me.data);
    cacheUser(me.data);
    return me.data;
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, refresh: revalidate, setSession, enterDemo }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
