import { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = anonymous, object = authed
  const [permissions, setPermissions] = useState({});
  const [loading, setLoading] = useState(true);

  const loadPermissions = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/permissions");
      setPermissions(data || {});
    } catch {
      setPermissions({});
    }
  }, []);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      await loadPermissions();
    } catch {
      setUser(false);
      setPermissions({});
    } finally {
      setLoading(false);
    }
  }, [loadPermissions]);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = useCallback(async (email, password) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      setUser(data);
      await loadPermissions();
      return { ok: true, user: data };
    } catch (e) {
      return { ok: false, error: formatApiErrorDetail(e.response?.data?.detail) || e.message };
    }
  }, [loadPermissions]);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {
      console.warn("Logout request failed (clearing local state anyway)", e);
    }
    setUser(false);
    setPermissions({});
  }, []);

  const can = useCallback((resource, action = "read") => {
    if (user?.role === "super_admin") return true;
    return !!permissions?.[resource]?.[action];
  }, [user, permissions]);

  const value = useMemo(
    () => ({ user, permissions, loading, login, logout, refresh: fetchMe, can }),
    [user, permissions, loading, login, logout, fetchMe, can]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
